#!/usr/bin/env python3
"""Smoke tests for Redis cache layer (DOCX, API JSON, invalidation)."""

from __future__ import annotations

import json
import sys
from io import BytesIO

from app.config import settings
from app.core.cache import (
    CacheService,
    cache_enabled,
    cache_service,
    docx_cache_key,
    docx_path_cache_key,
)
from app.database import SessionLocal
from app.services.cache_invalidation import CacheInvalidationService


def _header(title: str) -> None:
    print(f"\n=== {title} ===")


def test_basic_set_get() -> bool:
    _header("Basic SET/GET")
    if not cache_enabled():
        print("SKIP: REDIS_CACHE_ENABLED=false")
        return True
    key = "test:cache:ping"
    payload = b"hello-medinsight"
    ok = CacheService.set_bytes_sync(key, payload, ttl=60)
    got = CacheService.get_bytes_sync(key)
    CacheService.delete_sync(key)
    success = ok and got == payload
    print("PASS" if success else "FAIL", f"set={ok} get={got!r}")
    return success


def test_api_json_cache() -> bool:
    _header("API JSON cache")
    if not cache_enabled():
        print("SKIP")
        return True
    key = "patients:tenant:1:page:1:limit:20:test"
    data = {"items": [{"id": 1}], "total": 1, "page": 1, "limit": 20}
    CacheService.set_json_sync(key, data, ttl=60)
    cached = CacheService.get_json_sync(key)
    CacheService.delete_sync(key)
    success = cached == data
    print("PASS" if success else "FAIL", json.dumps(cached, ensure_ascii=False))
    return success


def test_docx_binary_cache() -> bool:
    _header("DOCX binary cache")
    if not cache_enabled():
        print("SKIP")
        return True
    options = {"sections": ["patient", "diagnoses"], "watermark": "TEST"}
    patient_id = 99999
    key = docx_cache_key(patient_id, options, version=1)
    path_key = docx_path_cache_key(patient_id, options, version=1)
    fake_docx = b"PK\x03\x04fake-docx-content"
    cache_service.set_bytes_sync(key, fake_docx, settings.REDIS_CACHE_DOCX_TTL)
    cache_service.set_bytes_sync(path_key, b"/tmp/fake.docx", settings.REDIS_CACHE_DOCX_TTL)
    hit = cache_service.get_bytes_sync(key)
    cache_service.delete_sync(key)
    cache_service.delete_sync(path_key)
    success = hit == fake_docx
    print("PASS" if success else "FAIL", f"size={len(hit or b'')}")
    return success


def test_invalidation() -> bool:
    _header("Cache invalidation + version bump")
    db = SessionLocal()
    try:
        svc = CacheInvalidationService(db)
        scope = "patient:99999"
        v1 = svc.get_cache_version(scope)
        v2 = svc.bump_version(scope)
        deleted = cache_service.invalidate_pattern_sync("docx:99999:*")
        success = v2 >= v1 + 1
        print("PASS" if success else "FAIL", f"version {v1}->{v2}, purged_keys={deleted}")
        return success
    finally:
        db.close()


def test_async_get_or_set() -> bool:
    _header("Async get_or_set")
    if not cache_enabled():
        print("SKIP")
        return True
    import asyncio

    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        return {"ok": True, "n": calls["n"]}

    async def run():
        key = "test:async:get_or_set"
        await CacheService.delete(key)
        first = await CacheService.get_or_set(key, producer, ttl=30)
        second = await CacheService.get_or_set(key, producer, ttl=30)
        await CacheService.delete(key)
        return first == second and calls["n"] == 1

    success = asyncio.run(run())
    print("PASS" if success else "FAIL", f"producer_calls={calls['n']}")
    return success


def main() -> int:
    print("MedInsight Redis cache tests")
    print(f"REDIS_URL={settings.REDIS_URL} cache_enabled={cache_enabled()}")
    results = [
        test_basic_set_get(),
        test_api_json_cache(),
        test_docx_binary_cache(),
        test_invalidation(),
        test_async_get_or_set(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\nResult: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
