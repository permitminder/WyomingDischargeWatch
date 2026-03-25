"""
Test script for EffluentWatch database utility.
"""

import streamlit as st
import sys
import os

# Add the project root directory to the Python path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from utils.database import load_data, get_unique_values, filter_exceedances

def test_database():
    """
    Test database loading and processing functions.
    """
    st.title("EffluentWatch Database Utility Test")
    
    # Load data
    st.header("1. Data Loading Test")
    df = load_data()
    
    if df.empty:
        st.error("❌ Failed to load data")
        return
    
    st.success(f"✅ Data loaded successfully. Total records: {len(df)}")
    
    # Display basic DataFrame info
    st.subheader("DataFrame Info")
    st.write("Columns:", list(df.columns))
    st.write("Sample Data:")
    st.dataframe(df.head())
    
    # Test unique value extraction
    st.header("2. Unique Values Test")
    try:
        counties = get_unique_values(df, 'COUNTY_NAME')
        parameters = get_unique_values(df, 'PARAMETER')
        st.subheader("Unique Counties")
        st.write(counties)

        st.subheader("Unique Parameters")
        st.write(parameters)
    except Exception as e:
        st.error(f"❌ Error extracting unique values: {e}")
    
    # Test filtering
    st.header("3. Filtering Test")
    try:
        # Example filter: First county
        if len(counties) > 1:
            filtered_df = filter_exceedances(
                df,
                county=counties[1],  # First real county (not 'All Counties')
            )
            
            st.subheader("Filtered Results")
            st.write(f"Filtered records: {len(filtered_df)}")
            st.dataframe(filtered_df.head())
    except Exception as e:
        st.error(f"❌ Error in filtering: {e}")

if __name__ == "__main__":
    test_database()