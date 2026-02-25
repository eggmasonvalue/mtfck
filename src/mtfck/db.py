import duckdb

DB_PATH = "./mtf_data/stock_data.duckdb"

def get_connection(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Establish and return a connection to the DuckDB database.
    
    Concurrent write access to DuckDB files can cause file lock contention. By defaulting 
    to read-only mode, the Streamlit UI can safely perform multiple simultaneous queries 
    without blocking. The separate ingestion process should explicitly request write 
    access when updating the database.
    
    Args:
        read_only (bool): Whether to open the database in read-only mode. Defaults to True.
        
    Returns:
        duckdb.DuckDBPyConnection: An active connection to the DuckDB database.
    """
    return duckdb.connect(DB_PATH, read_only=read_only)

def close_connection():
    """
    Close the shared database connection if one exists.
    
    Deprecated: Connections are now managed per-request to avoid file lock contention,
    so this function is a no-op kept temporarily for backward compatibility.
    """
    pass
