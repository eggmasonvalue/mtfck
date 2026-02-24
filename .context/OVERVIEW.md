# MTFCK (Margin Trading Facility Analytics)

## Purpose
A Streamlit-based dashboard for analyzing NSE Margin Trading Facility (MTF) data. Track stock exposure, amount financed, and leverage trends over time.

## Key Features
- **Top Stocks Analysis**: By Amount Financed, % Change, and Exposure %.
- **Trend Visualization**: Historical trends for Amount Financed and Price.
- **Market Overview**: Daily Net Outstanding trends compared with NIFTY TOTAL MARKET.
- **New Additions**: Identify stocks newly added to the MTF list.

## Tech Stack
- **Frontend**: Streamlit (`app.py`)
- **Backend/Logic**: Python (`src/mtfck/mtfck.py`)
- **Data Ingestion**: Python (`src/mtfck/ingestion.py`) - Handles fetching and parsing NSE reports.
- **Database**: DuckDB (`mtf_data/stock_data.duckdb`) in `MTFDB` submodule.
- **Data Source**: NSE Archives (ZIP/CSV) & Live Quotes


