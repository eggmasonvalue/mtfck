from datetime import date, timedelta
from pathlib import Path
import duckdb
import pandas as pd
from exchange_access import NSEClient, get_retry_decorator
from .db import get_connection
import csv
import io
import requests

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

# Underlying NSE instance from the shared L1 client (single construction
# source). Uses the native bulk retry profile.
nse = NSEClient(str(DATA_DIR), server=True, retry_profile='bulk').nse


def create_table() -> None:
    """
    Ensure required tables exist in the database.
    Since we use in-memory DuckDB with Parquet, table creation is handled by get_connection().
    """
    get_connection(read_only=False)


def parse_and_insert(csv_path: str, date_str: str) -> None:
    """
    Parse a Margin Trading Facility (MTF) CSV file and insert the data into the database.
    
    Extracts overall daily summary metrics and individual stock financing data. 
    Inserts data directly into the denormalized stock_data table.
    
    Args:
        csv_path (str): Path to the daily CSV file (or directory containing it).
        date_str (str): Date of the file contents in YYYY-MM-DD format.
    """
    p = Path(csv_path)
    if p.is_dir():
        csv_files = list(p.glob("**/*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No CSV file found in directory {csv_path}")
        # Use the first CSV file found
        actual_path = str(csv_files[0])
    else:
        actual_path = csv_path

    with open(actual_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    header_idx = None
    summary = {}
    for idx, line in enumerate(lines):
        if line.startswith("Symbol,Name,"):
            header_idx = idx
            break
            
        if line.startswith("1,Scripwise Total Outstanding"):
            summary["total_outstanding_begin"] = float(line.split(",")[2].replace(",", "").strip())
        elif line.startswith("2,Fresh Exposure taken"):
            summary["fresh_exposure"] = float(line.split(",")[2].replace(",", "").strip())
        elif line.startswith("3,Exposure liquidated"):
            summary["exposure_liquidated"] = float(line.split(",")[2].replace(",", "").strip())
        elif line.startswith("4,Net scripwise outstanding"):
            summary["net_outstanding_end"] = float(line.split(",")[2].replace(",", "").strip())
            
    if header_idx is None:
        raise ValueError(f"Header not found in {actual_path}")

    conn = get_connection(read_only=False)

    if summary:
        summary["date"] = pd.to_datetime(date_str).date()
        df_summary = pd.DataFrame([summary])  # noqa: F841
        conn.sql("""
            INSERT OR REPLACE INTO daily_summary
            (date, total_outstanding_begin, fresh_exposure, exposure_liquidated, net_outstanding_end)
            SELECT date, total_outstanding_begin, fresh_exposure, exposure_liquidated, net_outstanding_end
            FROM df_summary
        """)

    df = pd.read_csv(actual_path, skiprows=header_idx)
    df = df.rename(
        columns={
            "Symbol": "symbol",
            "Qty Fin by all the members(No.of Shares)": "qty_financed",
            "Amt Fin by all the members(Rs. In Lakhs)": "amt_financed",
        }
    )
    df["date"] = pd.to_datetime(date_str).date()

    required_cols = ["symbol", "qty_financed", "amt_financed"]
    df = df.dropna(subset=required_cols)
    df = df[df[required_cols].map(lambda x: str(x).strip() != "").all(axis=1)]

    conn.register("df_staging", df)

    # Note: duckdb automatically handles inserting directly via SQL from the registered DataFrame
    conn.sql("""
        INSERT OR IGNORE INTO stock_data (date, symbol, qty_financed, amt_financed)
        SELECT
            d.date,
            d.symbol,
            d.qty_financed,
            d.amt_financed
        FROM df_staging d
    """)

    try:
        if p.is_dir():
            import shutil
            shutil.rmtree(csv_path)
            print(f"Deleted directory {csv_path}")
        else:
            p.unlink()
            print(f"Deleted file {csv_path}")
    except Exception as e:
        print(f"Warning: Could not delete {csv_path}: {e}")


def _download_for_date(d: date) -> None:
    """
    Download and parse report for a single date with retry mechanism.
    """
    date_str = d.strftime("%Y-%m-%d")
    print(f"Processing {d}")
    url = f"https://nsearchives.nseindia.com/content/equities/mrg_trading_{d.strftime('%d%m%y')}.zip"
    print(f"Downloading from: {url}")
    result = nse.download_document(url=url, folder=DATA_DIR)
    if not result.is_file():
        result.unlink(missing_ok=True)
        raise FileNotFoundError(f"Failed to download file: {result.name}")

    parse_and_insert(str(result), date_str)
    print(f"Loaded {result} into DB for date {d}")


def download_and_store_range(from_date: date, to_date: date) -> None:
    """
    Download and store NSE MTF Disclosure reports for a specific date range.
    
    Dates already present in the database are skipped.
    
    Args:
        from_date (date): Start date for the download range.
        to_date (date): End date for the download range.
    """
    create_table()
    conn = get_connection()
    try:
        res = conn.sql("SELECT DISTINCT date FROM stock_data").fetchall()
        db_dates = set([row[0] for row in res])
    except duckdb.CatalogException:
        db_dates = set()
    except Exception:
        db_dates = set()

    all_dates = [from_date + timedelta(days=i) for i in range((to_date - from_date).days + 1)]
    missing_dates = [d for d in all_dates if d not in db_dates]
    skipped_dates = [d for d in all_dates if d in db_dates]

    print(f"Skipping {len(skipped_dates)} dates already in DB")
    print(f"Downloading {len(missing_dates)} dates: {[d.strftime('%Y-%m-%d') for d in missing_dates]}")

    for d in missing_dates:
        try:
            _download_for_date(d)
        except Exception as e:
            print(f"Failed for {d}: {e}")


@get_retry_decorator('bulk')
def _download_symbol_change_csv(url: str) -> str:
    """
    Download symbol change CSV with retry.
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.content.decode('ISO-8859-1')


def process_symbol_changes() -> None:
    """
    Download and process corporate symbol changes from NSE.
    
    Handles the renaming of historic stock data by updating symbols directly.
    """
    print("Checking for symbol changes...")
    url = "https://nsearchives.nseindia.com/content/equities/symbolchange.csv"
    try:
        content = _download_symbol_change_csv(url)
    except Exception as e:
        print(f"Failed to download symbol change CSV: {e}")
        return

    csv_reader = csv.reader(io.StringIO(content))
    changes = []

    header_idx = -1
    rows = list(csv_reader)

    for i, row in enumerate(rows):
        if len(row) >= 3 and "Old Symbol" in str(row) and "New Symbol" in str(row):
            header_idx = i
            break

    start_idx = 0 if header_idx == -1 else header_idx + 1

    for row in rows[start_idx:]:
        if len(row) < 3:
            continue
        old_sym = row[1].strip()
        new_sym = row[2].strip()
        if not old_sym or not new_sym:
            continue
        changes.append((old_sym, new_sym))

    if not changes:
        print("No symbol changes found.")
        return

    conn = get_connection(read_only=False)

    count_renamed = 0

    for old_sym, new_sym in changes:
        # Check if the old symbol exists in the database
        try:
            res = conn.execute("SELECT 1 FROM stock_data WHERE symbol = ? LIMIT 1", [old_sym]).fetchone()
            if not res:
                continue
        except Exception:
            continue

        try:
            # We want to rename old_sym to new_sym
            # But what if new_sym already has data on those dates? We should ignore conflicts or sum them up.
            # Easiest way in DuckDB without complex joins: update where no conflict, then delete remaining old.
            conn.execute("""
                UPDATE stock_data
                SET symbol = ?
                WHERE symbol = ? 
                AND date NOT IN (SELECT date FROM stock_data WHERE symbol = ?)
            """, [new_sym, old_sym, new_sym])
            
            # Delete any remaining rows for old_sym that couldn't be updated (collisions)
            conn.execute("DELETE FROM stock_data WHERE symbol = ?", [old_sym])
            count_renamed += 1
            print(f"Merged/Renamed {old_sym} -> {new_sym}")
        except Exception as e:
            print(f"Error renaming {old_sym} to {new_sym}: {e}")

    if count_renamed > 0:
        print(f"Symbol changes processed: {count_renamed} symbols affected.")


def update_to_today(from_date_str: str = None) -> None:
    """
    Calculate missing dates since the last update and fetch the latest reports.
    """
    create_table()
    process_symbol_changes()

    conn = get_connection(read_only=False)
    try:
        row = conn.sql("SELECT MAX(date) FROM stock_data").fetchone()
        last_date = row[0] if row else None
    except Exception:
        last_date = None

    if from_date_str:
        from_date = pd.to_datetime(from_date_str).date()
    elif last_date:
        from_date = last_date + timedelta(days=1)
    else:
        from_date = date.today() - timedelta(days=30)

    to_date = date.today()

    if from_date > to_date:
        print("Database is already up to date.")
        return

    print(f"Updating database from {from_date} to {to_date}")
    download_and_store_range(from_date, to_date)
    
    # Export in-memory tables back to parquet
    from .db import DB_PATH, SUMMARY_PATH
    print("Exporting updated tables to parquet...")
    conn.execute(f"COPY stock_data TO '{DB_PATH}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    conn.execute(f"COPY daily_summary TO '{SUMMARY_PATH}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print("Export complete.")
