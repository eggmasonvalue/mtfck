from datetime import date, datetime, timedelta
from NSE import NSE
from pathlib import Path
import zipfile
from typing import Union
import urllib.parse
import json
import shutil
import sqlite3
import os
import pandas as pd
import matplotlib.pyplot as plt
import requests

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

def unzip(zip_path: Path, extract_to: Path) -> Path:
    """
    Unzips the given zip file to the specified directory.
    Returns the path to the first extracted file.
    """
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
        extracted_files = zip_ref.namelist()
        if extracted_files:
            return extract_to / extracted_files[0]
        else:
            raise FileNotFoundError("No files found in the zip archive.")

def download_document(url: str, folder: Union[str, Path, None] = None) -> Path:
    """
    Download the document from the specified URL and return the saved file path.
    If the downloaded file is a zip file, extracts its contents to the specified folder.

    :param url: URL of the document to download e.g. `https://archives.nseindia.com/annual_reports/AR_ULTRACEMCO_2010_2011_08082011052526.zip`
    :type url: str
    :param folder: Folder path to save file. If not specified, uses DATA_DIR.
    :type folder: pathlib.Path or str or None

    :raise ValueError: If folder is not a directory
    :raise FileNotFoundError: If download failed or file corrupted
    :raise RuntimeError: If file extraction fails

    :return: Path to saved file (or extracted file if zip)
    :rtype: pathlib.Path
    """
    # Use the NSE instance's download_document method for robust downloading
    folder = Path(folder) if folder else DATA_DIR
    return nse.download_document(url, folder)

def download_nse_report(
    archives: list,
    report_date: datetime,
    report_type: str = "equities",
    mode: str = "single",
    folder: Union[str, Path, None] = None
) -> Path:
    """
    Download a report from NSE using the /api/reports endpoint with archives payload.
    """
    folder = Path(folder) if folder else Path(".")
    archives_param = urllib.parse.quote(json.dumps(archives))
    date_str = report_date.strftime("%d-%b-%Y").replace(
        report_date.strftime("%b"), report_date.strftime("%b").capitalize()
    )
    url = (
        f"https://www.nseindia.com/api/reports?"
        f"archives={archives_param}"
        f"&date={date_str}"
        f"&type={report_type}"
        f"&mode={mode}"
    )
    print(f"Downloading from: {url}")
    file = download_document(url=url, folder=folder)
    if not file.is_file():
        file.unlink(missing_ok=True)
        raise FileNotFoundError(f"Failed to download file: {file.name}")
    return file

def is_date_in_db(date_str: str) -> bool:
    """Check if data for the given date already exists in stock_data table."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT 1 FROM stock_data WHERE date = ? LIMIT 1", (date_str,)
        )
        return cur.fetchone() is not None

def download_and_store_range(from_date: date, to_date: date):
    """
    Download NSE Margin Trading Disclosure report for each date in [from_date, to_date] and store in DB.
    """
    archives = [{
        "name": "CM - Margin Trading Disclosure",
        "type": "archives",
        "category": "capital-market",
        "section": "equities"
    }]
    create_table()
    d = from_date
    while d <= to_date:
        date_str = d.strftime('%Y-%m-%d')
        if is_date_in_db(date_str):
            print(f"Skipping {d}: already in database.")
            d += timedelta(days=1)
            continue
        try:
            print(f"Processing {d}")
            result = download_nse_report(
                archives=archives,
                report_date=datetime(d.year, d.month, d.day),
                report_type="equities",
                mode="single",
                folder=DATA_DIR
            )
            csv_path = DATA_DIR / f"mrg_trading_{d.strftime('%d%m%Y')}.csv"
            shutil.move(str(result), csv_path)
            parse_and_insert(str(csv_path), date_str)
            print(f"Loaded {csv_path} into DB for date {d}")
        except Exception as e:
            print(f"Failed for {d}: {e}")
        d += timedelta(days=1)

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

def get_top5_amt_financed(to_date: str, top_n: int = 5, industries: list = None):
    """
    Return top N stocks by amt_financed on to_date,
    with ffmc (free float market cap, in lakhs) and exposure % (amt_financed/ffmc).
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

    # Add ffmc and exposure % columns
    ffmc_list = []
    exposure_pct_list = []
    for _, row in df.iterrows():
        try:
            # Call NSE.quote() with section='trade_info'
            q = nse.quote(row['symbol'], section='trade_info')
            ffmc = q.get('marketDeptOrderBook', {}).get('tradeInfo', {}).get('ffmc', None)
            if ffmc is not None:
                ffmc_lakhs = ffmc * 100  # ffmc is in crores, convert to lakhs
                exposure_pct = (row['amt_financed'] / ffmc_lakhs) * 100 if ffmc_lakhs else None
            else:
                ffmc_lakhs = None
                exposure_pct = None
        except Exception as e:
            # print(f"Failed to fetch data for {row['symbol']}")
            ffmc_lakhs = None
            exposure_pct = None
        ffmc_list.append(ffmc_lakhs)
        exposure_pct_list.append(exposure_pct)

    df['Free Float Market Cap (₹ Lakhs)'] = ffmc_list
    df['Exposure (%)'] = exposure_pct_list
    return df.rename(columns={
        'symbol': 'Symbol',
        'name': 'Name',
        'industry': 'Industry',
        'amt_financed': 'Amount Financed (₹ Lakhs)'
    })[['Symbol', 'Name', 'Industry', 'Amount Financed (₹ Lakhs)', 'Free Float Market Cap (₹ Lakhs)', 'Exposure (%)']]

