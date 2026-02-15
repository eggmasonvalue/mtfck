CREATE SEQUENCE IF NOT EXISTS stock_id_seq;
CREATE TABLE IF NOT EXISTS stock_master (
    stock_id INTEGER PRIMARY KEY DEFAULT nextval('stock_id_seq'),
    symbol TEXT UNIQUE,
    name TEXT,
    industry TEXT
);

CREATE TABLE IF NOT EXISTS stock_data (
    date DATE,
    stock_id INTEGER,
    qty_financed INTEGER,
    amt_financed REAL,
    PRIMARY KEY (date, stock_id),
    FOREIGN KEY(stock_id) REFERENCES stock_master(stock_id)
);

CREATE TABLE IF NOT EXISTS daily_summary (
    date DATE PRIMARY KEY,
    total_outstanding_begin REAL,
    fresh_exposure REAL,
    exposure_liquidated REAL,
    net_outstanding_end REAL
);
