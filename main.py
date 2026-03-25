import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

from utils.styles import inject_css
from utils.secrets import get_secret
from views.search_records import render_search_records
from views.email_alerts import render_email_alerts
from views.dashboard import render_dashboard
from views.terms import show_terms_page
from views.privacy import show_privacy_page
from state_config import APP_NAME, APP_TAGLINE, DATA_FILE as _CFG_DATA_FILE, CONTACT_EMAIL, DOMAIN

# ── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=f"{APP_NAME} | {APP_TAGLINE}",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="auto"
)

# ── GLOBAL CSS ──────────────────────────────────────────────────────────────
inject_css()

# ── SESSION STATE ───────────────────────────────────────────────────────────
if 'selected_permit' not in st.session_state:
    st.session_state.selected_permit = None
if 'nav_page' not in st.session_state:
    st.session_state.nav_page = "Search Records"
if 'is_paid_user' not in st.session_state:
    st.session_state.is_paid_user = False
if 'current_view' not in st.session_state:
    st.session_state.current_view = "search"
if 'current_page' not in st.session_state:
    st.session_state.current_page = "search"

# ── URL QUERY PARAMS (deep links from email alerts) ───────────────────────
_params = st.query_params
if "permit" in _params:
    st.session_state.nav_page = "Search Records"
    st.session_state.selected_permit = _params["permit"].upper()
if "page" in _params:
    _page_map = {"search": "Search Records", "alerts": "Email Alerts", "dashboard": "Dashboard"}
    st.session_state.nav_page = _page_map.get(_params["page"], "Search Records")
if "verify" in _params:
    st.session_state.nav_page = "Email Alerts"
    st.session_state["_pending_verify"] = _params["verify"]
if "unsub" in _params:
    st.session_state.nav_page = "Email Alerts"
    st.session_state["_pending_unsub"] = _params["unsub"]

# ── SIDEBAR NAVIGATION ─────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style="font-family:'IBM Plex Mono',monospace;font-size:14px;font-weight:600;
            color:#1a1814;margin-bottom:16px;letter-spacing:0.3px;">
    <span style="display:inline-flex;align-items:center;justify-content:center;
                 width:22px;height:22px;border:1.5px solid #3a6b1a;border-radius:3px;
                 font-size:8px;color:#3a6b1a;font-weight:600;margin-right:6px;
                 vertical-align:middle;">EW</span>
    {APP_NAME}