def get_top5_amt_financed_pct_change(from_date: str, to_date: str, top_n: int = 5, industries: list = None):
    """
    Return top N stocks by percentage change in amt_financed between from_date and to_date.
    Only stocks present on both dates are considered.
    Optionally filter by industries.
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
        # Add name and industry for reporting
        df_master = pd.read_sql_query("SELECT symbol, name, industry FROM stock_master", conn)
        df = pd.merge(df, df_master, on="symbol")
        df = df.sort_values('pct_change', ascending=False).head(top_n)
    # Add ffmc and exposure % columns
    ffmc_list = []
    exposure_pct_list = []
    for _, row in df.iterrows():
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
    df['Free Float Market Cap (₹ Lakhs)'] = ffmc_list
    df['Exposure (%)'] = exposure_pct_list
    return df.rename(columns={
        'symbol': 'Symbol',
        'name': 'Name',
        'industry': 'Industry',
        'amt_financed_from': 'Amount Financed Start (₹ Lakhs)',
        'amt_financed_to': 'Amount Financed End (₹ Lakhs)',
        'pct_change': '% Change'
    })[['Symbol', 'Name', 'Industry', 'Amount Financed Start (₹ Lakhs)', 'Amount Financed End (₹ Lakhs)', '% Change', 'Free Float Market Cap (₹ Lakhs)', 'Exposure (%)']]

def get_newly_added_stocks(from_date: str, to_date: str, top_n: int = 5, industries: list = None):
    """
    Return top N stocks that are newly added in MTF from from_date to to_date.
    Optionally filter by industries.
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
        # Add name and industry for reporting
        df_master = pd.read_sql_query("SELECT symbol, name, industry FROM stock_master", conn)
        df_new = pd.merge(df_new, df_master, on="symbol")
        df_new = df_new.rename(columns={'amt_financed': 'amt_financed_to'})
        # Add ffmc and exposure % columns
        ffmc_list = []
        exposure_pct_list = []
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
        df_new['Free Float Market Cap (₹ Lakhs)'] = ffmc_list
        df_new['Exposure (%)'] = exposure_pct_list
        df_new = df_new.sort_values('amt_financed_to', ascending=False).head(top_n)
        return df_new.rename(columns={
            'symbol': 'Symbol',
            'name': 'Name',
            'industry': 'Industry',
            'amt_financed_from': 'Amount Financed Start (₹ Lakhs)',
            'amt_financed_to': 'Amount Financed End (₹ Lakhs)'
        })[['Symbol', 'Name', 'Industry', 'Amount Financed Start (₹ Lakhs)', 'Amount Financed End (₹ Lakhs)', 'Free Float Market Cap (₹ Lakhs)', 'Exposure (%)']]

def get_top5_exposure_pct(to_date: str, top_n: int = 5, industries: list = None):
    """
    Return top N stocks by exposure % (amt_financed/ffmc) for all stocks on to_date.
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
            """
            params = (to_date, *industries)
        else:
            query = """
                SELECT s.symbol, m.name, m.industry, s.amt_financed
                FROM stock_data s
                JOIN stock_master m ON s.symbol = m.symbol
                WHERE s.date = ?
            """
            params = (to_date,)
        df = pd.read_sql_query(query, conn, params=params)

    # Compute ffmc (in lakhs) and exposure %
    ffmc_list = []
    exposure_pct_list = []
    for _, row in df.iterrows():
        try:
            q = nse.quote(row['symbol'], section='trade_info')
            ffmc = q.get('marketDeptOrderBook', {}).get('tradeInfo', {}).get('ffmc', None)
            if ffmc is not None:
                ffmc_lakhs = ffmc * 100  # ffmc is in crores, convert to lakhs
                exposure_pct = (row['amt_financed'] / ffmc_lakhs) * 100 if ffmc_lakhs else None
            else:
                ffmc_lakhs = None
                exposure_pct = None
        except Exception:
            print(f"Failed to fetch data for {row['symbol']}")
            ffmc_lakhs = None
            exposure_pct = None
        ffmc_list.append(ffmc_lakhs)
        exposure_pct_list.append(exposure_pct)

    df['Free Float Market Cap (₹ Lakhs)'] = ffmc_list
    df['Exposure (%)'] = exposure_pct_list
    # Drop rows where exposure_pct is None or NaN
    df = df.dropna(subset=['Exposure (%)'])
    df = df.sort_values('Exposure (%)', ascending=False).head(top_n)
    return df.rename(columns={
        'symbol': 'Symbol',
        'name': 'Name',
        'industry': 'Industry',
        'amt_financed': 'Amount Financed (₹ Lakhs)'
    })[['Symbol', 'Name', 'Industry', 'Amount Financed (₹ Lakhs)', 'Free Float Market Cap (₹ Lakhs)', 'Exposure (%)']]

__all__ = [
    "DB_PATH",
    "download_and_store_range",
    "get_next_available_date",
    "get_prev_available_date",
    "get_top5_amt_financed",
    "get_top5_amt_financed_pct_change",
    "get_newly_added_stocks",
    "get_top5_exposure_pct",
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