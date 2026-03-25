#!/usr/bin/env python3
"""
EPA ECHO DMR Scraper

Downloads the current fiscal year bulk DMR CSV from EPA ECHO ICIS-NPDES,
filters to the configured state, identifies effluent limit exceedances,
maps columns to the exceedances CSV format, deduplicates against existing
rows, and appends new rows.

Data source:
  https://echo.epa.gov/tools/data-downloads/icis-npdes-dmr-and-limit-data-set

File naming convention on ECHO:
  ZIP : https://echo.epa.gov/files/echodownloads/npdes_dmrs_fy{YEAR}.zip
  CSV inside ZIP: npdes_dmr_fy{YEAR}.csv

Requirements: requests, pandas, numpy (no Selenium, no browser)
"""

import csv
import os
import sys
import tempfile
import zipfile
from datetime import date, datetime

import pandas as pd
import requests

from launch_ready_columns import add_chemical_laundering_flags, prepare_launch_ready_dmr
from state_config import STATE_CODE, STATE_NAME, APP_NAME, DATA_FILE

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ECHO_BASE_URL = "https://echo.epa.gov/files/echodownloads"

# Chunk size for reading the large nationwide CSV
READ_CHUNK_SIZE = 50_000

# Map EPA ECHO column names -> tx_exceedances_launch_ready.csv column names.
# Columns not listed here are either derived or blank-filled below.
ECHO_TO_CSV = {
    "EXTERNAL_PERMIT_NMBR":        "PERMIT_NUMBER",
    "FACILITY_NAME":               "PF_NAME",
    "MONITORING_PERIOD_BEGIN_DATE": "MONITORING_PERIOD_BEGIN_DATE",
    "MONITORING_PERIOD_END_DATE":  "MONITORING_PERIOD_END_DATE",
    "PERM_FEATURE_NMBR":           "OUTFALL_NUMBER",
    "PARAMETER_DESC":              "PARAMETER",
    "DMR_VALUE_STANDARD_UNITS":    "SAMPLE_VALUE",
    "LIMIT_VALUE_STANDARD_UNITS":  "PERMIT_VALUE",
    "STANDARD_UNIT_DESC":          "UNIT_OF_MEASURE",
    "STATISTICAL_BASE_CODE":       "STAT_BASE_CODE",
    "DMR_VALUE_QUALIFIER_CODE":    "VIOLATION_CONDITION",
}

# Columns required by send_notifications.py / launch_ready_columns.py
# that are not present in ECHO data — blank-filled.
BLANK_FILL_COLS = [
    "COUNTY_NAME",
    "MUNICIPALITY_NAME",
    "PF_KIND",
    "REGION",
    "CHESAPEAKE_BAY_IND",
    "DISCHARGE_COMMENTS",
    "FACILITY_COMMENTS",
    "SUBMISSION_DATE",
]


# ---------------------------------------------------------------------------
# Fiscal year helpers
# ---------------------------------------------------------------------------

def current_fiscal_year() -> int:
    """
    Return the US federal fiscal year number for today's date.
    The federal FY runs Oct 1 – Sep 30.
      - Months Oct–Dec  → FY = calendar year + 1
      - Months Jan–Sep  → FY = calendar year
    """
    today = date.today()
    return today.year + 1 if today.month >= 10 else today.year


def fy_zip_url(fy: int) -> str:
    return f"{ECHO_BASE_URL}/npdes_dmrs_fy{fy}.zip"


def fy_csv_name(fy: int) -> str:
    return f"npdes_dmr_fy{fy}.csv"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def stream_download(url: str, dest_path: str) -> None:
    """Stream-download *url* to *dest_path*, printing progress."""
    print(f"  Downloading: {url}")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    chunk_mb = 1 << 20  # 1 MB

    with open(dest_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=chunk_mb):
            if chunk:
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(
                        f"\r  {downloaded / 1e6:.1f} MB / {total / 1e6:.1f} MB"
                        f" ({pct:.0f}%)",
                        end="",
                        flush=True,
                    )
    print()  # newline after progress bar