</div>
""", unsafe_allow_html=True)
nav_page = st.sidebar.radio(
    "Navigate",
    ["Search Records", "Email Alerts", "Dashboard"],
    index=["Search Records", "Email Alerts", "Dashboard"].index(st.session_state.nav_page),
    label_visibility="collapsed",
)
st.session_state.nav_page = nav_page

# ── DATA ────────────────────────────────────────────────────────────────────
DATA_FILE = _CFG_DATA_FILE
FACILITY_LOOKUP = "utils/permit_facility_lookup.csv"
INDUSTRY_LOOKUP = "utils/permit_industry_lookup.csv"

@st.cache_data
def load_data():
    """Load real exceedance data from EPA ECHO CSV."""
    _COLS = [
        "PERMIT_NUMBER", "PF_NAME", "COUNTY_NAME",
        "PARAMETER", "NON_COMPL_CATEGORY_DESC",
        "NON_COMPLIANCE_DATE", "MONITORING_PERIOD_END_DATE",
        "SAMPLE_VALUE", "PERMIT_VALUE",
        "VIOLATION_CONDITION", "STAT_BASE_CODE",
    ]
    _DTYPES = {
        "PERMIT_NUMBER":           "string",
        "PF_NAME":                 "string",
        "COUNTY_NAME":             "category",
        "PARAMETER":               "category",
        "NON_COMPL_CATEGORY_DESC": "category",
        "VIOLATION_CONDITION":     "category",
        "STAT_BASE_CODE":          "category",
        "SAMPLE_VALUE":            "float32",
        "PERMIT_VALUE":            "float32",
    }
    df = pd.read_csv(DATA_FILE, usecols=_COLS)
    df = df.dropna(subset=["PARAMETER"])
    # Clean non-numeric values (e.g., "< 120.0") from numeric columns
    numeric_cols = [col for col in df.columns if col in ['DMR_VALUE_NMBR', 'LIMIT_VALUE_NMBR', 'VIOLATION_PCT']]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Backfill PF_NAME and COUNTY_NAME from facility lookup
    # (ECHO DMR data doesn't include these; lookup built from prior records)
    try:
        lookup = pd.read_csv(FACILITY_LOOKUP)
        lookup = lookup.drop_duplicates(subset="PERMIT_NUMBER", keep="first")
        if "PF_NAME" not in df.columns:
            df = df.merge(lookup[["PERMIT_NUMBER", "PF_NAME"]], on="PERMIT_NUMBER", how="left")
        if df["COUNTY_NAME"].isna().all():
            df = df.drop(columns=["COUNTY_NAME"]).merge(
                lookup[["PERMIT_NUMBER", "COUNTY_NAME"]], on="PERMIT_NUMBER", how="left"
            )
    except FileNotFoundError:
        pass

    # Backfill industry codes (SIC/NAICS) from industry lookup
    try:
        ind_lookup = pd.read_csv(INDUSTRY_LOOKUP, dtype=str)
        ind_lookup = ind_lookup.drop_duplicates(subset="PERMIT_NUMBER", keep="first")
        ind_lookup["PERMIT_NUMBER"] = ind_lookup["PERMIT_NUMBER"].str.strip().str.upper()
        df = df.merge(
            ind_lookup[["PERMIT_NUMBER", "SIC_CODE", "SIC_DESC", "NAICS_CODE", "NAICS_DESC"]],
            on="PERMIT_NUMBER", how="left"
        )
    except FileNotFoundError:
        for col in ["SIC_CODE", "SIC_DESC", "NAICS_CODE", "NAICS_DESC"]:
            if col not in df.columns:
                df[col] = ""

    # Fill NaN industry fields and strip whitespace
    for col in ["SIC_CODE", "SIC_DESC", "NAICS_CODE", "NAICS_DESC"]:
        df[col] = df[col].fillna("").str.strip()

    # Effluent exceedances only
    df = df[df["NON_COMPL_CATEGORY_DESC"].str.startswith("Effluent", na=False)].copy()

    # Parse dates
    df["NON_COMPLIANCE_DATE"] = pd.to_datetime(df["NON_COMPLIANCE_DATE"], format="mixed", errors="coerce")
    df["MONITORING_PERIOD_END_DATE"] = pd.to_datetime(df["MONITORING_PERIOD_END_DATE"], format="mixed", errors="coerce")

    # Clean columns — ensure PF_NAME exists (may be missing from CSV)
    df["COUNTY_NAME"] = df["COUNTY_NAME"].fillna("Unknown")
    if "PF_NAME" not in df.columns:
        df["PF_NAME"] = "Unknown Facility"
    df["PF_NAME"] = df["PF_NAME"].fillna("Unknown Facility")
    df["VIOLATION_CONDITION"] = df["VIOLATION_CONDITION"].fillna(">")
    df["SAMPLE_VALUE"] = pd.to_numeric(df["SAMPLE_VALUE"], errors="coerce")
    df["PERMIT_VALUE"] = pd.to_numeric(df["PERMIT_VALUE"], errors="coerce")

    # Drop rows where permit limit is 0 (Monitor & Report — not a real limit)
    df = df[df["PERMIT_VALUE"] != 0].copy()

    # Identify minimum-limit (floor) parameters by stat base code AND parameter name.
    # Only pH, dissolved oxygen, and percent-removal parameters are true floors.
    # Other parameters with min codes (e.g. Chlorine IB) have ceiling limits.
    _MIN_CODES = {"IB", "DC", "ME", "MJ"}
    _stat = df["STAT_BASE_CODE"].fillna("").str.strip()
    _has_min_code = _stat.str.upper().isin(_MIN_CODES) | _stat.str.lower().str.contains("minimum", na=False)
    _FLOOR_PARAMS = {"pH", "Oxygen, dissolved [DO]"}
    _is_floor_param = df["PARAMETER"].isin(_FLOOR_PARAMS) | df["PARAMETER"].str.contains("removal", case=False, na=False)
    _is_min = _has_min_code & _is_floor_param

    # Keep only real exceedances based on actual values, not VIOLATION_CONDITION
    # (VIOLATION_CONDITION is "=" for ~99% of ECHO data and can't be relied on)
    #   - Minimum-limit rows: exceedance = sample BELOW the floor
    #   - Maximum-limit rows: exceedance = sample ABOVE the cap
    has_limit = df["PERMIT_VALUE"] > 0
    real_min_exc = _is_min & has_limit & (df["SAMPLE_VALUE"] < df["PERMIT_VALUE"])
    real_max_exc = ~_is_min & has_limit & (df["SAMPLE_VALUE"] > df["PERMIT_VALUE"])
    df = df[real_min_exc | real_max_exc].copy()

    # Recalculate is_min after filtering (index changed)
    _stat = df["STAT_BASE_CODE"].fillna("").str.strip()
    _has_min_code = _stat.str.upper().isin(_MIN_CODES) | _stat.str.lower().str.contains("minimum", na=False)
    _is_floor_param = df["PARAMETER"].isin(_FLOOR_PARAMS) | df["PARAMETER"].str.contains("removal", case=False, na=False)
    _is_min = _has_min_code & _is_floor_param
    has_limit = df["PERMIT_VALUE"] > 0

    # Calculate percent deviation from limit
    df["pct_over"] = np.nan
    df.loc[~_is_min & has_limit, "pct_over"] = (
        (df.loc[~_is_min & has_limit, "SAMPLE_VALUE"] - df.loc[~_is_min & has_limit, "PERMIT_VALUE"])
        / df.loc[~_is_min & has_limit, "PERMIT_VALUE"] * 100
    )
    df.loc[_is_min & has_limit, "pct_over"] = (
        (df.loc[_is_min & has_limit, "PERMIT_VALUE"] - df.loc[_is_min & has_limit, "SAMPLE_VALUE"])
        / df.loc[_is_min & has_limit, "PERMIT_VALUE"] * 100
    )
    df["pct_over"] = df["pct_over"].round(1)

    df["direction"] = "Over"
    df.loc[_is_min, "direction"] = "Under"

    # Rolling 5-year window
    five_years_ago = pd.Timestamp.now() - pd.DateOffset(years=5)
    df = df[df["MONITORING_PERIOD_END_DATE"] >= five_years_ago].copy()

    return df


def build_permit_summary(_df):
    """Build a per-permit summary table from the raw exceedance data."""
    summary = _df.groupby("PERMIT_NUMBER").agg(
        facility_name=("PF_NAME", "first"),
        county=("COUNTY_NAME", "first"),
        exceedance_count=("PERMIT_NUMBER", "size"),
        worst_pct=("pct_over", "max"),
        avg_pct=("pct_over", "mean"),
    ).reset_index()
    summary["worst_pct"] = summary["worst_pct"].round(1)
    summary["avg_pct"] = summary["avg_pct"].round(1)
    return summary


df_all = load_data()
permit_summary = build_permit_summary(df_all)

# ── NAV BAR ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="pm-nav">
    <span class="pm-logo-mark">EW</span>
    <span class="pm-logo-text">{APP_NAME}</span>
</div>
""", unsafe_allow_html=True)

