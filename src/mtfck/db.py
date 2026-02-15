
import duckdb

DB_PATH = "./db/stock_data.duckdb"
_SHARED_CONN = None

def get_connection(read_only=False):
    """
    Returns a shared DuckDB connection.
    For a local Streamlit app, we maintain a single Read-Write connection 
    to allow both querying and ingestion within the same process.
    """
    global _SHARED_CONN
    if _SHARED_CONN is None:
        try:
            # Always try to open in Read-Write mode first so ingestion can work
            _SHARED_CONN = duckdb.connect(DB_PATH, read_only=False)
        except Exception as e:
            print(f"Warning: Could not open DB in Read-Write mode. Trying Read-Only. Error: {e}")
            try:
                _SHARED_CONN = duckdb.connect(DB_PATH, read_only=True)
            except Exception as e2:
                print(f"Critical: Could not open DB. Error: {e2}")
                raise e2
    return _SHARED_CONN

def close_connection():
    global _SHARED_CONN
    if _SHARED_CONN:
        _SHARED_CONN.close()
        _SHARED_CONN = None
