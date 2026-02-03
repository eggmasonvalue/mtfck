# Architecture

## System Diagram
```mermaid
graph TD
    User[User] -->|Interacts| UI[Streamlit App (app.py)]
    UI -->|Requests Data| Core[Core Logic (mtfck.py)]
    Core -->|Queries| DB[(SQLite: stock_data.db)]
    Core -->|Downloads/Scrapes| NSE[NSE Archives/API]
    NSE -->|ZIP/CSV| Core
    DB -->|Dataframes| Core
    Core -->|Dataframes| UI
```

## Components
### 1. Presentation Layer (`app.py`)
- Handles user inputs (Date Range, Analysis Type).
- Renders Plotly charts and Pandas dataframes.
- Manages session state for caching.

### 2. Data Layer (`mtfck.py`)
- **ETL Process**: Downloads daily MTF reports from NSE, parses CSVs, and updates SQLite.
- **Query Engine**: Aggregates data for Top N lists and Trends.
- **Market Data**: Fetches meta-info (Industry, FFMC) via `nse` library.

### 3. Storage (`stock_data.db`)
- **daily_summary**: Market-wide stats.
- **stock_data**: Daily financing data per symbol.
- **stock_master**: Static metadata (Industry).
