#!/usr/bin/env python3
"""Cron-friendly static cache cleanup."""

from __future__ import annotations

import sys

from app.config import settings
from app.services.static_cache import StaticCache


def main() -> int:
    if not settings.STATIC_CACHE_ENABLED:
        print("Static cache disabled (STATIC_CACHE_ENABLED=false)")
        return 0

    static = StaticCache()
    removed_old = static.cleanup_old(settings.STATIC_CACHE_RETENTION_DAYS)
    removed_size = static.cleanup_by_size(settings.STATIC_CACHE_MAX_SIZE_MB)
    stats = static.get_cache_stats()
    print(
        f"Cleanup done: removed_old={removed_old} removed_size={removed_size} "
        f"files={stats['file_count']} size_mb={stats['total_size_mb']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
