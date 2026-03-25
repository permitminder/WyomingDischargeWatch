#!/usr/bin/env python3
"""
Daily Notification System

Reads subscriptions from Supabase (primary) and email_subscriptions.csv (fallback),
pulls recent exceedances from the configured state CSV, and sends HTML alert
emails via Gmail SMTP.

Supports three subscription types:
  - Permit Number: alerts for a specific NPDES permit
  - County: alerts for all exceedances in a county
  - Facility Type: alerts for exceedances at a given SIC industry type

Required environment variables:
  GMAIL_USER     - sender Gmail address (e.g. effluentwatch@gmail.com)
  GMAIL_PASS     - Gmail app password (not account password)
  SUPABASE_URL   - Supabase project URL (optional; falls back to CSV-only)
  SUPABASE_KEY   - Supabase anon key (optional; falls back to CSV-only)
"""

import os
import csv
import re
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import numpy as np
import pandas as pd

from state_config import (
    STATE_CODE, APP_NAME, DATA_FILE as _CFG_DATA_FILE,
    DOMAIN, MAILING_ADDRESS, CONTACT_EMAIL,
)

SUBSCRIPTIONS_FILE = "email_subscriptions.csv"
DATA_FILE = _CFG_DATA_FILE
FACILITY_LOOKUP = "utils/permit_facility_lookup.csv"
INDUSTRY_LOOKUP = "utils/permit_industry_lookup.csv"
ALERT_LOG_FILE = "alert_log.csv"
APP_URL = f"https://{DOMAIN}"

# Stat base codes that indicate minimum-limit parameters (pH floor, DO floor, etc.)
_MIN_CODES = {"IB", "DC", "ME", "MJ"}
# Only these parameters are true floors; other min-code params (Chlorine, Boron) have ceiling limits
_FLOOR_PARAMS = {"pH", "Oxygen, dissolved [DO]"}

