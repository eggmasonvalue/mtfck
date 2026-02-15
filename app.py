import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

import streamlit as st
import pandas as pd
# import sqlite3  <-- Removed
from datetime import datetime, date
from mtfck.db import get_connection  # Used for direct DB access
from mtfck.mtfck import (
    DB_PATH,
    download_and_store_range,
    get_next_available_date,
    get_prev_available_date,
    get_top5_amt_financed,
    get_top5_amt_financed_pct_change,
    get_newly_added_stocks,
    get_top_exposure_stocks,
    create_table,
    nse,
    calculate_returns,
    get_ffmc_and_exposure,
    migrate_legacy_data,
)
import plotly.graph_objects as go

# Ensure DB and tables exist
create_table()
# Try auto-migration of legacy data
try:
    migrate_legacy_data()
except Exception as e:
    st.error(f"Migration Error: {e}")


def get_available_dates():
    try:
        conn = get_connection()
        # DuckDB read_sql_query works, or we can use conn.sql().df()
        df = conn.sql("SELECT DISTINCT date FROM stock_data ORDER BY date").df()
        # Ensure we return strings in YYYY-MM-DD format to avoid timestamp issues
        return pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d").tolist()
    except Exception:
        return []


def get_unique_industries():
    try:
        conn = get_connection()
        df = conn.sql(
            "SELECT DISTINCT industry FROM stock_master WHERE industry IS NOT NULL AND industry != '' ORDER BY industry"
        ).df()
        return df["industry"].dropna().tolist()
    except Exception:
        return []


