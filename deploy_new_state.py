#!/usr/bin/env python3
"""
Deploy EffluentWatch for a new US state.

Usage:
    python deploy_new_state.py OH
    python deploy_new_state.py OH --app-name "BuckeyeWatch"

This script:
  1. Overwrites state_config.py with values for the target state
  2. Creates an empty CSV data file with correct headers
  3. Runs fetch_industry_codes.py to generate the industry lookup
  4. Prints a manual setup checklist
"""

import argparse
import csv
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# All 50 states + DC + territories with EPA region and timezone
# ---------------------------------------------------------------------------

STATES = {
    # EPA Region 1 — New England
    "CT": ("Connecticut",       1, "EST"), "ME": ("Maine",             1, "EST"),
    "MA": ("Massachusetts",     1, "EST"), "NH": ("New Hampshire",     1, "EST"),
    "RI": ("Rhode Island",      1, "EST"), "VT": ("Vermont",           1, "EST"),
    # EPA Region 2 — NY/NJ + territories
    "NJ": ("New Jersey",        2, "EST"), "NY": ("New York",          2, "EST"),
    "PR": ("Puerto Rico",       2, "AST"), "VI": ("U.S. Virgin Islands", 2, "AST"),
    # EPA Region 3 — Mid-Atlantic
    "DE": ("Delaware",          3, "EST"), "DC": ("District of Columbia", 3, "EST"),
    "MD": ("Maryland",          3, "EST"), "PA": ("Pennsylvania",      3, "EST"),
    "VA": ("Virginia",          3, "EST"), "WV": ("West Virginia",     3, "EST"),
    # EPA Region 4 — Southeast
    "AL": ("Alabama",           4, "CST"), "FL": ("Florida",           4, "EST"),
    "GA": ("Georgia",           4, "EST"), "KY": ("Kentucky",          4, "EST"),
    "MS": ("Mississippi",       4, "CST"), "NC": ("North Carolina",    4, "EST"),
    "SC": ("South Carolina",    4, "EST"), "TN": ("Tennessee",         4, "CST"),
    # EPA Region 5 — Great Lakes
    "IL": ("Illinois",          5, "CST"), "IN": ("Indiana",           5, "EST"),
    "MI": ("Michigan",          5, "EST"), "MN": ("Minnesota",         5, "CST"),
    "OH": ("Ohio",              5, "EST"), "WI": ("Wisconsin",         5, "CST"),
    # EPA Region 6 — South Central
    "AR": ("Arkansas",          6, "CST"), "LA": ("Louisiana",         6, "CST"),
    "NM": ("New Mexico",        6, "MST"), "OK": ("Oklahoma",          6, "CST"),
    "TX": ("Texas",             6, "CST"),
    # EPA Region 7 — Midwest
    "IA": ("Iowa",              7, "CST"), "KS": ("Kansas",            7, "CST"),
    "MO": ("Missouri",          7, "CST"), "NE": ("Nebraska",          7, "CST"),
    # EPA Region 8 — Mountains & Plains
    "CO": ("Colorado",          8, "MST"), "MT": ("Montana",           8, "MST"),
    "ND": ("North Dakota",      8, "CST"), "SD": ("South Dakota",      8, "CST"),
    "UT": ("Utah",              8, "MST"), "WY": ("Wyoming",           8, "MST"),
    # EPA Region 9 — Pacific Southwest + territories
    "AZ": ("Arizona",           9, "MST"), "CA": ("California",        9, "PST"),
    "HI": ("Hawaii",            9, "HST"), "NV": ("Nevada",            9, "PST"),
    "AS": ("American Samoa",    9, "SST"), "GU": ("Guam",              9, "ChST"),
    "MP": ("Northern Mariana Islands", 9, "ChST"),
    # EPA Region 10 — Pacific Northwest
    "AK": ("Alaska",           10, "AKST"), "ID": ("Idaho",            10, "MST"),
    "OR": ("Oregon",           10, "PST"),  "WA": ("Washington",       10, "PST"),
}

