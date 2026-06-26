"""Redis cache layer for DOCX binaries, API JSON responses, and DICOM frames."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import redis
import redis.asyncio as aioredis

from app.config import settings
from app.core.metrics import record_cache_hit, record_cache_miss, record_cache_set

logger = logging.getLogger(__name__)

T = TypeVar("T")

_async_client: aioredis.Redis | None = None
_sync_binary_client: redis.Redis | None = None


def cache_enabled() -> bool:
    return bool(settings.REDIS_CACHE_ENABLED)


def _get_sync_binary_client() -> redis.Redis | None:
    """Sync Redis client for binary payloads (DOCX, PNG). decode_responses=False."""
    global _sync_binary_client
    if _sync_binary_client is not None:
        return _sync_binary_client
    if not cache_enabled():
        return None
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=False,
        )
        client.ping()
        _sync_binary_client = client
        return _sync_binary_client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis binary cache unavailable (%s)", exc)
        return None


async def _get_async_client() -> aioredis.Redis | None:
    """Async Redis client (redis.asyncio — same package as sync redis)."""
    global _async_client
    if _async_client is not None:
        return _async_client
    if not cache_enabled():
        return None
    try:
        client = aioredis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=False,
        )
        await client.ping()
        _async_client = client
        return _async_client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Async Redis cache unavailable (%s)", exc)
        return None


def hash_options(options: dict[str, Any]) -> str:
    raw = json.dumps(options, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def docx_cache_key(patient_id: int, options: dict[str, Any], version: int = 0) -> str:
    return f"docx:{patient_id}:{hash_options(options)}:v{version}"


def docx_path_cache_key(patient_id: int, options: dict[str, Any], version: int = 0) -> str:
    return f"docx:path:{patient_id}:{hash_options(options)}:v{version}"


class CacheService:
    """Redis cache with async API and sync helpers for Celery / sync routes."""

    # ------------------------------------------------------------------ sync

    @staticmethod
    def get_bytes_sync(key: str) -> bytes | None:
        client = _get_sync_binary_client()
        if client is None:
            return None
        try:
            value = client.get(key)
            if value is None:
                record_cache_miss("sync")
                return None
            record_cache_hit("sync")
            return value
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache GET failed for %s: %s", key, exc)
            return None

    @staticmethod
    def set_bytes_sync(key: str, value: bytes, ttl: int | None = None) -> bool:
        client = _get_sync_binary_client()
        if client is None:
            return False
        try:
            client.setex(key, ttl or settings.REDIS_CACHE_DEFAULT_TTL, value)
            record_cache_set(len(value))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache SET failed for %s: %s", key, exc)
            return False

    @staticmethod
    def delete_sync(key: str) -> bool:
        client = _get_sync_binary_client()
        if client is None:
            return False
        try:
            return bool(client.delete(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache DELETE failed for %s: %s", key, exc)
            return False

    @staticmethod
    def exists_sync(key: str) -> bool:
        client = _get_sync_binary_client()
        if client is None:
            return False
        try:
            return bool(client.exists(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache EXISTS failed for %s: %s", key, exc)
            return False

    @staticmethod
    def get_json_sync(key: str) -> Any | None:
        raw = CacheService.get_bytes_sync(key)
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Cache JSON decode failed for %s: %s", key, exc)
            CacheService.delete_sync(key)
            return None

    @staticmethod
    def set_json_sync(key: str, value: Any, ttl: int | None = None) -> bool:
        try:
            payload = json.dumps(value, default=str).encode("utf-8")
        except (TypeError, ValueError) as exc:
            logger.warning("Cache JSON encode failed for %s: %s", key, exc)
            return False
        return CacheService.set_bytes_sync(key, payload, ttl)

    @staticmethod
    def invalidate_pattern_sync(pattern: str) -> int:
        client = _get_sync_binary_client()
        if client is None:
            return 0
        deleted = 0
        try:
            for key in client.scan_iter(match=pattern, count=200):
                deleted += int(client.delete(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache pattern delete failed for %s: %s", pattern, exc)
        return deleted

    @staticmethod
    def clear_all_sync() -> bool:
        client = _get_sync_binary_client()
        if client is None:
            return False
        try:
            client.flushdb()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache flush failed: %s", exc)
            return False

    @staticmethod
    def get_or_set_sync(key: str, func: Callable[[], T], ttl: int | None = None) -> T:
        cached = CacheService.get_bytes_sync(key)
        if cached is not None:
            try:
                return json.loads(cached.decode("utf-8"))  # type: ignore[return-value]
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        result = func()
        CacheService.set_json_sync(key, result, ttl)
        return result

    # ------------------------------------------------------------------ async

    @staticmethod
    async def get(key: str) -> bytes | None:
        client = await _get_async_client()
        if client is None:
            return None
        try:
            value = await client.get(key)
            if value is None:
                record_cache_miss("async")
                return None
            record_cache_hit("async")
            return value
        except Exception as exc:  # noqa: BLE001
            logger.warning("Async cache GET failed for %s: %s", key, exc)
            return None

    @staticmethod
    async def set(key: str, value: bytes, ttl: int = 3600) -> bool:
        client = await _get_async_client()
        if client is None:
            return False
        try:
            await client.setex(key, ttl, value)
            record_cache_set(len(value))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Async cache SET failed for %s: %s", key, exc)
            return False

    @staticmethod
    async def delete(key: str) -> bool:
        client = await _get_async_client()
        if client is None:
            return False
        try:
            return bool(await client.delete(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Async cache DELETE failed for %s: %s", key, exc)
            return False

    @staticmethod
    async def exists(key: str) -> bool:
        client = await _get_async_client()
        if client is None:
            return False
        try:
            return bool(await client.exists(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Async cache EXISTS failed for %s: %s", key, exc)
            return False

    @staticmethod
    async def get_or_set(key: str, func: Callable[..., Any], ttl: int = 3600) -> Any:
        cached = await CacheService.get(key)
        if cached is not None:
            try:
                return json.loads(cached.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                await CacheService.delete(key)

        if inspect.iscoroutinefunction(func):
            result = await func()
        else:
            result = await asyncio.to_thread(func)

        try:
            payload = json.dumps(result, default=str).encode("utf-8")
            await CacheService.set(key, payload, ttl)
        except (TypeError, ValueError) as exc:
            logger.warning("Async cache encode failed for %s: %s", key, exc)
        return result

    @staticmethod
    async def invalidate_pattern(pattern: str) -> int:
        client = await _get_async_client()
        if client is None:
            return 0
        deleted = 0
        try:
            async for key in client.scan_iter(match=pattern, count=200):
                deleted += int(await client.delete(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Async pattern delete failed for %s: %s", pattern, exc)
        return deleted

    @staticmethod
    async def clear_all() -> bool:
        client = await _get_async_client()
        if client is None:
            return False
        try:
            await client.flushdb()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Async cache flush failed: %s", exc)
            return False


cache_service = CacheService()


async def close_async_cache() -> None:
    global _async_client
    if _async_client is None:
        return
    try:
        await _async_client.aclose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error closing async Redis cache: %s", exc)
    finally:
        _async_client = None


def close_sync_binary_cache() -> None:
    global _sync_binary_client
    if _sync_binary_client is None:
        return
    try:
        _sync_binary_client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error closing sync binary Redis cache: %s", exc)
    finally:
        _sync_binary_client = None


def _build_cache_key(prefix: str, func_name: str, args: tuple, kwargs: dict) -> str:
    digest_input = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    digest = hashlib.sha256(digest_input.encode()).hexdigest()[:16]
    return f"{prefix}:{func_name}:{digest}"


def cache(ttl: int = 3600, key_prefix: str = "api") -> Callable:
    """Decorator for caching sync function results in Redis (JSON)."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if not cache_enabled():
                return func(*args, **kwargs)
            key = _build_cache_key(key_prefix, func.__name__, args, kwargs)
            cached = CacheService.get_json_sync(key)
            if cached is not None:
                return cached  # type: ignore[return-value]
            result = func(*args, **kwargs)
            CacheService.set_json_sync(key, result, ttl)
            return result

        return wrapper

    return decorator
