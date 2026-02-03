from datetime import date, timedelta
from nse import NSE
from pathlib import Path
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

DB_PATH = "./stock_data.db"
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
SCHEMA_PATH = "./db/schema.sql"

nse = NSE(download_folder=Path("."))


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

    # Insert unique symbols/names into stock_master
    with sqlite3.connect(DB_PATH) as conn:
        unique_symbols = df[["symbol", "name"]].drop_duplicates()
        for _, row in unique_symbols.iterrows():
            symbol = row["symbol"]
            name = row["name"]
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
                    industry = meta.get("industry", None)
                except Exception:
                    # break
                    industry = None
                conn.execute(
                    "INSERT OR IGNORE INTO stock_master (symbol, name, industry) VALUES (?, ?, ?)",
                    (symbol, name, industry),
                )
                print(f"Inserted {symbol} into stock_master with industry {industry}")
            # else: do nothing if already exists
        # Insert daily data, referencing only symbol
        df_daily = df[["date", "symbol", "qty_financed", "amt_financed"]]
        df_daily.to_sql("stock_data", conn, if_exists="append", index=False)
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


def plot_net_outstanding_end():
    """Fetch daily_summary and plot net_outstanding_end for each day."""
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            "SELECT date, net_outstanding_end FROM daily_summary ORDER BY date", conn
        )
    if df.empty:
        print("No summary data found.")
        return
    df["date"] = pd.to_datetime(df["date"])
    plt.figure(figsize=(10, 5))
    plt.plot(df["date"], df["net_outstanding_end"], marker="o")
    plt.title("Net Outstanding End (Daily)")
    plt.xlabel("Date")
    plt.ylabel("Net Outstanding End")
    plt.grid(True)
    plt.tight_layout()
    plt.show()


""" Note: Price related historical data is not corporate action adjusted."""


def calculate_returns(symbol, to_date, from_date=None):
    """
    Calculate p2p, 1yr, and 3yr returns for a symbol.
    Returns (ptp_return, one_year_return, three_year_cagr)
    """
    close_to = get_next_trading_close(symbol, pd.to_datetime(to_date).date())
    ptp_return = None
    one_year_return = None
    three_year_cagr = None

    # Point-to-point return
    if from_date:
        close_from = get_next_trading_close(symbol, pd.to_datetime(from_date).date())
        if close_from is not None and close_to is not None:
            ptp_return = ((close_to - close_from) / close_from) * 100

    # 1yr Return (%)
    one_year_date = (pd.to_datetime(to_date) - timedelta(days=365)).date()
    close_1yr = get_next_trading_close(symbol, one_year_date)
    if close_1yr is not None and close_to is not None:
        one_year_return = ((close_to - close_1yr) / close_1yr) * 100

    # 3yr Return (%) (CAGR)
    three_year_date = (pd.to_datetime(to_date) - timedelta(days=3 * 365)).date()
    close_3yr = get_next_trading_close(symbol, three_year_date)
    if close_3yr is not None and close_to is not None:
        three_year_cagr = (((close_to / close_3yr) ** (1 / 3)) - 1) * 100

    return ptp_return, one_year_return, three_year_cagr


def get_top5_amt_financed(
    to_date: str, top_n: int = 5, industries: list = None, from_date: str = None
):
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

    ffmc_list = []
    exposure_pct_list = []
    ptp_return_list = []
    one_year_return_list = []
    three_year_cagr_list = []

    for _, row in df.iterrows():
        ffmc_lakhs, exposure_pct = get_ffmc_and_exposure(row, "amt_financed")
        ffmc_list.append(ffmc_lakhs)
        exposure_pct_list.append(exposure_pct)

        ptp_return, one_year_return, three_year_cagr = calculate_returns(
            row["symbol"], to_date, from_date
        )
        ptp_return_list.append(ptp_return)
        one_year_return_list.append(one_year_return)
        three_year_cagr_list.append(three_year_cagr)

    df["Free Float Market Cap (₹ Lakhs)"] = ffmc_list
    df["Exposure (%)"] = exposure_pct_list
    df["Point-to-Point Return (%)"] = ptp_return_list
    df["1yr Return (%)"] = one_year_return_list
    df["3yr Return (%) (CAGR)"] = three_year_cagr_list

    # Return the full DataFrame with all columns
    return df


