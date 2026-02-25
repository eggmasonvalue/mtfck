from datetime import date, timedelta
from pathlib import Path
import duckdb
import pandas as pd
from nse import NSE
from .db import get_connection
import csv
import io
import requests

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
SCHEMA_PATH = "./mtf_data/schema.sql"

nse = NSE(download_folder=DATA_DIR)


def create_table() -> None:
    """
    Ensure required tables exist in the database.
    Executes the schema definition from the associated SQL file.
    """
    conn = get_connection(read_only=False)
    with open(SCHEMA_PATH, "r") as f:
        conn.sql(f.read())


def parse_and_insert(csv_path: str, date_str: str) -> None:
    """
    Parse a Margin Trading Facility (MTF) CSV file and insert the data into the database.
    
    Extracts overall daily summary metrics and individual stock financing data. 
    New symbols are automatically resolved against the NSE API for industry metadata 
    and added to the master table before the daily data is recorded.
    
    Args:
        csv_path (str): Path to the daily CSV file.
        date_str (str): Date of the file contents in YYYY-MM-DD format.
    """
    with open(csv_path, "r", encoding="utf-8") as f:
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
        raise ValueError(f"Header not found in {csv_path}")

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

    df = pd.read_csv(csv_path, skiprows=header_idx)
    df = df.rename(
        columns={
            "Symbol": "symbol",
            "Name": "name",
            "Qty Fin by all the members(No.of Shares)": "qty_financed",
            "Amt Fin by all the members(Rs. In Lakhs)": "amt_financed",
        }
    )
    df["date"] = pd.to_datetime(date_str).date()

    required_cols = ["symbol", "name", "qty_financed", "amt_financed"]
    df = df.dropna(subset=required_cols)
    df = df[df[required_cols].map(lambda x: str(x).strip() != "").all(axis=1)]

    unique_symbols = df[["symbol", "name"]].drop_duplicates()

    existing_symbols_df = conn.sql("SELECT symbol FROM stock_master").df()
    existing_symbols = set(existing_symbols_df["symbol"]) if not existing_symbols_df.empty else set()

    new_symbols_df = unique_symbols[~unique_symbols["symbol"].isin(existing_symbols)].copy()

    if not new_symbols_df.empty:
        print(f"Found {len(new_symbols_df)} new symbols. Fetching industries...")
        industries = []
        for symbol in new_symbols_df["symbol"]:
            try:
                meta = nse.equityMetaInfo(symbol)
                industry = meta.get("industry", None)
            except Exception:
                industry = None
            industries.append(industry)
        new_symbols_df["industry"] = industries

        conn.sql("INSERT INTO stock_master (symbol, name, industry) SELECT symbol, name, industry FROM new_symbols_df")
        print(f"Inserted {len(new_symbols_df)} new symbols.")

    conn.register("df_staging", df)

    conn.sql("""
        INSERT INTO stock_data (date, stock_id, qty_financed, amt_financed)
        SELECT
            d.date,
            m.stock_id,
            d.qty_financed,
            d.amt_financed
        FROM df_staging d
        JOIN stock_master m ON d.symbol = m.symbol
    """)

    try:
        Path(csv_path).unlink()
        print(f"Deleted file {csv_path}")
    except Exception as e:
        print(f"Warning: Could not delete file {csv_path}: {e}")


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
        date_str = d.strftime("%Y-%m-%d")
        try:
            print(f"Processing {d}")
            url = f"https://nsearchives.nseindia.com/content/equities/mrg_trading_{d.strftime('%d%m%y')}.zip"
            print(f"Downloading from: {url}")
            result = nse.download_document(url=url, folder=DATA_DIR)
            if not result.is_file():
                result.unlink(missing_ok=True)
                raise FileNotFoundError(f"Failed to download file: {result.name}")

            parse_and_insert(str(result), date_str)
            print(f"Loaded {result} into DB for date {d}")
        except Exception as e:
            print(f"Failed for {d}: {e}")


