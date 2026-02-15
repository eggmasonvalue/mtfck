# System Architecture

## Components

### 1. Data Ingestion Layer (`src/mtfck/ingestion.py`)
-   **Responsibility**: Validates local DB state vs NSE Archives, downloads missing daily Zip reports, parses CSVs, and updates DuckDB.
-   **Key Functions**: `update_to_today()`, `download_and_store_range()`.
-   **Optimization**: Uses DuckDB's in-process SQL engine for direct Pandas DataFrame ingestion and efficient bulk inserts.

### 2. Core Logic Layer (`src/mtfck/mtfck.py`)
-   **Responsibility**: Querying the DuckDB database for analytical views (Top Stocks, Trends, New Additions).
-   **Optimization**: Leverages DuckDB's columnar layout for fast aggregation and filtering.

### 3. Presentation Layer (`app.py`)
-   **Responsibility**: Streamlit dashboard interface.

## Data Flow
1.  **Daily Update**: GitHub Action -> `ingestion.py` -> `stock_data.duckdb` (Commit/Push)
2.  **User Access**: `app.py` -> `mtfck.py` -> `stock_data.duckdb` (Read Only)
