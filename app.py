"""
The beginnings of a very basic app.

EAD March 2026
"""
import streamlit as st
import polars as pl
import plotly.express as px
import os

# Set page config for a professional look
st.set_page_config(page_title="Evan's Athlete Dashboard", layout="wide")

st.title("Evan's Athlete Dashboard")

# 1. Load the data we saved in the previous step
# In a real app, you'd pull this from a DB, but reading the parquet is fast!
if os.path.exists("latest_activity.parquet"):
    df = pl.read_parquet("latest_activity.parquet")

    # 2. Sidebar Stats
    st.sidebar.header("Activity Summary")
    st.sidebar.metric("Samples Collected", df.height)
    st.sidebar.metric("Avg Cadence", f"{df['cadence'].mean():.1f} rpm")
    st.sidebar.metric("Max HR", int(df['heartrate'].max()))

    # 3. Create the Visualization
    st.subheader("Heart Rate vs. Cadence over Time")

    # We use Plotly to create a dual-axis style chart or a faceted chart
    # Faceted is often cleaner for biomechanics to avoid "spaghetti" lines

    # Convert Polars to Long format for Plotly
    df_long = df.select(['time', 'heartrate', 'cadence']).unpivot(
        index='time',
        on=['heartrate', 'cadence'],
        variable_name='Metric',
        value_name='Value'
    )

    fig = px.line(
        df_long,
        x='time',
        y='Value',
        color='Metric',
        facet_row='Metric',
        line_shape='spline',
        title="Time-Series Sensor Data"
    )

    fig.update_layout(height=600, showlegend=False)
    fig.update_yaxes(matches=None)  # Allows HR and Cadence to have their own scales

    st.plotly_chart(fig, width='stretch')

    # 4. Raw Data Inspection (Optional)
    with st.expander("View Raw Data Table"):
        st.write(df)

else:
    st.warning("No data found. Please run `fetch_data.py` first to pull your latest activity!")