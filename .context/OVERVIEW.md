# MTFCK (Margin Trading Facility Analytics)

## Purpose
A Streamlit-based dashboard for analyzing NSE Margin Trading Facility (MTF) data. Track stock exposure, amount financed, and leverage trends over time.

## Key Features
- **Top Stocks Analysis**: By Amount Financed, % Change, and Exposure %.
- **Trend Visualization**: Historical trends for Amount Financed and Price.
- **Market Overview**: Daily Net Outstanding trends compared with NIFTY TOTAL MARKET.
- **New Additions**: Identify stocks newly added to the MTF list.
- **Cloud Sync**: One-click database synchronization with GitHub hosted data.

## Tech Stack
- **Frontend**: Streamlit (`app.py`)
- **Backend/Logic**: Python (`src/mtfck/mtfck.py`)
- **Data Ingestion**: Python (`src/mtfck/ingestion.py`) - Manages daily Parquet exports.
- **Storage**: Apache Parquet (hosted in `eggmasonvalue/MTFDB` repository).
- **Analytics Engine**: DuckDB (In-memory SQL processing).
- **Data Source**: NSE Archives (ZIP/CSV) & Live Quotes.
