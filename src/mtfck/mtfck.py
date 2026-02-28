from datetime import timedelta
from nse import NSE
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import requests
from .ingestion import create_table, download_and_store_range
from .db import get_connection, DB_PATH
from .utils import retry_request

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

nse = NSE(download_folder=DATA_DIR, server=True)


@retry_request()
def _fetch_industry_data_unsafe() -> dict:
    """Fetch the latest industry mapping JSON from GitHub (may raise exception)."""
    url = "https://raw.githubusercontent.com/eggmasonvalue/stock-industry-map-in/main/out/industry_data.json"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json().get("data", {})


def fetch_industry_data() -> dict:
    """Fetch the latest industry mapping JSON from GitHub."""
    try:
        return _fetch_industry_data_unsafe()
    except Exception as e:
        print(f"Error fetching industry data after retries: {e}")
        return {}


def plot_net_outstanding_end():
    """Fetch daily_summary and plot net_outstanding_end for each day."""
    conn = get_connection()
    try:
        df = conn.sql(
            "SELECT date, net_outstanding_end FROM daily_summary ORDER BY date"
        ).df()
    except Exception:
        df = pd.DataFrame()

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

    if from_date:
        close_from = get_next_trading_close(symbol, pd.to_datetime(from_date).date())
        if close_from is not None and close_to is not None:
            ptp_return = ((close_to - close_from) / close_from) * 100

    one_year_date = (pd.to_datetime(to_date) - timedelta(days=365)).date()
    close_1yr = get_next_trading_close(symbol, one_year_date)
    if close_1yr is not None and close_to is not None:
        one_year_return = ((close_to - close_1yr) / close_1yr) * 100

    three_year_date = (pd.to_datetime(to_date) - timedelta(days=3 * 365)).date()
    close_3yr = get_next_trading_close(symbol, three_year_date)
    if close_3yr is not None and close_to is not None:
        three_year_cagr = (((close_to / close_3yr) ** (1 / 3)) - 1) * 100

    return ptp_return, one_year_return, three_year_cagr


def _apply_industry(df: pd.DataFrame, industry_data: dict) -> pd.DataFrame:
    padding = chr(160) * 80
    if not df.empty and "symbol" in df.columns:
        df["industry_path"] = df["symbol"].apply(
            lambda x: f"{industry_data.get(x)[-1]}{padding}[{' > '.join(industry_data.get(x)[:-1]) if len(industry_data.get(x)) > 1 else 'Unknown'}]"
            if isinstance(industry_data.get(x), list) and len(industry_data.get(x)) > 0 else "Unknown"
        )
        df["industry"] = df["symbol"].apply(
            lambda x: industry_data.get(x)[-1] if isinstance(industry_data.get(x), list) and len(industry_data.get(x)) > 0 else "Unknown"
        )
    else:
        df["industry"] = pd.Series(dtype=str)
        df["industry_path"] = pd.Series(dtype=str)
    return df


def get_top5_amt_financed(
    to_date: str, top_n: int = 5, industries: list = None, from_date: str = None, industry_data: dict = None
):
    """
    Return top N stocks by amt_financed on to_date.
    """
    conn = get_connection()
    query = "SELECT symbol, amt_financed FROM stock_data WHERE date = ?"
    df = conn.execute(query, (to_date,)).df()

    if industry_data:
        df = _apply_industry(df, industry_data)
    else:
        df["industry"] = "Unknown"
        df["industry_path"] = "Unknown"

    if industries:
        df = df[df["industry_path"].isin(industries)]

    df = df.sort_values("amt_financed", ascending=False).head(top_n)

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

    return df


def get_top5_amt_financed_pct_change(
    from_date: str, to_date: str, top_n: int = 5, industries: list = None, industry_data: dict = None
):
    """
    Return top N stocks by percentage change in amt_financed between from_date and to_date.
    """
    conn = get_connection()

    df_from = conn.execute(
        "SELECT symbol, amt_financed FROM stock_data WHERE date = ? AND amt_financed != 0",
        (from_date,)
    ).df()
    df_to = conn.execute(
        "SELECT symbol, amt_financed FROM stock_data WHERE date = ? AND amt_financed >= 50",
        (to_date,)
    ).df()

    df = pd.merge(df_from, df_to, on="symbol", suffixes=("_from", "_to"))
    df["pct_change"] = ((df["amt_financed_to"] - df["amt_financed_from"]) / df["amt_financed_from"]) * 100

    if industry_data:
        df = _apply_industry(df, industry_data)
    else:
        df["industry"] = "Unknown"
        df["industry_path"] = "Unknown"

    if industries:
        df = df[df["industry_path"].isin(industries)]

    df = df.sort_values("pct_change", ascending=False).head(top_n)

    ffmc_list = []
    exposure_pct_list = []
    ptp_return_list = []
    one_year_return_list = []
    three_year_cagr_list = []

    for _, row in df.iterrows():
        ffmc_lakhs, exposure_pct = get_ffmc_and_exposure(row, "amt_financed_to")
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

    return df


