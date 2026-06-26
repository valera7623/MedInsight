"""Unit tests for Redis cache helpers (no live Redis required for key building)."""

from app.core.cache import docx_cache_key, hash_options


def test_docx_cache_key_stable():
    options = {"sections": ["patient", "lab"], "watermark": "X"}
    assert docx_cache_key(10, options, 1) == docx_cache_key(10, options, 1)
    assert docx_cache_key(10, options, 1) != docx_cache_key(10, options, 2)


def test_hash_options_order_independent():
    a = hash_options({"b": 2, "a": 1})
    b = hash_options({"a": 1, "b": 2})
    assert a == b
