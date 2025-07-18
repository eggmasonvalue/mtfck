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
    nse,  # Import the nse instance
    calculate_returns  # <-- Add this line
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
    trend_symbol_input = st.text_input("Enter Symbol for Amount Financed Trend", key="trend_symbol_input").upper()
    show_trend_clicked = st.button("Show Amount Financed Trend", key="trend_btn_sidebar")
    show_net_outstanding_clicked = st.button("Show Total Outstanding Trend", key="net_outstanding_btn_sidebar")

    # --- Track trend chart display intent ---
    if show_trend_clicked:
        st.session_state['show_trend'] = True
    if show_net_outstanding_clicked:
        st.session_state['show_net_outstanding'] = True

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
if st.session_state.get("show_trend", False) or st.session_state.get("show_price_return", False):
    trend_df = get_amt_financed_trend(trend_symbol_input, from_date_db, to_date_db)
    if not trend_df.empty:
        # Use calculate_returns directly
        ptp_return, one_year_return, three_year_cagr = None, None, None
        try:
            ptp_return, one_year_return, three_year_cagr = calculate_returns(
                trend_symbol_input, to_date_db, from_date_db
            )
        except Exception:
            ptp_return, one_year_return, three_year_cagr = None, None, None

        # Display Symbol, P2P, 1yr, and 3yr Return (CAGR) in equal-width columns
        col1, col2, col3, col4 = st.columns(4)
        col1.markdown(f"<b>Symbol:</b> {trend_symbol_input}", unsafe_allow_html=True)
        col2.markdown(f"<b>P2P Return:</b> {ptp_return:.2f}%" if ptp_return is not None else "<b>P2P Return:</b> N/A", unsafe_allow_html=True)
        col3.markdown(f"<b>1yr Return:</b> {one_year_return:.2f}%" if one_year_return is not None else "<b>1yr Return:</b> N/A", unsafe_allow_html=True)
        col4.markdown(f"<b>3yr Return (CAGR):</b> {three_year_cagr:.2f}%" if three_year_cagr is not None else "<b>3yr Return (CAGR):</b> N/A", unsafe_allow_html=True)

        # Checkbox to show price return, rerun if toggled
        show_price_return = st.checkbox("Show price return during the period", key="show_price_return")
        if show_price_return != st.session_state.get("_last_show_price_return", None):
            st.session_state["_last_show_price_return"] = show_price_return
            st.rerun()

        # Prepare Plotly figure
        trend_df['pct_change'] = trend_df['amt_financed_cr'].pct_change() * 100  # Calculate % change
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=trend_df['date'],
            y=trend_df['amt_financed_cr'],
            mode='lines+markers',
            name='Amount Financed (₹ Cr)',
            line=dict(color='blue', width=2),
            hovertemplate="<b>Date:</b> %{x}<br><b>Amount Financed:</b> ₹%{y:.2f} Cr<br><b>% Change:</b> %{customdata:.2f}%",
            customdata=trend_df['pct_change']
        ))

        # If checkbox is checked, fetch and plot price data
        if show_price_return:
            price_data = nse.fetch_equity_historical_data(
                trend_symbol_input,
                from_date=pd.to_datetime(from_date_db).date(),
                to_date=pd.to_datetime(to_date_db).date()
            )
            if price_data:
                price_df = pd.DataFrame(price_data)
                price_df['date'] = pd.to_datetime(price_df['mTIMESTAMP'])
                price_df = price_df.sort_values('date')
                price_df['pct_change'] = price_df['CH_CLOSING_PRICE'].pct_change() * 100  # Calculate % change for price
                fig.add_trace(go.Scatter(
                    x=price_df['date'],
                    y=price_df['CH_CLOSING_PRICE'],
                    mode='lines+markers',
                    name='Closing Price',
                    line=dict(color='orange', width=2, dash='dot'),
                    yaxis='y2',
                    hovertemplate="<b>Date:</b> %{x}<br><b>Closing Price:</b> ₹%{y:.2f}<br><b>% Change:</b> %{customdata:.2f}%",
                    customdata=price_df['pct_change']  # Pass % change as custom data
                ))
                # Add secondary y-axis for price
                fig.update_layout(
                    yaxis2=dict(
                        title="Closing Price (₹)",
                        overlaying='y',
                        side='right',
                        showgrid=False
                    )
                )

        fig.update_layout(
            title=f"Amount Financed Trend for {trend_symbol_input}",
            xaxis_title="Date",
            yaxis_title="Amount Financed (₹ Cr)",
            xaxis_range=[trend_df['date'].min(), trend_df['date'].max()],
            yaxis_range=[trend_df['amt_financed_cr'].min(), trend_df['amt_financed_cr'].max()],
            width=800,
            height=400,
            hovermode='x unified'  # <-- Add this line for unified hover and vertical cursor
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.subheader(f"No trend data available for {trend_symbol_input} in the selected range.")

# --- Net Outstanding Trend Display ---
if st.session_state.get("show_net_outstanding", False) or st.session_state.get("show_index_trend", False):
    with sqlite3.connect(DB_PATH) as conn:
        df_chart = pd.read_sql_query(
            "SELECT date, net_outstanding_end FROM daily_summary ORDER BY date", conn
        )
    if not df_chart.empty:
        df_chart['date'] = pd.to_datetime(df_chart['date'])
        df_chart['net_outstanding_end_cr'] = df_chart['net_outstanding_end'] / 100  # Convert from Lakhs to Cr
        df_chart['pct_change'] = df_chart['net_outstanding_end_cr'].pct_change() * 100  # Calculate % change

        # Persist index trend checkbox state and rerun if toggled
        show_index_trend = st.checkbox("Show NIFTY TOTAL MARKET Index Trend", key="show_index_trend")
        if show_index_trend != st.session_state.get("_last_show_index_trend", None):
            st.session_state["_last_show_index_trend"] = show_index_trend
            st.rerun()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_chart['date'],
            y=df_chart['net_outstanding_end_cr'],
            mode='lines+markers',
            name='Net Outstanding End (₹ Cr)',
            line=dict(color='green', width=2),
            hovertemplate="<b>Date:</b> %{x}<br><b>Net Outstanding:</b> ₹%{y:.2f} Cr<br><b>% Change:</b> %{customdata:.2f}%",
            customdata=df_chart['pct_change']
        ))

        # If checkbox checked, plot index data as secondary y-axis
        if show_index_trend:
            index_data = nse.fetch_historical_index_data(
                index="NIFTY TOTAL MARKET",
                from_date=pd.to_datetime(df_chart['date'].min()).date(),
                to_date=pd.to_datetime(df_chart['date'].max()).date()
            )
            price_list = index_data.get("price", [])
            price_df = pd.DataFrame(price_list)
            # Use EOD_CLOSE_INDEX_VAL for plotting, EOD_TIMESTAMP for date
            if not price_df.empty and "EOD_CLOSE_INDEX_VAL" in price_df.columns:
                price_df['date'] = pd.to_datetime(price_df['EOD_TIMESTAMP'], format="%d-%b-%Y", errors='coerce')
                price_df = price_df.sort_values('date')
                price_df['pct_change'] = price_df['EOD_CLOSE_INDEX_VAL'].pct_change() * 100
                fig.add_trace(go.Scatter(
                    x=price_df['date'],
                    y=price_df['EOD_CLOSE_INDEX_VAL'],
                    mode='lines+markers',
                    name='NIFTY TOTAL MARKET',
                    line=dict(color='blue', width=2, dash='dot'),
                    yaxis='y2',
                    hovertemplate="<b>Date:</b> %{x}<br><b>Index Close:</b> %{y:.2f}<br><b>% Change:</b> %{customdata:.2f}%",
                    customdata=price_df['pct_change']
                ))
                fig.update_layout(
                    yaxis2=dict(
                        title="NIFTY TOTAL MARKET Close",
                        overlaying='y',
                        side='right',
                        showgrid=False
                    )
                )

        fig.update_layout(
            title="Net Outstanding End (Daily Trend)",
            xaxis_title="Date",
            yaxis_title="Net Outstanding End (₹ Cr)",
            xaxis_range=[df_chart['date'].min(), df_chart['date'].max()],
            yaxis_range=[df_chart['net_outstanding_end_cr'].min(), df_chart['net_outstanding_end_cr'].max()],
            width=800,
            height=400,
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No summary data found.")

st.caption("NSE MTF Analytics Dashboard - Powered by Caffeine and Copilot")