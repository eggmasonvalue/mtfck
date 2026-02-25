# System Architecture

## Components

### 1. Data Ingestion Layer (`src/mtfck/ingestion.py`)
-   **Responsibility**: Executes daily in GitHub Actions. Validates cloud state, downloads missing daily Zip reports from NSE, and merges them into the persistent Parquet data lake.
-   **Process**: Loads existing `stock_data.parquet` into an in-memory DuckDB table, appends new records, and exports the entire table back to Parquet using ZSTD compression.
-   **Key Functions**: `update_to_today()`, `download_and_store_range()`.

### 2. Core Logic Layer (`src/mtfck/mtfck.py`)
-   **Responsibility**: Querying the Parquet data via in-memory DuckDB for analytical views.
-   **Optimization**: Utilizes Just-In-Time (JIT) data enrichment by fetching `industry_data.json` at runtime. Maps industry hierarchy to symbols in-memory to keep storage denormalized and lean.

### 3. Presentation Layer (`app.py`)
-   **Responsibility**: Streamlit dashboard interface and Cloud Sync management.
-   **Sync Logic**: Downloads `stock_data.parquet` and `daily_summary.parquet` directly from the `MTFDB` repository via HTTP streaming.
-   **UI Enhancement**: Implements a searchable multiselect for industries that hides full hierarchy paths using non-breaking space padding, allowing for clean display with native hover tooltips.

## Data Flow
1.  **Daily Update**: GitHub Action (in `MTFDB` repo) -> `ingestion.py` -> In-memory DuckDB -> `stock_data.parquet` (Overwrite & Push).
2.  **User Access**: `app.py` -> (Optional Sync Button) -> Downloads latest `.parquet` files from GitHub -> Maps files to in-memory DuckDB tables -> Performs SQL Analysis -> Dashboard.
