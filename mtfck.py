from datetime import date, datetime, timedelta
from nse import NSE
from pathlib import Path
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

DB_PATH = './stock_data.db'
DATA_DIR = Path('./data')
DATA_DIR.mkdir(exist_ok=True)
SCHEMA_PATH = './db/schema.sql'

nse = NSE(download_folder=Path("."))

def create_table():
    """Create tables if they do not exist."""
    with sqlite3.connect(DB_PATH) as conn:
        with open(SCHEMA_PATH, 'r') as f:
            conn.executescript(f.read())
        # Ensure daily_summary table exists (redundant if in schema.sql, but safe)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            date TEXT PRIMARY KEY,
            total_outstanding_begin REAL,
            fresh_exposure REAL,
            exposure_liquidated REAL,
            net_outstanding_end REAL
        )
        """)

def parse_and_insert(csv_path: str, date_str: str):
    """
    Parse the CSV file, extract summary and stock data, and insert into the database.
    Only rows with all required fields are stored.
    """
    # Find the header row and summary fields
    with open(csv_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    header_idx = None
    summary = {}
    for idx, line in enumerate(lines):
        if line.startswith('Symbol,Name,'):
            header_idx = idx
            break
        # Parse summary fields
        if line.startswith('1,Scripwise Total Outstanding'):
            summary['total_outstanding_begin'] = float(line.split(',')[2].replace(',', '').strip())
        elif line.startswith('2,Fresh Exposure taken'):
            summary['fresh_exposure'] = float(line.split(',')[2].replace(',', '').strip())
        elif line.startswith('3,Exposure liquidated'):
            summary['exposure_liquidated'] = float(line.split(',')[2].replace(',', '').strip())
        elif line.startswith('4,Net scripwise outstanding'):
            summary['net_outstanding_end'] = float(line.split(',')[2].replace(',', '').strip())
    if header_idx is None:
        raise ValueError(f"Header not found in {csv_path}")

    # Insert summary if found
    if summary:
        summary['date'] = date_str
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_summary
                (date, total_outstanding_begin, fresh_exposure, exposure_liquidated, net_outstanding_end)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    summary['date'],
                    summary.get('total_outstanding_begin'),
                    summary.get('fresh_exposure'),
                    summary.get('exposure_liquidated'),
                    summary.get('net_outstanding_end')
                )
            )

    # Read stock data
    df = pd.read_csv(csv_path, skiprows=header_idx)
    df = df.rename(columns={
        'Symbol': 'symbol',
        'Name': 'name',
        'Qty Fin by all the members(No.of Shares)': 'qty_financed',
        'Amt Fin by all the members(Rs. In Lakhs)': 'amt_financed'
    })
    df['date'] = date_str

    # Keep only rows where all required fields are present and not null/empty
    required_cols = ['symbol', 'name', 'qty_financed', 'amt_financed']
    df = df.dropna(subset=required_cols)
    # Remove rows where any required field is empty string after stripping
    df = df[
        df[required_cols].map(lambda x: str(x).strip() != '').all(axis=1)
    ]

    # Insert unique symbols/names into stock_master
    with sqlite3.connect(DB_PATH) as conn:
        unique_symbols = df[['symbol', 'name']].drop_duplicates()
        for _, row in unique_symbols.iterrows():
            symbol = row['symbol']
            name = row['name']
            # Check if symbol already exists in stock_master
            cur = conn.execute(
                "SELECT 1 FROM stock_master WHERE symbol = ? LIMIT 1", (symbol,)
            )
            exists = cur.fetchone() is not None
            if not exists:
                # Fetch industry info from NSE only if not present
                # print(f"Fetching industry info for {symbol}")
                try:
                    meta = nse.equityMetaInfo(symbol)
                    industry = meta.get('industry', None)
                except Exception:
                    #break
                    industry = None
                conn.execute(
                    "INSERT OR IGNORE INTO stock_master (symbol, name, industry) VALUES (?, ?, ?)",
                    (symbol, name, industry)
                )
                print(f"Inserted {symbol} into stock_master with industry {industry}")
            # else: do nothing if already exists
        # Insert daily data, referencing only symbol
        df_daily = df[['date', 'symbol', 'qty_financed', 'amt_financed']]
        df_daily.to_sql('stock_data', conn, if_exists='append', index=False)
    # Delete the CSV file after processing
    try:
        Path(csv_path).unlink()
    except Exception as e:
        print(f"Warning: Could not delete file {csv_path}: {e}")

def download_and_store_range(from_date: date, to_date: date):
    """
    Download NSE Margin Trading Disclosure report for each date in [from_date, to_date] and store in DB.
    Only downloads for dates not already present in the DB.
    """
    create_table()
    # Get all dates already present in DB
    with sqlite3.connect(DB_PATH) as conn:
        existing_dates = set(
            row[0] for row in conn.execute("SELECT DISTINCT date FROM stock_data WHERE date BETWEEN ? AND ?", (from_date.strftime('%Y-%m-%d'), to_date.strftime('%Y-%m-%d')))
        )
    # Prepare all dates in the range
    all_dates = [from_date + timedelta(days=i) for i in range((to_date - from_date).days + 1)]
    missing_dates = [d for d in all_dates if d.strftime('%Y-%m-%d') not in existing_dates]
    skipped_dates = [d for d in all_dates if d.strftime('%Y-%m-%d') in existing_dates]

    print(f"Skipping {len(skipped_dates)} dates already in DB: {[d.strftime('%Y-%m-%d') for d in skipped_dates]}")
    print(f"Downloading {len(missing_dates)} dates: {[d.strftime('%Y-%m-%d') for d in missing_dates]}")

    for d in missing_dates:
        date_str = d.strftime('%Y-%m-%d')
        try:
            print(f"Processing {d}")
            url = f"https://nsearchives.nseindia.com/content/equities/mrg_trading_{d.strftime('%d%m%y')}.zip"
            print(f"Downloading from: {url}")
            result = nse.download_document(url=url, folder=DATA_DIR)
            if not result.is_file():
                result.unlink(missing_ok=True)
                raise FileNotFoundError(f"Failed to download file: {result.name}")

            # result is already the extracted CSV file
            parse_and_insert(str(result), date_str)
            print(f"Loaded {result} into DB for date {d}")
        except Exception as e:
            print(f"Failed for {d}: {e}")

def plot_net_outstanding_end():
    """Fetch daily_summary and plot net_outstanding_end for each day."""
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            "SELECT date, net_outstanding_end FROM daily_summary ORDER BY date", conn
        )
    if df.empty:
        print("No summary data found.")
        return
    df['date'] = pd.to_datetime(df['date'])
    plt.figure(figsize=(10, 5))
    plt.plot(df['date'], df['net_outstanding_end'], marker='o')
    plt.title('Net Outstanding End (Daily)')
    plt.xlabel('Date')
    plt.ylabel('Net Outstanding End')
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def get_top5_amt_financed(to_date: str, top_n: int = 5, industries: list = None, from_date: str = None):
    """
    Return top N stocks by amt_financed on to_date,
    with ffmc (free float market cap, in lakhs), exposure % (amt_financed/ffmc),
    and point-to-point return (%) between from_date and to_date.
    Optionally filter by industries.
    """
    with sqlite3.connect(DB_PATH) as conn:
        if industries:
            placeholders = ",".join("?" for _ in industries)
            query = f"""
                SELECT s.symbol, m.name, m.industry, s.amt_financed
                FROM stock_data s
                JOIN stock_master m ON s.symbol = m.symbol
                WHERE s.date = ? AND m.industry IN ({placeholders})
                ORDER BY s.amt_financed DESC
                LIMIT ?
            """
            params = (to_date, *industries, top_n)
        else:
            query = """
                SELECT s.symbol, m.name, m.industry, s.amt_financed
                FROM stock_data s
                JOIN stock_master m ON s.symbol = m.symbol
                WHERE s.date = ?
                ORDER BY s.amt_financed DESC
                LIMIT ?
            """
            params = (to_date, top_n)
        df = pd.read_sql_query(query, conn, params=params)

    # Add ffmc, exposure %, and point-to-point return columns
    ffmc_list = []
    exposure_pct_list = []
    ptp_return_list = []
    one_year_return_list = []
    three_year_cagr_list = []
    for _, row in df.iterrows():
        try:
            q = nse.quote(row['symbol'], section='trade_info')
            ffmc = q.get('marketDeptOrderBook', {}).get('tradeInfo', {}).get('ffmc', None)
            if ffmc is not None:
                ffmc_lakhs = ffmc * 100
                exposure_pct = (row['amt_financed'] / ffmc_lakhs) * 100 if ffmc_lakhs else None
            else:
                ffmc_lakhs = None
                exposure_pct = None
        except Exception:
            ffmc_lakhs = None
            exposure_pct = None
        ffmc_list.append(ffmc_lakhs)
        exposure_pct_list.append(exposure_pct)

        # Point-to-point return calculation
        ptp_return = None
        if from_date:
            try:
                hist_from = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(from_date).date(), to_date=pd.to_datetime(from_date).date())
                hist_to = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(to_date).date(), to_date=pd.to_datetime(to_date).date())
                close_from = hist_from[0]['CH_CLOSING_PRICE'] if hist_from else None
                close_to = hist_to[0]['CH_CLOSING_PRICE'] if hist_to else None
                try:
                    close_from = float(close_from) if close_from is not None else None
                    close_to = float(close_to) if close_to is not None else None
                except Exception:
                    close_from = None
                    close_to = None
                if close_from is not None and close_to is not None:
                    ptp_return = ((close_to - close_from) / close_from) * 100
                else:
                    print(f"[WARN] {row['symbol']} either changed symbol, listed or delisted within the chosen date range")
            except Exception as e:
                print(f"[ERROR] {row['symbol']} error in p2p return: {e}")
                ptp_return = None
        ptp_return_list.append(ptp_return)

        # Calculate 1yr Return (%)
        one_year_return = None
        try:
            one_year_date = (pd.to_datetime(to_date) - timedelta(days=365)).date()
            hist_1yr = nse.fetch_equity_historical_data(row['symbol'], from_date=one_year_date, to_date=one_year_date)
            hist_to = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(to_date).date(), to_date=pd.to_datetime(to_date).date())
            close_1yr = hist_1yr[0]['CH_CLOSING_PRICE'] if hist_1yr else None
            close_to = hist_to[0]['CH_CLOSING_PRICE'] if hist_to else None
            if close_1yr is not None and close_to is not None:
                one_year_return = ((close_to - close_1yr) / close_1yr) * 100
        except Exception as e:
            print(f"[ERROR] {row['symbol']} error in 1yr return: {e}")
            one_year_return = None
        one_year_return_list.append(one_year_return)

        # Calculate 3yr Return (%) (CAGR)
        three_year_cagr = None
        try:
            three_year_date = (pd.to_datetime(to_date) - timedelta(days=3 * 365)).date()
            hist_3yr = nse.fetch_equity_historical_data(row['symbol'], from_date=three_year_date, to_date=three_year_date)
            close_3yr = hist_3yr[0]['CH_CLOSING_PRICE'] if hist_3yr else None
            if close_3yr is not None and close_to is not None:
                three_year_cagr = (((close_to / close_3yr) ** (1 / 3)) - 1) * 100
        except Exception as e:
            print(f"[ERROR] {row['symbol']} error in 3yr CAGR: {e}")
            three_year_cagr = None
        three_year_cagr_list.append(three_year_cagr)

    # Ensure the columns are added to the DataFrame
    df['Free Float Market Cap (₹ Lakhs)'] = ffmc_list if len(df) == len(ffmc_list) else [None] * len(df)
    df['Exposure (%)'] = exposure_pct_list if len(df) == len(exposure_pct_list) else [None] * len(df)
    df['Point-to-Point Return (%)'] = ptp_return_list if len(df) == len(ptp_return_list) else [None] * len(df)
    df['1yr Return (%)'] = one_year_return_list if len(df) == len(one_year_return_list) else [None] * len(df)
    df['3yr Return (%) (CAGR)'] = three_year_cagr_list if len(df) == len(three_year_cagr_list) else [None] * len(df)

    return df.rename(columns={
        'symbol': 'Symbol',
        'name': 'Name',
        'industry': 'Industry',
        'amt_financed': 'Amount Financed (₹ Lakhs)'
    })[['Symbol', 'Name', 'Industry', 'Amount Financed (₹ Lakhs)', 'Free Float Market Cap (₹ Lakhs)', 'Exposure (%)', '1yr Return (%)', '3yr Return (%) (CAGR)', 'Point-to-Point Return (%)']]

def get_top5_amt_financed_pct_change(from_date: str, to_date: str, top_n: int = 5, industries: list = None):
    """
    Return top N stocks by percentage change in amt_financed between from_date and to_date.
    Only stocks present on both dates are considered.
    Optionally filter by industries.
    Adds point-to-point return (%) for the date range.
    """
    with sqlite3.connect(DB_PATH) as conn:
        if industries:
            placeholders = ",".join("?" for _ in industries)
            df_from = pd.read_sql_query(
                f"""SELECT s.symbol, s.amt_financed
                    FROM stock_data s
                    JOIN stock_master m ON s.symbol = m.symbol
                    WHERE s.date = ? AND s.amt_financed != 0 AND m.industry IN ({placeholders})""",
                conn, params=(from_date, *industries)
            )
            df_to = pd.read_sql_query(
                f"""SELECT s.symbol, s.amt_financed
                    FROM stock_data s
                    JOIN stock_master m ON s.symbol = m.symbol
                    WHERE s.date = ? AND s.amt_financed >= 50 AND m.industry IN ({placeholders})""",
                conn, params=(to_date, *industries)
            )
        else:
            df_from = pd.read_sql_query(
                "SELECT symbol, amt_financed FROM stock_data WHERE date = ? AND amt_financed != 0", conn, params=(from_date,)
            )
            df_to = pd.read_sql_query(
                "SELECT symbol, amt_financed FROM stock_data WHERE date = ? AND amt_financed >= 50", conn, params=(to_date,)
            )
        df = pd.merge(df_from, df_to, on="symbol", suffixes=('_from', '_to'))
        df['pct_change'] = ((df['amt_financed_to'] - df['amt_financed_from']) / df['amt_financed_from']) * 100
        df_master = pd.read_sql_query("SELECT symbol, name, industry FROM stock_master", conn)
        df = pd.merge(df, df_master, on="symbol")
        df = df.sort_values('pct_change', ascending=False).head(top_n)

    ffmc_list = []
    exposure_pct_list = []
    ptp_return_list = []
    one_year_return_list = []
    three_year_cagr_list = []
    for _, row in df.iterrows():
        try:
            q = nse.quote(row['symbol'], section='trade_info')
            ffmc = q.get('marketDeptOrderBook', {}).get('tradeInfo', {}).get('ffmc', None)
            if ffmc is not None:
                ffmc_lakhs = ffmc * 100
                exposure_pct = (row['amt_financed'] / ffmc_lakhs) * 100 if ffmc_lakhs else None
            else:
                ffmc_lakhs = None
                exposure_pct = None
        except Exception:
            ffmc_lakhs = None
            exposure_pct = None
        ffmc_list.append(ffmc_lakhs)
        exposure_pct_list.append(exposure_pct)

        # Point-to-point return calculation
        ptp_return = None
        try:
            hist_from = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(from_date).date(), to_date=pd.to_datetime(from_date).date())
            hist_to = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(to_date).date(), to_date=pd.to_datetime(to_date).date())
            close_from = hist_from[0]['CH_CLOSING_PRICE'] if hist_from else None
            close_to = hist_to[0]['CH_CLOSING_PRICE'] if hist_to else None
            try:
                close_from = float(close_from) if close_from is not None else None
                close_to = float(close_to) if close_to is not None else None
            except Exception:
                close_from = None
                close_to = None
            if close_from is not None and close_to is not None:
                ptp_return = ((close_to - close_from) / close_from) * 100
            else:
                print(f"[WARN] {row['symbol']} either changed symbol, listed or delisted within the chosen date range")
        except Exception as e:
            print(f"[ERROR] {row['symbol']} error in p2p return: {e}")
            ptp_return = None
        ptp_return_list.append(ptp_return)

        # Calculate 1yr Return (%)
        one_year_return = None
        try:
            one_year_date = (pd.to_datetime(to_date) - timedelta(days=365)).date()
            hist_1yr = nse.fetch_equity_historical_data(row['symbol'], from_date=one_year_date, to_date=one_year_date)
            hist_to = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(to_date).date(), to_date=pd.to_datetime(to_date).date())
            close_1yr = hist_1yr[0]['CH_CLOSING_PRICE'] if hist_1yr else None
            close_to = hist_to[0]['CH_CLOSING_PRICE'] if hist_to else None
            if close_1yr is not None and close_to is not None:
                one_year_return = ((close_to - close_1yr) / close_1yr) * 100
        except Exception as e:
            print(f"[ERROR] {row['symbol']} error in 1yr return: {e}")
            one_year_return = None
        one_year_return_list.append(one_year_return)

        # Calculate 3yr Return (%) (CAGR)
        three_year_cagr = None
        try:
            three_year_date = (pd.to_datetime(to_date) - timedelta(days=3 * 365)).date()
            hist_3yr = nse.fetch_equity_historical_data(row['symbol'], from_date=three_year_date, to_date=three_year_date)
            close_3yr = hist_3yr[0]['CH_CLOSING_PRICE'] if hist_3yr else None
            if close_3yr is not None and close_to is not None:
                three_year_cagr = (((close_to / close_3yr) ** (1 / 3)) - 1) * 100
        except Exception as e:
            print(f"[ERROR] {row['symbol']} error in 3yr CAGR: {e}")
            three_year_cagr = None
        three_year_cagr_list.append(three_year_cagr)

    # Add new columns to the DataFrame
    df['1yr Return (%)'] = one_year_return_list if len(df) == len(one_year_return_list) else [None] * len(df)
    df['3yr Return (%) (CAGR)'] = three_year_cagr_list if len(df) == len(three_year_cagr_list) else [None] * len(df)
    df['Point-to-Point Return (%)'] = ptp_return_list if len(df) == len(ptp_return_list) else [None] * len(df)
    # Ensure the columns are added to the DataFrame
    df['Free Float Market Cap (₹ Lakhs)'] = ffmc_list if len(df) == len(ffmc_list) else [None] * len(df)
    df['Exposure (%)'] = exposure_pct_list if len(df) == len(exposure_pct_list) else [None] * len(df)

    # Only select columns that exist for pct_change function
    return df.rename(columns={
        'symbol': 'Symbol',
        'name': 'Name',
        'industry': 'Industry',
        'amt_financed_from': 'Amount Financed Start (₹ Lakhs)',
        'amt_financed_to': 'Amount Financed End (₹ Lakhs)',
        'pct_change': '% Change'
    })[['Symbol', 'Name', 'Industry', 'Amount Financed Start (₹ Lakhs)', 'Amount Financed End (₹ Lakhs)', '% Change', 'Free Float Market Cap (₹ Lakhs)', 'Exposure (%)', '1yr Return (%)', '3yr Return (%) (CAGR)', 'Point-to-Point Return (%)']]

def get_newly_added_stocks(from_date: str, to_date: str, top_n: int = 5, industries: list = None):
    """
    Return top N stocks that are newly added in MTF from from_date to to_date.
    Optionally filter by industries.
    Adds point-to-point return (%) for the date range.
    """
    with sqlite3.connect(DB_PATH) as conn:
        if industries:
            placeholders = ",".join("?" for _ in industries)
            df_to = pd.read_sql_query(
                f"""SELECT s.symbol, s.amt_financed
                    FROM stock_data s
                    JOIN stock_master m ON s.symbol = m.symbol
                    WHERE s.date = ? AND m.industry IN ({placeholders})""",
                conn, params=(to_date, *industries)
            )
            df_from = pd.read_sql_query(
                f"""SELECT s.symbol, s.amt_financed
                    FROM stock_data s
                    JOIN stock_master m ON s.symbol = m.symbol
                    WHERE s.date = ? AND m.industry IN ({placeholders})""",
                conn, params=(from_date, *industries)
            )
        else:
            df_to = pd.read_sql_query(
                "SELECT symbol, amt_financed FROM stock_data WHERE date = ?", conn, params=(to_date,)
            )
            df_from = pd.read_sql_query(
                "SELECT symbol, amt_financed FROM stock_data WHERE date = ?", conn, params=(from_date,)
            )
        new_symbols = set(df_to['symbol']) - set(df_from['symbol'])
        df_new = df_to[df_to['symbol'].isin(new_symbols)].copy()
        df_new['amt_financed_from'] = 0
        df_master = pd.read_sql_query("SELECT symbol, name, industry FROM stock_master", conn)
        df_new = pd.merge(df_new, df_master, on="symbol")
        df_new = df_new.rename(columns={'amt_financed': 'amt_financed_to'})

        ffmc_list = []
        exposure_pct_list = []
        ptp_return_list = []
        one_year_return_list = []
        three_year_cagr_list = []
        for _, row in df_new.iterrows():
            try:
                q = nse.quote(row['symbol'], section='trade_info')
                ffmc = q.get('marketDeptOrderBook', {}).get('tradeInfo', {}).get('ffmc', None)
                if ffmc is not None:
                    ffmc_lakhs = ffmc * 100
                    exposure_pct = (row['amt_financed_to'] / ffmc_lakhs) * 100 if ffmc_lakhs else None
                else:
                    ffmc_lakhs = None
                    exposure_pct = None
            except Exception:
                ffmc_lakhs = None
                exposure_pct = None
            ffmc_list.append(ffmc_lakhs)
            exposure_pct_list.append(exposure_pct)

            # Point-to-point return calculation
            ptp_return = None
            try:
                hist_from = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(from_date).date(), to_date=pd.to_datetime(from_date).date())
                hist_to = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(to_date).date(), to_date=pd.to_datetime(to_date).date())
                close_from = hist_from[0]['CH_CLOSING_PRICE'] if hist_from else None
                close_to = hist_to[0]['CH_CLOSING_PRICE'] if hist_to else None
                try:
                    close_from = float(close_from) if close_from is not None else None
                    close_to = float(close_to) if close_to is not None else None
                except Exception:
                    close_from = None
                    close_to = None
                if close_from is not None and close_to is not None:
                    ptp_return = ((close_to - close_from) / close_from) * 100
                else:
                    print(f"[WARN] {row['symbol']} either changed symbol, listed or delisted within the chosen date range")
            except Exception as e:
                print(f"[ERROR] {row['symbol']} error in p2p return: {e}")
                ptp_return = None
            ptp_return_list.append(ptp_return)

            # Calculate 1yr Return (%)
            one_year_return = None
            try:
                one_year_date = (pd.to_datetime(to_date) - timedelta(days=365)).date()
                hist_1yr = nse.fetch_equity_historical_data(row['symbol'], from_date=one_year_date, to_date=one_year_date)
                hist_to = nse.fetch_equity_historical_data(row['symbol'], from_date=pd.to_datetime(to_date).date(), to_date=pd.to_datetime(to_date).date())
                close_1yr = hist_1yr[0]['CH_CLOSING_PRICE'] if hist_1yr else None
                close_to = hist_to[0]['CH_CLOSING_PRICE'] if hist_to else None
                if close_1yr is not None and close_to is not None:
                    one_year_return = ((close_to - close_1yr) / close_1yr) * 100
            except Exception as e:
                print(f"[ERROR] {row['symbol']} error in 1yr return: {e}")
                one_year_return = None
            one_year_return_list.append(one_year_return)

            # Calculate 3yr Return (%) (CAGR)
            three_year_cagr = None
            try:
                three_year_date = (pd.to_datetime(to_date) - timedelta(days=3 * 365)).date()
                hist_3yr = nse.fetch_equity_historical_data(row['symbol'], from_date=three_year_date, to_date=three_year_date)
                close_3yr = hist_3yr[0]['CH_CLOSING_PRICE'] if hist_3yr else None
                if close_3yr is not None and close_to is not None:
                    three_year_cagr = (((close_to / close_3yr) ** (1 / 3)) - 1) * 100
            except Exception as e:
                print(f"[ERROR] {row['symbol']} error in 3yr CAGR: {e}")
                three_year_cagr = None
            three_year_cagr_list.append(three_year_cagr)

        # Assign columns before sorting and selecting columns
        df_new['Free Float Market Cap (₹ Lakhs)'] = ffmc_list if len(df_new) == len(ffmc_list) else [None] * len(df_new)
        df_new['Exposure (%)'] = exposure_pct_list if len(df_new) == len(exposure_pct_list) else [None] * len(df_new)
        df_new['Point-to-Point Return (%)'] = ptp_return_list if len(df_new) == len(ptp_return_list) else [None] * len(df_new)
        df_new['1yr Return (%)'] = one_year_return_list if len(df_new) == len(one_year_return_list) else [None] * len(df_new)
        df_new['3yr Return (%) (CAGR)'] = three_year_cagr_list if len(df_new) == len(three_year_cagr_list) else [None] * len(df_new)
        df_new = df_new.sort_values('amt_financed_to', ascending=False).head(top_n)
        return df_new.rename(columns={
            'symbol': 'Symbol',
            'name': 'Name',
            'industry': 'Industry',
            'amt_financed_from': 'Amount Financed Start (₹ Lakhs)',
            'amt_financed_to': 'Amount Financed End (₹ Lakhs)'
        })[['Symbol', 'Name', 'Industry', 'Amount Financed Start (₹ Lakhs)', 'Amount Financed End (₹ Lakhs)', 'Free Float Market Cap (₹ Lakhs)', 'Exposure (%)', '1yr Return (%)', '3yr Return (%) (CAGR)', 'Point-to-Point Return (%)']]

__all__ = [
    "DB_PATH",
    "download_and_store_range",
    "get_next_available_date",
    "get_prev_available_date",
    "get_top5_amt_financed",
    "get_top5_amt_financed_pct_change",
    "get_newly_added_stocks",
    "create_table",
]

def get_next_available_date(target_date):
    """Return the earliest date >= target_date present in stock_data table as YYYY-MM-DD string, or None if not found."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT MIN(date) FROM stock_data WHERE date >= ?", (target_date.strftime('%Y-%m-%d'),)
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    return None

