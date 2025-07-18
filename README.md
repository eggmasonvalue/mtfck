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

1. **Install requirements**  
   ```
   pip install -r requirements.txt
   ```

2. **Run the dashboard**  
   ```
   streamlit run app.py
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

## License

MIT License
