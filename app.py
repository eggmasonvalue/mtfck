import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from mtfck import (
    DB_PATH,
    download_and_store_range,
    get_next_available_date,
    get_prev_available_date,
    get_top5_amt_financed,
    get_top5_amt_financed_pct_change,
    get_newly_added_stocks,
    get_top5_exposure_pct,
    create_table,
)

# Ensure DB and tables exist
create_table()

def get_available_dates():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT DISTINCT date FROM stock_data ORDER BY date", conn)
        return df['date'].tolist()
    except Exception:
        return []

def get_unique_industries():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT DISTINCT industry FROM stock_master WHERE industry IS NOT NULL AND industry != '' ORDER BY industry", conn)
        return df['industry'].dropna().tolist()
    except Exception:
        return []

st.set_page_config(page_title="MTF Analytics Dashboard", layout="wide")
st.title("NSE Margin Trading Facility (MTF) Analytics Dashboard")

# --- Sidebar Controls ---
with st.sidebar:
    st.header("Analysis Controls")
    dates = get_available_dates()
    if dates:
        min_date = min(dates)
        max_date = max(dates)
    else:
        min_date = max_date = date.today().strftime("%Y-%m-%d")
    from_date = st.date_input("From Date", value=datetime.strptime(min_date, "%Y-%m-%d").date(), key="from_date")
    to_date = st.date_input("To Date", value=datetime.strptime(max_date, "%Y-%m-%d").date(), key="to_date")
    # Move fetch button here, right after to_date
    fetch_clicked = st.button("Fetch/Update Data for Selected Range", use_container_width=True)
    top_n = st.selectbox("Number of Top Stocks", [5, 10, 15, 20], index=0)
    industries = get_unique_industries()
    selected_industries = st.multiselect("Industry Filter (optional)", industries, default=[])
    function = st.selectbox(
        "Analysis Type",
        [
            "Top by Amount Financed",
            # "Top by Exposure Percentage",
            "Top by % Change in Amount Financed",
            "Newly Added MTF Stocks"
        ]
    )
    run_analysis = st.button("Run Analysis", use_container_width=True)

st.markdown(f"**Selected Range:** {from_date} to {to_date}")

# --- Data Fetch Logic ---
def ensure_data_in_db(from_date, to_date):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT MIN(date), MAX(date) FROM stock_data")
        row = cur.fetchone()
        db_min = row[0]
        db_max = row[1]
    need_download = False
    if not db_min or not db_max:
        need_download = True
    else:
        if from_date.strftime("%Y-%m-%d") < db_min or to_date.strftime("%Y-%m-%d") > db_max:
            need_download = True
    if need_download:
        st.info("Fetching missing data from NSE. This may take a while...")
        download_and_store_range(from_date, to_date)
        st.success("Data updated!")

if fetch_clicked:
    ensure_data_in_db(from_date, to_date)
    st.rerun()

# --- Net Outstanding/Trend Chart ---
if 'trend_df' not in st.session_state:
    st.session_state['trend_df'] = None
if 'trend_title' not in st.session_state:
    st.session_state['trend_title'] = None

with sqlite3.connect(DB_PATH) as conn:
    df_chart = pd.read_sql_query(
        "SELECT date, net_outstanding_end FROM daily_summary ORDER BY date", conn
    )

# --- Analysis Output Section ---
if 'last_range' not in st.session_state:
    st.session_state['last_range'] = {}
if 'results' not in st.session_state:
    st.session_state['results'] = {}

def cache_key(function, from_date_db, to_date_db, top_n, selected_industries):
    industries_key = ",".join(sorted(selected_industries)) if selected_industries else "ALL"
    return f"{function}|{from_date_db}|{to_date_db}|{top_n}|{industries_key}"

from_date_db = get_next_available_date(from_date)
to_date_db = get_prev_available_date(to_date)

if not from_date_db or not to_date_db:
    st.warning("No data available for the selected range. Please fetch/update data.")
    st.stop()

key = cache_key(function, from_date_db, to_date_db, top_n, selected_industries)
current_range = (from_date_db, to_date_db, top_n, tuple(sorted(selected_industries)) if selected_industries else ())
last_range = st.session_state['last_range'].get(function)
rerun_needed = (last_range != current_range) or (key not in st.session_state['results'])

def filter_by_industry(df, industry_map, selected_industries):
    if selected_industries:
        df['Industry'] = df['Symbol'].map(industry_map)
        df = df[df['Industry'].isin(selected_industries)]
    else:
        df['Industry'] = df['Symbol'].map(industry_map)
    return df

