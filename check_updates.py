"""
check_updates.py - Detect new monitoring periods for watched permits.

Scans ./incoming/ for .xlsx files, extracts (permit_number, period_begin,
period_end) tuples for watched permits, compares against seen_periods in
effluentwatch.db, logs new detections, and moves processed files to ./processed/.
"""

import glob
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INCOMING_DIR = "./incoming"
PROCESSED_DIR = "./processed"
DB_PATH = "./effluentwatch.db"
LOG_FILE = "./check_updates.log"
TOP_N_PERMITS = 20

# Column name variants from EPA ECHO exports
COLUMN_ALIASES = {
    "EXTERNAL_PERMIT_NMBR": "PERMIT_NUMBER",
    "PERMIT NUMBER": "PERMIT_NUMBER",
    "Monitoring Period Begin Date": "MONITORING_PERIOD_BEGIN_DATE",
    "Monitoring Period End Date": "MONITORING_PERIOD_END_DATE",
    "Facility Name": "PF_NAME",
    "Parameter Name": "PARAMETER",
}

log = logging.getLogger("check_updates")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def init_db(db_path):
    """Create/connect to the SQLite database and ensure tables exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS watched_permits ("
        "  permit_number TEXT PRIMARY KEY"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS seen_periods ("
        "  permit_number TEXT NOT NULL,"
        "  period_begin  TEXT NOT NULL,"
        "  period_end    TEXT NOT NULL,"
        "  detected_at   TEXT NOT NULL DEFAULT (datetime('now')),"
        "  source_file   TEXT,"
        "  UNIQUE(permit_number, period_begin, period_end)"
        ")"
    )
    conn.commit()
    return conn


def get_watched_permits(conn):
    """Return the set of watched permit numbers."""
    rows = conn.execute("SELECT permit_number FROM watched_permits").fetchall()
    return {r[0] for r in rows}


def get_seen_periods(conn):
    """Return seen periods as a set of (permit_number, period_begin, period_end)."""
    rows = conn.execute(
        "SELECT permit_number, period_begin, period_end FROM seen_periods"
    ).fetchall()
    return set(rows)


def populate_watched_permits(conn, df):
    """Insert the top N permits by row count into watched_permits."""
    counts = df["PERMIT_NUMBER"].value_counts().head(TOP_N_PERMITS)
    log.info(
        "Populating watched_permits with top %d permits by exceedance count:",
        TOP_N_PERMITS,
    )
    for permit_number, count in counts.items():
        conn.execute(
            "INSERT OR IGNORE INTO watched_permits (permit_number) VALUES (?)",
            (str(permit_number),),
        )
        log.info("  %s (%d rows)", permit_number, count)
    conn.commit()


# ---------------------------------------------------------------------------
# Excel processing helpers
# ---------------------------------------------------------------------------

def normalize_columns(df):
    """Standardize column names to the canonical uppercase_underscore form.

    Returns the modified DataFrame and a boolean indicating whether the
    required columns are present.
    """
    # First, apply known aliases (exact match on original names)
    rename_map = {}
    for orig, canonical in COLUMN_ALIASES.items():
        if orig in df.columns:
            rename_map[orig] = canonical
    if rename_map:
        df = df.rename(columns=rename_map)

    # Then uppercase + underscore any remaining columns
    df.columns = [
        col.upper().strip().replace(" ", "_") if col not in df.columns else col
        for col in df.columns
    ]
    # Re-apply after uppercasing (catches "MONITORING_PERIOD_BEGIN_DATE" etc.)
    df.columns = [c.upper().strip().replace(" ", "_") for c in df.columns]

    # Fallback: if MONITORING_PERIOD_BEGIN_DATE is missing, try LIMIT_BEGIN_DATE
    if "MONITORING_PERIOD_BEGIN_DATE" not in df.columns:
        if "LIMIT_BEGIN_DATE" in df.columns:
            df = df.rename(columns={"LIMIT_BEGIN_DATE": "MONITORING_PERIOD_BEGIN_DATE"})
            log.info("Using LIMIT_BEGIN_DATE as MONITORING_PERIOD_BEGIN_DATE")

    # Check required columns
    required = ["PERMIT_NUMBER", "MONITORING_PERIOD_END_DATE"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return df, False

    # If begin date is still missing, fill with empty string
    if "MONITORING_PERIOD_BEGIN_DATE" not in df.columns:
        df["MONITORING_PERIOD_BEGIN_DATE"] = ""
        log.warning("MONITORING_PERIOD_BEGIN_DATE not found; defaulting to empty")

    return df, True


def process_excel_file(conn, filepath, watched, seen):
    """Process a single Excel file. Returns the count of new detections."""
    basename = os.path.basename(filepath)
    log.info("Reading %s ...", basename)

    # Try header=0 first; if columns look wrong, try rows 1-5
    df = None
    for hdr in [0, 1, 2, 3, 4, 5]:
        test = pd.read_excel(filepath, engine="openpyxl", header=hdr)
        cols_upper = [str(c).upper() for c in test.columns]
        if any("PERMIT" in c for c in cols_upper) and any("MONITORING" in c for c in cols_upper):
            df = test
            break
    if df is None:
        df = pd.read_excel(filepath, engine="openpyxl")
    if df.empty:
        log.warning("  %s is empty — skipping", basename)
        return 0

    df, ok = normalize_columns(df)
    if not ok:
        log.error(
            "  %s missing required columns (PERMIT_NUMBER, "
            "MONITORING_PERIOD_END_DATE) — skipping",
            basename,
        )
        return 0

    # Auto-populate watched permits on first run
    if not watched:
        populate_watched_permits(conn, df)
        watched.update(get_watched_permits(conn))
        if not watched:
            log.warning("  No permits to watch — skipping")
            return 0

    # Filter to watched permits
    mask = df["PERMIT_NUMBER"].astype(str).isin(watched)
    filtered = df.loc[mask, [
        "PERMIT_NUMBER",
        "MONITORING_PERIOD_BEGIN_DATE",
        "MONITORING_PERIOD_END_DATE",
    ]].copy()

    if filtered.empty:
        log.info("  No rows for watched permits in %s", basename)
        return 0

    # Normalize date values to strings for consistent comparison
    for col in ["MONITORING_PERIOD_BEGIN_DATE", "MONITORING_PERIOD_END_DATE"]:
        filtered[col] = filtered[col].astype(str).str.strip()

    # Extract unique tuples
    tuples = (
        filtered
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )

    new_count = 0
    for permit_number, period_begin, period_end in tuples:
        permit_number = str(permit_number).strip()
        period_begin = str(period_begin).strip()
        period_end = str(period_end).strip()

        key = (permit_number, period_begin, period_end)
        if key in seen:
            continue

        try:
            conn.execute(
                "INSERT OR IGNORE INTO seen_periods "
                "(permit_number, period_begin, period_end, source_file) "
                "VALUES (?, ?, ?, ?)",
                (permit_number, period_begin, period_end, basename),
            )
            seen.add(key)
            new_count += 1
            log.info(
                "  NEW  %s  period %s — %s",
                permit_number,
                period_begin,
                period_end,
            )
        except sqlite3.Error as exc:
            log.error("  DB error for %s: %s", key, exc)

    conn.commit()
    return new_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Logging: stdout + file
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )

    log.info("=== check_updates.py started ===")

    # Ensure directories exist
    os.makedirs(INCOMING_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # Scan for incoming files
    xlsx_files = sorted(glob.glob(os.path.join(INCOMING_DIR, "*.xlsx")))
    if not xlsx_files:
        log.info("No new files to process.")
        return

    log.info("Found %d file(s) in %s", len(xlsx_files), INCOMING_DIR)

    conn = init_db(DB_PATH)
    watched = get_watched_permits(conn)
    seen = get_seen_periods(conn)

    total_new = 0
    files_processed = 0

    for filepath in xlsx_files:
        basename = os.path.basename(filepath)
        try:
            new_count = process_excel_file(conn, filepath, watched, seen)
            total_new += new_count
            files_processed += 1
            log.info(
                "%d new period(s) detected in %s", new_count, basename
            )

            # Move to processed (handle duplicate names)
            dest = os.path.join(PROCESSED_DIR, basename)
            if os.path.exists(dest):
                name, ext = os.path.splitext(basename)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = os.path.join(PROCESSED_DIR, f"{name}_{stamp}{ext}")
            shutil.move(filepath, dest)
            log.info("Moved %s -> %s", basename, dest)

        except Exception:
            log.exception("Error processing %s — skipping", basename)

    conn.close()

    log.info(
        "=== Done. Processed %d file(s), %d total new detection(s). ===",
        files_processed,
        total_new,
    )


if __name__ == "__main__":
    main()
