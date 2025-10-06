import streamlit as st
import plotly.graph_objects as go

# ---------- Fetching Sector Performance Data from Database ----------

def fetch_sector_performance(rds):
    """
    Fetches the top performing sectors from your RDS database.
    """
    try:
        # Modify this query based on your actual database structure
        query = "SELECT sector, performance FROM sector_performance ORDER BY performance DESC LIMIT 10"
        
        # Fetch the results using SQLAlchemy's execute method
        with rds.connect() as connection:
            result = connection.execute(query)
            results = result.fetchall()

        # Convert results to a list of dictionaries
        return [{"sector": row['sector'], "performance": row['performance']} for row in results]
        
    except Exception as e:
        st.error(f"Failed to fetch sector performance: {e}")
        return []

# ---------- Display Insights Page ----------

def insights_page(rds):
    """
    This function renders the 'Insights' page in Streamlit, displaying the top-performing sectors
    as a bar chart using Plotly.
    """
    st.title("📊 Sector Insights")
    st.caption("View the top-performing sectors based on recent data.")
    
    # Fetch sector performance data from the RDS
    sector_data = fetch_sector_performance(rds)

    if not sector_data:
        st.warning("No sector data available.")
        return

    # Prepare data for Plotly chart
    sectors = [item['sector'] for item in sector_data]
    performances = [item['performance'] for item in sector_data]

    # Create a bar chart using Plotly
    fig = go.Figure([go.Bar(
        x=sectors,
        y=performances,
        text=performances,
        textposition='auto',
        marker_color='royalblue',
        hovertemplate='Sector: %{x}<br>Performance: %{y}%',  # Add custom hover text
    )])

    # Add title and labels to the chart
    fig.update_layout(
        title="Top Performing Sectors",
        xaxis_title="Sector",
        yaxis_title="Performance (%)",
        template="plotly_dark",
        plot_bgcolor="rgba(0, 0, 0, 0)",  # Set the background color to transparent
        margin=dict(l=40, r=40, t=40, b=40)  # Adjust margins
    )

    # Display the chart in Streamlit
    st.plotly_chart(fig, use_container_width=True)

# ---------- Main Function to Switch Between Tabs ----------

def page(rds=None, dynamo=None):
    """
    The main function to manage tabs in the Streamlit page.
    """
    if rds is None:
        st.error("RDS engine not provided to page().")
        st.stop()

    # Selectbox to switch between tabs
    tab = st.selectbox("Select Tab", ["Home", "Insights"])

    if tab == "Home":
        # Placeholder content for Home (you can replace this with actual content)
        st.title("🏠 Home")
        st.caption("Latest content from your RDS database.")
        st.write("Home content will be here.")
    elif tab == "Insights":
        # Call the function to display insights
        insights_page(rds)