st.set_page_config(page_title="MTF Analytics Dashboard", layout="wide")
st.markdown(
    """
    <h1 style='text-align: center; font-family: "Impact"; font-size: 3em; font-weight: bold; color: orange; margin-bottom: 0.5em; letter-spacing: 0.05em;'>
        MTFCK!
    </h1>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar Controls ---
with st.sidebar:
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
    fetch_clicked = st.button(
        "Fetch/Update Data for Selected Range", use_container_width=True
    )
    # Change top_n from selectbox to slider
    top_n = st.slider(
        "Number of Top Stocks", min_value=5, max_value=50, value=5, step=1
    )
    industries = get_unique_industries()
    selected_industries = st.multiselect(
        "Industry Filter (optional)", industries, default=[]
    )
    function = st.selectbox(
        "Analysis Type",
        [
            "Top by Amount Financed",
            "Top by % Change in Amount Financed",
            "Newly Added MTF Stocks",
            "Top by Exposure %",  # <-- add new option
        ],
    )
    # Add warning if exposure % selected and no industry filter
    if function == "Top by Exposure %" and not selected_industries:
        st.warning(
            "For Exposure % analysis, please choose one or more industry filters to avoid long load time."
        )
    run_analysis = st.button("Run Analysis", use_container_width=True)
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


# --- Data Fetch Logic ---
def ensure_data_in_db(from_date, to_date):
    conn = get_connection()
    # DuckDB returns None if table doesn't exist or empty, need to handle gracefully
    try:
        row = conn.execute("SELECT MIN(date), MAX(date) FROM stock_data").fetchone()
        db_min = row[0]
        db_max = row[1]
    except Exception:
        db_min = None
        db_max = None
        
    need_download = False
    if not db_min or not db_max:
        need_download = True
    else:
        # db_min/max are dates, standard comparison should work
        # Convert inputs to strings if needed for specific logic, but date objects compare fine usually
        if from_date < db_min or to_date > db_max:
            need_download = True
            
    if need_download:
        st.info("Fetching missing data from NSE. This may take a while...")
        try:
            download_and_store_range(from_date, to_date)
            st.success("Data updated!")
        except Exception as e:
            st.error(f"Error updating data: {e}")


if fetch_clicked:
    ensure_data_in_db(from_date, to_date)
    st.rerun()


# --- Trend Analysis Logic ---
def get_amt_financed_trend(symbol, from_date, to_date):
    conn = get_connection()
    # Use DuckDB parameterized execute and .df()
    df = conn.execute(
        "SELECT s.date, s.amt_financed FROM stock_data s JOIN stock_master m ON s.stock_id = m.stock_id WHERE m.symbol = ? AND s.date BETWEEN ? AND ? ORDER BY s.date",
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
    st.warning("No data available for the selected range. Please fetch/update data.")
    # But allow fetch button to work! The stop() prevents rendering below, which is fine
    # But if fetch_clicked was set, it runs above and re-runs.
    if not fetch_clicked:
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


def filter_by_industry(df, industry_map, selected_industries):
    if selected_industries:
        df["Industry"] = df["Symbol"].map(industry_map)
        df = df[df["Industry"].isin(selected_industries)]
    else:
        df["Industry"] = df["Symbol"].map(industry_map)
    return df


# --- Always get the latest analysis result for the current controls ---
if run_analysis:
    if (
        rerun_needed
        or "analysis_df" not in st.session_state
        or st.session_state.get("analysis_key") != key
    ):
        if function == "Top by Amount Financed":
            df = get_top5_amt_financed(
                to_date_db, top_n, selected_industries, from_date_db
            )
            df["Amount Financed (₹ Cr)"] = df["amt_financed"] / 100
            df["Free Float Market Cap (₹ Cr)"] = (
                df["Free Float Market Cap (₹ Lakhs)"] / 100
            )
            df = df.rename(
                columns={
                    "symbol": "Symbol",
                    "name": "Name",
                    "industry": "Industry",
                    "Exposure (%)": "Exposure (%)",
                }
            )
        elif function == "Top by % Change in Amount Financed":
            df = get_top5_amt_financed_pct_change(
                from_date_db, to_date_db, top_n, selected_industries
            )
            df["Amount Financed Start (₹ Cr)"] = df["amt_financed_from"] / 100
            df["Amount Financed End (₹ Cr)"] = df["amt_financed_to"] / 100
            df["Free Float Market Cap (₹ Cr)"] = (
                df["Free Float Market Cap (₹ Lakhs)"] / 100
            )
            df = df.rename(
                columns={
                    "symbol": "Symbol",
                    "name": "Name",
                    "industry": "Industry",
                    "pct_change": "% Change",
                    "Exposure (%)": "Exposure (%)",
                }
            )
        elif function == "Newly Added MTF Stocks":
            df = get_newly_added_stocks(from_date_db, to_date_db, selected_industries)
            df["Amount Financed Start (₹ Cr)"] = df["amt_financed_from"] / 100
            df["Amount Financed End (₹ Cr)"] = df["amt_financed_to"] / 100
            df["Free Float Market Cap (₹ Cr)"] = (
                df["Free Float Market Cap (₹ Lakhs)"] / 100
            )
            df = df.rename(
                columns={
                    "symbol": "Symbol",
                    "name": "Name",
                    "industry": "Industry",
                    "Exposure (%)": "Exposure (%)",
                }
            )
        elif function == "Top by Exposure %":
            df = get_top_exposure_stocks(to_date_db, top_n, selected_industries)
            df["Amount Financed (₹ Cr)"] = df["amt_financed"] / 100
            df["Free Float Market Cap (₹ Cr)"] = (
                df["Free Float Market Cap (₹ Lakhs)"] / 100
            )
            df = df.rename(
                columns={
                    "symbol": "Symbol",
                    "name": "Name",
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
                    "Name",
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
                    "Name",
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
                    "Name",
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
                    "Name",
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
            # Use last available row for ffmc/exposure
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

        # Convert lakhs to crores for display
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

        # Always show price overlay when button is clicked
        price_data = nse.fetch_equity_historical_data(
            trend_symbol_input,
            from_date=pd.to_datetime(from_date_db).date(),
            to_date=pd.to_datetime(to_date_db).date(),
        )
        if price_data:
            price_df = pd.DataFrame(price_data)
            # Handle potential column name changes in v2
            timestamp_col = (
                "mTIMESTAMP" if "mTIMESTAMP" in price_df.columns else "CH_TIMESTAMP"
            )
            closing_col = "CH_CLOSING_PRICE"

            if timestamp_col in price_df.columns and closing_col in price_df.columns:
                price_df["date"] = pd.to_datetime(
                    price_df[timestamp_col], errors="coerce"
                )  # Format might vary
                price_df = price_df.sort_values("date")
                price_df["pct_change"] = price_df[closing_col].pct_change() * 100
                fig.add_trace(
                    go.Scatter(
                        x=price_df["date"],
                        y=price_df["CH_CLOSING_PRICE"],
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

        # Always show index overlay when button is clicked
        try:
            index_data = nse.fetch_historical_index_data(
                index="NIFTY TOTAL MARKET",
                from_date=pd.to_datetime(df_chart["date"].min()).date(),
                to_date=pd.to_datetime(df_chart["date"].max()).date(),
            )
            # v2.0.0 returns a list of dicts directly
            price_list = index_data if isinstance(index_data, list) else []
        except Exception as e:
            print(f"Error fetching index data: {e}")
            price_list = []

        price_df = pd.DataFrame(price_list)
        if not price_df.empty and "EOD_CLOSE_INDEX_VAL" in price_df.columns:
            # Ensure date column handling matches new format if needed
            # Old code used EOD_TIMESTAMP, let's verify if that key still exists or use logic to find date key
            timestamp_col = (
                "EOD_TIMESTAMP" if "EOD_TIMESTAMP" in price_df.columns else "mTIMESTAMP"
            )  # Fallback if needed

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
