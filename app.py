import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, timedelta
from mtfck import (
    DB_PATH,
    download_and_store_range,
    get_next_available_date,
    get_prev_available_date,
    get_top5_amt_financed,
    get_top5_amt_financed_pct_change,
    get_newly_added_stocks,
    create_table,
    nse  # Import the nse instance
)
import plotly.graph_objects as go

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
    fetch_clicked = st.button("Fetch/Update Data for Selected Range", use_container_width=True)
    top_n = st.selectbox("Number of Top Stocks", [5, 10, 15, 20], index=0)
    industries = get_unique_industries()
    selected_industries = st.multiselect("Industry Filter (optional)", industries, default=[])
    function = st.selectbox(
        "Analysis Type",
        [
            "Top by Amount Financed",
            "Top by % Change in Amount Financed",
            "Newly Added MTF Stocks"
        ]
    )
    run_analysis = st.button("Run Analysis", use_container_width=True)
    st.markdown("---")
    
    # --- Trends Section ---
    st.header("Trends")
    trend_symbol_input = st.text_input("Enter Symbol for Amount Financed Trend", key="trend_symbol_input").upper()  # Convert to uppercase
    show_trend_clicked = st.button("Show Amount Financed Trend", key="trend_btn_sidebar")
    show_net_outstanding_clicked = st.button("Show Total Outstanding Trend", key="net_outstanding_btn_sidebar")

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

# --- Trend Analysis Logic ---
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

# --- Always get the latest analysis result for the current controls ---
if run_analysis:
    if rerun_needed or 'analysis_df' not in st.session_state or st.session_state.get('analysis_key') != key:
        if function == "Top by Amount Financed":
            df = get_top5_amt_financed(to_date_db, top_n, selected_industries, from_date_db)
            df['Amount Financed (₹ Cr)'] = df['amt_financed'] / 100
            df['Free Float Market Cap (₹ Cr)'] = df['Free Float Market Cap (₹ Lakhs)'] / 100
            df = df.rename(columns={
                'symbol': 'Symbol',
                'name': 'Name',
                'industry': 'Industry',
                'Exposure (%)': 'Exposure (%)'
            })
        elif function == "Top by % Change in Amount Financed":
            df = get_top5_amt_financed_pct_change(from_date_db, to_date_db, top_n, selected_industries)
            df['Amount Financed Start (₹ Cr)'] = df['amt_financed_from'] / 100
            df['Amount Financed End (₹ Cr)'] = df['amt_financed_to'] / 100
            df['Free Float Market Cap (₹ Cr)'] = df['Free Float Market Cap (₹ Lakhs)'] / 100
            df = df.rename(columns={
                'symbol': 'Symbol',
                'name': 'Name',
                'industry': 'Industry',
                'pct_change': '% Change',
                'Exposure (%)': 'Exposure (%)'
            })
        elif function == "Newly Added MTF Stocks":
            df = get_newly_added_stocks(from_date_db, to_date_db, selected_industries)
            df['Amount Financed Start (₹ Cr)'] = df['amt_financed_from'] / 100
            df['Amount Financed End (₹ Cr)'] = df['amt_financed_to'] / 100
            df['Free Float Market Cap (₹ Cr)'] = df['Free Float Market Cap (₹ Lakhs)'] / 100
            df = df.rename(columns={
                'symbol': 'Symbol',
                'name': 'Name',
                'industry': 'Industry',
                'Exposure (%)': 'Exposure (%)'
            })
        else:
            df = pd.DataFrame()
        st.session_state['analysis_df'] = df
        st.session_state['analysis_key'] = key
    else:
        df = st.session_state['analysis_df']

    # --- Dropdown below graph, button below dropdown, then subheader, then table ---
    if function == "Top by Amount Financed":
        st.subheader(f"Top {top_n} Stocks by Amount Financed on {to_date_db}")
        st.dataframe(
            df[['Symbol', 'Name', 'Industry', 'Amount Financed (₹ Cr)', 'Free Float Market Cap (₹ Cr)', 'Exposure (%)', '1yr Return (%)', '3yr Return (%) (CAGR)', 'Point-to-Point Return (%)']],
            use_container_width=True
        )

    elif function == "Top by % Change in Amount Financed":
        st.subheader(f"Top {top_n} Stocks by % Change in Amount Financed ({from_date_db} to {to_date_db})")
        st.dataframe(
            df[['Symbol', 'Name', 'Industry', 'Amount Financed Start (₹ Cr)', 'Amount Financed End (₹ Cr)', '% Change', 'Free Float Market Cap (₹ Cr)', 'Exposure (%)', '1yr Return (%)', '3yr Return (%) (CAGR)', 'Point-to-Point Return (%)']],
            use_container_width=True
        )

    elif function == "Newly Added MTF Stocks":
        st.subheader(f"Newly Added MTF Stocks ({from_date_db} to {to_date_db})")
        st.dataframe(
            df[['Symbol', 'Name', 'Industry', 'Amount Financed Start (₹ Cr)', 'Amount Financed End (₹ Cr)', 'Free Float Market Cap (₹ Cr)', 'Exposure (%)', '1yr Return (%)', '3yr Return (%) (CAGR)', 'Point-to-Point Return (%)']],
            use_container_width=True
        )

