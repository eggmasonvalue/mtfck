from datetime import date, timedelta
from pathlib import Path
import sqlite3
import pandas as pd
from nse import NSE

DB_PATH = "./db/stock_data.db"
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
SCHEMA_PATH = "./db/schema.sql"

nse = NSE(download_folder=DATA_DIR)


def create_table():
    """Create tables if they do not exist."""
    with sqlite3.connect(DB_PATH) as conn:
        with open(SCHEMA_PATH, "r") as f:
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
        summary["date"] = date_str
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_summary
                (date, total_outstanding_begin, fresh_exposure, exposure_liquidated, net_outstanding_end)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    summary["date"],
                    summary.get("total_outstanding_begin"),
                    summary.get("fresh_exposure"),
                    summary.get("exposure_liquidated"),
                    summary.get("net_outstanding_end"),
                ),
            )

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
    df["date"] = date_str

    # Keep only rows where all required fields are present and not null/empty
    required_cols = ["symbol", "name", "qty_financed", "amt_financed"]
    df = df.dropna(subset=required_cols)
    # Remove rows where any required field is empty string after stripping
    df = df[df[required_cols].map(lambda x: str(x).strip() != "").all(axis=1)]

    # Insert/Get stock_ids
    with sqlite3.connect(DB_PATH) as conn:
        unique_symbols = df[["symbol", "name"]].drop_duplicates()
        symbol_to_id = {}

        # 1. Ensure all symbols are in stock_master and get their IDs
        for _, row in unique_symbols.iterrows():
            symbol = row["symbol"]
            name = row["name"]

            # Check if exists and get ID
            cur = conn.execute(
                "SELECT stock_id FROM stock_master WHERE symbol = ?", (symbol,)
            )
            res = cur.fetchone()

            if res:
                stock_id = res[0]
            else:
                # Need to insert
                try:
                    meta = nse.equityMetaInfo(symbol)
                    industry = meta.get("industry", None)
                except Exception:
                    industry = None

                cur = conn.execute(
                    "INSERT INTO stock_master (symbol, name, industry) VALUES (?, ?, ?)",
                    (symbol, name, industry),
                )
                stock_id = cur.lastrowid
                print(
                    f"Inserted {symbol} into stock_master with industry {industry}, ID: {stock_id}"
                )

            symbol_to_id[symbol] = stock_id

        # 2. Map symbols to IDs in the dataframe
        df["stock_id"] = df["symbol"].map(symbol_to_id)

        # 3. Insert daily data using stock_id
        df_daily = df[["date", "stock_id", "qty_financed", "amt_financed"]]
        df_daily.to_sql("stock_data", conn, if_exists="append", index=False)
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
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT DISTINCT date FROM stock_data")
        db_dates = set(pd.to_datetime([row[0] for row in cur.fetchall()]).date)

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
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT MAX(date) FROM stock_data")
        row = cur.fetchone()
        last_date_str = row[0]

    if last_date_str:
        last_date = pd.to_datetime(last_date_str).date()
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
