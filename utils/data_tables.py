"""
Data table module for EffluentWatch application.

Provides exportable data exploration capabilities using native Streamlit components.
"""

import streamlit as st
import pandas as pd
from typing import Optional, List, Dict, Any


class PermitDataTables:
    @staticmethod
    def interactive_permit_table(
        df: pd.DataFrame,
        page_size: int = 20,
    ) -> Optional[List[int]]:
        """
        Create an interactive permit table using native st.dataframe with row selection.

        Args:
            df: Permit exceedance DataFrame
            page_size: Number of rows per page. Defaults to 20.

        Returns:
            List of selected row indices, if any
        """
        st.header("Permit Exceedance Records")

        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )

        return event.selection.rows if event.selection.rows else None

    @staticmethod
    def export_data_section(df: pd.DataFrame) -> None:
        """
        Create a data export section with multiple format options.

        Args:
            df: Permit exceedance DataFrame
        """
        st.sidebar.header("Data Export")

        export_format = st.sidebar.selectbox(
            "Select Export Format",
            ["CSV", "Excel", "JSON"]
        )

        st.sidebar.subheader("Export Filters")
        export_columns = st.sidebar.multiselect(
            "Select Columns to Export",
            df.columns.tolist(),
            default=df.columns.tolist()
        )

        export_df = df[export_columns]

        if st.sidebar.button("Export Data"):
            try:
                if export_format == "CSV":
                    csv = export_df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name="permit_exceedances.csv",
                        mime="text/csv"
                    )
                elif export_format == "Excel":
                    excel = export_df.to_excel(index=False)
                    st.download_button(
                        label="Download Excel",
                        data=excel,
                        file_name="permit_exceedances.xlsx",
                        mime="application/vnd.ms-excel"
                    )
                else:
                    json_data = export_df.to_json(orient='records')
                    st.download_button(
                        label="Download JSON",
                        data=json_data,
                        file_name="permit_exceedances.json",
                        mime="application/json"
                    )
                st.success(f"Data exported successfully as {export_format}!")
            except Exception as e:
                st.error(f"Export failed: {e}")


def render_data_tables(df: pd.DataFrame) -> None:
    """
    Render comprehensive data table interface.

    Args:
        df: Permit exceedance DataFrame
    """
    st.sidebar.header("Data Exploration")

    view_mode = st.sidebar.radio(
        "View Mode",
        ["Interactive Table", "Export Data"]
    )

    if view_mode == "Interactive Table":
        selected_rows = PermitDataTables.interactive_permit_table(df)

        if selected_rows:
            st.subheader("Selected Rows Details")
            st.dataframe(df.iloc[selected_rows])
    else:
        PermitDataTables.export_data_section(df)
