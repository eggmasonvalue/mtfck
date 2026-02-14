# Design

## Current Status
- [x] Dashboard UI (Streamlit)
- [x] SQLite Integration
- [x] Data Fetching (NSE Archives)
- [x] Trend Analysis
- [x] Exposure Calculation

## Decisions
- **Local Database**: SQLite used for simplicity and local persistence of historical data.
- **On-demand Update**: Data is fetched only when the requested date range is missing from DB.
- **Automated Ingestion**: Daily GitHub Action updates the database at 06:00 IST.
- **Modules**: Ingestion logic separated into `src/mtfck/ingestion.py`.
- **Visualization**: Plotly used for interactive charts (Trends, Price overlays).
- **Database Normalization**: Normalized schema with `stock_master` (IDs) and `stock_data` (References) to reduce storage size by ~86%.