def get_top5_amt_financed_pct_change(
    from_date: str, to_date: str, top_n: int = 5, industries: list = None
):
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
                conn,
                params=(from_date, *industries),
            )
            df_to = pd.read_sql_query(
                f"""SELECT s.symbol, s.amt_financed
                    FROM stock_data s
                    JOIN stock_master m ON s.symbol = m.symbol
                    WHERE s.date = ? AND s.amt_financed >= 50 AND m.industry IN ({placeholders})""",
                conn,
                params=(to_date, *industries),
            )
        else:
            df_from = pd.read_sql_query(
                "SELECT symbol, amt_financed FROM stock_data WHERE date = ? AND amt_financed != 0",
                conn,
                params=(from_date,),
            )
            df_to = pd.read_sql_query(
                "SELECT symbol, amt_financed FROM stock_data WHERE date = ? AND amt_financed >= 50",
                conn,
                params=(to_date,),
            )
        df = pd.merge(df_from, df_to, on="symbol", suffixes=("_from", "_to"))
        df["pct_change"] = (
            (df["amt_financed_to"] - df["amt_financed_from"]) / df["amt_financed_from"]
        ) * 100
        df_master = pd.read_sql_query(
            "SELECT symbol, name, industry FROM stock_master", conn
        )
        df = pd.merge(df, df_master, on="symbol")
        df = df.sort_values("pct_change", ascending=False).head(top_n)

    ffmc_list = []
    exposure_pct_list = []
    ptp_return_list = []
    one_year_return_list = []
    three_year_cagr_list = []
    for _, row in df.iterrows():
        # Use amt_financed_to for ffmc/exposure
        ffmc_lakhs, exposure_pct = get_ffmc_and_exposure(row, "amt_financed_to")
        ffmc_list.append(ffmc_lakhs)
        exposure_pct_list.append(exposure_pct)

        # Use symbol and to_date for returns
        ptp_return, one_year_return, three_year_cagr = calculate_returns(
            row["symbol"], to_date, from_date
        )
        ptp_return_list.append(ptp_return)
        one_year_return_list.append(one_year_return)
        three_year_cagr_list.append(three_year_cagr)

    df["Free Float Market Cap (₹ Lakhs)"] = ffmc_list
    df["Exposure (%)"] = exposure_pct_list
    df["Point-to-Point Return (%)"] = ptp_return_list
    df["1yr Return (%)"] = one_year_return_list
    df["3yr Return (%) (CAGR)"] = three_year_cagr_list

    # Return the full DataFrame with all columns
    return df


