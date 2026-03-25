import streamlit as st
from utils.charts import (
    exceedance_range_chart,
    monthly_trend_chart,
    top_parameters_chart,
    county_bar_chart,
)


def render_dashboard(df_all, permit_summary):
    """Render the Dashboard page."""
    st.markdown("""
    <div class="pm-hero">
        <div class="pm-eyebrow">Dashboard</div>
        <div class="pm-headline">Exceedance <em>overview.</em></div>
        <div class="pm-subhead">
            A summary of discharge monitoring exceedances across Texas facilities.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)

    total_facilities = permit_summary["PERMIT_NUMBER"].nunique()
    total_ex = len(df_all)
    unique_params = df_all["PARAMETER"].nunique()
    over_100 = (df_all["pct_over"] > 100).sum()
    unique_counties = df_all.loc[df_all["COUNTY_NAME"] != "Unknown", "COUNTY_NAME"].nunique()

    m1, m2, m3 = st.columns(3)
    m1.metric("Facilities Tracked", total_facilities)
    m2.metric("Total Exceedances", f"{total_ex:,}")
    m3.metric("Counties Represented", unique_counties)

    m4, m5, m6 = st.columns(3)
    m4.metric("Parameters Tracked", unique_params)
    m5.metric("Over 100% of Limit", f"{over_100:,}")
    dates = df_all["MONITORING_PERIOD_END_DATE"].dropna()
    if not dates.empty:
        m6.metric("Latest Data", dates.max().strftime("%b %Y"))
    else:
        m6.metric("Latest Data", "\u2014")

    # ── Charts ──
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown('<div class="pm-section-title">Exceedances by % Over Limit</div>', unsafe_allow_html=True)
        st.markdown('<div class="pm-section-sub">Distribution by range</div>', unsafe_allow_html=True)
        st.plotly_chart(exceedance_range_chart(df_all), use_container_width=True)

    with chart_right:
        st.markdown('<div class="pm-section-title">Monthly Trend</div>', unsafe_allow_html=True)
        st.markdown('<div class="pm-section-sub">Exceedance count over time</div>', unsafe_allow_html=True)
        st.plotly_chart(monthly_trend_chart(df_all), use_container_width=True)

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

    chart_left2, chart_right2 = st.columns(2)
    with chart_left2:
        st.markdown('<div class="pm-section-title">Top Counties</div>', unsafe_allow_html=True)
        st.markdown('<div class="pm-section-sub">By exceedance count</div>', unsafe_allow_html=True)
        st.plotly_chart(county_bar_chart(df_all), use_container_width=True)

    with chart_right2:
        st.markdown('<div class="pm-section-title">Top Parameters</div>', unsafe_allow_html=True)
        st.markdown('<div class="pm-section-sub">Most frequently exceeded</div>', unsafe_allow_html=True)
        st.plotly_chart(top_parameters_chart(df_all), use_container_width=True)

    st.markdown('<hr>', unsafe_allow_html=True)
    st.info("Raw reported data, not a compliance determination. Data sourced from EPA ECHO system.")
