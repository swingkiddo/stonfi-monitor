-- One row per hour: overall DEX health
CREATE TABLE IF NOT EXISTS dex_stats (
    id          SERIAL PRIMARY KEY,
    captured_at TIMESTAMP DEFAULT NOW(),
    tvl_usd     NUMERIC,
    volume_24h  NUMERIC,
    trades_24h  INTEGER,
    users_24h   INTEGER
);

-- 20 rows per hour: snapshot of top pools
CREATE TABLE IF NOT EXISTS pool_snapshots (
    id           SERIAL PRIMARY KEY,
    captured_at  TIMESTAMP DEFAULT NOW(),
    pool_address TEXT,
    token_a      TEXT,
    token_b      TEXT,
    tvl_usd      NUMERIC,
    volume_24h   NUMERIC,
    apy          NUMERIC,
    rank         INTEGER  -- position in the top list at snapshot time
);
