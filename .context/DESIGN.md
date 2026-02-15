# Design

## Current Status
- [x] Dashboard UI (Streamlit)
- [x] SQLite Integration
- [x] Data Fetching (NSE Archives)
- [x] Trend Analysis
- [x] Exposure Calculation

## Decisions
- **Database Engine**: Migrated from SQLite to **DuckDB** for superior compression (10x-20x storage reduction) and analytical query performance.
- **Columnar Storage**: Leverages DuckDB's columnar format to efficiently store time-series financial data (Date, StockID, Amount) without wide-table complexity.
- **Normalization**: Maintained `stock_master` and `stock_data` schema but adapted for DuckDB sequences.