def get_newly_added_stocks(from_date: str, to_date: str, industries: list = None, industry_data: dict = None):
    """
    Return all stocks that are newly added in MTF from from_date to to_date.
    """
    conn = get_connection()
    df_to = conn.execute(
        "SELECT symbol, amt_financed FROM stock_data WHERE date = ?",
        (to_date,)
    ).df()
    df_from = conn.execute(
        "SELECT symbol, amt_financed FROM stock_data WHERE date = ?",
        (from_date,)
    ).df()

    new_symbols = set(df_to["symbol"]) - set(df_from["symbol"])
    df_new = df_to[df_to["symbol"].isin(new_symbols)].copy()
    df_new["amt_financed_from"] = 0
    df_new = df_new.rename(columns={"amt_financed": "amt_financed_to"})

    if industry_data:
        df_new = _apply_industry(df_new, industry_data)
    else:
        df_new["industry"] = "Unknown"
        df_new["industry_path"] = "Unknown"

    if industries:
        df_new = df_new[df_new["industry_path"].isin(industries)]

    ffmc_list = []
    exposure_pct_list = []
    ptp_return_list = []
    one_year_return_list = []
    three_year_cagr_list = []

    for idx, row in df_new.iterrows():
        print(f"Processing newly added symbol: {row['symbol']}")
        ffmc_lakhs, exposure_pct = get_ffmc_and_exposure(row, "amt_financed_to")
        ffmc_list.append(ffmc_lakhs)
        exposure_pct_list.append(exposure_pct)

        ptp_return, one_year_return, three_year_cagr = calculate_returns(
            row["symbol"], to_date, from_date
        )
        ptp_return_list.append(ptp_return)
        one_year_return_list.append(one_year_return)
        three_year_cagr_list.append(three_year_cagr)

    df_new["Free Float Market Cap (₹ Lakhs)"] = ffmc_list if len(df_new) == len(ffmc_list) else [None] * len(df_new)
    df_new["Exposure (%)"] = exposure_pct_list if len(df_new) == len(exposure_pct_list) else [None] * len(df_new)
    df_new["Point-to-Point Return (%)"] = ptp_return_list if len(df_new) == len(ptp_return_list) else [None] * len(df_new)
    df_new["1yr Return (%)"] = one_year_return_list if len(df_new) == len(one_year_return_list) else [None] * len(df_new)
    df_new["3yr Return (%) (CAGR)"] = three_year_cagr_list if len(df_new) == len(three_year_cagr_list) else [None] * len(df_new)

    return df_new


def get_top_exposure_stocks(to_date: str, top_n: int = 5, industries: list = None, industry_data: dict = None):
    """
    Return top N stocks by exposure % (amt_financed / ffmc) on to_date.
    """
    conn = get_connection()
    df = conn.execute(
        "SELECT symbol, amt_financed FROM stock_data WHERE date = ?",
        (to_date,)
    ).df()

    if industry_data:
        df = _apply_industry(df, industry_data)
    else:
        df["industry"] = "Unknown"
        df["industry_path"] = "Unknown"

    if industries:
        df = df[df["industry_path"].isin(industries)]

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

    return df[
        [
            "symbol",
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
    "fetch_industry_data",
]


def get_next_available_date(target_date):
    """Return the earliest date >= target_date present in stock_data table."""
    conn = get_connection()
    res = conn.execute(
        "SELECT MIN(date) FROM stock_data WHERE date >= ?",
        (target_date.strftime("%Y-%m-%d"),),
    ).fetchone()
    if res and res[0]:
        return res[0]
    return None


def get_prev_available_date(target_date):
    """Return the latest date <= target_date present in stock_data table."""
    conn = get_connection()
    res = conn.execute(
        "SELECT MAX(date) FROM stock_data WHERE date <= ?",
        (target_date.strftime("%Y-%m-%d"),),
    ).fetchone()
    if res and res[0]:
        return res[0]
    return None


@retry_request()
def _fetch_equity_historical_data_with_retry(symbol, from_date, to_date):
    """Fetch equity historical data with retry."""
    return nse.fetch_equity_historical_data(symbol, from_date=from_date, to_date=to_date)


def get_next_trading_close(symbol, target_date):
    """Return closing price for the next available trading day >= target_date."""
    max_tries = 15
    for i in range(max_tries):
        d = target_date + timedelta(days=i)
        try:
            hist = _fetch_equity_historical_data_with_retry(symbol, from_date=d, to_date=d)
            if hist and "chClosingPrice" in hist[0]:
                try:
                    return float(hist[0]["chClosingPrice"])
                except Exception:
                    continue
        except Exception as e:
            # If we hit an exception here, it means the retry decorator exhausted its attempts.
            # This likely indicates a persistent network failure or API issue.
            # We log it and stop trying subsequent days to avoid a long hang.
            print(f"Failed to fetch historical data for {symbol} on {d} after retries: {e}")
            break

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
