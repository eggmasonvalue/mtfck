# MTFCK! (NSE MTF Analytics Dashboard)

A dashboard for analyzing NSE Margin Trading Facility (MTF) data, including top stocks by amount financed, exposure %, returns, and interactive trends.

## Features

- **Automated Data Pipeline**: Daily updates via GitHub Actions in the `MTFDB` repository.
- **Parquet Data Lake**: Uses hyper-compressed Parquet files for storage, reducing 200MB+ of raw CSV data into ~2.5MB.
- **One-Click Sync**: Synchronize your local dashboard with the latest cloud data directly from the UI.
- **Top Stocks Analysis**: View leaders by Amount Financed, % Change, and Exposure %.
- **Interactive Trends**: Overlap Margin Trading trends with NSE Stock Price and Index movements.
- **Smart Industry Filtering**: Searchable industry hierarchy with hover tooltips for deep sector analysis.
- **Performance Optimized**: Uses DuckDB in-memory for lightning-fast analytical queries on top of Parquet files.

## Usage

1. **Install dependencies**  
   ```bash
   uv sync
   ```

2. **Run the dashboard**  
   ```bash
   uv run streamlit run app.py
   ```

3. **Controls**  
   - **Sync Database**: Click "Sync Database from Cloud" in the sidebar to download the latest data.
   - **Analysis**: Select date range, industry, and analysis type, then click "Run Analysis".
   - **Trends**: Enter a symbol and click "Show Amount Financed Trend" to see historical MTF data overlapped with price.
   - **NIFTY Overlay**: Click "Show Total Outstanding Trend" to see the market-wide leverage trend overlapped with the NIFTY Total Market index.

## Project Structure

- `app.py` - Streamlit dashboard UI and cloud sync logic.
- `src/mtfck/mtfck.py` - Core analytical logic and Just-In-Time (JIT) industry enrichment.
- `src/mtfck/ingestion.py` - Data pipeline for parsing NSE reports and managing Parquet exports.
- `src/mtfck/db.py` - Database connection manager (In-memory DuckDB mapped to Parquet).
- `mtf_data/` - Local cache for `.parquet` data files (ignored by Git).

## Tech Stack

- **UI**: Streamlit
- **Analytics**: DuckDB (In-process SQL engine)
- **Storage**: Apache Parquet (ZSTD Compressed)
- **Data Pipeline**: Python + GitHub Actions
- **Data Source**: NSE India (National Stock Exchange)

## License
MIT License
