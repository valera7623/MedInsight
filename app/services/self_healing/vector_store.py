"""Knowledge base for error fixes.

Durable storage lives in the SQL ``error_fixes`` table. When ChromaDB and an
embedding backend are available, records are also indexed there for semantic
similarity search; otherwise a keyword-overlap fallback is used so the system
keeps working without the heavy ML stack.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import ErrorFix

logger = logging.getLogger(__name__)

COLLECTION_NAME = "error_fixes"
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9_]{2,}")

_kb_instance: "ErrorKnowledgeBase | None" = None
_kb_lock = threading.Lock()


def is_self_healing_enabled() -> bool:
    return bool(settings.SELF_HEALING_ENABLED)


def _now() -> datetime:
    return datetime.utcnow()


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _record_to_dict(row: ErrorFix, similarity: float = 0.0) -> dict[str, Any]:
    return {
        "id": row.id,
        "error_text": row.error_text,
        "error_type": row.error_type,
        "agent_name": row.agent_name,
        "stack_trace": row.stack_trace or "",
        "solution_prompt": row.solution_prompt or "",
        "solution_code": row.solution_code or {},
        "was_successful": bool(row.was_successful),
        "success_count": int(row.success_count or 0),
        "fail_count": int(row.fail_count or 0),
        "tenant_id": row.tenant_id,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else "",
        "similarity": similarity,
    }


class ErrorKnowledgeBase:
    """Vector/keyword store for error → fix mappings."""

    def __init__(self) -> None:
        self._collection = None
        self._chroma_ok = False
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from chromadb.utils import embedding_functions

            from pathlib import Path

            Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            embed_fn = embedding_functions.DefaultEmbeddingFunction()
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
                embedding_function=embed_fn,
            )
            self._chroma_ok = True
            logger.info("Self-healing: ChromaDB index ready (%d docs)", self._collection.count())
        except Exception as exc:
            self._collection = None
            self._chroma_ok = False
            logger.info("Self-healing: ChromaDB unavailable (%s) — using keyword fallback", exc)

    # -- writes -------------------------------------------------------------

    def add_error(self, error_record: dict[str, Any]) -> int:
        """Insert (or update by id) an ErrorFix row; index in ChromaDB. Returns id."""
        error_text = (error_record.get("error_text") or "").strip()
        if not error_text:
            raise ValueError("error_text is required")

        solution_code = error_record.get("solution_code")
        if isinstance(solution_code, str) and solution_code.strip():
            try:
                solution_code = json.loads(solution_code)
            except json.JSONDecodeError:
                solution_code = {"raw": solution_code}

        db = SessionLocal()
        try:
            existing_id = error_record.get("id")
            row = db.get(ErrorFix, existing_id) if existing_id else None
            if row is None:
                row = ErrorFix(error_text=error_text)
                db.add(row)

            row.error_text = error_text
            row.error_type = error_record.get("error_type", "unknown")
            row.agent_name = error_record.get("agent_name", "unknown")
            row.stack_trace = (error_record.get("stack_trace") or "")[:2000] or None
            row.solution_prompt = error_record.get("solution_prompt") or None
            row.solution_code = solution_code or None
            row.was_successful = bool(error_record.get("was_successful", False))
            row.success_count = int(error_record.get("success_count", 0))
            row.fail_count = int(error_record.get("fail_count", 0))
            row.tenant_id = error_record.get("tenant_id")
            row.last_used_at = _now()
            db.commit()
            db.refresh(row)
            fix_id = row.id
            self._index_chroma(fix_id, error_text, row.agent_name, row.error_type)
            logger.info("Self-healing: stored fix %s (agent=%s)", fix_id, row.agent_name)
            return fix_id
        finally:
            db.close()

    def _index_chroma(self, fix_id: int, text: str, agent_name: str, error_type: str) -> None:
        if not self._chroma_ok or self._collection is None:
            return
        try:
            self._collection.upsert(
                ids=[str(fix_id)],
                documents=[text],
                metadatas=[{"agent_name": agent_name, "error_type": error_type}],
            )
        except Exception as exc:
            logger.warning("ChromaDB upsert failed for %s: %s", fix_id, exc)

    # -- reads --------------------------------------------------------------

    def search_similar_errors(
        self,
        error_text: str,
        agent_name: str,
        limit: int = 3,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        min_score = threshold if threshold is not None else settings.SIMILARITY_THRESHOLD
        if self._chroma_ok and self._collection is not None:
            matches = self._search_chroma(error_text, agent_name, limit, min_score)
            if matches is not None:
                return matches
        return self._search_keyword(error_text, agent_name, limit, min_score)

    def _search_chroma(
        self, error_text: str, agent_name: str, limit: int, min_score: float
    ) -> list[dict[str, Any]] | None:
        try:
            if self._collection.count() == 0:
                return []
            where = {"agent_name": agent_name} if agent_name else None
            res = self._collection.query(
                query_texts=[error_text],
                n_results=min(max(limit * 3, 5), 20),
                where=where,
                include=["distances"],
            )
            ids = res.get("ids", [[]])[0]
            distances = res.get("distances", [[]])[0]
            scored: list[tuple[int, float]] = []
            for doc_id, distance in zip(ids, distances):
                similarity = 1.0 - float(distance)
                if similarity >= min_score:
                    try:
                        scored.append((int(doc_id), similarity))
                    except ValueError:
                        continue
            return self._load_and_rank([fid for fid, _ in scored], dict(scored), limit)
        except Exception as exc:
            logger.warning("ChromaDB query failed (%s) — keyword fallback", exc)
            return None

    def _search_keyword(
        self, error_text: str, agent_name: str, limit: int, min_score: float
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize(error_text)
        if not query_tokens:
            return []
        db = SessionLocal()
        try:
            stmt = select(ErrorFix)
            if agent_name:
                stmt = stmt.where(ErrorFix.agent_name == agent_name)
            rows = db.execute(stmt).scalars().all()
            scored: list[tuple[ErrorFix, float]] = []
            for row in rows:
                tokens = _tokenize(row.error_text)
                if not tokens:
                    continue
                overlap = len(query_tokens & tokens) / len(query_tokens | tokens)
                if overlap >= min(min_score, 0.2):  # keyword overlap uses a softer floor
                    scored.append((row, overlap))
            scored.sort(
                key=lambda x: (
                    x[0].was_successful,
                    (x[0].success_count or 0) - (x[0].fail_count or 0),
                    x[1],
                ),
                reverse=True,
            )
            return [_record_to_dict(row, sim) for row, sim in scored[:limit]]
        finally:
            db.close()

    def _load_and_rank(
        self, ids: list[int], sim_map: dict[int, float], limit: int
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        db = SessionLocal()
        try:
            rows = db.execute(select(ErrorFix).where(ErrorFix.id.in_(ids))).scalars().all()
            results = [_record_to_dict(row, sim_map.get(row.id, 0.0)) for row in rows]
            results.sort(
                key=lambda r: (
                    r["was_successful"],
                    r["success_count"] - r["fail_count"],
                    r["similarity"],
                ),
                reverse=True,
            )
            return results[:limit]
        finally:
            db.close()

    def get_record(self, fix_id: int) -> dict[str, Any] | None:
        db = SessionLocal()
        try:
            row = db.get(ErrorFix, fix_id)
            return _record_to_dict(row) if row else None
        finally:
            db.close()

    def list_all(self) -> list[dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = db.execute(select(ErrorFix)).scalars().all()
            return [_record_to_dict(row) for row in rows]
        finally:
            db.close()

    # -- counters -----------------------------------------------------------

    def mark_fix_success(self, fix_id: int) -> None:
        db = SessionLocal()
        try:
            row = db.get(ErrorFix, fix_id)
            if row:
                row.success_count = (row.success_count or 0) + 1
                row.was_successful = True
                row.last_used_at = _now()
                db.commit()
        finally:
            db.close()

    def mark_fix_failure(self, fix_id: int) -> None:
        db = SessionLocal()
        try:
            row = db.get(ErrorFix, fix_id)
            if row:
                row.fail_count = (row.fail_count or 0) + 1
                row.last_used_at = _now()
                db.commit()
        finally:
            db.close()

    def confirm_fix(self, fix_id: int) -> bool:
        db = SessionLocal()
        try:
            row = db.get(ErrorFix, fix_id)
            if not row:
                return False
            row.was_successful = True
            row.last_used_at = _now()
            db.commit()
            return True
        finally:
            db.close()

    def delete_fix(self, fix_id: int) -> bool:
        db = SessionLocal()
        try:
            row = db.get(ErrorFix, fix_id)
            if not row:
                return False
            db.delete(row)
            db.commit()
        finally:
            db.close()
        if self._chroma_ok and self._collection is not None:
            try:
                self._collection.delete(ids=[str(fix_id)])
            except Exception as exc:
                logger.warning("ChromaDB delete failed for %s: %s", fix_id, exc)
        return True

    def find_stale_failures(self, min_age_days: int = 7) -> list[dict[str, Any]]:
        cutoff = _now() - timedelta(days=min_age_days)
        db = SessionLocal()
        try:
            rows = (
                db.execute(
                    select(ErrorFix).where(
                        ErrorFix.fail_count > ErrorFix.success_count,
                        ErrorFix.last_used_at < cutoff,
                    )
                )
                .scalars()
                .all()
            )
            return [_record_to_dict(row) for row in rows]
        finally:
            db.close()

    def get_stats(self) -> dict[str, Any]:
        records = self.list_all()
        total = len(records)
        successful = sum(1 for r in records if r["was_successful"])
        total_applications = sum(r["success_count"] + r["fail_count"] for r in records)

        agent_counts: dict[str, int] = {}
        error_counts: dict[str, int] = {}
        for r in records:
            agent_counts[r["agent_name"]] = agent_counts.get(r["agent_name"], 0) + 1
            key = (r["error_text"] or "")[:80]
            error_counts[key] = error_counts.get(key, 0) + 1

        top_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "total_fixes": total,
            "successful_fixes": successful,
            "success_rate": round(successful / total, 4) if total else 0.0,
            "total_applications": total_applications,
            "chroma_enabled": self._chroma_ok,
            "by_agent": agent_counts,
            "top_errors": [{"error": e, "count": c} for e, c in top_errors],
        }


def get_knowledge_base() -> ErrorKnowledgeBase | None:
    """Return singleton knowledge base, or None when self-healing is disabled."""
    global _kb_instance
    if not is_self_healing_enabled():
        return None
    with _kb_lock:
        if _kb_instance is None:
            try:
                _kb_instance = ErrorKnowledgeBase()
            except Exception as exc:
                logger.error("Failed to init ErrorKnowledgeBase: %s", exc)
                return None
        return _kb_instance


def reset_knowledge_base() -> None:
    """Reset singleton (used by tests)."""
    global _kb_instance
    with _kb_lock:
        _kb_instance = None


def seed_knowledge_base(*, overwrite: bool = False) -> tuple[int, int]:
    """Load seed_fixes.json into the knowledge base. Returns (imported, skipped)."""
    import json
    from pathlib import Path

    kb = get_knowledge_base()
    if kb is None:
        return 0, 0

    seed_file = Path(__file__).resolve().parent / "seed_fixes.json"
    if not seed_file.is_file():
        return 0, 0

    with open(seed_file, encoding="utf-8") as fh:
        seeds = json.load(fh)

    db = SessionLocal()
    try:
        existing_texts = {
            (row.error_text or "")[:120]
            for row in db.execute(select(ErrorFix)).scalars().all()
        }
    finally:
        db.close()

    imported = 0
    skipped = 0
    for entry in seeds:
        if not overwrite and (entry.get("error_text") or "")[:120] in existing_texts:
            skipped += 1
            continue
        entry.pop("id", None)
        try:
            kb.add_error(entry)
            imported += 1
        except Exception as exc:
            logger.warning("Seed import failed: %s", exc)
            skipped += 1
    return imported, skipped