def fetch_state_exceedances(fy: int, tmp_dir: str) -> pd.DataFrame:
    """
    Download the ECHO DMR ZIP for *fy*, stream-read the CSV in chunks,
    filter to the configured state's rows only, and return them as a DataFrame.

    Returns an empty DataFrame if the file is unavailable or unreadable.
    """
    url      = fy_zip_url(fy)
    zip_path = os.path.join(tmp_dir, f"npdes_dmrs_fy{fy}.zip")

    # --- Download ---
    try:
        stream_download(url, zip_path)
    except requests.HTTPError as exc:
        print(f"  HTTP {exc.response.status_code} for FY{fy} — file may not be published yet.")
        return pd.DataFrame()
    except Exception as exc:
        print(f"  Download error for FY{fy}: {exc}")
        return pd.DataFrame()

    # --- Extract & read in chunks, keeping only TX rows ---
    csv_name = fy_csv_name(fy)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names_in_zip = zf.namelist()
            # Tolerant name match (case-insensitive)
            match = next(
                (n for n in names_in_zip if n.lower() == csv_name.lower()),
                names_in_zip[0] if names_in_zip else None,
            )
            if not match:
                print(f"  No CSV found in ZIP; contents: {names_in_zip}")
                return pd.DataFrame()

            print(f"  Streaming '{match}' and filtering to {STATE_CODE} …")
            state_chunks = []

            with zf.open(match) as csv_fh:
                reader = pd.read_csv(
                    csv_fh,
                    dtype=str,
                    low_memory=False,
                    chunksize=READ_CHUNK_SIZE,
                )
                total_rows = 0
                for chunk in reader:
                    total_rows += len(chunk)
                    state_chunk = _filter_chunk_to_state(chunk)
                    if not state_chunk.empty:
                        state_chunks.append(state_chunk)

            print(f"  Total rows scanned: {total_rows:,}")

            if not state_chunks:
                print(f"  No {STATE_CODE} rows found.")
                return pd.DataFrame()

            state_df = pd.concat(state_chunks, ignore_index=True)
            print(f"  {STATE_CODE} rows retained: {len(state_df):,}")
            return state_df

    except zipfile.BadZipFile:
        print(f"  Downloaded file is not a valid ZIP for FY{fy}.")
        return pd.DataFrame()
    except Exception as exc:
        print(f"  Error reading ZIP for FY{fy}: {exc}")
        return pd.DataFrame()


def _filter_chunk_to_state(chunk: pd.DataFrame) -> pd.DataFrame:
    """Return only rows matching the configured STATE_CODE from *chunk*."""
    if "STATE_CODE" in chunk.columns:
        return chunk[chunk["STATE_CODE"].str.upper().str.strip() == STATE_CODE].copy()
    # Fallback: use permit number prefix
    if "EXTERNAL_PERMIT_NMBR" in chunk.columns:
        return chunk[
            chunk["EXTERNAL_PERMIT_NMBR"].str.upper().str.startswith(STATE_CODE)
        ].copy()
    # Cannot filter — return everything (shouldn't happen with real ECHO data)
    print("  Warning: STATE_CODE column absent; keeping all rows unfiltered.")
    return chunk.copy()


# ---------------------------------------------------------------------------
# Exceedance detection
# ---------------------------------------------------------------------------