def process_symbol_changes() -> None:
    """
    Download and process corporate symbol changes from NSE.
    
    Handles the renaming and merging of historic stock data by correctly mapping 
    old symbols to their new identities in the master table and updating foreign keys.
    """
    print("Checking for symbol changes...")
    url = "https://nsearchives.nseindia.com/content/equities/symbolchange.csv"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        content = response.content.decode('ISO-8859-1')
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

    try:
        existing_symbols_df = conn.sql("SELECT stock_id, symbol, name, industry FROM stock_master").df()
    except Exception:
        return

    if existing_symbols_df.empty:
        return

    symbol_map = {row['symbol']: row.to_dict() for _, row in existing_symbols_df.iterrows()}
    count_renamed = 0
    count_merged = 0

    for old_sym, new_sym in changes:
        if old_sym not in symbol_map:
            continue

        old_row = symbol_map[old_sym]
        old_id = old_row['stock_id']

        if new_sym in symbol_map:
            new_id = symbol_map[new_sym]['stock_id']
            print(f"Merging {old_sym} (ID: {old_id}) into existing {new_sym} (ID: {new_id})")
            count_merged += 1
        else:
            name = old_row['name']
            industry = old_row['industry']
            print(f"Renaming {old_sym} (ID: {old_id}) -> {new_sym} (New Entry)")

            conn.execute("INSERT INTO stock_master (symbol, name, industry) VALUES (?, ?, ?)", [new_sym, name, industry])
            try:
                new_id = conn.sql(f"SELECT stock_id FROM stock_master WHERE symbol = '{new_sym}'").fetchone()[0]
                symbol_map[new_sym] = {'stock_id': new_id, 'symbol': new_sym, 'name': name, 'industry': industry}
                count_renamed += 1
            except Exception as e:
                print(f"Error inserting new symbol {new_sym}: {e}")
                continue

        query_update = f"""
            UPDATE stock_data
            SET stock_id = {new_id}
            WHERE stock_id = {old_id}
            AND date NOT IN (SELECT date FROM stock_data WHERE stock_id = {new_id})
        """
        conn.execute(query_update)
        conn.execute(f"DELETE FROM stock_data WHERE stock_id = {old_id}")
        
        try:
            conn.execute(f"DELETE FROM stock_master WHERE stock_id = {old_id}")
        except Exception as e:
            print(f"Warning: Could not delete old master record for {old_sym} (ID {old_id}): {e}")

        if old_sym in symbol_map:
            del symbol_map[old_sym]

    if count_renamed > 0 or count_merged > 0:
        print(f"Symbol changes processed: {count_renamed} renamed, {count_merged} merged.")

    null_ind_df = conn.sql("SELECT symbol FROM stock_master WHERE industry IS NULL").df()
    if not null_ind_df.empty:
        print(f"Fetching missing industries for {len(null_ind_df)} symbols...")
        for sym in null_ind_df['symbol']:
            try:
                meta = nse.equityMetaInfo(sym)
                ind = meta.get('industry', None)
                if ind:
                    conn.execute("UPDATE stock_master SET industry = ? WHERE symbol = ?", [ind, sym])
            except Exception:
                pass


def sync_sequence() -> None:
    """
    Ensure the stock_id sequence matches the highest existing ID.
    
    DuckDB does not currently support 'ALTER SEQUENCE RESTART', so synchronization 
    is handled by incrementally pulling values to fast-forward the sequence state.
    """
    conn = get_connection(read_only=False)
    try:
        conn.execute("SELECT 1 FROM stock_master LIMIT 1")
    except duckdb.CatalogException:
        return
    except Exception:
        return

    row = conn.execute("SELECT MAX(stock_id) FROM stock_master").fetchone()
    max_id = row[0] if row and row[0] is not None else 0

    try:
        seq_info = conn.execute("SELECT last_value FROM duckdb_sequences() WHERE sequence_name='stock_id_seq'").fetchone()
        if seq_info:
            current_val = seq_info[0] if seq_info[0] is not None else 0
            if current_val < max_id:
                diff = max_id - current_val
                print(f"Syncing sequence: lagging by {diff}. Fast-forwarding...")
                conn.execute(f"SELECT nextval('stock_id_seq') FROM range({diff})")
                print(f"Sequence fast-forwarded to > {max_id}")
    except Exception as e:
        print(f"Warning: Could not sync sequence: {e}")


def update_to_today() -> None:
    """
    Calculate missing dates since the last update and fetch the latest reports.
    """
    create_table()
    sync_sequence()
    process_symbol_changes()

    conn = get_connection(read_only=False)
    try:
        row = conn.sql("SELECT MAX(date) FROM stock_data").fetchone()
        last_date = row[0] if row else None
    except Exception:
        last_date = None

    if last_date:
        from_date = last_date + timedelta(days=1)
    else:
        from_date = date.today() - timedelta(days=30)

    to_date = date.today()

    if from_date > to_date:
        print("Database is already up to date.")
        return

    print(f"Updating database from {from_date} to {to_date}")
    download_and_store_range(from_date, to_date)
