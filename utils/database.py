"""
Database utility functions for EffluentWatch application.

Handles data loading, processing, and basic query operations for permit exceedance records.
"""

import os
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

def find_csv_files(base_dir: Optional[str] = None) -> List[str]:
    """
    Find potential CSV files for data loading.

    Args:
        base_dir (str, optional): Base directory to search. 
                                  Defaults to current directory or user's desktop.

    Returns:
        List[str]: List of potential CSV file paths
    """
    # Default search paths
    search_paths = [
        os.path.join(os.path.expanduser('~'), 'Desktop', 'Launch_Ready'),
        os.path.join(os.getcwd()),
        os.path.join(os.path.expanduser('~'), 'Documents', 'Launch_Ready')
    ]

    # Add custom base directory if provided
    if base_dir:
        search_paths.insert(0, base_dir)

    # Potential CSV filenames to look for
    csv_patterns = [
        'tx_exceedances_launch_ready.csv',
        'trimmed_tx_exceedances_2020_2024.csv',
        'exceedances.csv',
        'permit_data.csv'
    ]

    # Find matching CSV files
    matching_files = []
    for path in search_paths:
        for pattern in csv_patterns:
            full_path = os.path.join(path, pattern)
            if os.path.exists(full_path):
                matching_files.append(full_path)

    return matching_files

def load_data(
    primary_file: Optional[str] = None,
    backup_file: Optional[str] = None
) -> pd.DataFrame:
    """
    Load and cache permit exceedance data from CSV file.

    Args:
        primary_file (str, optional): Specific primary CSV file path.
        backup_file (str, optional): Specific backup CSV file path.

    Returns:
        pd.DataFrame: Loaded and processed DataFrame of permit exceedances.
    """
    @st.cache_data
    def _cached_load_data(path: str) -> pd.DataFrame:
        """
        Internal cached function to load data with additional processing.
        """
        try:
            # Load the raw data
            df = pd.read_csv(path)

            # Standardize column names
            df.columns = [col.upper().replace(' ', '_') for col in df.columns]

            # Ensure key columns exist
            _ensure_columns(df)

            # Date parsing with error handling
            date_columns = ['NON_COMPLIANCE_DATE', 'MONITORING_PERIOD_END_DATE']
            for col in date_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce')

            return df

        except Exception as e:
            st.error(f"Error loading data from {path}: {e}")
            return pd.DataFrame()

    # SIMPLIFIED PATH LOGIC FOR DEPLOYMENT
    possible_paths = [
        'tx_exceedances_launch_ready.csv',  # Root directory
        'archive_2025_09_06_before_refactor/tx_exceedances_launch_ready.csv',  # Archive folder
        'Launch_Ready/tx_exceedances_launch_ready.csv',  # Launch_Ready folder
        primary_file,  # Custom path if provided
        backup_file  # Backup path if provided
    ]
    
    # Try each path
    for path in possible_paths:
        if path and os.path.exists(path):
            print(f"Loading data from: {path}")
            return _cached_load_data(path)
    
    # If no file found, show error
    st.error("Could not find tx_exceedances_launch_ready.csv in any expected location!")
    st.error(f"Searched in: {possible_paths}")
    return pd.DataFrame()

def _ensure_columns(df: pd.DataFrame) -> None:
    """
    Ensure critical columns exist in the DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame to check and potentially modify.
    """
    # List of columns that should always be present
    critical_columns = [
        'PERMIT_NUMBER', 
        'PF_NAME', 
        'COUNTY_NAME', 
        'PARAMETER', 
        'NON_COMPLIANCE_DATE'
    ]

    # Add missing columns with default values
    for col in critical_columns:
        if col not in df.columns:
            st.warning(f"Column {col} not found. Adding with default values.")
            if 'DATE' in col:
                df[col] = pd.NaT
            else:
                df[col] = 'Unknown'

def filter_exceedances(
    df: pd.DataFrame, 
    county: Optional[str] = None,
    facility: Optional[str] = None,
    parameter: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Apply advanced filtering to exceedance records with detailed logging.
    """
    # Initial DataFrame size
    initial_size = len(df)

    # Detailed logging of input parameters
    st.write("Filtering Parameters:")
    st.write(f"Total initial records: {initial_size}")
    st.write(f"County filter: {county}")
    st.write(f"Facility filter: {facility}")
    st.write(f"Parameter filter: {parameter}")
    st.write(f"Start Date: {start_date}")
    st.write(f"End Date: {end_date}")

    # Create a copy of the DataFrame
    filtered_df = df.copy()

    # County filter
    if county and county != 'All County Names':
        filtered_df = filtered_df[filtered_df['COUNTY_NAME'] == county]
        st.write(f"Records after county filter: {len(filtered_df)}")

    # Facility name filter
    if facility:
        filtered_df = filtered_df[
            filtered_df['PF_NAME'].str.contains(facility, case=False, na=False)
        ]
        st.write(f"Records after facility filter: {len(filtered_df)}")

    # Parameter filter
    if parameter and parameter != 'All Parameters':
        filtered_df = filtered_df[filtered_df['PARAMETER'] == parameter]
        st.write(f"Records after parameter filter: {len(filtered_df)}")

    # Date range filter
    if start_date and end_date:
        filtered_df = filtered_df[
            (filtered_df['NON_COMPLIANCE_DATE'] >= start_date) & 
            (filtered_df['NON_COMPLIANCE_DATE'] <= end_date)
        ]
        st.write(f"Records after date filter: {len(filtered_df)}")

    return filtered_df

def get_unique_values(
    df: pd.DataFrame, 
    column: str, 
    include_all: bool = True
) -> List[str]:
    """
    Retrieves unique values for a given column.

    Args:
        df (pd.DataFrame): Input DataFrame.
        column (str): Column to extract unique values from.
        include_all (bool, optional): Whether to include 'All' option. Defaults to True.

    Returns:
        List[str]: List of unique values, optionally including 'All' option.
    """
    # Ensure column exists
    if column not in df.columns:
        st.warning(f"Column {column} not found in DataFrame")
        return ['All Columns']

    unique_values = df[column].dropna().unique().tolist()
    unique_values.sort()

    if include_all:
        all_prefix = 'All ' + column.replace('_', ' ').title()
        unique_values.insert(0, all_prefix)

    return unique_values