def identify_exceedances(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return rows where DMR value exceeds the permit limit.
    For minimum limits (e.g. pH floor), flag when value < limit.
    For maximum/average limits, flag when value > limit.
    Rows where the numeric limit is 0 (Monitor & Report) are skipped.
    """
    dmr_col   = "DMR_VALUE_STANDARD_UNITS"
    limit_col = "LIMIT_VALUE_STANDARD_UNITS"
    type_col  = "STATISTICAL_BASE_TYPE_CODE"

    missing = [c for c in (dmr_col, limit_col) if c not in df.columns]
    if missing:
        print(f"  Warning: columns absent — cannot detect exceedances: {missing}")
        return pd.DataFrame(columns=df.columns)

    numeric_dmr   = pd.to_numeric(df[dmr_col],   errors="coerce")
    numeric_limit = pd.to_numeric(df[limit_col],  errors="coerce")

    both_valid = numeric_dmr.notna() & numeric_limit.notna() & (numeric_limit != 0)

    is_minimum = (
        df[type_col].str.upper().isin(["MIN"])
        if type_col in df.columns
        else pd.Series(False, index=df.index)
    )

    exceeded = both_valid & (
        (is_minimum & (numeric_dmr < numeric_limit))
        | (~is_minimum & (numeric_dmr > numeric_limit))
    )

    exc_df = df[exceeded].copy()
    print(f"  Exceedances: {len(exc_df):,} of {len(df):,} {STATE_CODE} rows")
    return exc_df


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename ECHO columns to the tx_exceedances_launch_ready.csv schema,
    inject non-compliance descriptor columns, and blank-fill absent columns.
    """
    # If EXTERNAL_PERMIT_NMBR absent, fall back to NPDES_ID
    if "EXTERNAL_PERMIT_NMBR" not in df.columns and "NPDES_ID" in df.columns:
        df = df.rename(columns={"NPDES_ID": "EXTERNAL_PERMIT_NMBR"})

    rename_map = {k: v for k, v in ECHO_TO_CSV.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # Non-compliance descriptors — all rows here are confirmed exceedances
    df["NON_COMPL_TYPE_DESC"]     = "Effluent Limit Exceedance"
    df["NON_COMPL_CATEGORY_DESC"] = "Effluent Limit Exceedance"

    # Use monitoring period end date as the non-compliance date
    df["NON_COMPLIANCE_DATE"] = df.get("MONITORING_PERIOD_END_DATE", "")

    # Blank-fill columns not available in ECHO export
    for col in BLANK_FILL_COLS:
        if col not in df.columns:
            df[col] = ""

    return df


# ---------------------------------------------------------------------------
# Deduplication + append
# ---------------------------------------------------------------------------

def load_existing_keys() -> set:
    """
    Return set of (PERMIT_NUMBER, Compliance_Period_Key) tuples already
    present in tx_exceedances_launch_ready.csv.
    """
    keys: set = set()
    if not os.path.exists(DATA_FILE):
        print("  No existing CSV found — starting fresh.")
        return keys

    try:
        cols = ["PERMIT_NUMBER", "Compliance_Period_Key"]
        existing = pd.read_csv(DATA_FILE, usecols=cols, dtype=str, low_memory=False)
        for _, row in existing.iterrows():
            permit = str(row.get("PERMIT_NUMBER", "")).strip().upper()
            cpk    = str(row.get("Compliance_Period_Key", "")).strip()
            if permit and cpk:
                keys.add((permit, cpk))
        print(f"  Existing dedup keys loaded: {len(keys):,}")
    except Exception as exc:
        print(f"  Warning: could not load existing keys: {exc}")

    return keys


def deduplicate_and_append(new_df: pd.DataFrame, existing_keys: set) -> int:
    """
    Drop rows already in *existing_keys*, then append survivors to DATA_FILE.
    Returns the number of rows written.
    """
    if new_df.empty:
        print("  No rows to write.")
        return 0

    if "Compliance_Period_Key" in new_df.columns and "PERMIT_NUMBER" in new_df.columns:
        mask = ~new_df.apply(
            lambda r: (
                str(r["PERMIT_NUMBER"]).strip().upper(),
                str(r["Compliance_Period_Key"]).strip(),
            ) in existing_keys,
            axis=1,
        )
        new_df = new_df[mask]

    if new_df.empty:
        print("  All rows already present — nothing to append.")
        return 0

    write_header = not os.path.exists(DATA_FILE)
    new_df.to_csv(
        DATA_FILE,
        mode="a",
        index=False,
        header=write_header,
        quoting=csv.QUOTE_NONNUMERIC,
    )
    print(f"  Appended {len(new_df):,} new row(s) to {DATA_FILE}")
    return len(new_df)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n{'='*60}")
    print(f"{APP_NAME} EPA ECHO DMR Scraper ({STATE_CODE})")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    fy = current_fiscal_year()
    print(f"Target fiscal year: FY{fy}")

    # Download + filter to state inside a temp directory (cleaned up on exit)
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_df = fetch_state_exceedances(fy, tmp_dir)

        # Fall back to prior FY if current year not yet published
        if state_df.empty:
            prior_fy = fy - 1
            print(f"\nFY{fy} unavailable — trying FY{prior_fy} …")
            state_df = fetch_state_exceedances(prior_fy, tmp_dir)

    if state_df.empty:
        print("\nERROR: Could not retrieve DMR data from ECHO. Exiting.")
        sys.exit(1)

    # --- Identify exceedances ---
    print("\nIdentifying exceedances …")
    exc_df = identify_exceedances(state_df)
    del state_df  # free memory

    if exc_df.empty:
        print("No exceedances found. CSV unchanged.")
        sys.exit(0)

    # --- Map to output schema ---
    print("\nMapping columns to output schema …")
    mapped_df = map_columns(exc_df)
    del exc_df

    # Cast numeric fields so launch_ready_columns.py can compare them.
    # ECHO data is read with dtype=str; PERMIT_VALUE and SAMPLE_VALUE must
    # be numeric before prepare_launch_ready_dmr() runs its is_exceedance logic.
    for numeric_col in ("SAMPLE_VALUE", "PERMIT_VALUE"):
        if numeric_col in mapped_df.columns:
            mapped_df[numeric_col] = pd.to_numeric(mapped_df[numeric_col], errors="coerce")

    # --- Enrich with launch-ready computed columns ---
    print("Enriching with computed columns …")
    try:
        enriched_df = prepare_launch_ready_dmr(mapped_df)
        enriched_df = add_chemical_laundering_flags(enriched_df)
    except Exception as exc:
        print(f"  Warning: enrichment failed ({exc}); using mapped columns only.")
        enriched_df = mapped_df
        enriched_df["Ingested_At"] = datetime.now().isoformat()

    # Tag source so rows can be distinguished
    enriched_df["Source_File"] = "EPA_ECHO"

    # --- Deduplicate + append ---
    print("\nDeduplicating against existing CSV …")
    existing_keys = load_existing_keys()
    total_new = deduplicate_and_append(enriched_df, existing_keys)

    print(f"\n{'='*60}")
    if total_new > 0:
        print(f"COMPLETE: {total_new:,} new row(s) appended to {DATA_FILE}")
    else:
        print(f"COMPLETE: No new data — {DATA_FILE} unchanged.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
