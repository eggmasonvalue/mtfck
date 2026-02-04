# MTFCK (Margin Trading Facility Analytics)

## Purpose
A Streamlit-based dashboard for analyzing NSE Margin Trading Facility (MTF) data. Track stock exposure, amount financed, and leverage trends over time.

## Key Features
- **Top Stocks Analysis**: By Amount Financed, % Change, and Exposure %.
- **Trend Visualization**: Historical trends for Amount Financed and Price.
- **Market Overview**: Daily Net Outstanding trends compared with NIFTY TOTAL MARKET.
- **New Additions**: Identify stocks newly added to the MTF list.

## Tech Stack
- **Frontend**: Streamlit
- **Backend/Logic**: Python (`mtfck.py`)
- **Data Ingestion**: Python (`ingestion.py`) - Handles fetching and parsing NSE reports.
- **Database**: SQLite (`stock_data.db`)
- **Data Source**: NSE Archives (ZIP/CSV) & Live Quotes
