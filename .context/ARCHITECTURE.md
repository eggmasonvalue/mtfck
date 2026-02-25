# System Architecture

## Components

### 1. Data Ingestion Layer (`src/mtfck/ingestion.py`)
-   **Responsibility**: Validates local DB state vs NSE Archives, downloads missing daily Zip reports, parses CSVs, and updates DuckDB.
-   **Key Functions**: `update_to_today()`, `download_and_store_range()`.
-   **Optimization**: Uses DuckDB's in-process SQL engine for direct Pandas DataFrame ingestion and efficient bulk inserts.

### 2. Core Logic Layer (`src/mtfck/mtfck.py`)
-   **Responsibility**: Querying the DuckDB database for analytical views (Top Stocks, Trends, New Additions).
-   **Optimization**: Leverages DuckDB's columnar layout for fast aggregation and filtering. Utilizes Just-In-Time (JIT) data enrichment by fetching `industry_data.json` at runtime instead of relying on SQL Joins against a static master table.

### 3. Presentation Layer (`app.py`)
-   **Responsibility**: Streamlit dashboard interface.
-   **Optimization**: Uses `@st.cache_data` to locally cache the fetched JSON metadata for 24 hours, ensuring fast filtering by industry without network latency.

## Data Flow
1.  **Daily Update**: GitHub Action (in `MTFDB` submodule) -> `ingestion.py` -> `mtf_data/stock_data.duckdb` (Commit/Push to Submodule)
2.  **User Access**: `app.py` -> (fetches `industry_data.json` via HTTP GET) -> passes JSON mapping to `mtfck.py` -> reads `stock_data.duckdb` -> applies mapping & filters in Pandas -> Dashboard.
