from datetime import date, timedelta
from pathlib import Path
import time
import duckdb
import pandas as pd
from nse import NSE
from .db import get_connection, DB_PATH, close_connection
import csv
import io
import requests

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
SCHEMA_PATH = "./mtf_data/schema.sql"

nse = NSE(download_folder=DATA_DIR)


def create_table():
    """Create tables if they do not exist."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        # DuckDB supports most SQLite syntax, but we might need to adjust slightly
        # For now, assuming schema.sql is compatible
        conn.sql(f.read())
    # Ensure daily_summary table exists (redundant if in schema.sql, but safe)
    conn.sql("""
    CREATE TABLE IF NOT EXISTS daily_summary (
        date DATE PRIMARY KEY,
        total_outstanding_begin DOUBLE,
        fresh_exposure DOUBLE,
        exposure_liquidated DOUBLE,
        net_outstanding_end DOUBLE
    )
    """)


def parse_and_insert(csv_path: str, date_str: str):
    """
    Parse the CSV file, extract summary and stock data, and insert into the database.
    Only rows with all required fields are stored.
    """
    # Find the header row and summary fields
    with open(csv_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    header_idx = None
    summary = {}
    for idx, line in enumerate(lines):
        if line.startswith("Symbol,Name,"):
            header_idx = idx
            break
        # Parse summary fields
        if line.startswith("1,Scripwise Total Outstanding"):
            summary["total_outstanding_begin"] = float(
                line.split(",")[2].replace(",", "").strip()
            )
        elif line.startswith("2,Fresh Exposure taken"):
            summary["fresh_exposure"] = float(
                line.split(",")[2].replace(",", "").strip()
            )
        elif line.startswith("3,Exposure liquidated"):
            summary["exposure_liquidated"] = float(
                line.split(",")[2].replace(",", "").strip()
            )
        elif line.startswith("4,Net scripwise outstanding"):
            summary["net_outstanding_end"] = float(
                line.split(",")[2].replace(",", "").strip()
            )
    if header_idx is None:
        raise ValueError(f"Header not found in {csv_path}")

    # Insert summary if found
    if summary:
        summary["date"] = pd.to_datetime(date_str).date()
        conn = get_connection()
        # Create a localized DataFrame for insertion
        df_summary = pd.DataFrame([summary])
        # Explicit column selection to match table definition
        conn.sql("""
            INSERT OR REPLACE INTO daily_summary
            (date, total_outstanding_begin, fresh_exposure, exposure_liquidated, net_outstanding_end)
            SELECT date, total_outstanding_begin, fresh_exposure, exposure_liquidated, net_outstanding_end
            FROM df_summary
        """)

    # Read stock data
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

    # Keep only rows where all required fields are present and not null/empty
    required_cols = ["symbol", "name", "qty_financed", "amt_financed"]
    df = df.dropna(subset=required_cols)
    # Remove rows where any required field is empty string after stripping
    df = df[df[required_cols].map(lambda x: str(x).strip() != "").all(axis=1)]

    # Insert/Get stock_ids
    conn = get_connection()
    unique_symbols = df[["symbol", "name"]].drop_duplicates()

    # 1. Update stock_master with new symbols
    # DuckDB efficient merge/upsert
    # First, ensure stock_master has all symbols

    # We need to fetch industry for new symbols. This is slow loop, but better logic:
    # Identify symbols NOT in stock_master
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

        # Insert new symbols into stock_master
        # Note: stock_id is AUTOINCREMENT, so we just insert other columns
        # But DuckDB 'INSERT INTO ... SELECT' doesn't easily return IDs for mapping in one go without RETURNING
        # However, for the 'stock_data' table, we need 'stock_id'.
        # Strategy: Insert new, then Select ALL to create the map.
        conn.sql("INSERT INTO stock_master (symbol, name, industry) SELECT symbol, name, industry FROM new_symbols_df")
        print(f"Inserted {len(new_symbols_df)} new symbols.")

    # 2. Map symbols to IDs
    # Read full master table to get IDs
    # Creating a map inside DuckDB or in Memory? DuckDB Join is better.

    # Let's do the join in DuckDB for insertion!
    # stock_data needs: date, stock_id, qty_financed, amt_financed

    # Register the dataframe so SQL can see it
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

    # Delete the CSV file after processing
    try:
        Path(csv_path).unlink()
        print(f"Deleted file {csv_path}")
    except Exception as e:
        print(f"Warning: Could not delete file {csv_path}: {e}")


def download_and_store_range(from_date: date, to_date: date):
    """
    Download NSE Margin Trading Disclosure report for each date in [from_date, to_date] and store in DB.
    Only downloads for dates not already present in the DB.
    """
    create_table()
    # Get all dates present in DB
    conn = get_connection()
    # Check if table has data first to avoid error
    try:
        res = conn.sql("SELECT DISTINCT date FROM stock_data").fetchall()
        db_dates = set([row[0] for row in res])
    except duckdb.CatalogException: # Table might not exist or be empty behavior
            db_dates = set()
    except Exception:
            db_dates = set()

    # Prepare all dates in the range
    all_dates = [
        from_date + timedelta(days=i) for i in range((to_date - from_date).days + 1)
    ]
    missing_dates = [d for d in all_dates if d not in db_dates]
    skipped_dates = [d for d in all_dates if d in db_dates]

    print(f"Skipping {len(skipped_dates)} dates already in DB")
    print(
        f"Downloading {len(missing_dates)} dates: {[d.strftime('%Y-%m-%d') for d in missing_dates]}"
    )

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

            # result is already the extracted CSV file
            parse_and_insert(str(result), date_str)
            print(f"Loaded {result} into DB for date {d}")
        except Exception as e:
            print(f"Failed for {d}: {e}")


def process_symbol_changes():
    """
    Download and process symbol changes from NSE.
    Handles renaming and merging of stock data.
    """
    print("Checking for symbol changes...")
    url = "https://nsearchives.nseindia.com/content/equities/symbolchange.csv"
    try:
        # User-Agent might be needed to avoid blocking
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        # Decode using ISO-8859-1 (common for NSE/legacy systems) or utf-8 with replace
        content = response.content.decode('ISO-8859-1')
    except Exception as e:
        print(f"Failed to download symbol change CSV: {e}")
        return

    csv_reader = csv.reader(io.StringIO(content))
    changes = []

    # Try to find header
    header_idx = -1
    rows = list(csv_reader)

    for i, row in enumerate(rows):
        if len(row) >= 3 and "Old Symbol" in str(row) and "New Symbol" in str(row):
            header_idx = i
            break

    if header_idx == -1:
        # Fallback: assume data starts after some lines, or just try to parse all
        # Logic: Look for lines with 4 columns where col 3 is date-like
        start_idx = 0
    else:
        start_idx = header_idx + 1

    for row in rows[start_idx:]:
        if len(row) < 3: continue
        # CSV Format: Company Name, Old Symbol, New Symbol, Change Date
        old_sym = row[1].strip()
        new_sym = row[2].strip()
        if not old_sym or not new_sym: continue
        changes.append((old_sym, new_sym))

    if not changes:
        print("No symbol changes found.")
        return

    conn = get_connection()

    # 1. Identify relevant changes (Old Symbol in DB)
    # Fetch all current symbols
    try:
        existing_symbols_df = conn.sql("SELECT stock_id, symbol, name, industry FROM stock_master").df()
    except Exception:
        return # DB might be empty

    if existing_symbols_df.empty:
        return

    # Map symbol -> row (dict) for quick lookup
    symbol_map = {row['symbol']: row.to_dict() for _, row in existing_symbols_df.iterrows()}

    count_renamed = 0
    count_merged = 0

    for old_sym, new_sym in changes:
        if old_sym not in symbol_map:
            continue

        old_row = symbol_map[old_sym]
        old_id = old_row['stock_id']

        # Determine Target ID (New Symbol)
        if new_sym in symbol_map:
            # Target exists -> Merge
            new_id = symbol_map[new_sym]['stock_id']
            print(f"Merging {old_sym} (ID: {old_id}) into existing {new_sym} (ID: {new_id})")
            count_merged += 1
        else:
            # Target does not exist -> Create new master entry
            # Use name/industry from old symbol if available
            name = old_row['name']
            industry = old_row['industry']

            print(f"Renaming {old_sym} (ID: {old_id}) -> {new_sym} (New Entry)")

            # Insert new symbol
            # Note: Parameter logic for connection.execute varies. Using f-string for simplicity/speed safely here as symbols are trusted?
            # Or assume parameterized query works with execute.
            conn.execute("INSERT INTO stock_master (symbol, name, industry) VALUES (?, ?, ?)", [new_sym, name, industry])

            # Fetch the new ID
            # Assuming uniqueness of symbol, verify it was inserted
            try:
                new_id = conn.sql(f"SELECT stock_id FROM stock_master WHERE symbol = '{new_sym}'").fetchone()[0]
                # Update local map for chain updates
                symbol_map[new_sym] = {'stock_id': new_id, 'symbol': new_sym, 'name': name, 'industry': industry}
                count_renamed += 1
            except Exception as e:
                print(f"Error inserting new symbol {new_sym}: {e}")
                continue

        # Common Relink Logic (Move Old ID data to New ID)

        # 1. Update IDs in stock_data for non-conflicting dates
        query_update = f"""
            UPDATE stock_data
            SET stock_id = {new_id}
            WHERE stock_id = {old_id}
            AND date NOT IN (SELECT date FROM stock_data WHERE stock_id = {new_id})
        """
        conn.execute(query_update)

        # 2. Delete remaining rows for old_id (collisions, we keep new_id's data)
        conn.execute(f"DELETE FROM stock_data WHERE stock_id = {old_id}")

        # 3. Delete from stock_master (Old Symbol)
        # Verify no constraints block this? Now stock_data for old_id is GONE.
        try:
            conn.execute(f"DELETE FROM stock_master WHERE stock_id = {old_id}")
        except Exception as e:
            print(f"Warning: Could not delete old master record for {old_sym} (ID {old_id}): {e}")

        # Remove from local map
        if old_sym in symbol_map:
            del symbol_map[old_sym]

    if count_renamed > 0 or count_merged > 0:
        print(f"Symbol changes processed: {count_renamed} renamed, {count_merged} merged.")

    # Post-clean: Fetch industries for symbols with NULL industry
    # This might happen if we just renamed and didn't have industry, or if merge happend
    # Actually, verify if any industry is NULL
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


def sync_sequence():
    """Ensure stock_id_seq is consistent with stock_master.stock_id."""
    conn = get_connection()
    try:
        # Check if table exists
        conn.execute("SELECT 1 FROM stock_master LIMIT 1")
    except duckdb.CatalogException:
        return # Table doesn't exist yet, nothing to sync
    except Exception:
        return

    # Get Max ID
    row = conn.execute("SELECT MAX(stock_id) FROM stock_master").fetchone()
    max_id = row[0] if row and row[0] is not None else 0

    # Sync sequence
    try:
        seq_info = conn.execute("SELECT last_value FROM duckdb_sequences() WHERE sequence_name='stock_id_seq'").fetchone()
        if seq_info:
            current_val = seq_info[0] if seq_info[0] is not None else 0
            if current_val < max_id:
                diff = max_id - current_val
                print(f"Syncing sequence: lagging by {diff}. Fast-forwarding...")
                # Use nextval loop as ALTER SEQUENCE RESTART is not supported in some versions
                conn.execute(f"SELECT nextval('stock_id_seq') FROM range({diff})")
                print(f"Sequence fast-forwarded to > {max_id}")
    except Exception as e:
        print(f"Warning: Could not sync sequence: {e}")


def update_to_today():
    """Calculates the missing range (Last DB Date -> Today) and runs the download."""
    create_table()

    # Ensure sequence is synced before we do anything that might rely on it for new inserts
    sync_sequence()

    process_symbol_changes()

    conn = get_connection()
    try:
        row = conn.sql("SELECT MAX(date) FROM stock_data").fetchone()
        last_date = row[0] if row else None
    except Exception:
        last_date = None

    if last_date:
        # last_date is datetime.date object in DuckDB
        from_date = last_date + timedelta(days=1)
    else:
        # Default to 30 days ago if DB is empty
        from_date = date.today() - timedelta(days=30)

    to_date = date.today()

    if from_date > to_date:
        print("Database is already up to date.")
        return

    print(f"Updating database from {from_date} to {to_date}")
    download_and_store_range(from_date, to_date)


def migrate_legacy_data():
    """Migrates data from legacy SQLite DB if it exists and DuckDB is empty."""
    import os
    sqlite_db_path = "./db/stock_data.db"
    if not os.path.exists(sqlite_db_path):
        return

    conn = get_connection()
    try:
        # Check if we already have meaningful data
        # If count is small (e.g. from tests), we might still want to migrate?
        # But merging is hard. Let's assume if < 100 rows, it's just test data and we can WIPE it and migrate.
        count = conn.sql("SELECT count(*) FROM stock_master").fetchone()[0]
        if count > 100:
            return # Already has substantial data

        print("Migrating legacy data from SQLite...")

        # If we are migrating, we should probably clear any test data first to avoid ID conflicts
        if count > 0:
            print("Clearing existing (test) data before migration...")
            conn.execute("DELETE FROM stock_data")
            conn.execute("DELETE FROM daily_summary")
            conn.execute("DELETE FROM stock_master")
            # Create fresh sequence
            try:
                conn.execute("DROP SEQUENCE IF EXISTS stock_id_seq")
                conn.execute("CREATE SEQUENCE stock_id_seq START 1")
            except:
                pass

        # Install/Load sqlite extension
        conn.execute("INSTALL sqlite; LOAD sqlite;")

        # Attach
        conn.execute(f"ATTACH '{sqlite_db_path}' AS sqlite_db (TYPE SQLITE);")

        # 1. Stock Master
        conn.execute("INSERT INTO stock_master SELECT * FROM sqlite_db.stock_master")
        # Reset Sequence
        sync_sequence()

        # 2. Daily Summary
        conn.execute("""
            INSERT INTO daily_summary
            SELECT
                CAST(date AS DATE),
                total_outstanding_begin,
                fresh_exposure,
                exposure_liquidated,
                net_outstanding_end
            FROM sqlite_db.daily_summary
        """)

        # 3. Stock Data
        conn.execute("""
            INSERT INTO stock_data
            SELECT
                CAST(date AS DATE),
                stock_id,
                CAST(qty_financed AS DOUBLE),
                CAST(amt_financed AS DOUBLE)
            FROM sqlite_db.stock_data
        """)

        conn.execute("DETACH sqlite_db")
        print("Legacy migration complete.")

    except Exception as e:
        print(f"Error during migration: {e}")

if __name__ == "__main__":
    update_to_today()
