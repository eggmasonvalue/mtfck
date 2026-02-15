# MTFCK! (NSE MTF Analytics Dashboard)

A dashboard for analyzing NSE Margin Trading Facility (MTF) data, including top stocks by amount financed, exposure %, returns, and interactive trends.

## Features

- Download and store daily NSE Margin Trading Disclosure reports.
- Analyze top stocks by amount financed, % change in amount financed, and newly added MTF stocks.
- Filter results by industry and date range.
- View interactive trend charts for any stock, including overlays for price and index trends.
- Display Free Float Market Cap (Cr), Exposure (%), Point-to-Point Return (%), 1yr Return (%), and 3yr CAGR for each stock.
- Fast data fetch and update for missing date ranges.
- Industry information is fetched and cached for each symbol.
- Tables are interactive and sortable.
- Project structure is modular and extensible.
- **New Exposure % Analysis**: Sort stocks by exposure % (amount financed / free float market cap).

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
   - Use the sidebar to select date range, industry, and analysis type.
   - Click "Fetch/Update Data for Selected Range" to download missing data.
   - Click "Run Analysis" to view results.
   - Use the "Trends" section to enter a symbol and view amount financed trends, price overlays, and index overlays.
   - All trend charts display monetary values in ₹ Crores and allow comparison with price and index movements.
   - For "Top by Exposure %", you **must** select at least one industry filter, otherwise the analysis may take a very long time.

4. **Data**  
   - Data is stored in `stock_data.db` and `data/` directory.
   - Schema is defined in `db/schema.sql`.

## Project Structure

- `app.py` - Streamlit dashboard UI and logic.
- `mtfck.py` - Data download, parsing, and analysis functions.
- `db/schema.sql` - SQLite schema.
- `data/` - Downloaded CSV files.

## Notes

- All amounts are displayed in ₹ Crores (Cr) for consistency.
- Trend charts and tables are interactive and sortable.
- Industry information is fetched and cached for each symbol.
- Exposure % is calculated as: `amt_financed / free float market cap`.
- Price data is not adjusted for corporate actions.
- For best performance, always use industry filters when running exposure analysis.


# Challenges:
- Likely to be abandoned/completely refactored due to several challenges
  - throttling/rate limiting of data from NSE because of most functions requiring high frequency fetches - difficult to perform analysis by fetching exposure, ffmcap, return and other metrics, difficult to fetch and store stock-industry mapping data etc
  - all of it can be fixed but the juice isn't worth the squeeze. much better alternative approaches available


## License
MIT License



## Task 1: Separation of concerns
The MTF database must be segregated to https://github.com/eggmasonvalue/MTFDB(currently empty) and it should be a submodule to the current module. MTFDB will house just the database and a GitHub workflow. The workflow will clone the current repo to update and maintain that database
## Task 2: maintainance
 ### symbol renaming: 
The database maintainer/updater function should have the following logic: -  this link contains a CSV file for the list of all symbol changes historically:https://nsearchives.nseindia.com/content/equities/symbolchange.csv
Download this .csv and use this to come up with a strategy to merge data where data exists with the old name in part of the db and with the new name for the rest