# --- Trend Analysis Display ---
if show_trend_clicked:
    trend_df = get_amt_financed_trend(trend_symbol_input, from_date_db, to_date_db)
    if not trend_df.empty:
        # Calculate 1yr Return (%)
        one_year_return = None
        try:
            one_year_date = (pd.to_datetime(to_date_db) - timedelta(days=365)).date()
            hist_1yr = nse.fetch_equity_historical_data(trend_symbol_input, from_date=one_year_date, to_date=one_year_date)
            hist_to = nse.fetch_equity_historical_data(trend_symbol_input, from_date=pd.to_datetime(to_date_db).date(), to_date=pd.to_datetime(to_date_db).date())
            close_1yr = hist_1yr[0]['CH_CLOSING_PRICE'] if hist_1yr else None
            close_to = hist_to[0]['CH_CLOSING_PRICE'] if hist_to else None
            if close_1yr is not None and close_to is not None:
                one_year_return = ((close_to - close_1yr) / close_1yr) * 100
        except Exception:
            one_year_return = None

        # Calculate 3yr Return (%) (CAGR)
        three_year_cagr = None
        try:
            three_year_date = (pd.to_datetime(to_date_db) - timedelta(days=3 * 365)).date()
            hist_3yr = nse.fetch_equity_historical_data(trend_symbol_input, from_date=three_year_date, to_date=three_year_date)
            close_3yr = hist_3yr[0]['CH_CLOSING_PRICE'] if hist_3yr else None
            if close_3yr is not None and close_to is not None:
                three_year_cagr = (((close_to / close_3yr) ** (1 / 3)) - 1) * 100
        except Exception:
            three_year_cagr = None

        # Display Symbol, 1yr Return, and 3yr Return (CAGR) in equal-width columns
        col1, col2, col3 = st.columns(3)
        col1.markdown(f"<b>Symbol:</b> {trend_symbol_input}", unsafe_allow_html=True)
        col2.markdown(f"<b>1yr Return:</b> {one_year_return:.2f}%" if one_year_return is not None else "<b>1yr Return:</b> N/A", unsafe_allow_html=True)
        col3.markdown(f"<b>3yr Return (CAGR):</b> {three_year_cagr:.2f}%" if three_year_cagr is not None else "<b>3yr Return (CAGR):</b> N/A", unsafe_allow_html=True)

        # Plot the graph
        trend_df['pct_change'] = trend_df['amt_financed_cr'].pct_change() * 100  # Calculate % change
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=trend_df['date'],
            y=trend_df['amt_financed_cr'],
            mode='lines+markers',
            name='',  # Set name to an empty string to hide "trace 0"
            line=dict(color='blue', width=2),
            hovertemplate="<b>Date:</b> %{x}<br><b>Amount Financed:</b> ₹%{y:.2f} Cr<br><b>% Change:</b> %{customdata:.2f}%",
            customdata=trend_df['pct_change']  # Pass % change as custom data
        ))
        fig.update_layout(
            title=f"Amount Financed Trend for {trend_symbol_input}",
            xaxis_title="Date",
            yaxis_title="Amount Financed (₹ Cr)",
            xaxis_range=[trend_df['date'].min(), trend_df['date'].max()],
            yaxis_range=[trend_df['amt_financed_cr'].min(), trend_df['amt_financed_cr'].max()],
            width=800,
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.subheader(f"No trend data available for {trend_symbol_input} in the selected range.")

if show_net_outstanding_clicked:
    with sqlite3.connect(DB_PATH) as conn:
        df_chart = pd.read_sql_query(
            "SELECT date, net_outstanding_end FROM daily_summary ORDER BY date", conn
        )
    if not df_chart.empty:
        df_chart['date'] = pd.to_datetime(df_chart['date'])
        df_chart['net_outstanding_end_cr'] = df_chart['net_outstanding_end'] / 100  # Convert from Lakhs to Cr
        df_chart['pct_change'] = df_chart['net_outstanding_end_cr'].pct_change() * 100  # Calculate % change

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_chart['date'],
            y=df_chart['net_outstanding_end_cr'],
            mode='lines+markers',
            name='',  # Set name to an empty string to hide "trace 0"
            line=dict(color='green', width=2),
            hovertemplate="<b>Date:</b> %{x}<br><b>Net Outstanding:</b> ₹%{y:.2f} Cr<br><b>% Change:</b> %{customdata:.2f}%",
            customdata=df_chart['pct_change']  # Pass % change as custom data
        ))
        fig.update_layout(
            title="Net Outstanding End (Daily Trend)",
            xaxis_title="Date",
            yaxis_title="Net Outstanding End (₹ Cr)",
            xaxis_range=[df_chart['date'].min(), df_chart['date'].max()],
            yaxis_range=[df_chart['net_outstanding_end_cr'].min(), df_chart['net_outstanding_end_cr'].max()],
            width=800,
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No summary data found.")

st.caption("NSE MTF Analytics Dashboard - Powered by Streamlit")