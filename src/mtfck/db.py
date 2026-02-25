import duckdb
import os

DB_PATH = "mtf_data/stock_data.parquet"
SUMMARY_PATH = "mtf_data/daily_summary.parquet"
_SHARED_CONN = None

def get_connection(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Establish and return a shared connection to an in-memory DuckDB database.
    
    This function initializes the in-memory schema with strict PRIMARY KEY constraints
    and populates the tables from local Parquet files if they exist. This ensures 
    that SQL operations like 'INSERT OR REPLACE' or 'INSERT OR IGNORE' have the 
    necessary metadata to identify row conflicts.
    """
    global _SHARED_CONN
    
    if _SHARED_CONN is not None:
        return _SHARED_CONN
        
    _SHARED_CONN = duckdb.connect(':memory:')
    
    # Define Schema for stock_data
    _SHARED_CONN.execute("""
        CREATE TABLE stock_data (
            date DATE, 
            symbol VARCHAR, 
            qty_financed INTEGER, 
            amt_financed REAL,
            PRIMARY KEY (date, symbol)
        )
    """)
    if os.path.exists(DB_PATH):
        _SHARED_CONN.execute(f"INSERT INTO stock_data SELECT * FROM read_parquet('{DB_PATH}')")

    # Define Schema for daily_summary
    _SHARED_CONN.execute("""
        CREATE TABLE daily_summary (
            date DATE PRIMARY KEY, 
            total_outstanding_begin REAL, 
            fresh_exposure REAL, 
            exposure_liquidated REAL, 
            net_outstanding_end REAL
        )
    """)
    if os.path.exists(SUMMARY_PATH):
        _SHARED_CONN.execute(f"INSERT INTO daily_summary SELECT * FROM read_parquet('{SUMMARY_PATH}')")
        
    return _SHARED_CONN

def close_connection():
    """Close the shared database connection if one exists."""
    global _SHARED_CONN
    if _SHARED_CONN:
        _SHARED_CONN.close()
        _SHARED_CONN = None
