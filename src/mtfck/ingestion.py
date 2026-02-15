from datetime import date, timedelta
from pathlib import Path
import duckdb
import pandas as pd
from nse import NSE
from .db import get_connection, DB_PATH, close_connection

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
SCHEMA_PATH = "./db/schema.sql"

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


def update_to_today():
    """Calculates the missing range (Last DB Date -> Today) and runs the download."""
    create_table()
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
        row = conn.execute("SELECT MAX(stock_id) FROM stock_master").fetchone()
        max_id = row[0] if row else 0
        try:
            conn.execute(f"ALTER SEQUENCE stock_id_seq RESTART WITH {max_id + 1}")
        except Exception as e:
            print(f"Warning: Could not reset sequence: {e}")

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
