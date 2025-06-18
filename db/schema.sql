CREATE TABLE IF NOT EXISTS stock_master (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    industry TEXT
);

CREATE TABLE IF NOT EXISTS stock_data (
    date DATE,
    symbol TEXT,
    qty_financed INTEGER,
    amt_financed REAL,
    FOREIGN KEY(symbol) REFERENCES stock_master(symbol)
);

CREATE TABLE IF NOT EXISTS daily_summary (
    date DATE PRIMARY KEY,
    total_outstanding_begin REAL,
    fresh_exposure REAL,
    exposure_liquidated REAL,
    net_outstanding_end REAL
);
