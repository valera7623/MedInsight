"""Semantic index of DICOM clinical context for similarity search."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "dicom_clinical_context"
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9_]{2,}")

_rag_instance: "DicomRagService | None" = None
_rag_lock = threading.Lock()


def is_dicom_rag_enabled() -> bool:
    return bool(settings.DICOM_RAG_ENABLED)


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


class DicomRagService:
    """Index and search DICOM clinical context (ChromaDB with keyword fallback)."""

    def __init__(self) -> None:
        self._collection = None
        self._chroma_ok = False
        self._memory_index: dict[str, dict[str, Any]] = {}
        self._init_chroma()

    def _init_chroma(self) -> None:
        if not is_dicom_rag_enabled():
            return
        try:
            from pathlib import Path

            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from chromadb.utils import embedding_functions

            Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=settings.EMBEDDING_MODEL,
            )
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma_ok = True
            logger.info("DicomRagService: ChromaDB collection %s ready", COLLECTION_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DicomRagService: Chroma unavailable, using memory index: %s", exc)
            self._chroma_ok = False

    def _doc_id(self, study_uid: str, chunk_idx: int) -> str:
        raw = f"{study_uid}:{chunk_idx}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def index_dicom_study(
        self,
        dicom_study_uid: str,
        *,
        clinical_context: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not clinical_context:
            return

        meta = metadata or {}
        chunk_size = settings.DICOM_RAG_CHUNK_SIZE
        overlap = settings.DICOM_RAG_OVERLAP
        chunks = _chunk_text(clinical_context, chunk_size, overlap)

        summary = {
            "study_uid": dicom_study_uid,
            "modality": meta.get("modality", ""),
            "body_part": meta.get("body_part", ""),
            "findings": meta.get("findings", []),
            "text": clinical_context,
            "tokens": _tokenize(clinical_context),
        }
        self._memory_index[dicom_study_uid] = summary

        if not self._chroma_ok or self._collection is None:
            return

        ids = [self._doc_id(dicom_study_uid, i) for i in range(len(chunks))]
        metadatas = [
            {
                "study_uid": dicom_study_uid,
                "modality": str(meta.get("modality", "")),
                "body_part": str(meta.get("body_part", "")),
                "chunk": i,
            }
            for i in range(len(chunks))
        ]
        try:
            self._collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DicomRag index failed for %s: %s", dicom_study_uid, exc)

    def search_similar_studies(self, dicom_study_uid: str, limit: int = 5) -> list[dict[str, Any]]:
        base = self._memory_index.get(dicom_study_uid)
        if not base and self._chroma_ok and self._collection is not None:
            try:
                got = self._collection.get(where={"study_uid": dicom_study_uid}, include=["documents", "metadatas"])
                if got and got.get("documents"):
                    base = {
                        "study_uid": dicom_study_uid,
                        "text": " ".join(got["documents"]),
                        "tokens": _tokenize(" ".join(got["documents"])),
                        "modality": (got["metadatas"][0] or {}).get("modality", "") if got["metadatas"] else "",
                        "body_part": (got["metadatas"][0] or {}).get("body_part", "") if got["metadatas"] else "",
                    }
            except Exception:  # noqa: BLE001
                pass

        if not base:
            return []

        query_text = base.get("text", "")
        if self._chroma_ok and self._collection is not None and query_text:
            try:
                results = self._collection.query(query_texts=[query_text[:2000]], n_results=limit + 1)
                hits: list[dict[str, Any]] = []
                ids = results.get("ids", [[]])[0]
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                dists = results.get("distances", [[]])[0]
                for i, doc_id in enumerate(ids):
                    meta = metas[i] if i < len(metas) else {}
                    uid = (meta or {}).get("study_uid", "")
                    if uid == dicom_study_uid:
                        continue
                    hits.append(
                        {
                            "study_uid": uid,
                            "modality": (meta or {}).get("modality"),
                            "body_part": (meta or {}).get("body_part"),
                            "excerpt": (docs[i] if i < len(docs) else "")[:300],
                            "similarity": round(1.0 - float(dists[i]), 3) if i < len(dists) else 0.0,
                        }
                    )
                    if len(hits) >= limit:
                        break
                return hits
            except Exception as exc:  # noqa: BLE001
                logger.debug("Chroma query failed: %s", exc)

        base_tokens = base.get("tokens", set())
        scored: list[tuple[float, dict[str, Any]]] = []
        for uid, entry in self._memory_index.items():
            if uid == dicom_study_uid:
                continue
            sim = _jaccard(base_tokens, entry.get("tokens", set()))
            if base.get("modality") and entry.get("modality") == base.get("modality"):
                sim += 0.15
            if base.get("body_part") and entry.get("body_part") == base.get("body_part"):
                sim += 0.1
            scored.append(
                (
                    sim,
                    {
                        "study_uid": uid,
                        "modality": entry.get("modality"),
                        "body_part": entry.get("body_part"),
                        "excerpt": (entry.get("text") or "")[:300],
                        "similarity": round(sim, 3),
                    },
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def get_clinical_context(self, dicom_study_uid: str) -> str:
        entry = self._memory_index.get(dicom_study_uid)
        if entry:
            return entry.get("text", "")
        if self._chroma_ok and self._collection is not None:
            try:
                got = self._collection.get(where={"study_uid": dicom_study_uid}, include=["documents"])
                if got and got.get("documents"):
                    return "\n".join(got["documents"])
            except Exception:  # noqa: BLE001
                pass
        return ""


def get_dicom_rag_service() -> DicomRagService:
    global _rag_instance
    with _rag_lock:
        if _rag_instance is None:
            _rag_instance = DicomRagService()
        return _rag_instance
