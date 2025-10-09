import os
import psycopg2
from dotenv import load_dotenv
import dash
from dash import html, dcc, Input, Output
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../pipeline_scripts/pipeline/.env'))

# Get DB credentials
USE_RDS = os.getenv("USE_RDS", "0") == "1"

if USE_RDS:
    DB_HOST = os.getenv("PG_HOST")
    DB_NAME = os.getenv("PG_DB")
    DB_USER = os.getenv("PG_USER")
    DB_PASSWORD = os.getenv("PG_PASS")
    DB_PORT = os.getenv("PG_PORT", 5432)
else:
    # fallback/default/test values
    DB_HOST = "localhost"
    DB_NAME = "test_db"
    DB_USER = "user"
    DB_PASSWORD = "password"
    DB_PORT = 5432

# Database connection
try:
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    cursor = conn.cursor()
except Exception as e:
    print(f"❌ Failed to connect to database: {e}")
    conn = None

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server  # for deployment

# App layout
app.layout = dbc.Container([
    html.H2("📊 Market Insights", className="page-title"),
    html.P("Sector Performance Overview", className="section-title"),

    dbc.Row([
        dbc.Col([
            dcc.Graph(id="sector-performance-chart")
        ], width=12)
    ])
], fluid=True)


# Callback to update chart
@app.callback(
    Output("sector-performance-chart", "figure"),
    Input("sector-performance-chart", "id")
)
def update_chart(_):
    if conn is None:
        return px.bar(title="Database not connected.")

    try:
        df = pd.read_sql("""
            SELECT sector, performance 
            FROM sector_performance 
            WHERE performance IS NOT NULL
            ORDER BY performance DESC
            LIMIT 20
        """, conn)

        fig = px.bar(df, x="sector", y="performance", title="Top 20 Sector Performance", color="performance")
        return fig

    except Exception as e:
        print(f"❌ Failed to fetch sector performance: {e}")
        return px.bar(title=f"Error loading data: {e}")


# Run the app
if __name__ == "__main__":
    app.run_server(debug=True, host="0.0.0.0", port=8501)
