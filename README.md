# NSE MTF Analytics Dashboard

A Streamlit dashboard for analyzing NSE Margin Trading Facility (MTF) data, including top stocks by amount financed, exposure %, and trends.

## Features

- Download and store daily NSE Margin Trading Disclosure reports.
- Analyze top stocks by amount financed, % change, and newly added MTF stocks.
- Filter by industry and date range.
- Interactive trend charts for each stock.
- All monetary values displayed in ₹ Crores for clarity.
- Data is stored in a local SQLite database.

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
   - Use the dropdown and "Show Trend" button above the table to view amount financed trends for any symbol.

4. **Data**  
   - Data is stored in `stock_data.db` and `data/` directory.
   - Schema is defined in `db/schema.sql`.

## Project Structure

- `app.py` - Streamlit dashboard UI and logic.
- `mtfck.py` - Data download, parsing, and analysis functions.
- `NSE.py` - NSE India API wrapper.
- `db/schema.sql` - SQLite schema.
- `data/` - Downloaded CSV files.

## Notes

- All amounts are displayed in ₹ Crores (Cr) for consistency.
- Trend charts and tables are interactive and sortable.
- Industry information is fetched and cached for each symbol.

## License

MIT License
