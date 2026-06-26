-- Cache access statistics (Phase 20)
CREATE TABLE IF NOT EXISTS cache_stats (
    id SERIAL PRIMARY KEY,
    cache_type VARCHAR(32) NOT NULL,
    key VARCHAR(512) NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cache_stats_type ON cache_stats (cache_type);
CREATE INDEX IF NOT EXISTS idx_cache_stats_key ON cache_stats (key);
