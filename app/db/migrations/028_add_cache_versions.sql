-- Cache version tracking for Redis invalidation (Phase 19)
CREATE TABLE IF NOT EXISTS cache_versions (
    id SERIAL PRIMARY KEY,
    cache_key VARCHAR(255) NOT NULL UNIQUE,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cache_versions_cache_key ON cache_versions (cache_key);