# Permit number pattern: state code followed by alphanumerics
PERMIT_RE = re.compile(rf"\b({STATE_CODE}[A-Z0-9]{{3,}})\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Subscription loading
# ---------------------------------------------------------------------------

def load_supabase_subscriptions():
    """
    Load subscriptions from Supabase 'signups' table.

    Returns list of dicts: [{email, type, value}, ...]
    Returns empty list if Supabase is unavailable.
    """
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")

    if not url or not key:
        print("  Supabase credentials not set — skipping Supabase subscriptions.")
        return []

    try:
        from supabase import create_client
        client = create_client(url, key)
        result = client.table("signups").select("*").eq("verified", True).execute()
        rows = result.data if result.data else []
        print(f"  Loaded {len(rows)} subscription(s) from Supabase.")

        subs = []
        for row in rows:
            email = (row.get("email") or "").strip().lower()
            alert_type = (row.get("alert_type") or "").strip()
            alert_value = (row.get("alert_value") or "").strip()
            if email and alert_type and alert_value:
                subs.append({
                    "email": email,
                    "type": alert_type,
                    "value": alert_value,
                    "unsub_token": (row.get("unsub_token") or ""),
                })
        return subs
    except Exception as e:
        print(f"  Warning: Supabase query failed ({e}). Falling back to CSV only.")
        return []


def load_csv_subscriptions():
    """
    Load subscriptions from the legacy email_subscriptions.csv.

    CSV columns: email, facilities, frequency, created_date, status
    The 'facilities' field embeds a permit number, e.g.:
      "43RD STREET CONCRETE - PAG036362 (Allegheny)"

    Returns list of dicts: [{email, type, value}, ...]
    """
    subs = []
    try:
        with open(SUBSCRIPTIONS_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status", "").strip().lower() != "active":
                    continue
                email = row["email"].strip().lower()
                facilities_raw = row.get("facilities", "")
                permits = PERMIT_RE.findall(facilities_raw)
                for p in permits:
                    subs.append({"email": email, "type": "Permit Number", "value": p.upper()})
        if subs:
            print(f"  Loaded {len(subs)} subscription(s) from CSV.")
    except FileNotFoundError:
        pass
    return subs


def load_all_subscriptions():
    """
    Load and merge subscriptions from Supabase + CSV.

    Returns dict: {email: [{type, value}, ...]}
    Deduplicates by (email, type, value).
    """
    all_subs = load_supabase_subscriptions() + load_csv_subscriptions()

    # Deduplicate
    seen = set()
    merged = {}
    for sub in all_subs:
        key = (sub["email"], sub["type"], sub["value"].lower())
        if key in seen:
            continue
        seen.add(key)
        email = sub["email"]
        if email not in merged:
            merged[email] = []
        merged[email].append({
            "type": sub["type"],
            "value": sub["value"],
            "unsub_token": sub.get("unsub_token", ""),
        })

    return merged


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def filter_real_exceedances(df):
    """
    Keep only real exceedances using direct value comparison.

    - Drop Monitor & Report rows (PERMIT_VALUE == 0)
    - For minimum-limit codes (IB, DC, ME, MJ): keep only sample < limit
    - For maximum-limit codes: keep only sample > limit

    Mirrors the filtering logic in main.py load_data().
    The ECHO field VIOLATION_CONDITION is unreliable (~99% is "=" in ECHO data).
    """
    df["SAMPLE_VALUE"] = pd.to_numeric(df["SAMPLE_VALUE"], errors="coerce")
    df["PERMIT_VALUE"] = pd.to_numeric(df["PERMIT_VALUE"], errors="coerce")

    # Drop Monitor & Report rows (not real limits)
    df = df[df["PERMIT_VALUE"] != 0].copy()

    # Identify minimum-limit (floor) parameters by stat base code AND parameter name
    _stat = df["STAT_BASE_CODE"].fillna("").str.strip()
    _has_min_code = _stat.str.upper().isin(_MIN_CODES) | _stat.str.lower().str.contains("minimum", na=False)
    _is_floor_param = df["PARAMETER"].isin(_FLOOR_PARAMS) | df["PARAMETER"].str.contains("removal", case=False, na=False)
    _is_min = _has_min_code & _is_floor_param

    # Keep only rows where the value actually exceeds the limit
    has_limit = df["PERMIT_VALUE"] > 0
    real_min_exc = _is_min & has_limit & (df["SAMPLE_VALUE"] < df["PERMIT_VALUE"])
    real_max_exc = ~_is_min & has_limit & (df["SAMPLE_VALUE"] > df["PERMIT_VALUE"])
    df = df[real_min_exc | real_max_exc].copy()

    # Calculate pct_over for sorting/display (matches main.py logic)
    _stat = df["STAT_BASE_CODE"].fillna("").str.strip()
    _has_min_code = _stat.str.upper().isin(_MIN_CODES) | _stat.str.lower().str.contains("minimum", na=False)
    _is_floor_param = df["PARAMETER"].isin(_FLOOR_PARAMS) | df["PARAMETER"].str.contains("removal", case=False, na=False)
    _is_min = _has_min_code & _is_floor_param
    has_limit = df["PERMIT_VALUE"] > 0

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

    return df


def load_exceedances():
    """Load exceedance data with facility names, county, and industry info."""
    try:
        df = pd.read_csv(DATA_FILE, low_memory=False)
        raw_count = len(df)
        df = filter_real_exceedances(df)
        print(f"Loaded {raw_count:,} raw records, filtered to {len(df):,} real exceedances")
    except FileNotFoundError:
        print(f"ERROR: Data file not found: {DATA_FILE}")
        return pd.DataFrame()
    except Exception as e:
        print(f"ERROR loading data: {e}")
        return pd.DataFrame()

    # Merge facility names and county from lookup
    try:
        lookup = pd.read_csv(FACILITY_LOOKUP)
        lookup = lookup.drop_duplicates(subset="PERMIT_NUMBER", keep="first")
        if "PF_NAME" not in df.columns:
            df = df.merge(lookup[["PERMIT_NUMBER", "PF_NAME"]], on="PERMIT_NUMBER", how="left")
        if "COUNTY_NAME" not in df.columns or df["COUNTY_NAME"].isna().all():
            if "COUNTY_NAME" in df.columns:
                df = df.drop(columns=["COUNTY_NAME"])
            df = df.merge(lookup[["PERMIT_NUMBER", "COUNTY_NAME"]], on="PERMIT_NUMBER", how="left")
    except FileNotFoundError:
        print(f"  Warning: {FACILITY_LOOKUP} not found — county/facility names may be missing.")

    # Merge industry codes (SIC/NAICS) from industry lookup
    try:
        ind_lookup = pd.read_csv(INDUSTRY_LOOKUP, dtype=str)
        ind_lookup = ind_lookup.drop_duplicates(subset="PERMIT_NUMBER", keep="first")
        ind_lookup["PERMIT_NUMBER"] = ind_lookup["PERMIT_NUMBER"].str.strip().str.upper()
        df = df.merge(
            ind_lookup[["PERMIT_NUMBER", "SIC_CODE", "SIC_DESC", "NAICS_CODE", "NAICS_DESC"]],
            on="PERMIT_NUMBER", how="left"
        )
    except FileNotFoundError:
        print(f"  Warning: {INDUSTRY_LOOKUP} not found — industry filtering unavailable.")

    # Clean up
    for col in ["PF_NAME"]:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown Facility")
    for col in ["COUNTY_NAME"]:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")
    for col in ["SIC_CODE", "SIC_DESC", "NAICS_CODE", "NAICS_DESC"]:
        if col in df.columns:
            df[col] = df[col].fillna("").str.strip()
        else:
            df[col] = ""

    return df


# ---------------------------------------------------------------------------
# Exceedance queries by subscription type
# ---------------------------------------------------------------------------

def _rank_exceedances(df, limit):
    """Sort by worst exceedance first, then most recent. Return top N."""
    if df.empty:
        return df

    sort_cols, ascending = [], []
    if "pct_over" in df.columns:
        df["pct_over"] = pd.to_numeric(df["pct_over"], errors="coerce").fillna(0)
        sort_cols.append("pct_over")
        ascending.append(False)
    for date_col in ["NON_COMPLIANCE_DATE", "MONITORING_PERIOD_END_DATE"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            sort_cols.append(date_col)
            ascending.append(False)
            break
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=ascending)
    return df.head(limit)


def get_exceedances_for_permit(df, permit_number, limit=15):
    """Return top exceedances for a specific permit."""
    mask = df["PERMIT_NUMBER"].astype(str).str.upper().str.strip() == permit_number.upper()
    return _rank_exceedances(df[mask].copy(), limit)


def get_exceedances_for_county(df, county_name, limit=25):
    """Return top exceedances across all permits in a county."""
    mask = df["COUNTY_NAME"].str.strip().str.lower() == county_name.strip().lower()
    return _rank_exceedances(df[mask].copy(), limit)


def get_exceedances_for_facility_type(df, facility_type, limit=25):
    """Return top exceedances for facilities matching a SIC description."""
    mask = df["SIC_DESC"].str.strip().str.lower() == facility_type.strip().lower()
    return _rank_exceedances(df[mask].copy(), limit)


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

def cv(value, fallback="\u2014"):
    """Clean a cell value: map NaN/None/blank/literal-'nan' to fallback."""
    if value is None:
        return fallback
    s = str(value).strip()
    if s.lower() in ("nan", "none", ""):
        return fallback
    return s


def pct_over_display(raw_pct):
    """Format percent over limit with color hint."""
    val = cv(raw_pct)
    if val == "\u2014":
        return "\u2014", "#999"
    try:
        num = float(raw_pct)
        if num >= 200:
            return f"{num:.1f}%", "#dc2626"
        elif num >= 50:
            return f"{num:.1f}%", "#ea580c"
        elif num > 0:
            return f"{num:.1f}%", "#ca8a04"
        else:
            return f"{num:.1f}%", "#999"
    except (ValueError, TypeError):
        return val, "#999"


def _build_exceedance_table(exc_df):
    """Build an HTML table of exceedance rows."""
    # Detect date column
    date_col = None
    for col in ["NON_COMPLIANCE_DATE", "MONITORING_PERIOD_END_DATE"]:
        if col in exc_df.columns:
            date_col = col
            break

    html = """<table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tr style="background:#e8edf4;">
        <th style="padding:8px;text-align:left;color:#1e3a5f;">Date</th>
        <th style="padding:8px;text-align:left;color:#1e3a5f;">Facility</th>
        <th style="padding:8px;text-align:left;color:#1e3a5f;">Parameter</th>
        <th style="padding:8px;text-align:left;color:#1e3a5f;">Reported</th>
        <th style="padding:8px;text-align:left;color:#1e3a5f;">Limit</th>
        <th style="padding:8px;text-align:left;color:#1e3a5f;">% Over</th>
      </tr>"""

    for _, row in exc_df.iterrows():
        date_val = ""
        if date_col and pd.notna(row.get(date_col)):
            date_val = str(row[date_col])[:10]

        param = cv(row.get("PARAMETER"))
        facility = cv(row.get("PF_NAME"), "")
        if len(facility) > 30:
            facility = facility[:28] + ".."
        sample = cv(row.get("SAMPLE_VALUE"))
        limit = cv(row.get("PERMIT_VALUE"))
        permit = cv(row.get("PERMIT_NUMBER"), "")

        raw_pct = row.get("pct_over")
        pct_text, pct_color = pct_over_display(raw_pct)
        sample_color = "#dc2626" if sample != "\u2014" else "#999"

        # Deep link for permit number
        permit_link = ""
        if permit:
            permit_link = f' <a href="{APP_URL}/?permit={permit}" style="color:#1e3a5f;font-size:11px;text-decoration:none;">[view]</a>'

        html += f"""
      <tr style="border-bottom:1px solid #f0f0f0;">
        <td style="padding:8px;">{date_val}</td>
        <td style="padding:8px;font-size:12px;">{facility}{permit_link}</td>
        <td style="padding:8px;">{param}</td>
        <td style="padding:8px;color:{sample_color};font-weight:bold;">{sample}</td>
        <td style="padding:8px;">{limit}</td>
        <td style="padding:8px;color:{pct_color};font-weight:bold;">{pct_text}</td>
      </tr>"""

    html += "</table>"
    return html


def build_email_html(email, grouped_results):
    """
    Build the full HTML email body.

    grouped_results: list of dicts, each with:
      - type: "Permit Number", "County", or "Facility Type"
      - value: the subscription value
      - label: human-readable section header
      - df: DataFrame of matching exceedances
      - total_count: total matches before capping
    """
    today_str = datetime.now().strftime("%B %d, %Y")
    total_records = sum(r["total_count"] for r in grouped_results)
    sections_with_data = sum(1 for r in grouped_results if not r["df"].empty)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto;">

  <div style="background:#1e3a5f;color:white;padding:24px 30px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:22px;">{APP_NAME} Daily Alert</h1>
    <p style="margin:6px 0 0;opacity:.85;font-size:14px;">{today_str} &nbsp;|&nbsp; Exceedance Monitoring Summary</p>
  </div>

  <div style="padding:20px 30px;border-bottom:1px solid #e0e0e0;">
    <p>Your daily monitoring summary is ready. You have
       <strong>{len(grouped_results)}</strong> active alert(s).</p>
    <p><strong>{sections_with_data}</strong> alert(s) found matching exceedances
       (<strong>{total_records}</strong> record(s) total).</p>
    <p style="color:#888;font-size:12px;">
      Data sourced from EPA ECHO eDMR public reports. Values shown are self-reported
      by facilities. This is raw reported data, not a compliance determination.
    </p>
  </div>
"""

    for result in grouped_results:
        sub_type = result["type"]
        sub_value = result["value"]
        label = result["label"]
        exc_df = result["df"]
        total_count = result["total_count"]

        # Section header with context
        type_labels = {
            "Permit Number": "permit",
            "County": "county",
            "Facility Type": "facility type",
        }
        tracking_label = type_labels.get(sub_type, "filter")

        html += f"""
  <div style="padding:20px 30px;border-bottom:1px solid #e0e0e0;">
    <div style="background:#f5f5f5;padding:10px 15px;border-radius:5px;margin-bottom:15px;">
      <p style="margin:0 0 4px;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px;">
        Tracking {tracking_label}</p>
      <h3 style="margin:0;color:#1e3a5f;">{label}</h3>
    </div>
"""

        if exc_df.empty:
            html += '<p style="color:#16a34a;font-style:italic;">No exceedance records found for this alert.</p>'
        else:
            shown = len(exc_df)
            if total_count > shown:
                html += f"<p><strong>Showing top {shown} of {total_count} exceedance records — ranked worst first:</strong></p>"
            else:
                html += f"<p><strong>{shown} exceedance record(s) — ranked worst first:</strong></p>"
            html += _build_exceedance_table(exc_df)

        unsub_token = result.get("unsub_token", "")
        if unsub_token:
            html += f"""
    <p style="margin:12px 0 0;font-size:11px;color:#999;">
      <a href="{APP_URL}/?unsub={unsub_token}" style="color:#999;text-decoration:underline;">
        Unsubscribe from this alert</a>
    </p>"""

        html += "\n  </div>"

    html += f"""
  <div style="padding:20px 30px;text-align:center;border-bottom:1px solid #e0e0e0;">
    <a href="{APP_URL}"
       style="background:#1e3a5f;color:white;padding:10px 28px;text-decoration:none;
              border-radius:5px;display:inline-block;">
      View Full Details on {APP_NAME} &rarr;
    </a>
  </div>

  <hr style="border:none;border-top:1px solid #e0e0e0;margin:0;">
  <!-- Physical mailing address for CAN-SPAM compliance -->
  <div style="background:#f5f5f5;padding:20px 30px;text-align:center;
              font-size:12px;color:#888;border-radius:0 0 8px 8px;line-height:1.6;">
    <p style="margin:0;">
      This alert was sent by <a href="{APP_URL}" style="color:#1e3a5f;text-decoration:none;">{APP_NAME}</a>
      ({DOMAIN}) because you subscribed to exceedance alerts.
    </p>
    <p style="margin:10px 0;color:#999;font-size:11px;">
      Exceedance data reflects values reported to EPA ECHO and may not reflect current
      facility status. This is not a compliance determination or legal advice.
      Verify independently before taking action.
    </p>
    <p style="margin:10px 0 0;font-size:11px;">
      &copy; 2026 {APP_NAME} &middot;
      <a href="{APP_URL}" style="color:#1e3a5f;text-decoration:none;">{DOMAIN}</a><br>
      {MAILING_ADDRESS}
    </p>
    <p style="margin:6px 0 0;">
      <a href="{APP_URL}/?page=alerts" style="color:#1e3a5f;">Manage your subscriptions</a>
      &nbsp;|&nbsp;
      <a href="{APP_URL}/?page=terms" style="color:#1e3a5f;">Terms</a>
      &nbsp;|&nbsp;
      <a href="{APP_URL}/?page=privacy" style="color:#1e3a5f;">Privacy</a>
    </p>
  </div>

</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def send_email(recipient, subject, body_html, sender_email, sender_password):
    """Send via Gmail SMTP SSL. Returns True on success."""
    if not sender_password:
        print(f"  [DRY RUN] Would send '{subject}' to {recipient}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{APP_NAME} <{sender_email}>"
        msg["To"] = recipient
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)

        print(f"  Sent to {recipient}")
        return True
    except Exception as e:
        print(f"  Failed to send to {recipient}: {e}")
        return False


def log_alert(email, subscriptions, total_records, status):
    """Append one row to alert_log.csv."""
    file_exists = os.path.exists(ALERT_LOG_FILE)
    sub_desc = "|".join(f"{s['type']}:{s['value']}" for s in subscriptions)
    with open(ALERT_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "email", "subscriptions", "records_shown", "status"])
        writer.writerow([
            datetime.now().isoformat(),
            email,
            sub_desc,
            total_records,
            status,
        ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"\n{'='*60}")
    print(f"{APP_NAME} Daily Notification System ({STATE_CODE})")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    sender_email = os.environ.get("GMAIL_USER", "")
    sender_password = os.environ.get("GMAIL_PASS", "")

    if not sender_password:
        print("WARNING: GMAIL_PASS not set — running in dry-run mode (no emails sent).\n")

    # Load subscriptions from Supabase + CSV
    print("Loading subscriptions...")
    subscriptions = load_all_subscriptions()
    if not subscriptions:
        print("No active subscriptions found. Nothing to send. Exiting cleanly.")
        return

    total_subs = sum(len(v) for v in subscriptions.values())
    print(f"Active subscribers: {len(subscriptions)} ({total_subs} total alerts)\n")

    # Load exceedance data
    print("Loading exceedance data...")
    df = load_exceedances()
    if df.empty:
        print("ERROR: No data loaded. Cannot send meaningful alerts.")
        sys.exit(1)
    print()

    sent_count = 0
    skipped_count = 0
    failed_count = 0

    for email, subs in subscriptions.items():
        print(f"Processing: {email} ({len(subs)} alert(s))")

        grouped_results = []
        total_records = 0

        for sub in subs:
            sub_type = sub["type"]
            sub_value = sub["value"]

            if sub_type == "Permit Number":
                exc_df = get_exceedances_for_permit(df, sub_value)
                # Build label
                if not exc_df.empty and "PF_NAME" in exc_df.columns:
                    facility = exc_df["PF_NAME"].iloc[0]
                    label = f"{facility} ({sub_value})"
                else:
                    label = sub_value
                total_before_cap = len(df[df["PERMIT_NUMBER"].astype(str).str.upper().str.strip() == sub_value.upper()])

            elif sub_type == "County":
                exc_df = get_exceedances_for_county(df, sub_value)
                label = f"{sub_value} County"
                total_before_cap = len(df[df["COUNTY_NAME"].str.strip().str.lower() == sub_value.strip().lower()])

            elif sub_type == "Facility Type":
                exc_df = get_exceedances_for_facility_type(df, sub_value)
                label = sub_value
                total_before_cap = len(df[df["SIC_DESC"].str.strip().str.lower() == sub_value.strip().lower()])

            else:
                print(f"  Unknown subscription type '{sub_type}' — skipping.")
                continue

            print(f"  {sub_type}: {sub_value} — {len(exc_df)} record(s)")
            total_records += len(exc_df)
            grouped_results.append({
                "type": sub_type,
                "value": sub_value,
                "label": label,
                "df": exc_df,
                "total_count": total_before_cap,
                "unsub_token": sub.get("unsub_token", ""),
            })

        if total_records == 0:
            print(f"  Skipping {email} — no exceedance records for any alert.")
            log_alert(email, subs, 0, "skipped_no_data")
            skipped_count += 1
            continue

        subject = f"{APP_NAME} Alert: {total_records} exceedance(s) — {datetime.now().strftime('%b %d, %Y')}"
        body = build_email_html(email, grouped_results)
        success = send_email(email, subject, body, sender_email, sender_password)

        if success:
            sent_count += 1
            log_alert(email, subs, total_records, "sent")
        else:
            failed_count += 1
            log_alert(email, subs, total_records, "dry_run" if not sender_password else "failed")

    print(f"\n{'='*60}")
    print(f"COMPLETE: {sent_count} sent, {skipped_count} skipped (no data), {failed_count} {'dry-run' if not sender_password else 'failed'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
