import os
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

# ==========================================
# Load environment variables
# ==========================================
load_dotenv()

PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT", 5432)
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASS = os.getenv("PG_PASS")

# ==========================================
# Setup DB connection
# ==========================================
@st.cache_resource
def get_engine():
    try:
        url = f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
        return create_engine(url, pool_pre_ping=True)
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None

engine = get_engine()

# ==========================================
# Utility: Explore all tables
# ==========================================
def explore_database(engine):
    """Show all table names and columns."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if not tables:
        st.info("No tables found in database.")
        return

    for t in tables:
        cols = [c["name"] for c in inspector.get_columns(t)]
        st.markdown(f"**🗂 {t}** — Columns: `{', '.join(cols)}`")

# ==========================================
# Fetch Sector Performance Logic
# ==========================================
@st.cache_data(ttl=900)
def fetch_sector_performance(limit=20, page=1):
    """
    Tries to fetch sector-level performance.
    Priority: financials table → companies table
    """
    try:
        with engine.connect() as conn:
            # Try from 'financials' table first
            result = conn.execute(text("""
                SELECT c.sector, AVG(f.revenue_growth) AS performance
                FROM financials f
                JOIN companies c ON f.ticker = c.ticker
                WHERE f.revenue_growth IS NOT NULL
                GROUP BY c.sector
                ORDER BY performance DESC
                LIMIT :limit OFFSET :offset;
            """), {"limit": limit, "offset": (page - 1) * limit})
            rows = result.fetchall()

            if not rows:
                # fallback to companies table
                result = conn.execute(text("""
                    SELECT sector, COUNT(*)::float AS performance
                    FROM companies
                    WHERE sector IS NOT NULL
                    GROUP BY sector
                    ORDER BY performance DESC
                    LIMIT :limit OFFSET :offset;
                """), {"limit": limit, "offset": (page - 1) * limit})
                rows = result.fetchall()

        df = pd.DataFrame(rows, columns=["sector", "performance"])
        return df

    except Exception as e:
        st.warning("⚠️ Could not fetch sector performance data.")
        st.caption(f"Error details: {e}")
        return pd.DataFrame(columns=["sector", "performance"])

# ==========================================
# Page UI & Styling
# ==========================================
def page(rds=None, dynamo=None, **kwargs):
    st.set_page_config(layout="wide")
    st.markdown("""
        <style>
        .main {
            background-color: #fffaf3;
            padding: 30px;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(255,140,0,0.1);
        }
        .title {
            color: #ff7f00;
            text-align: center;
            font-weight: 700;
            font-size: 28px;
            margin-bottom: 10px;
        }
        .subtitle {
            text-align: center;
            color: #555;
            font-size: 16px;
            margin-bottom: 30px;
        }
        .metric-card {
            background-color: #fff;
            border: 1px solid #f5d6a3;
            border-radius: 14px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(255,165,0,0.1);
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='main'>", unsafe_allow_html=True)
    st.markdown("<h1 class='title'>📊 Sector Performance Insights</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>View performance trends across sectors using RDS data</p>", unsafe_allow_html=True)

    # ----------------- Database Explorer -----------------
    with st.expander("🔍 Explore Database"):
        if engine:
            explore_database(engine)
        else:
            st.warning("Database connection not available.")

    # ----------------- Controls -----------------
    col1, col2 = st.columns([1, 1])
    limit = col1.number_input("Rows per page:", 5, 50, 20)
    page_num = col2.number_input("Page number:", 1, 50, 1)

    # ----------------- Fetch Data -----------------
    df = fetch_sector_performance(limit, page_num)

    if df.empty:
        st.info("No data to display.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ----------------- Metrics -----------------
    top_sector = df.iloc[0]
    avg_perf = df["performance"].mean()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
        <div class='metric-card'>
            <h4>🏆 Top Sector</h4>
            <h2 style='color:#ff7f00'>{top_sector['sector']}</h2>
            <p>{top_sector['performance']:.2f}%</p>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class='metric-card'>
            <h4>📈 Average Performance</h4>
            <h2 style='color:#ff7f00'>{avg_perf:.2f}%</h2>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ----------------- Chart -----------------
    fig = px.bar(
        df,
        x="sector",
        y="performance",
        text="performance",
        color="performance",
        color_continuous_scale="Oranges",
        title="Sector Performance Overview",
    )
    fig.update_layout(
        title_x=0.5,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#333"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ----------------- Table -----------------
    st.markdown("### 📋 Detailed Data")
    st.dataframe(df, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

# Run directly (optional for testing)
if __name__ == "__main__":
    page()