# ── EMAIL VERIFICATION HANDLER ─────────────────────────────────────────────
if st.session_state.get("_pending_verify"):
    _token = st.session_state.pop("_pending_verify")
    try:
        from supabase import create_client as _sb_client
        _sb = _sb_client(get_secret("supabase", "url"), get_secret("supabase", "key"))
        _result = (
            _sb.table("signups")
            .select("id, email, alert_type, alert_value, verified, created_at")
            .eq("verify_token", _token)
            .execute()
        )
        if not _result.data:
            st.error("Invalid or expired verification link.")
        elif _result.data[0].get("verified"):
            st.info("This subscription is already verified. You're all set!")
        else:
            _row = _result.data[0]
            _created = datetime.fromisoformat(_row["created_at"].replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - _created).total_seconds() > 48 * 3600:
                st.error(
                    "This verification link has expired. "
                    "Please sign up again to receive a fresh link."
                )
            else:
                _sb.table("signups").update({
                    "verified": True,
                    "verify_token": None,
                }).eq("id", _row["id"]).execute()
                st.success(
                    f"Email verified! You'll now receive alerts for "
                    f"**{_row['alert_type']}**: **{_row['alert_value']}**."
                )
    except Exception as e:
        st.error(f"Verification failed \u2014 please try again. ({e})")

# ── UNSUBSCRIBE HANDLER ──────────────────────────────────────────────────
if st.session_state.get("_pending_unsub"):
    _unsub_token = st.session_state.pop("_pending_unsub")
    try:
        from supabase import create_client as _sb_client2
        _sb2 = _sb_client2(get_secret("supabase", "url"), get_secret("supabase", "key"))
        _unsub_result = (
            _sb2.table("signups")
            .select("id, email, alert_type, alert_value")
            .eq("unsub_token", _unsub_token)
            .execute()
        )
        if not _unsub_result.data:
            st.error("Invalid or expired unsubscribe link.")
        else:
            _unsub_row = _unsub_result.data[0]
            _sb2.table("signups").delete().eq("id", _unsub_row["id"]).execute()
            st.success(
                f"You've been unsubscribed from **{_unsub_row['alert_type']}**: "
                f"**{_unsub_row['alert_value']}**. You will no longer receive these alerts."
            )
    except Exception as e:
        st.error(f"Unsubscribe failed \u2014 please try again. ({e})")

# ── PAGE DISPATCH ───────────────────────────────────────────────────────────
if st.session_state.current_view == "terms":
    show_terms_page()
elif st.session_state.current_view == "privacy":
    show_privacy_page()
elif nav_page == "Search Records":
    render_search_records(df_all, permit_summary, build_permit_summary)
elif nav_page == "Email Alerts":
    render_email_alerts(df_all)
elif nav_page == "Dashboard":
    render_dashboard(df_all, permit_summary)

# ── FOOTER ──────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align: center; color: #6b6560; font-size: 13px; margin-top: 40px; padding: 20px 0; border-top: 1px solid #e0ddd9;">
    © 2026 {APP_NAME} · Data sourced from EPA ECHO · For informational purposes only<br>
    Your searches are not logged or shared<br>
    <a href="mailto:{CONTACT_EMAIL}" style="color: #6b6560;">Report a Data Concern</a>
</div>
""", unsafe_allow_html=True)
# Add clickable navigation links below footer
footer_col1, footer_col2, footer_col3 = st.columns([1, 1, 1])
with footer_col1:
    if st.button("Terms of Service", key="footer_terms"):
        st.session_state.current_view = "terms"
        st.session_state.current_page = "terms"
        st.rerun()
with footer_col2:
    if st.button("Privacy Policy", key="footer_privacy"):
        st.session_state.current_view = "privacy"
        st.session_state.current_page = "privacy"
        st.rerun()
