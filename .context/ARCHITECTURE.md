# System Architecture

## Components

### 1. Data Ingestion Layer (`ingestion.py`)
-   **Responsibility**: Validates local DB state vs NSE Archives, downloads missing daily Zip reports, parses CSVs, and updates SQLite.
-   **Key Functions**: `update_to_today()`, `download_and_store_range()`.
-   **Automation**: Triggered daily via GitHub Actions.

### 2. Core Logic Layer (`mtfck.py`)
-   **Responsibility**: Querying the SQLite database for analytical views (Top Stocks, Trends, New Additions).
-   **Dependencies**: Imports DB path and helper functions from `ingestion.py`.

### 3. Presentation Layer (`app.py`)
-   **Responsibility**: Streamlit dashboard interface.

## Data Flow
1.  **Daily Update**: GitHub Action -> `ingestion.py` -> `stock_data.db` (Commit/Push)
2.  **User Access**: `app.py` -> `mtfck.py` -> `stock_data.db` (Read Only)
