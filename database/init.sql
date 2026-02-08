-- Database initialization script for Price Comparison MCP Server
-- SQLite schema for storing search results and user preferences

-- Table for storing price search results
CREATE TABLE IF NOT EXISTS search_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    url TEXT NOT NULL,
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    shipping_cost REAL,
    availability TEXT,
    store_name TEXT,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_normalized_name ON search_results(normalized_name);
CREATE INDEX IF NOT EXISTS idx_created_at ON search_results(created_at);
CREATE INDEX IF NOT EXISTS idx_price ON search_results(price);
CREATE INDEX IF NOT EXISTS idx_store_name ON search_results(store_name);
CREATE INDEX IF NOT EXISTS idx_currency ON search_results(currency);

-- Composite index for product queries with date filtering
CREATE INDEX IF NOT EXISTS idx_product_date ON search_results(normalized_name, created_at);

-- Table for user preferences and settings
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value JSON NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for preference lookups
CREATE INDEX IF NOT EXISTS idx_preference_key ON user_preferences(key);

-- Table for tracking price alerts
CREATE TABLE IF NOT EXISTS price_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    target_price REAL NOT NULL,
    currency TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    triggered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for active alerts
CREATE INDEX IF NOT EXISTS idx_active_alerts ON price_alerts(normalized_name, is_active);

-- Table for caching search queries
CREATE TABLE IF NOT EXISTS search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT UNIQUE NOT NULL,
    query_type TEXT NOT NULL,
    response JSON NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for cache lookups
CREATE INDEX IF NOT EXISTS idx_cache_hash ON search_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON search_cache(expires_at);

-- Table for tracking API usage and rate limits
CREATE TABLE IF NOT EXISTS api_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    request_count INTEGER DEFAULT 1,
    window_start TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for rate limit checks
CREATE INDEX IF NOT EXISTS idx_api_window ON api_usage(api_name, window_start);

-- Trigger to update timestamps
CREATE TRIGGER IF NOT EXISTS update_preferences_timestamp
AFTER UPDATE ON user_preferences
BEGIN
    UPDATE user_preferences SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Insert default preferences
INSERT OR IGNORE INTO user_preferences (key, value) VALUES
    ('default_currency', '"ILS"'),
    ('default_country', '"il"'),
    ('max_results', '20'),
    ('cache_ttl_minutes', '30');