def get_amt_financed_trend(symbol, from_date, to_date):
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            "SELECT date, amt_financed FROM stock_data WHERE symbol = ? AND date BETWEEN ? AND ? ORDER BY date",
            conn,
            params=(symbol, from_date, to_date)
        )
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df['amt_financed_cr'] = df['amt_financed'] / 100
    return df

# --- Show Trend Controls (horizontal, symmetric, above table/chart) ---
trend_symbol = None
trend_title = None
trend_df = None

if run_analysis:
    def show_trend_for_symbol(symbol, name):
        trend_df = get_amt_financed_trend(symbol, from_date_db, to_date_db)
        if not trend_df.empty:
            st.session_state['trend_df'] = trend_df
            st.session_state['trend_title'] = f"Amount Financed Trend for {symbol} ({name})"
        else:
            st.session_state['trend_df'] = None
            st.session_state['trend_title'] = "No trend data available for this symbol in selected range."

    # Place dropdown above table, button below dropdown, graph always at the top
    if function == "Top by Amount Financed":
        if rerun_needed:
            df = get_top5_amt_financed(to_date_db, top_n, selected_industries)
            st.session_state['results'][key] = df
            st.session_state['last_range'][function] = current_range
        df = st.session_state['results'][key]
        df['Amount Financed (₹ Cr)'] = df['Amount Financed (₹ Lakhs)'] / 100
        df['Free Float Market Cap (₹ Cr)'] = df['Free Float Market Cap (₹ Lakhs)'] / 100
        df = df.rename(columns={
            'symbol': 'Symbol',
            'name': 'Name',
            'Exposure %': 'Exposure (%)'
        })

        # --- Graph at the top ---
        if st.session_state.get('trend_df') is not None:
            st.subheader(st.session_state.get('trend_title', 'Amount Financed Trend'))
            st.line_chart(st.session_state['trend_df'].set_index('date')['amt_financed_cr'])
        else:
            st.subheader("Net Outstanding End (Daily Trend) (₹ Cr)")
            if not df_chart.empty:
                df_chart['date'] = pd.to_datetime(df_chart['date'])
                df_chart['net_outstanding_end_cr'] = df_chart['net_outstanding_end'] / 100  # Convert from Lakhs to Cr
                st.line_chart(df_chart.set_index('date')['net_outstanding_end_cr'])
            else:
                st.info("No summary data found.")

        # --- Dropdown below graph, button below dropdown, then subheader, then table ---
        trend_symbol = st.selectbox(
            "Show Amount Financed Trend for Symbol",
            df['Symbol'],
            format_func=lambda sym: f"{sym} - {df[df['Symbol'] == sym]['Name'].values[0]}",
            key="trend_amt_financed"
        )
        if st.button("Show Trend", key="trend_btn_amt_financed"):
            show_trend_for_symbol(trend_symbol, df[df['Symbol'] == trend_symbol]['Name'].values[0])

        st.subheader(f"Top {top_n} Stocks by Amount Financed on {to_date_db}")

        st.dataframe(
            df[['Symbol', 'Name', 'Industry', 'Amount Financed (₹ Cr)', 'Free Float Market Cap (₹ Cr)', 'Exposure (%)']],
            use_container_width=True
        )

    elif function == "Top by % Change in Amount Financed":
        if rerun_needed:
            df = get_top5_amt_financed_pct_change(from_date_db, to_date_db, top_n, selected_industries)
            st.session_state['results'][key] = df
            st.session_state['last_range'][function] = current_range
        df = st.session_state['results'][key]
        df['Amount Financed Start (₹ Cr)'] = df['Amount Financed Start (₹ Lakhs)'] / 100
        df['Amount Financed End (₹ Cr)'] = df['Amount Financed End (₹ Lakhs)'] / 100
        df['Free Float Market Cap (₹ Cr)'] = df['Free Float Market Cap (₹ Lakhs)'] / 100
        df = df.rename(columns={
            'symbol': 'Symbol',
            'name': 'Name',
            'pct_change': '% Change',
            'Exposure %': 'Exposure (%)'
        })

        if st.session_state.get('trend_df') is not None:
            st.subheader(st.session_state.get('trend_title', 'Amount Financed Trend'))
            st.line_chart(st.session_state['trend_df'].set_index('date')['amt_financed_cr'])
        else:
            st.subheader("Net Outstanding End (Daily Trend) (₹ Cr)")
            if not df_chart.empty:
                df_chart['date'] = pd.to_datetime(df_chart['date'])
                df_chart['net_outstanding_end_cr'] = df_chart['net_outstanding_end'] / 100
                st.line_chart(df_chart.set_index('date')['net_outstanding_end_cr'])
            else:
                st.info("No summary data found.")

        trend_symbol = st.selectbox(
            "Show Amount Financed Trend for Symbol",
            df['Symbol'],
            format_func=lambda sym: f"{sym} - {df[df['Symbol'] == sym]['Name'].values[0]}",
            key="trend_select_pct"
        )
        if st.button("Show Trend", key="trend_btn_pct"):
            show_trend_for_symbol(trend_symbol, df[df['Symbol'] == trend_symbol]['Name'].values[0])

        st.subheader(f"Top {top_n} Stocks by % Change in Amount Financed ({from_date_db} to {to_date_db})")

        st.dataframe(
            df[['Symbol', 'Name', 'Industry', 'Amount Financed Start (₹ Cr)', 'Amount Financed End (₹ Cr)', '% Change', 'Free Float Market Cap (₹ Cr)', 'Exposure (%)']],
            use_container_width=True
        )

    elif function == "Newly Added MTF Stocks":
        if rerun_needed:
            df = get_newly_added_stocks(from_date_db, to_date_db, top_n, selected_industries)
            st.session_state['results'][key] = df
            st.session_state['last_range'][function] = current_range
        df = st.session_state['results'][key]
        df['Amount Financed Start (₹ Cr)'] = df['Amount Financed Start (₹ Lakhs)'] / 100
        df['Amount Financed End (₹ Cr)'] = df['Amount Financed End (₹ Lakhs)'] / 100
        df['Free Float Market Cap (₹ Cr)'] = df['Free Float Market Cap (₹ Lakhs)'] / 100
        df = df.rename(columns={
            'symbol': 'Symbol',
            'name': 'Name',
            'Exposure %': 'Exposure (%)'
        })

        if st.session_state.get('trend_df') is not None:
            st.subheader(st.session_state.get('trend_title', 'Amount Financed Trend'))
            st.line_chart(st.session_state['trend_df'].set_index('date')['amt_financed_cr'])
        else:
            st.subheader("Net Outstanding End (Daily Trend) (₹ Cr)")
            if not df_chart.empty:
                df_chart['date'] = pd.to_datetime(df_chart['date'])
                df_chart['net_outstanding_end_cr'] = df_chart['net_outstanding_end'] / 100
                st.line_chart(df_chart.set_index('date')['net_outstanding_end_cr'])
            else:
                st.info("No summary data found.")

        trend_symbol = st.selectbox(
            "Show Amount Financed Trend for Symbol",
            df['Symbol'],
            format_func=lambda sym: f"{sym} - {df[df['Symbol'] == sym]['Name'].values[0]}",
            key="trend_select_new"
        )
        if st.button("Show Trend", key="trend_btn_new"):
            show_trend_for_symbol(trend_symbol, df[df['Symbol'] == trend_symbol]['Name'].values[0])

        st.subheader(f"Top {top_n} Newly Added MTF Stocks ({from_date_db} to {to_date_db})")

        st.dataframe(
            df[['Symbol', 'Name', 'Industry', 'Amount Financed Start (₹ Cr)', 'Amount Financed End (₹ Cr)', 'Free Float Market Cap (₹ Cr)', 'Exposure (%)']],
            use_container_width=True
        )

# --- Show either Net Outstanding or Trend Chart if no analysis run ---
if not run_analysis:
    if st.session_state.get('trend_df') is not None:
        st.subheader(st.session_state.get('trend_title', 'Amount Financed Trend'))
        st.line_chart(st.session_state['trend_df'].set_index('date')['amt_financed_cr'])
    else:
        st.subheader("Net Outstanding End (Daily Trend) (₹ Cr)")
        if not df_chart.empty:
            df_chart['date'] = pd.to_datetime(df_chart['date'])
            df_chart['net_outstanding_end_cr'] = df_chart['net_outstanding_end'] / 100  # Convert from Lakhs to Cr
            st.line_chart(df_chart.set_index('date')['net_outstanding_end_cr'])
        else:
            st.info("No summary data found.")

st.caption("NSE MTF Analytics Dashboard - Powered by Streamlit")