def get_prev_available_date(target_date):
    """Return the latest date <= target_date present in stock_data table as YYYY-MM-DD string, or None if not found."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT MAX(date) FROM stock_data WHERE date <= ?", (target_date.strftime('%Y-%m-%d'),)
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    return None

if __name__ == "__main__":
    # import sys

    # def parse_date(s):
    #     # Accepts YYYY-MM-DD or DD-MM-YYYY
    #     for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
    #         try:
    #             return datetime.strptime(s, fmt).date()
    #         except ValueError:
    #             continue
    #     raise ValueError(f"Invalid date format: {s}")

    # if len(sys.argv) == 3:
    #     from_date = parse_date(sys.argv[1])
    #     to_date = parse_date(sys.argv[2])

    #     # Adjusted logic: from_date = next available, to_date = previous available
    #     from_date_db = get_next_available_date(from_date)
    #     to_date_db = get_prev_available_date(to_date)

    #     if not from_date_db:
    #         print(f"No data available in DB for {from_date} or any later date.")
    #         sys.exit(1)
    #     if not to_date_db:
    #         print(f"No data available in DB for {to_date} or any earlier date.")
    #         sys.exit(1)

    #     print(f"Using from_date: {from_date_db}, to_date: {to_date_db} (nearest available in DB)")

    #     # download_and_store_range(from_date, to_date)  # Optionally keep this if you want to fetch new data
    #     # plot_net_outstanding_end()
    #     print("\nTop 5 stocks by amt_financed on", to_date_db)
    #     print(get_top5_amt_financed(to_date_db))
    #     # print("\nTop 5 stocks by % change in amt_financed between", from_date_db, "and", to_date_db)
    #     # print(get_top5_amt_financed_pct_change(from_date_db, to_date_db))
    #     # print("\nStocks newly added in MTF from", from_date_db, "to", to_date_db)
    #     # print(get_newly_added_stocks(from_date_db, to_date_db))
    #     print("\nTop 5 stocks by exposure % on", to_date_db)
    #     print(get_top5_exposure_pct(to_date_db))
    # else:
    #     # plot_net_outstanding_end()
    #     print("Usage: python mtfck.py FROM_DATE TO_DATE")
    #     print("Example: python mtfck.py 2025-06-04 2025-06-11")
    #     sys.exit(1)

    equityIndustryInfo = nse.equityMetaInfo(symbol='RELIANCE')
    print("Industry Info for RELIANCE:", equityIndustryInfo)