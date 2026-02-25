from datetime import timedelta
from nse import NSE
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from .ingestion import create_table, download_and_store_range
from .db import get_connection, DB_PATH

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
SCHEMA_PATH = "./db/schema.sql"

# Note: download_folder is set to DATA_DIR to match ingestion.py
nse = NSE(download_folder=DATA_DIR)


def plot_net_outstanding_end():
    """Fetch daily_summary and plot net_outstanding_end for each day."""
    conn = get_connection()
    try:
        df = conn.sql(
            "SELECT date, net_outstanding_end FROM daily_summary ORDER BY date"
        ).df()
    except Exception:
        df = pd.DataFrame() # Handle table not exists or empty
        
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
    conn = get_connection()
    if industries:
        placeholders = ",".join(f"'{ind}'" for ind in industries) 
        query = f"""
            SELECT m.symbol, m.name, m.industry, s.amt_financed
            FROM stock_data s
            JOIN stock_master m ON s.stock_id = m.stock_id
            WHERE s.date = ? AND m.industry IN ({placeholders})
            ORDER BY s.amt_financed DESC
            LIMIT ?
        """
        params = (to_date, top_n)
    else:
        query = """
            SELECT m.symbol, m.name, m.industry, s.amt_financed
            FROM stock_data s
            JOIN stock_master m ON s.stock_id = m.stock_id
            WHERE s.date = ?
            ORDER BY s.amt_financed DESC
            LIMIT ?
        """
        params = (to_date, top_n)
    
    # duckdb execute requires a list/tuple for params
    df = conn.execute(query, params).df()

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
    conn = get_connection()
    if industries:
        placeholders = ",".join(f"'{ind}'" for ind in industries)
        
        # Using f-strings for industries for now as DuckDB python api doesn't always handle IN list params smoothly across versions
        df_from = conn.execute(
            f"""SELECT m.symbol, s.amt_financed
                FROM stock_data s
                JOIN stock_master m ON s.stock_id = m.stock_id
                WHERE s.date = ? AND s.amt_financed != 0 AND m.industry IN ({placeholders})""",
            (from_date,)
        ).df()
        df_to = conn.execute(
            f"""SELECT m.symbol, s.amt_financed
                FROM stock_data s
                JOIN stock_master m ON s.stock_id = m.stock_id
                WHERE s.date = ? AND s.amt_financed >= 50 AND m.industry IN ({placeholders})""",
            (to_date,)
        ).df()
    else:
        df_from = conn.execute(
            """SELECT m.symbol, s.amt_financed
               FROM stock_data s
               JOIN stock_master m ON s.stock_id = m.stock_id
               WHERE s.date = ? AND s.amt_financed != 0""",
            (from_date,)
        ).df()
        df_to = conn.execute(
            """SELECT m.symbol, s.amt_financed
               FROM stock_data s
               JOIN stock_master m ON s.stock_id = m.stock_id
               WHERE s.date = ? AND s.amt_financed >= 50""",
            (to_date,)
        ).df()
    
    df = pd.merge(df_from, df_to, on="symbol", suffixes=("_from", "_to"))
    df["pct_change"] = (
        (df["amt_financed_to"] - df["amt_financed_from"]) / df["amt_financed_from"]
    ) * 100
    
    df_master = conn.execute("SELECT symbol, name, industry FROM stock_master").df()
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
    conn = get_connection()
    if industries:
        placeholders = ",".join(f"'{ind}'" for ind in industries)
        df_to = conn.execute(
            f"""SELECT m.symbol, s.amt_financed
                FROM stock_data s
                JOIN stock_master m ON s.stock_id = m.stock_id
                WHERE s.date = ? AND m.industry IN ({placeholders})""",
            (to_date,)
        ).df()
        df_from = conn.execute(
            f"""SELECT m.symbol, s.amt_financed
                FROM stock_data s
                JOIN stock_master m ON s.stock_id = m.stock_id
                WHERE s.date = ? AND m.industry IN ({placeholders})""",
            (from_date,)
        ).df()
    else:
        df_to = conn.execute(
            """SELECT m.symbol, s.amt_financed
               FROM stock_data s
               JOIN stock_master m ON s.stock_id = m.stock_id
               WHERE s.date = ?""",
            (to_date,)
        ).df()
        df_from = conn.execute(
            """SELECT m.symbol, s.amt_financed
               FROM stock_data s
               JOIN stock_master m ON s.stock_id = m.stock_id
               WHERE s.date = ?""",
            (from_date,)
        ).df()
        
    new_symbols = set(df_to["symbol"]) - set(df_from["symbol"])
    df_new = df_to[df_to["symbol"].isin(new_symbols)].copy()
    df_new["amt_financed_from"] = 0
    
    df_master = conn.execute("SELECT symbol, name, industry FROM stock_master").df()
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

        ptp_return, one_year_return, three_year_cagr = calculate_returns(
            row["symbol"], to_date, from_date
        )
        ptp_return_list.append(ptp_return)
        one_year_return_list.append(one_year_return)
        three_year_cagr_list.append(three_year_cagr)
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
    conn = get_connection()
    if industries:
        placeholders = ",".join(f"'{ind}'" for ind in industries)
        query = f"""
            SELECT m.symbol, m.name, m.industry, s.amt_financed
            FROM stock_data s
            JOIN stock_master m ON s.stock_id = m.stock_id
            WHERE s.date = ? AND m.industry IN ({placeholders})
        """
        params = (to_date,)
    else:
        query = """
            SELECT m.symbol, m.name, m.industry, s.amt_financed
            FROM stock_data s
            JOIN stock_master m ON s.stock_id = m.stock_id
            WHERE s.date = ?
        """
        params = (to_date,)
    
    df = conn.execute(query, params).df()

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
    conn = get_connection()
    res = conn.execute(
        "SELECT MIN(date) FROM stock_data WHERE date >= ?",
        (target_date.strftime("%Y-%m-%d"),),
    ).fetchone()
    if res and res[0]:
        return res[0] # Returns date object
    return None


def get_prev_available_date(target_date):
    """Return the latest date <= target_date present in stock_data table as YYYY-MM-DD string, or None if not found."""
    conn = get_connection()
    res = conn.execute(
        "SELECT MAX(date) FROM stock_data WHERE date <= ?",
        (target_date.strftime("%Y-%m-%d"),),
    ).fetchone()
    if res and res[0]:
        return res[0] # Returns date object
    return None


def get_next_trading_close(symbol, target_date):
    """Return closing price for the next available trading day >= target_date."""
    max_tries = 15
    for i in range(max_tries):
        d = target_date + timedelta(days=i)
        try:
            # Fetch historical data for the symbol
            hist = nse.fetch_equity_historical_data(symbol, from_date=d, to_date=d)
            if hist and "chClosingPrice" in hist[0]:
                try:
                    return float(hist[0]["chClosingPrice"])
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
