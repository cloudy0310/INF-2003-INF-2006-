# views/user/stock_analysis.py
import streamlit as st
import pandas as pd
import plotly.express as px
from app.api.stock_analysis import get_company_info, get_financials, get_stock_prices

st.title("📈 Stock Analysis Dashboard")

# --- Search bar ---
ticker = st.text_input("Search Stock Ticker (e.g., AAPL, MSFT)").upper()
if not ticker:
    st.info("Enter a ticker symbol to start analysis.")
    st.stop()

# --- Company Info ---
st.subheader("🏢 Company Overview")
company_info = get_company_info(ticker)
if company_info:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Name:** {company_info.get('name', 'N/A')}")
        st.markdown(f"**Ticker:** {company_info.get('ticker', 'N/A')}")
        st.markdown(f"**Sector:** {company_info.get('sector', 'N/A')}")
    with col2:
        st.markdown(f"**Industry:** {company_info.get('industry', 'N/A')}")
        st.markdown(f"**Headquarters:** {company_info.get('headquarters', 'N/A')}")
        st.markdown(f"**CEO:** {company_info.get('ceo', 'N/A')}")
    with col3:
        st.markdown(f"**Founded:** {company_info.get('founded', 'N/A')}")
        st.markdown(f"**Employees:** {company_info.get('employees', 'N/A')}")
        st.markdown(f"**Website:** {company_info.get('website', 'N/A')}")

else:
    st.warning("No company info found.")

# --- Financials ---
st.subheader("💰 Key Financials")
df_fin = get_financials(ticker)
if not df_fin.empty:
    # Rename columns for clarity
    df_fin = df_fin.rename(columns={
        'fiscal_year': 'Year',
        'revenue': 'Revenue ($M)',
        'net_income': 'Net Income ($M)',
        'eps': 'EPS',
        'ebitda': 'EBITDA ($M)'
    })
    st.dataframe(df_fin.style.format({
        'Revenue ($M)': "${:,.0f}",
        'Net Income ($M)': "${:,.0f}",
        'EPS': "{:.2f}",
        'EBITDA ($M)': "${:,.0f}"
    }))
else:
    st.warning("No financial data found.")

# --- Stock Price Chart ---
st.subheader("📊 Stock Price History")
try:
    df_price = get_stock_prices(ticker)  # make sure this uses table 'stock_prices'
    if not df_price.empty:
        df_price['date'] = pd.to_datetime(df_price['date'])
        fig = px.line(df_price, x="date", y="close", title=f"{ticker} Stock Price History",
                      labels={"date": "Date", "close": "Closing Price ($)"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No stock price data found.")
except Exception as e:
    st.error(f"Error fetching stock prices: {e}")
