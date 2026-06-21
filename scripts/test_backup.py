#!/usr/bin/env python3
"""Manual test for Phase 8: backup & restore.

Runs against a throwaway temp DB + storage so it never touches real data:
  1. create a full backup (and db / storage backups)
  2. list backups
  3. restore into a fresh location and verify data integrity (checksums/content)

Run from the project root:
    python scripts/test_backup.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    conn.executemany("INSERT INTO t (val) VALUES (?)", [("alpha",), ("beta",), ("gamma",)])
    conn.commit()
    conn.close()


def main() -> int:
    print("=== ТЕСТ BACKUP & RESTORE ===")
    workspace = Path(tempfile.mkdtemp(prefix="medinsight_backup_test_"))
    db_path = workspace / "medinsight.db"
    storage = workspace / "storage"
    (storage / "encrypted" / "tenant_1").mkdir(parents=True, exist_ok=True)
    (storage / "encrypted" / "tenant_1" / "file.txt").write_text("secret-content", encoding="utf-8")
    _seed_db(db_path)

    # Point settings at the throwaway workspace.
    settings.DATABASE_URL = f"sqlite:///{db_path}"
    settings.STORAGE_PATH = str(storage)
    settings.BACKUP_DIR = str(workspace / "backups")
    settings.BACKUP_ENCRYPTION_ENABLED = False

    # Import after settings tweak so the service picks up paths.
    from app.services.backup import BackupService

    svc = BackupService(backup_dir=settings.BACKUP_DIR)
    ok = True

    # 1) create backups
    full = svc.backup_full()
    print(f"  full backup: {full['path']} ({full['size']} bytes, {full['duration']}s)")
    db_b = svc.backup_database()
    storage_b = svc.backup_storage()
    print(f"  db backup: {db_b}")
    print(f"  storage backup: {storage_b}")
    for p in (full["path"], db_b, storage_b):
        if not Path(p).exists():
            print(f"  FAIL: file missing {p}"); ok = False

    # 2) list
    backups = svc.list_backups()
    types = sorted({b["type"] for b in backups})
    print(f"  list_backups: {len(backups)} записей, типы={types}")
    if types != ["db", "full", "storage"]:
        print("  FAIL: ожидались типы db/full/storage"); ok = False

    # 3) restore full into fresh location and verify
    db_path.unlink()
    import shutil
    shutil.rmtree(storage)
    full_id = next(b["id"] for b in backups if b["type"] == "full")
    full_path = svc._find_backup_path(full_id, "full")
    svc.restore_from_backup(str(full_path), "full")

    restored_ok = True
    if not db_path.exists():
        print("  FAIL: DB не восстановлена"); restored_ok = False
    else:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT val FROM t ORDER BY id").fetchall()
        conn.close()
        if [r[0] for r in rows] != ["alpha", "beta", "gamma"]:
            print(f"  FAIL: данные БД не совпадают: {rows}"); restored_ok = False
        else:
            print("  ✓ данные БД восстановлены (3 строки)")
    restored_file = storage / "encrypted" / "tenant_1" / "file.txt"
    if not restored_file.exists() or restored_file.read_text() != "secret-content":
        print("  FAIL: файл storage не восстановлен"); restored_ok = False
    else:
        print("  ✓ файл storage восстановлен с корректным содержимым")
    ok = ok and restored_ok

    # 4) cleanup function runs
    removed = svc.cleanup_old_backups(days_to_keep=7)
    print(f"  cleanup_old_backups → удалено {removed}")

    shutil.rmtree(workspace, ignore_errors=True)
    print("\n=== ИТОГ ===")
    print("  Результат:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
