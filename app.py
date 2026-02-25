import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
import requests
from mtfck.db import get_connection, close_connection
from mtfck.mtfck import (
    get_next_available_date,
    get_prev_available_date,
    get_top5_amt_financed,
    get_top5_amt_financed_pct_change,
    get_newly_added_stocks,
    get_top_exposure_stocks,
    nse,
    calculate_returns,
    get_ffmc_and_exposure,
    fetch_industry_data,
)
import plotly.graph_objects as go

def download_database():
    db_path = "mtf_data/stock_data.parquet"
    summary_path = "mtf_data/daily_summary.parquet"
    db_url = "https://github.com/eggmasonvalue/MTFDB/raw/main/stock_data.parquet"
    summary_url = "https://github.com/eggmasonvalue/MTFDB/raw/main/daily_summary.parquet"
    
    os.makedirs("mtf_data", exist_ok=True)
    
    with st.spinner("Downloading latest database from cloud..."):
        try:
            close_connection()
            r = requests.get(db_url, stream=True)
            r.raise_for_status()
            with open(db_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            r_summary = requests.get(summary_url, stream=True)
            r_summary.raise_for_status()
            with open(summary_path, "wb") as f:
                for chunk in r_summary.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            st.error(f"Failed to sync database: {e}")

# Auto-download on first load if missing
if not os.path.exists("mtf_data/stock_data.parquet"):
    download_database()

@st.cache_data(ttl=86400)
def get_cached_industry_data():
    """Fetch and cache industry mapping data for 24 hours."""
    return fetch_industry_data()


def get_available_dates():
    try:
        conn = get_connection()
        df = conn.sql("SELECT DISTINCT date FROM stock_data ORDER BY date").df()
        return pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d").tolist()
    except Exception:
        return []


def get_unique_industries(industry_data):
    """Extract unique industries from the JSON dataset and format them for display."""
    industries = set()
    for _, details in industry_data.items():
        if isinstance(details, list) and len(details) > 0:
            # Create a 2-tier format using newlines. The CSS we inject will handle the wrapping.
            # details typically looks like: [Macro, Sector, Industry, Basic Industry]
            basic_industry = details[-1]
            hierarchy = " > ".join(details[:-1]) if len(details) > 1 else "Unknown"
            
            # Use upper case for emphasis on the first line
            formatted_string = f"{basic_industry.upper()}\n└ {hierarchy}"
            industries.add(formatted_string)
    return sorted(list(industries))


st.set_page_config(page_title="MTF Analytics Dashboard", layout="wide")
st.markdown(
    """
    <style>
    /* Make multiselect dropdown text wrap and support newlines */
    div[data-baseweb="select"] ul[role="listbox"] li {
        white-space: pre-wrap !important;
        word-break: break-word !important;
        line-height: 1.4 !important;
        padding-top: 8px !important;
        padding-bottom: 8px !important;
        border-bottom: 1px solid #f0f0f0;
    }
    </style>
    <h1 style='text-align: center; font-family: "Impact"; font-size: 3em; font-weight: bold; color: orange; margin-bottom: 0.5em; letter-spacing: 0.05em;'>
        MTFCK!
    </h1>
    """,
    unsafe_allow_html=True,
)

industry_data = get_cached_industry_data()

# --- Sidebar Controls ---
with st.sidebar:
    st.header("Database Sync")
    
    # Check sync status
    db_path = "mtf_data/stock_data.parquet"
    if os.path.exists(db_path):
        mtime = os.path.getmtime(db_path)
        last_synced = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %I:%M %p')
        st.caption(f"Last Synced: {last_synced}")
    else:
        st.caption("Database not downloaded yet.")

    sync_clicked = st.button("Sync Database from Cloud", width="stretch")
    if sync_clicked:
        download_database()
        st.rerun()

    st.markdown("---")
    st.header("Analysis Controls")
    
    dates = get_available_dates()
    if dates:
        min_date = min(dates)
        max_date = max(dates)
    else:
        min_date = max_date = date.today().strftime("%Y-%m-%d")
        
    from_date = st.date_input(
        "From Date",
        value=datetime.strptime(str(min_date), "%Y-%m-%d").date(),
        key="from_date",
    )
    to_date = st.date_input(
        "To Date", value=datetime.strptime(str(max_date), "%Y-%m-%d").date(), key="to_date"
    )
    
    top_n = st.slider(
        "Number of Top Stocks", min_value=5, max_value=50, value=5, step=1
    )
    
    industries = get_unique_industries(industry_data)
    selected_industries = st.multiselect(
        "Industry Filter (optional)", industries, default=[]
    )
    
    function = st.selectbox(
        "Analysis Type",
        [
            "Top by Amount Financed",
            "Top by % Change in Amount Financed",
            "Newly Added MTF Stocks",
            "Top by Exposure %",
        ],
    )
    if function == "Top by Exposure %" and not selected_industries:
        st.warning(
            "For Exposure % analysis, please choose one or more industry filters to avoid long load time."
        )
    run_analysis = st.button("Run Analysis", width="stretch")
    st.markdown("---")

    # --- Trends Section ---
    st.header("Trends")
    show_net_outstanding_clicked = st.button(
        "Show Total Outstanding Trend", key="net_outstanding_btn_sidebar"
    )
    trend_symbol_input = st.text_input(
        "Enter Symbol for Amount Financed Trend", key="trend_symbol_input"
    ).upper()
    show_trend_clicked = st.button(
        "Show Amount Financed Trend", key="trend_btn_sidebar"
    )

st.markdown(f"**Selected Range:** {from_date} to {to_date}")

# --- Trend Analysis Logic ---
def get_amt_financed_trend(symbol, from_date, to_date):
    conn = get_connection()
    df = conn.execute(
        "SELECT date, amt_financed FROM stock_data WHERE symbol = ? AND date BETWEEN ? AND ? ORDER BY date",
        (symbol, from_date, to_date)
    ).df()
    
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["amt_financed_cr"] = df["amt_financed"] / 100
    return df


# --- Analysis Output Section ---
if "last_range" not in st.session_state:
    st.session_state["last_range"] = {}
if "results" not in st.session_state:
    st.session_state["results"] = {}


def cache_key(function, from_date_db, to_date_db, top_n, selected_industries):
    industries_key = (
        ",".join(sorted(selected_industries)) if selected_industries else "ALL"
    )
    return f"{function}|{from_date_db}|{to_date_db}|{top_n}|{industries_key}"


from_date_db = get_next_available_date(from_date)
to_date_db = get_prev_available_date(to_date)

if not from_date_db or not to_date_db:
    st.warning("No data available for the selected range. Please sync the database.")
    st.stop()

if from_date_db and to_date_db:
    key = cache_key(function, from_date_db, to_date_db, top_n, selected_industries)
    current_range = (
        from_date_db,
        to_date_db,
        top_n,
        tuple(sorted(selected_industries)) if selected_industries else (),
    )
    last_range = st.session_state["last_range"].get(function)
    rerun_needed = (last_range != current_range) or (key not in st.session_state["results"])


# --- Always get the latest analysis result for the current controls ---
if run_analysis:
    if (
        rerun_needed
        or "analysis_df" not in st.session_state
        or st.session_state.get("analysis_key") != key
    ):
        if function == "Top by Amount Financed":
            df = get_top5_amt_financed(
                to_date_db, top_n, selected_industries, from_date_db, industry_data
            )
            df["Amount Financed (₹ Cr)"] = df["amt_financed"] / 100
            df["Free Float Market Cap (₹ Cr)"] = (
                df["Free Float Market Cap (₹ Lakhs)"] / 100
            )
            df = df.rename(
                columns={
                    "symbol": "Symbol",
                    "industry": "Industry",
                    "Exposure (%)": "Exposure (%)",
                }
            )
        elif function == "Top by % Change in Amount Financed":
            df = get_top5_amt_financed_pct_change(
                from_date_db, to_date_db, top_n, selected_industries, industry_data
            )
            df["Amount Financed Start (₹ Cr)"] = df["amt_financed_from"] / 100
            df["Amount Financed End (₹ Cr)"] = df["amt_financed_to"] / 100
            df["Free Float Market Cap (₹ Cr)"] = (
                df["Free Float Market Cap (₹ Lakhs)"] / 100
            )
            df = df.rename(
                columns={
                    "symbol": "Symbol",
                    "industry": "Industry",
                    "pct_change": "% Change",
                    "Exposure (%)": "Exposure (%)",
                }
            )
        elif function == "Newly Added MTF Stocks":
            df = get_newly_added_stocks(from_date_db, to_date_db, selected_industries, industry_data)
            df["Amount Financed Start (₹ Cr)"] = df["amt_financed_from"] / 100
            df["Amount Financed End (₹ Cr)"] = df["amt_financed_to"] / 100
            df["Free Float Market Cap (₹ Cr)"] = (
                df["Free Float Market Cap (₹ Lakhs)"] / 100
            )
            df = df.rename(
                columns={
                    "symbol": "Symbol",
                    "industry": "Industry",
                    "Exposure (%)": "Exposure (%)",
                }
            )
        elif function == "Top by Exposure %":
            df = get_top_exposure_stocks(to_date_db, top_n, selected_industries, industry_data)
            df["Amount Financed (₹ Cr)"] = df["amt_financed"] / 100
            df["Free Float Market Cap (₹ Cr)"] = (
                df["Free Float Market Cap (₹ Lakhs)"] / 100
            )
            df = df.rename(
                columns={
                    "symbol": "Symbol",
                    "industry": "Industry",
                    "Exposure (%)": "Exposure (%)",
                }
            )
        else:
            df = pd.DataFrame()
        st.session_state["analysis_df"] = df
        st.session_state["analysis_key"] = key
    else:
        df = st.session_state["analysis_df"]

    # --- Dropdown below graph, button below dropdown, then subheader, then table ---
    if function == "Top by Amount Financed":
        st.subheader(f"Top {top_n} Stocks by Amount Financed on {to_date_db}")
        st.dataframe(
            df[
                [
                    "Symbol",
                    "Industry",
                    "Amount Financed (₹ Cr)",
                    "Free Float Market Cap (₹ Cr)",
                    "Exposure (%)",
                    "1yr Return (%)",
                    "3yr Return (%) (CAGR)",
                    "Point-to-Point Return (%)",
                ]
            ],
            use_container_width=True,
        )

    elif function == "Top by % Change in Amount Financed":
        st.subheader(
            f"Top {top_n} Stocks by % Change in Amount Financed ({from_date_db} to {to_date_db})"
        )
        st.dataframe(
            df[
                [
                    "Symbol",
                    "Industry",
                    "Amount Financed Start (₹ Cr)",
                    "Amount Financed End (₹ Cr)",
                    "% Change",
                    "Free Float Market Cap (₹ Cr)",
                    "Exposure (%)",
                    "1yr Return (%)",
                    "3yr Return (%) (CAGR)",
                    "Point-to-Point Return (%)",
                ]
            ],
            use_container_width=True,
        )

    elif function == "Newly Added MTF Stocks":
        st.subheader(f"Newly Added MTF Stocks ({from_date_db} to {to_date_db})")
        st.dataframe(
            df[
                [
                    "Symbol",
                    "Industry",
                    "Amount Financed Start (₹ Cr)",
                    "Amount Financed End (₹ Cr)",
                    "Free Float Market Cap (₹ Cr)",
                    "Exposure (%)",
                    "1yr Return (%)",
                    "3yr Return (%) (CAGR)",
                    "Point-to-Point Return (%)",
                ]
            ],
            use_container_width=True,
        )
    elif function == "Top by Exposure %":
        st.subheader(f"Top {top_n} Stocks by Exposure % on {to_date_db}")
        st.dataframe(
            df[
                [
                    "Symbol",
                    "Industry",
                    "Amount Financed (₹ Cr)",
                    "Free Float Market Cap (₹ Cr)",
                    "Exposure (%)",
                ]
            ],
            use_container_width=True,
        )

# --- Trend Analysis Display ---
if show_trend_clicked:
    trend_df = get_amt_financed_trend(trend_symbol_input, from_date_db, to_date_db)
    if not trend_df.empty:
        ptp_return, one_year_return, three_year_cagr = None, None, None
        ffmc_lakhs, exposure_pct = None, None
        try:
            ptp_return, one_year_return, three_year_cagr = calculate_returns(
                trend_symbol_input, to_date_db, from_date_db
            )
            if not trend_df.empty:
                amt_field = "amt_financed"
                last_row = trend_df.iloc[-1]
                ffmc_lakhs, exposure_pct = get_ffmc_and_exposure(
                    {"symbol": trend_symbol_input, amt_field: last_row[amt_field]},
                    amt_field,
                )
        except Exception:
            ptp_return, one_year_return, three_year_cagr = None, None, None
            ffmc_lakhs, exposure_pct = None, None

        ffmc_cr = ffmc_lakhs / 100 if ffmc_lakhs is not None else None

        st.markdown(
            f"<div style='font-weight:bold;font-size:1.5em'>{trend_symbol_input}</div>",
            unsafe_allow_html=True,
        )

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.markdown(
            f"<b>Free Float Market Cap:</b><br>{ffmc_cr:.2f} Cr"
            if ffmc_cr is not None
            else "<b>Free Float Market Cap:</b><br>N/A",
            unsafe_allow_html=True,
        )
        col2.markdown(
            f"<b>Exposure (%):</b><br>{exposure_pct:.2f}%"
            if exposure_pct is not None
            else "<b>Exposure (%):</b><br>N/A",
            unsafe_allow_html=True,
        )
        col3.markdown(
            f"<b>P2P Return:</b><br>{ptp_return:.2f}%"
            if ptp_return is not None
            else "<b>P2P Return:</b><br>N/A",
            unsafe_allow_html=True,
        )
        col4.markdown(
            f"<b>1yr Return:</b><br>{one_year_return:.2f}%"
            if one_year_return is not None
            else "<b>1yr Return:</b><br>N/A",
            unsafe_allow_html=True,
        )
        col5.markdown(
            f"<b>3yr CAGR:</b><br>{three_year_cagr:.2f}%"
            if three_year_cagr is not None
            else "<b>3yr CAGR:</b><br>N/A",
            unsafe_allow_html=True,
        )

        trend_df["pct_change"] = trend_df["amt_financed_cr"].pct_change() * 100
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=trend_df["date"],
                y=trend_df["amt_financed_cr"],
                mode="lines+markers",
                name="Amount Financed (₹ Cr)",
                line=dict(color="blue", width=2),
                hovertemplate="<b>Date:</b> %{x}<br><b>Amount Financed:</b> ₹%{y:.2f} Cr<br><b>% Change:</b> %{customdata:.2f}%",
                customdata=trend_df["pct_change"],
            )
        )

        price_data = []
        curr_from = pd.to_datetime(from_date_db).date()
        end_to = pd.to_datetime(to_date_db).date()
        while curr_from <= end_to:
            curr_to = min(curr_from + timedelta(days=90), end_to)
            try:
                chunk = nse.fetch_equity_historical_data(
                    trend_symbol_input,
                    from_date=curr_from,
                    to_date=curr_to,
                )
                if isinstance(chunk, list):
                    price_data.extend(chunk)
            except Exception:
                pass
            curr_from = curr_to + timedelta(days=1)

        if price_data:
            price_df = pd.DataFrame(price_data)
            timestamp_col = "mtimestamp" if "mtimestamp" in price_df.columns else "CH_TIMESTAMP"
            closing_col = "chClosingPrice" if "chClosingPrice" in price_df.columns else "CH_CLOSING_PRICE"

            if timestamp_col in price_df.columns and closing_col in price_df.columns:
                price_df["date"] = pd.to_datetime(
                    price_df[timestamp_col], errors="coerce"
                )
                price_df = price_df.sort_values("date")
                price_df["pct_change"] = price_df[closing_col].pct_change() * 100
                fig.add_trace(
                    go.Scatter(
                        x=price_df["date"],
                        y=price_df[closing_col],
                        mode="lines+markers",
                        name="Closing Price",
                        line=dict(color="orange", width=2, dash="dot"),
                        yaxis="y2",
                        hovertemplate="<b>Date:</b> %{x}<br><b>Closing Price:</b> ₹%{y:.2f}<br><b>% Change:</b> %{customdata:.2f}%",
                        customdata=price_df["pct_change"],
                    )
                )
            fig.update_layout(
                yaxis2=dict(
                    title="Closing Price (₹)",
                    overlaying="y",
                    side="right",
                    showgrid=False,
                )
            )

        fig.update_layout(
            title=f"Amount Financed Trend for {trend_symbol_input}",
            xaxis_title="Date",
            yaxis_title="Amount Financed (₹ Cr)",
            xaxis_range=[trend_df["date"].min(), trend_df["date"].max()],
            yaxis_range=[
                trend_df["amt_financed_cr"].min(),
                trend_df["amt_financed_cr"].max(),
            ],
            width=800,
            height=400,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.subheader(
            f"No trend data available for {trend_symbol_input} in the selected range."
        )

# --- Net Outstanding Trend Display ---
if show_net_outstanding_clicked:
    conn = get_connection()
    df_chart = conn.sql(
        "SELECT date, net_outstanding_end FROM daily_summary ORDER BY date"
    ).df()
    
    if not df_chart.empty:
        df_chart["date"] = pd.to_datetime(df_chart["date"])
        df_chart["net_outstanding_end_cr"] = df_chart["net_outstanding_end"] / 100
        df_chart["pct_change"] = df_chart["net_outstanding_end_cr"].pct_change() * 100

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df_chart["date"],
                y=df_chart["net_outstanding_end_cr"],
                mode="lines+markers",
                name="Net Outstanding End (₹ Cr)",
                line=dict(color="green", width=2),
                hovertemplate="<b>Date:</b> %{x}<br><b>Net Outstanding:</b> ₹%{y:.2f} Cr<br><b>% Change:</b> %{customdata:.2f}%",
                customdata=df_chart["pct_change"],
            )
        )

        price_list = []
        try:
            curr_from = pd.to_datetime(df_chart["date"].min()).date()
            end_to = pd.to_datetime(df_chart["date"].max()).date()
            while curr_from <= end_to:
                curr_to = min(curr_from + timedelta(days=90), end_to)
                chunk = nse.fetch_historical_index_data(
                    index="NIFTY TOTAL MARKET",
                    from_date=curr_from,
                    to_date=curr_to,
                )
                if isinstance(chunk, list):
                    price_list.extend(chunk)
                curr_from = curr_to + timedelta(days=1)
        except Exception as e:
            print(f"Error fetching index data: {e}")

        price_df = pd.DataFrame(price_list)
        if not price_df.empty and "EOD_CLOSE_INDEX_VAL" in price_df.columns:
            timestamp_col = (
                "EOD_TIMESTAMP" if "EOD_TIMESTAMP" in price_df.columns else "mTIMESTAMP"
            )

            if timestamp_col in price_df.columns:
                price_df["date"] = pd.to_datetime(
                    price_df[timestamp_col], format="%d-%b-%Y", errors="coerce"
                )
                price_df = price_df.sort_values("date")
                price_df["pct_change"] = (
                    price_df["EOD_CLOSE_INDEX_VAL"].pct_change() * 100
                )
                fig.add_trace(
                    go.Scatter(
                        x=price_df["date"],
                        y=price_df["EOD_CLOSE_INDEX_VAL"],
                        mode="lines+markers",
                        name="NIFTY TOTAL MARKET",
                        line=dict(color="blue", width=2, dash="dot"),
                        yaxis="y2",
                        hovertemplate="<b>Date:</b> %{x}<br><b>Index Close:</b> %{y:.2f}<br><b>% Change:</b> %{customdata:.2f}%",
                        customdata=price_df["pct_change"],
                    )
                )
            fig.update_layout(
                yaxis2=dict(
                    title="NIFTY TOTAL MARKET Close",
                    overlaying="y",
                    side="right",
                    showgrid=False,
                )
            )

        fig.update_layout(
            title="Net Outstanding End (Daily Trend)",
            xaxis_title="Date",
            yaxis_title="Net Outstanding End (₹ Cr)",
            xaxis_range=[df_chart["date"].min(), df_chart["date"].max()],
            yaxis_range=[
                df_chart["net_outstanding_end_cr"].min(),
                df_chart["net_outstanding_end_cr"].max(),
            ],
            width=800,
            height=400,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No summary data found.")

st.caption("NSE MTF Analytics Dashboard - Powered by Caffeine and Copilot")