# CSV column headers from the existing tx_exceedances_launch_ready.csv
CSV_HEADERS = (
    "COUNTY_NAME,MUNICIPALITY_NAME,PF_NAME,PERMIT_NUMBER,PF_KIND,"
    "MONITORING_PERIOD_BEGIN_DATE,MONITORING_PERIOD_END_DATE,SUBMISSION_DATE,"
    "OUTFALL_NUMBER,NON_COMPLIANCE_DATE,NON_COMPL_TYPE_DESC,"
    "NON_COMPL_CATEGORY_DESC,PARAMETER,SAMPLE_VALUE,VIOLATION_CONDITION,"
    "PERMIT_VALUE,UNIT_OF_MEASURE,STAT_BASE_CODE,DISCHARGE_COMMENTS,"
    "FACILITY_COMMENTS,Effective_Result,Is_Violation,Permit_Limit_Clean,"
    "Exceedance_Delta,Percent_of_Limit,Percent_Over_Limit,Severity,"
    "Data_Quality_Flag,Sample_Date,Month_Bucket,Compliance_Period_Key,"
    "Source_File,Ingested_At,Row_Hash,Has_Industrial_Parameters,"
    "Chemical_Laundering_Candidate,ACTIVITY_ID,VERSION_NMBR,PERM_FEATURE_ID,"
    "PERM_FEATURE_TYPE_CODE,LIMIT_SET_ID,LIMIT_SET_DESIGNATOR,"
    "LIMIT_SET_SCHEDULE_ID,LIMIT_ID,LIMIT_BEGIN_DATE,LIMIT_END_DATE,"
    "NMBR_OF_SUBMISSION,NMBR_OF_REPORT,PARAMETER_CODE,"
    "MONITORING_LOCATION_CODE,STAY_TYPE_CODE,LIMIT_VALUE_ID,"
    "LIMIT_VALUE_TYPE_CODE,LIMIT_VALUE_NMBR,LIMIT_UNIT_CODE,LIMIT_UNIT_DESC,"
    "STANDARD_UNIT_CODE,STATISTICAL_BASE_TYPE_CODE,"
    "LIMIT_VALUE_QUALIFIER_CODE,OPTIONAL_MONITORING_FLAG,"
    "LIMIT_SAMPLE_TYPE_CODE,LIMIT_FREQ_OF_ANALYSIS_CODE,STAY_VALUE_NMBR,"
    "LIMIT_TYPE_CODE,DMR_EVENT_ID,DMR_SAMPLE_TYPE_CODE,"
    "DMR_FREQ_OF_ANALYSIS_CODE,REPORTED_EXCURSION_NMBR,DMR_FORM_VALUE_ID,"
    "VALUE_TYPE_CODE,DMR_VALUE_ID,DMR_VALUE_NMBR,DMR_UNIT_CODE,"
    "DMR_UNIT_DESC,VALUE_RECEIVED_DATE,DAYS_LATE,NODI_CODE,EXCEEDENCE_PCT,"
    "NPDES_VIOLATION_ID,VIOLATION_CODE,RNC_DETECTION_CODE,"
    "RNC_DETECTION_DATE,RNC_RESOLUTION_CODE,RNC_RESOLUTION_DATE,REGION,"
    "CHESAPEAKE_BAY_IND"
)


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def main():
    parser = argparse.ArgumentParser(
        description="Deploy EffluentWatch for a new US state."
    )
    parser.add_argument(
        "state_code",
        type=str,
        help="2-letter US state code (e.g., OH, CA, TX)",
    )
    parser.add_argument(
        "--app-name",
        type=str,
        default=None,
        help='Custom app name (default: "{State Name} Discharge Monitor")',
    )
    args = parser.parse_args()

    code = args.state_code.upper()
    if code not in STATES:
        print(f"ERROR: Unknown state code '{code}'.")
        print(f"Valid codes: {', '.join(sorted(STATES.keys()))}")
        sys.exit(1)

    state_name, epa_region, tz_label = STATES[code]

    # App name
    if args.app_name:
        app_name = args.app_name
    else:
        app_name = f"{state_name} Discharge Monitor"

    slug = slugify(app_name)
    data_file = f"{code.lower()}_exceedances_launch_ready.csv"
    contact_email = f"data@{slug}.org"
    domain = f"{slug}.org"

    print(f"\n{'='*60}")
    print(f"Deploying for: {state_name} ({code})")
    print(f"App Name:      {app_name}")
    print(f"Domain:        {domain}")
    print(f"EPA Region:    {epa_region}")
    print(f"Timezone:      {tz_label}")
    print(f"Data File:     {data_file}")
    print(f"{'='*60}\n")

    # ── Step 1: Overwrite state_config.py ──────────────────────────────────
    config_content = f'''"""
State configuration for this {app_name} instance.

All state-specific values are centralized here. To deploy for a new state,
run: python deploy_new_state.py <STATE_CODE>

This file is overwritten by deploy_new_state.py — do not add logic here.
"""

STATE_CODE = "{code}"
STATE_NAME = "{state_name}"
APP_NAME = "{app_name}"
APP_TAGLINE = "{state_name} Discharge Monitoring"
DOMAIN = "{domain}"
DATA_FILE = "{data_file}"
CONTACT_EMAIL = "{contact_email}"
MAILING_ADDRESS = ""
TIMEZONE_LABEL = "{tz_label}"
EPA_REGION = {epa_region}
'''

    with open("state_config.py", "w") as f:
        f.write(config_content)
    print(f"[OK] state_config.py updated for {code}")

    # ── Step 2: Create empty CSV with headers ──────────────────────────────
    if not os.path.exists(data_file):
        with open(data_file, "w", newline="") as f:
            f.write(CSV_HEADERS + "\n")
        print(f"[OK] Created empty {data_file} with headers")
    else:
        print(f"[SKIP] {data_file} already exists")

    # ── Step 3: Run fetch_industry_codes.py ────────────────────────────────
    print(f"\nFetching industry codes for {code} permits...")
    print("(This downloads ~300 MB from EPA ECHO — may take a few minutes)\n")
    try:
        result = subprocess.run(
            [sys.executable, "fetch_industry_codes.py"],
            timeout=600,
        )
        if result.returncode == 0:
            print(f"\n[OK] Industry codes generated")
        else:
            print(f"\n[WARN] fetch_industry_codes.py exited with code {result.returncode}")
            print("       You can re-run it manually later.")
    except subprocess.TimeoutExpired:
        print("\n[WARN] Industry code fetch timed out (10 min).")
        print("       Run manually: python fetch_industry_codes.py")
    except Exception as e:
        print(f"\n[WARN] Could not run fetch_industry_codes.py: {e}")
        print("       Run manually: python fetch_industry_codes.py")

    # ── Step 4: Print setup checklist ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("DEPLOYMENT COMPLETE — Manual Setup Checklist")
    print(f"{'='*60}\n")

    checklist = f"""
1. Create a Supabase project and add the signups table:

   CREATE TABLE signups (
       id          BIGSERIAL PRIMARY KEY,
       email       TEXT NOT NULL,
       alert_type  TEXT NOT NULL,
       alert_value TEXT NOT NULL,
       verified    BOOLEAN DEFAULT FALSE,
       verify_token TEXT,
       unsub_token  TEXT,
       created_at  TIMESTAMPTZ DEFAULT NOW(),
       is_paid     BOOLEAN DEFAULT FALSE
   );

2. Create a Stripe product for the $29/month Pro tier.
   Update the Stripe payment link in views/search_records.py.

3. Set up Render deployment (or your preferred hosting).
   Build command: pip install -r requirements.txt
   Start command: streamlit run main.py --server.port $PORT

4. Add GitHub Secrets:
   - GMAIL_USER    (sender Gmail address)
   - GMAIL_PASS    (Gmail app password — NOT account password)
   - SUPABASE_URL  (Supabase project URL)
   - SUPABASE_KEY  (Supabase anon key)

5. Register domain: {domain}

6. Fill in MAILING_ADDRESS in state_config.py
   (required for CAN-SPAM email compliance)

7. Push to GitHub to trigger the first ECHO scrape.
   The weekly scraper runs every Monday at 6 AM UTC.

8. Wait 1-2 weeks for data to accumulate before listing
   the site publicly. The first scrape pulls the current
   fiscal year's data.
"""
    print(checklist)


if __name__ == "__main__":
    main()
