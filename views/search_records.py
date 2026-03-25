import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

from state_config import APP_NAME, APP_TAGLINE, STATE_NAME, CONTACT_EMAIL


def render_search_records(df_all, permit_summary, build_permit_summary):
    """Render the Search Records page.

    Args:
        df_all: Full exceedance DataFrame.
        permit_summary: Per-permit summary DataFrame.
        build_permit_summary: Function to rebuild summary from filtered data.
    """
    # ── HERO ──
    st.markdown("""
    <div class="pm-hero">
        <div class="pm-eyebrow">{APP_TAGLINE}</div>
        <div class="pm-headline">Track permit activity.<br>Get alerted when <em>limits are exceeded.</em></div>
        <div class="pm-subhead">
            {APP_NAME} pulls raw discharge monitoring data from the EPA ECHO system
            and surfaces it in one place — for attorneys, advocates, and communities who need quick answers.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── ACCESS CHECK (inline) ──
    if not st.session_state.get("is_paid_user", False):
        _ac_col1, _ac_col2 = st.columns([3, 1])
        with _ac_col1:
            _access_email = st.text_input(
                "Account email", placeholder="you@example.com",
                key="access_email", label_visibility="collapsed",
            )
        with _ac_col2:
            _check_clicked = st.button("Check Access", use_container_width=True)
        if _check_clicked:
            if _access_email and _access_email.strip():
                try:
                    from supabase import create_client as _sb_access
                    from utils.secrets import get_secret
                    _sb_ac = _sb_access(get_secret("supabase", "url"), get_secret("supabase", "key"))
                    _paid_result = (
                        _sb_ac.table("signups")
                        .select("email, is_paid")
                        .eq("email", _access_email.strip().lower())
                        .eq("is_paid", True)
                        .limit(1)
                        .execute()
                    )
                    if _paid_result.data:
                        st.session_state.is_paid_user = True
                        st.rerun()
                    else:
                        st.caption("{APP_NAME} Pro provides expanded access to publicly available EPA ECHO discharge monitoring data. Subscription does not guarantee data accuracy, completeness, or timeliness. See Terms of Service for details.")
                        st.warning(
                            "No active Pro subscription found for that email. "
                            "[Upgrade to {APP_NAME} Pro →]"
                            "(https://buy.stripe.com/4gM00jeJV6We5wI0Q41Nu00)"
                        )
                except Exception:
                    st.caption("{APP_NAME} Pro provides expanded access to publicly available EPA ECHO discharge monitoring data. Subscription does not guarantee data accuracy, completeness, or timeliness. See Terms of Service for details.")
                    st.warning(
                        "Could not verify account. "
                        "[Upgrade to {APP_NAME} Pro →]"
                        "(https://buy.stripe.com/4gM00jeJV6We5wI0Q41Nu00)"
                    )
            else:
                st.warning("Please enter your email to check access.")
    else:
        st.success("Pro Member — Full access")

    # ── STAT STRIP ──
    total_records = len(df_all)
    dates = df_all["NON_COMPLIANCE_DATE"].dropna()
    if not dates.empty:
        date_range_str = f"{dates.min().year}\u2013{dates.max().year}"
    else:
        date_range_str = "\u2014"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="pm-stat-num">{total_records:,}</div><div class="pm-stat-label">Records Tracked</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="pm-stat-num">{date_range_str}</div><div class="pm-stat-label">Date Range</div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="pm-stat-num">EPA ECHO</div><div class="pm-stat-label">Data Source</div>', unsafe_allow_html=True)
    with col4:
        st.markdown('<div class="pm-stat-num">Daily</div><div class="pm-stat-label">Alert Frequency</div>', unsafe_allow_html=True)

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)
    st.markdown('<hr>', unsafe_allow_html=True)

    # ── SEARCH FILTERS ──
    st.markdown('<div class="pm-section-title">Search Exceedance Records</div>', unsafe_allow_html=True)
    st.markdown('<div class="pm-section-sub">Filter by facility, permit, county, parameter, industry, or date range</div>', unsafe_allow_html=True)

    # Build dropdown options
    county_options = ["All Counties"] + sorted(df_all.loc[df_all["COUNTY_NAME"] != "Unknown", "COUNTY_NAME"].unique().tolist())
    param_options = ["All Parameters"] + sorted(df_all["PARAMETER"].unique().tolist())
    facility_type_options = ["All Facility Types"] + sorted(
        df_all.loc[df_all["SIC_DESC"] != "", "SIC_DESC"].unique().tolist()
    )

    # Compute date bounds for date pickers
    _nc_dates = df_all["NON_COMPLIANCE_DATE"].dropna()
    _date_min = _nc_dates.min().date() if not _nc_dates.empty else datetime(2021, 1, 1).date()
    _date_max = _nc_dates.max().date() if not _nc_dates.empty else datetime.now().date()

    # Wrap inputs in st.form so all values are submitted together
    with st.form("search_form"):
        # Row 1: Facility name (wide) | Permit number
        fr1a, fr1b = st.columns([3, 2])
        with fr1a:
            filter_facility = st.text_input("Facility name", placeholder="e.g., Municipal Authority", key="filter_facility")
        with fr1b:
            filter_permit = st.text_input("Permit number", placeholder="e.g., TX0255858", key="filter_permit")

        # Row 2: County | Parameter | Date start | Date end
        fr2a, fr2b, fr2c, fr2d = st.columns([2, 2, 1.5, 1.5])
        with fr2a:
            filter_county = st.selectbox("County", county_options, index=0, key="filter_county")
        with fr2b:
            filter_param = st.selectbox("Parameter", param_options, index=0, key="filter_param")
        with fr2c:
            filter_date_start = st.date_input("Date from", value=_date_min, min_value=_date_min, max_value=_date_max, key="filter_date_start")
        with fr2d:
            filter_date_end = st.date_input("Date to", value=_date_max, min_value=_date_min, max_value=_date_max, key="filter_date_end")

        # Row 3: Facility Type | Industry Code
        fr3a, fr3b = st.columns([3, 2])
        with fr3a:
            filter_facility_type = st.selectbox("Facility Type (SIC)", facility_type_options, index=0, key="filter_facility_type")
        with fr3b:
            filter_industry_code = st.text_input("Industry Code", placeholder="SIC or NAICS code, e.g., 4952", key="filter_industry_code")

        # Submit button inside the form
        search_btn = st.form_submit_button("Search Records", use_container_width=False)

    # Determine whether any filter is active
    has_facility = bool(filter_facility and filter_facility.strip())
    has_permit = bool(filter_permit and filter_permit.strip())
    has_county = filter_county != "All Counties"
    has_param = filter_param != "All Parameters"
    has_date_start = filter_date_start != _date_min
    has_date_end = filter_date_end != _date_max
    has_facility_type = filter_facility_type != "All Facility Types"
    has_industry_code = bool(filter_industry_code and filter_industry_code.strip())
    any_filter_active = has_facility or has_permit or has_county or has_param or has_date_start or has_date_end or has_facility_type or has_industry_code

    # If Search was clicked, store filter state
    if search_btn:
        if any_filter_active:
            st.session_state.selected_permit = "FILTERED"
        else:
            st.session_state.selected_permit = "ALL"
    # On first load (no selection yet), default to ALL permits view
    if st.session_state.selected_permit is None:
        st.session_state.selected_permit = "ALL"

    # ── RESULTS ──
    if st.session_state.selected_permit:
        st.markdown('<hr>', unsafe_allow_html=True)

        # ── FILTERED RESULTS ──
        if st.session_state.selected_permit == "FILTERED":
            # Apply filters to raw data
            filtered = df_all
            active_filters = []
            if has_facility:
                filtered = filtered[filtered["PF_NAME"].str.contains(filter_facility.strip(), case=False, na=False)]
                active_filters.append(f"Facility: {filter_facility.strip()}")
            if has_permit:
                filtered = filtered[filtered["PERMIT_NUMBER"].str.contains(filter_permit.strip(), case=False, na=False)]
                active_filters.append(f"Permit: {filter_permit.strip()}")
            if has_county:
                filtered = filtered[filtered["COUNTY_NAME"] == filter_county]
                active_filters.append(f"County: {filter_county}")
            if has_param:
                filtered = filtered[filtered["PARAMETER"] == filter_param]
                active_filters.append(f"Parameter: {filter_param}")
            if has_date_start:
                filtered = filtered[filtered["NON_COMPLIANCE_DATE"] >= pd.Timestamp(filter_date_start)]
                active_filters.append(f"From: {filter_date_start}")
            if has_date_end:
                filtered = filtered[filtered["NON_COMPLIANCE_DATE"] <= pd.Timestamp(filter_date_end)]
                active_filters.append(f"To: {filter_date_end}")
            if has_facility_type:
                filtered = filtered[filtered["SIC_DESC"] == filter_facility_type]
                active_filters.append(f"Facility Type: {filter_facility_type}")
            if has_industry_code:
                code = filter_industry_code.strip()
                filtered = filtered[
                    filtered["SIC_CODE"].str.contains(code, case=False, na=False) |
                    filtered["NAICS_CODE"].str.contains(code, case=False, na=False)
                ]
                active_filters.append(f"Industry Code: {code}")

            # Build summary from filtered records
            filter_summary = build_permit_summary(filtered)

            filter_desc = " + ".join(active_filters)
            st.markdown(f'<div class="pm-section-title">Filtered Results</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="pm-section-sub">{len(filter_summary)} permits found &mdash; {filter_desc}</div>', unsafe_allow_html=True)

            if filter_summary.empty:
                st.warning("No exceedance records match your filters. Try broadening your search.")
            else:
                _total_permits = len(filter_summary)
                df_display = filter_summary.sort_values("exceedance_count", ascending=False).copy()
                if not st.session_state.get("is_paid_user", False) and len(df_display) > 20:
                    df_display = df_display.head(20)
                    st.caption("{APP_NAME} Pro provides expanded access to publicly available EPA ECHO discharge monitoring data. Subscription does not guarantee data accuracy, completeness, or timeliness. See Terms of Service for details.")
                    st.warning(
                        f"Free preview: Showing 20 of {_total_permits:,} results. "
                        "[Upgrade to {APP_NAME} Pro →]"
                        "(https://buy.stripe.com/4gM00jeJV6We5wI0Q41Nu00)"
                    )
                else:
                    df_display = df_display.head(100)
                df_display["worst_pct"] = df_display["worst_pct"].apply(
                    lambda x: ">9,999%" if pd.notna(x) and x > 9999 else (f"+{x:.0f}%" if pd.notna(x) else "\u2014")
                )
                df_display = df_display[["PERMIT_NUMBER", "facility_name", "county", "exceedance_count", "worst_pct"]]
                df_display.columns = ["Permit #", "Facility", "County", "Exceedances", "Highest % Over"]

                st.markdown("""
<div style="background: #fff8e1; border: 1px solid #ffe082; border-radius: 8px; padding: 16px 20px; margin: 16px 0; font-size: 14px; line-height: 1.6; color: #5d4037;">
    <strong>Data Disclaimer</strong><br>
    Exceedance data shown here reflects values reported to the EPA ECHO (Enforcement and Compliance History Online) system for {STATE_NAME} NPDES permits and compared against permit limits on file. This data <strong>may not reflect current facility
    status</strong>. Reported exceedances may be subject to variances, consent orders, compliance schedules,
    reporting corrections, or other regulatory context not captured on this platform.<br><br>
    {APP_NAME} is an informational tool only. It does not make compliance determinations and is not a substitute
    for independent verification of facility records. No information on this platform constitutes legal advice.<br><br>
    <strong>Facility operators:</strong> To report a data concern or request a correction review, contact
    <a href="mailto:{CONTACT_EMAIL}" style="color: #5d4037;">{CONTACT_EMAIL}</a>.
</div>
""", unsafe_allow_html=True)
                st.caption("Click any row to view permit details")
                event = st.dataframe(df_display, use_container_width=True, hide_index=True,
                                     on_select="rerun", selection_mode="single-row", key="filtered_results")
                if event.selection.rows:
                    selected_idx = event.selection.rows[0]
                    st.session_state.selected_permit = df_display.iloc[selected_idx]["Permit #"]
                    st.rerun()

        # ── ALL PERMITS VIEW (default / no filters) ──
        elif st.session_state.selected_permit == "ALL":
            total_facilities = permit_summary["PERMIT_NUMBER"].nunique()
            total_ex = len(df_all)
            unique_params = df_all["PARAMETER"].nunique()
            over_100 = (df_all["pct_over"] > 100).sum()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Facilities", total_facilities)
            m2.metric("Total Exceedances", f"{total_ex:,}")
            m3.metric("Parameters Tracked", unique_params)
            m4.metric("Over 100% of Limit", f"{over_100:,}")

            # ── CTA BANNER ──
            st.markdown("""
            <div class="pm-cta-banner">
                <div>
                    <div class="pm-cta-text">Get notified when facilities exceed permit limits</div>
                    <div class="pm-cta-sub">Raw reported data, not a compliance determination</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Sign Up for Email Alerts", key="cta_email_alerts"):
                st.session_state.nav_page = "Email Alerts"
                st.rerun()

            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            st.markdown('<div class="pm-section-title">All Permits</div>', unsafe_allow_html=True)
            st.markdown('<div class="pm-section-sub">Sourced from EPA ECHO — for informational purposes only</div>', unsafe_allow_html=True)

            _total_all = len(permit_summary)
            if not st.session_state.get("is_paid_user", False) and _total_all > 20:
                df_display = permit_summary.sort_values("exceedance_count", ascending=False).head(20).copy()
                st.caption("{APP_NAME} Pro provides expanded access to publicly available EPA ECHO discharge monitoring data. Subscription does not guarantee data accuracy, completeness, or timeliness. See Terms of Service for details.")
                st.warning(
                    f"Free preview: Showing 20 of {_total_all:,} results. "
                    "[Upgrade to {APP_NAME} Pro →]"
                    "(https://buy.stripe.com/4gM00jeJV6We5wI0Q41Nu00)"
                )
            else:
                df_display = permit_summary.sort_values("exceedance_count", ascending=False).head(50).copy()

            # Flag: frequency + recency triage
            _now = pd.Timestamp.now()
            _12m_ago = _now - pd.DateOffset(months=12)
            _24m_ago = _now - pd.DateOffset(months=24)
            _recent_permits = set(
                df_all.loc[df_all["MONITORING_PERIOD_END_DATE"] >= _12m_ago, "PERMIT_NUMBER"].unique()
            )
            _24m_counts = (
                df_all.loc[df_all["MONITORING_PERIOD_END_DATE"] >= _24m_ago]
                .groupby("PERMIT_NUMBER").size()
            )
            def _assign_flag(permit):
                if permit in _recent_permits:
                    if _24m_counts.get(permit, 0) >= 3:
                        return "Active"
                    return "Recent"
                return "Historical"
            df_display["flag"] = df_display["PERMIT_NUMBER"].apply(_assign_flag)
            df_display["worst_pct"] = df_display["worst_pct"].apply(
                lambda x: ">9,999%" if pd.notna(x) and x > 9999 else (f"+{x:.0f}%" if pd.notna(x) else "\u2014")
            )
            df_display = df_display[["PERMIT_NUMBER", "facility_name", "county", "exceedance_count", "worst_pct", "flag"]]
            df_display.columns = ["Permit #", "Facility", "County", "Exceedances", "Highest % Over", "Flag"]

            st.markdown("""
<div style="background: #fff8e1; border: 1px solid #ffe082; border-radius: 8px; padding: 16px 20px; margin: 16px 0; font-size: 14px; line-height: 1.6; color: #5d4037;">
    <strong>Data Disclaimer</strong><br>
    Exceedance data shown here reflects values reported to the EPA ECHO (Enforcement and Compliance History Online) system for {STATE_NAME} NPDES permits and compared against permit limits on file. This data <strong>may not reflect current facility
    status</strong>. Reported exceedances may be subject to variances, consent orders, compliance schedules,
    reporting corrections, or other regulatory context not captured on this platform.<br><br>
    {APP_NAME} is an informational tool only. It does not make compliance determinations and is not a substitute
    for independent verification of facility records. No information on this platform constitutes legal advice.<br><br>
    <strong>Facility operators:</strong> To report a data concern or request a correction review, contact
    <a href="mailto:{CONTACT_EMAIL}" style="color: #5d4037;">{CONTACT_EMAIL}</a>.
</div>
""", unsafe_allow_html=True)
            st.caption("Click any row to view permit details")
            event = st.dataframe(df_display, use_container_width=True, hide_index=True,
                                 on_select="rerun", selection_mode="single-row", key="all_permits")
            if event.selection.rows:
                selected_idx = event.selection.rows[0]
                st.session_state.selected_permit = df_display.iloc[selected_idx]["Permit #"]
                st.rerun()

        # ── INDIVIDUAL PERMIT VIEW ──
        elif st.session_state.selected_permit in df_all["PERMIT_NUMBER"].values:
            if st.button("\u2190 Back to results"):
                # Return to filtered view if a search was active, otherwise ALL
                st.session_state.selected_permit = "FILTERED" if any_filter_active else "ALL"
                st.rerun()

            permit_num = st.session_state.selected_permit
            permit_rows = df_all[df_all["PERMIT_NUMBER"] == permit_num].copy()
            # Apply active search filters to permit detail view
            if has_param:
                permit_rows = permit_rows[permit_rows["PARAMETER"] == filter_param]
            if has_date_start:
                permit_rows = permit_rows[permit_rows["NON_COMPLIANCE_DATE"] >= pd.Timestamp(filter_date_start)]
            if has_date_end:
                permit_rows = permit_rows[permit_rows["NON_COMPLIANCE_DATE"] <= pd.Timestamp(filter_date_end)]
            facility_name = df_all.loc[df_all["PERMIT_NUMBER"] == permit_num, "PF_NAME"].iloc[0]
            county = df_all.loc[df_all["PERMIT_NUMBER"] == permit_num, "COUNTY_NAME"].iloc[0]
            sic_desc = df_all.loc[df_all["PERMIT_NUMBER"] == permit_num, "SIC_DESC"].iloc[0]
            sic_code = df_all.loc[df_all["PERMIT_NUMBER"] == permit_num, "SIC_CODE"].iloc[0]
            naics_desc = df_all.loc[df_all["PERMIT_NUMBER"] == permit_num, "NAICS_DESC"].iloc[0]
            naics_code = df_all.loc[df_all["PERMIT_NUMBER"] == permit_num, "NAICS_CODE"].iloc[0]
            exc_count = len(permit_rows)
            param_count = permit_rows["PARAMETER"].nunique()
            p_dates = permit_rows["NON_COMPLIANCE_DATE"].dropna()
            if not p_dates.empty:
                date_range_label = f"{p_dates.min().strftime('%b %Y')} \u2013 {p_dates.max().strftime('%b %Y')}"
            else:
                date_range_label = "\u2014"

            # Build industry info line
            industry_parts = []
            if sic_desc:
                industry_parts.append(f"{sic_desc} (SIC {sic_code})" if sic_code else sic_desc)
            if naics_desc:
                industry_parts.append(f"{naics_desc} (NAICS {naics_code})" if naics_code else naics_desc)
            industry_line = " &nbsp;&middot;&nbsp; ".join(industry_parts)
            industry_html = f'<div style="font-family:\'Source Sans 3\',sans-serif;font-size:13px;color:#8a8580;margin-top:4px;">{industry_line}</div>' if industry_line else ""

            st.markdown(f"""
            <div class="pm-card">
                <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:2px;
                            text-transform:uppercase;color:#b0aba6;margin-bottom:6px;">Permit Record</div>
                <div style="font-family:'Libre Baskerville',serif;font-size:26px;font-weight:700;
                            color:#1a1814;margin-bottom:4px;">{facility_name}</div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:15px;color:#6b6560;">
                    {permit_num} &nbsp;&middot;&nbsp; {county} County
                </div>
                {industry_html}
            </div>
            """, unsafe_allow_html=True)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("County", county)
            m2.metric("Reported Exceedances", exc_count)
            m3.metric("Parameters", param_count)
            m4.metric("Date Range", date_range_label)

            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

            if not permit_rows.empty:
                st.markdown('<div class="pm-section-title">DMR Exceedance History</div>', unsafe_allow_html=True)
                st.markdown('<div class="pm-section-sub">Reported values exceeding permit limits \u2014 raw data only, not a legal determination</div>', unsafe_allow_html=True)

                history = permit_rows[["MONITORING_PERIOD_END_DATE", "PARAMETER", "PERMIT_VALUE",
                                       "SAMPLE_VALUE", "pct_over", "direction"]].copy()
                history = history.sort_values("MONITORING_PERIOD_END_DATE", ascending=False)
                history["period"] = history["MONITORING_PERIOD_END_DATE"].dt.strftime("%Y-%m").fillna("\u2014")
                history["PERMIT_VALUE"] = pd.to_numeric(history["PERMIT_VALUE"], errors="coerce")
                history["SAMPLE_VALUE"] = pd.to_numeric(history["SAMPLE_VALUE"], errors="coerce")

                rows_html = ""
                for _, row in history.iterrows():
                    pct = row["pct_over"]
                    direction = row.get("direction", "Over")
                    if pd.notna(pct) and pct > 0:
                        dir_label = "over limit" if direction == "Over" else "under minimum"
                        pct_str = ">9,999" if pct > 9999 else f"+{pct:.1f}"
                        badge = f'<span class="badge-over">{pct_str}% {dir_label}</span>'
                    else:
                        badge = '<span class="badge-within">Within limit</span>'

                    limit_num = f"{row['PERMIT_VALUE']:.4g}" if pd.notna(row["PERMIT_VALUE"]) else "\u2014"
                    limit_val = f'{limit_num} <span style="font-size:11px;color:#6b7280;">\u2191 min</span>' if direction == "Under" else limit_num
                    sample_val = f"{row['SAMPLE_VALUE']:.4g}" if pd.notna(row["SAMPLE_VALUE"]) else "\u2014"

                    rows_html += f"""
                    <tr>
                      <td style="padding:14px 12px;border-bottom:1px solid #f0ece8;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#6b6560;">{row['period']}</td>
                      <td style="padding:14px 12px;border-bottom:1px solid #f0ece8;">{row['PARAMETER']}</td>
                      <td style="padding:14px 12px;border-bottom:1px solid #f0ece8;font-family:'IBM Plex Mono',monospace;">{limit_val}</td>
                      <td style="padding:14px 12px;border-bottom:1px solid #f0ece8;font-family:'IBM Plex Mono',monospace;">{sample_val}</td>
                      <td style="padding:14px 12px;border-bottom:1px solid #f0ece8;">{badge}</td>
                    </tr>"""

                table_html = f"""
                <table style="width:100%;border-collapse:collapse;font-family:'Source Sans 3',sans-serif;font-size:14px;">
                  <thead>
                    <tr style="background:#f8f7f5;">
                      <th style="padding:12px;text-align:left;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#b0aba6;font-weight:500;">Period</th>
                      <th style="padding:12px;text-align:left;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#b0aba6;font-weight:500;">Parameter</th>
                      <th style="padding:12px;text-align:left;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#b0aba6;font-weight:500;">Permit Limit</th>
                      <th style="padding:12px;text-align:left;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#b0aba6;font-weight:500;">Reported Value</th>
                      <th style="padding:12px;text-align:left;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#b0aba6;font-weight:500;">Status</th>
                    </tr>
                  </thead>
                  <tbody>{rows_html}</tbody>
                </table>"""

                st.markdown(table_html, unsafe_allow_html=True)

                st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
                st.info("Data Source: EPA ECHO System \u00b7 echo.epa.gov \u00b7 For informational purposes only. Independent verification recommended for any legal use.")

                st.markdown('<hr>', unsafe_allow_html=True)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Subscribe to Alerts", use_container_width=True):
                        st.session_state.nav_page = "Email Alerts"
                        st.rerun()
                with col2:
                    csv_export = history[["period", "PARAMETER", "PERMIT_VALUE", "SAMPLE_VALUE", "pct_over", "direction"]].copy()
                    csv_export.columns = ["Period", "Parameter", "Permit Limit", "Reported Value", "% Over Limit", "Direction"]
                    csv_bytes = csv_export.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="Export CSV",
                        data=csv_bytes,
                        file_name=f"{permit_num}_dmr_data.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

        else:
            st.warning(f"Permit {st.session_state.selected_permit} not found. Please check the number and try again.")