def get_newly_added_stocks(from_date: str, to_date: str, industries: list = None):
    """
    Return all stocks that are newly added in MTF from from_date to to_date.
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
                conn,
                params=(to_date, *industries),
            )
            df_from = pd.read_sql_query(
                f"""SELECT s.symbol, s.amt_financed
                    FROM stock_data s
                    JOIN stock_master m ON s.symbol = m.symbol
                    WHERE s.date = ? AND m.industry IN ({placeholders})""",
                conn,
                params=(from_date, *industries),
            )
        else:
            df_to = pd.read_sql_query(
                "SELECT symbol, amt_financed FROM stock_data WHERE date = ?",
                conn,
                params=(to_date,),
            )
            df_from = pd.read_sql_query(
                "SELECT symbol, amt_financed FROM stock_data WHERE date = ?",
                conn,
                params=(from_date,),
            )
        new_symbols = set(df_to["symbol"]) - set(df_from["symbol"])
        df_new = df_to[df_to["symbol"].isin(new_symbols)].copy()
        df_new["amt_financed_from"] = 0
        df_master = pd.read_sql_query(
            "SELECT symbol, name, industry FROM stock_master", conn
        )
        df_new = pd.merge(df_new, df_master, on="symbol")
        df_new = df_new.rename(columns={"amt_financed": "amt_financed_to"})

        ffmc_list = []
        exposure_pct_list = []
        ptp_return_list = []
        one_year_return_list = []
        three_year_cagr_list = []
        for idx, row in df_new.iterrows():
            print(f"Processing newly added symbol: {row['symbol']} ({row['name']})")
            ffmc_lakhs, exposure_pct = get_ffmc_and_exposure(row, "amt_financed_to")
            ffmc_list.append(ffmc_lakhs)
            exposure_pct_list.append(exposure_pct)

            # ptp_return, one_year_return, three_year_cagr = calculate_returns(row['symbol'], to_date, from_date)
            # ptp_return_list.append(ptp_return)
            # one_year_return_list.append(one_year_return)
            # three_year_cagr_list.append(three_year_cagr)
        # Assign columns before sorting and selecting columns
        df_new["Free Float Market Cap (₹ Lakhs)"] = (
            ffmc_list if len(df_new) == len(ffmc_list) else [None] * len(df_new)
        )
        df_new["Exposure (%)"] = (
            exposure_pct_list
            if len(df_new) == len(exposure_pct_list)
            else [None] * len(df_new)
        )
        df_new["Point-to-Point Return (%)"] = (
            ptp_return_list
            if len(df_new) == len(ptp_return_list)
            else [None] * len(df_new)
        )
        df_new["1yr Return (%)"] = (
            one_year_return_list
            if len(df_new) == len(one_year_return_list)
            else [None] * len(df_new)
        )
        df_new["3yr Return (%) (CAGR)"] = (
            three_year_cagr_list
            if len(df_new) == len(three_year_cagr_list)
            else [None] * len(df_new)
        )
        # Do not sort or filter by top_n, return all
        return df_new


def get_top_exposure_stocks(to_date: str, top_n: int = 5, industries: list = None):
    """
    Return top N stocks by exposure % (amt_financed / ffmc) on to_date.
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

    ffmc_list = []
    exposure_pct_list = []

    for _, row in df.iterrows():
        ffmc_lakhs, exposure_pct = get_ffmc_and_exposure(row, "amt_financed")
        ffmc_list.append(ffmc_lakhs)
        exposure_pct_list.append(exposure_pct)

    df["Free Float Market Cap (₹ Lakhs)"] = ffmc_list
    df["Exposure (%)"] = exposure_pct_list

    df = df.dropna(subset=["Exposure (%)"])
    df = df.sort_values("Exposure (%)", ascending=False).head(top_n)

    # Only keep relevant columns
    return df[
        [
            "symbol",
            "name",
            "industry",
            "amt_financed",
            "Free Float Market Cap (₹ Lakhs)",
            "Exposure (%)",
        ]
    ]


__all__ = [
    "DB_PATH",
    "download_and_store_range",
    "get_next_available_date",
    "get_prev_available_date",
    "get_top5_amt_financed",
    "get_top5_amt_financed_pct_change",
    "get_newly_added_stocks",
    "get_top_exposure_stocks",
    "create_table",
]


def get_next_available_date(target_date):
    """Return the earliest date >= target_date present in stock_data table as YYYY-MM-DD string, or None if not found."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT MIN(date) FROM stock_data WHERE date >= ?",
            (target_date.strftime("%Y-%m-%d"),),
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    return None


def get_prev_available_date(target_date):
    """Return the latest date <= target_date present in stock_data table as YYYY-MM-DD string, or None if not found."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT MAX(date) FROM stock_data WHERE date <= ?",
            (target_date.strftime("%Y-%m-%d"),),
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    return None


def get_next_trading_close(symbol, target_date):
    """Return closing price for the next available trading day >= target_date."""
    max_tries = 15
    for i in range(max_tries):
        d = target_date + timedelta(days=i)
        try:
            # Fetch historical data for the symbol
            hist = nse.fetch_equity_historical_data(symbol, from_date=d, to_date=d)
            if hist and "CH_CLOSING_PRICE" in hist[0]:
                try:
                    return float(hist[0]["CH_CLOSING_PRICE"])
                except Exception:
                    continue
        except Exception as e:
            print(f"Error fetching next trading close for {symbol} on {d}: {e}")
            return None
    return None


def get_ffmc_and_exposure(row, amt_field):
    """
    Returns (ffmc_lakhs, exposure_pct) for a given row and amount field.
    """
    try:
        q = nse.quote(row["symbol"], section="trade_info")
        ffmc = q.get("marketDeptOrderBook", {}).get("tradeInfo", {}).get("ffmc", None)
        ffmc_lakhs = ffmc * 100 if ffmc is not None else None
        exposure_pct = (row[amt_field] / ffmc_lakhs) * 100 if ffmc_lakhs else None
    except Exception:
        ffmc_lakhs = None
        exposure_pct = None
    return ffmc_lakhs, exposure_pct


if __name__ == "__main__":
    pass
