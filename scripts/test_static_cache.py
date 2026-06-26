#!/usr/bin/env python3
"""Tests for static disk cache."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from app.services.static_cache import StaticCache


def run_tests() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="medinsight_static_cache_"))
    passed = 0
    try:
        cache = StaticCache(cache_dir=str(tmp))
        options = {"sections": ["patient", "lab"], "watermark": "TEST"}
        key = cache.get_cache_key(42, options)
        data = b"PK\x03\x04fake-docx"

        path = cache.save(key, data)
        assert path.is_file(), "save failed"
        assert cache.has_cached(key), "has_cached failed"
        assert cache.load(key) == data, "load failed"
        info = cache.get_file_info(key)
        assert info["size_bytes"] == len(data), "file info size"
        passed += 1
        print("PASS save/load/info")

        assert cache.invalidate(42) >= 1, "invalidate patient"
        assert not cache.has_cached(key), "still cached after invalidate"
        passed += 1
        print("PASS invalidate")

        cache.save(key, data)
        cache.save(cache.get_cache_key(43, options), data + b"2")
        removed = cache.cleanup_old(days=0)
        assert removed >= 1, "cleanup_old"
        passed += 1
        print("PASS cleanup_old")

        for i in range(3):
            cache.save(cache.get_cache_key(100 + i, options), data * (i + 1))
        removed_size = cache.cleanup_by_size(max_size_mb=0)
        assert removed_size >= 1, "cleanup_by_size"
        stats = cache.get_cache_stats()
        assert "file_count" in stats, "stats"
        passed += 1
        print("PASS cleanup_by_size/stats")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = 4
    print(f"\nResult: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_tests())
