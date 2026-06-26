"""Unit tests for static cache key helpers."""

from app.services.static_cache import StaticCache


def test_static_cache_key_stable():
    options = {"sections": ["patient"], "watermark": "X"}
    assert StaticCache.get_cache_key(1, options) == StaticCache.get_cache_key(1, options)
