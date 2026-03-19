"""
Boston PD Data Quality Diagnostic
===================================
Downloads the CSV and reports on data completeness for every column.
Run this BEFORE ingestion to understand what we're working with.

Usage:
    python scripts/diagnose_boston_data.py
"""

import csv
import io
import os
import sys
from collections import Counter

import httpx
from dotenv import load_dotenv

load_dotenv()

# The "2023 to Present" CSV
CSV_URL = (
    "https://data.boston.gov/dataset/6220d948-eae2-4e4b-8723-2dc8e67722a3"
    "/resource/b973d8cb-eeb2-4e7e-99da-c92938efc9c0/download/tmp9yqo5c_0.csv"
)


def is_empty(value: str) -> bool:
    """Check if a cell value is effectively empty."""
    if value is None:
        return True
    v = value.strip()
    return v == "" or v.upper() in ("", "NA", "N/A", "NAN", "NULL", "NONE")


def is_bad_coordinate(value: str) -> bool:
    """Check if a lat/long is missing or the -1 sentinel value Boston PD uses."""
    if is_empty(value):
        return True
    try:
        f = float(value)
        # Boston PD uses -1 as a placeholder for missing coordinates
        return f == -1.0 or f == 0.0
    except ValueError:
        return True


def main():
    print("Downloading Boston PD crime incident CSV...")
    print(f"URL: {CSV_URL}")
    print()

    response = httpx.get(CSV_URL, follow_redirects=True, timeout=120.0)
    response.raise_for_status()
    print(f"Downloaded {len(response.text):,} bytes")

    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)
    total = len(rows)
    print(f"Total rows: {total:,}")
    print()

    if total == 0:
        print("No rows found!")
        return

    columns = list(rows[0].keys())

    # ===================================================================
    # 1. Completeness report for every column
    # ===================================================================
    print("=" * 70)
    print("COLUMN COMPLETENESS REPORT")
    print("=" * 70)
    print(f"{'Column':<30} {'Present':>10} {'Missing':>10} {'% Present':>10}")
    print("-" * 70)

    col_stats = {}
    for col in columns:
        present = sum(1 for row in rows if not is_empty(row.get(col, "")))
        missing = total - present
        pct = (present / total) * 100
        col_stats[col] = {"present": present, "missing": missing, "pct": pct}
        print(f"{col:<30} {present:>10,} {missing:>10,} {pct:>9.1f}%")

    # ===================================================================
    # 2. Special analysis for coordinates
    # ===================================================================
    print()
    print("=" * 70)
    print("COORDINATE QUALITY ANALYSIS")
    print("=" * 70)

    lat_good = 0
    lng_good = 0
    both_good = 0
    lat_bad_values = Counter()
    lng_bad_values = Counter()

    for row in rows:
        lat = row.get("Lat", "")
        lng = row.get("Long", "")

        lat_ok = not is_bad_coordinate(lat)
        lng_ok = not is_bad_coordinate(lng)

        if lat_ok:
            lat_good += 1
        else:
            lat_bad_values[lat.strip() if lat else "(empty)"] += 1

        if lng_ok:
            lng_good += 1
        else:
            lng_bad_values[lng.strip() if lng else "(empty)"] += 1

        if lat_ok and lng_ok:
            both_good += 1

    print(f"Rows with valid Lat:           {lat_good:>10,} ({lat_good / total * 100:.1f}%)")
    print(f"Rows with valid Long:          {lng_good:>10,} ({lng_good / total * 100:.1f}%)")
    print(f"Rows with BOTH valid:          {both_good:>10,} ({both_good / total * 100:.1f}%)")
    print(f"Rows needing geocoding:        {total - both_good:>10,} ({(total - both_good) / total * 100:.1f}%)")

    print()
    print("Bad Lat values (top 10):")
    for val, count in lat_bad_values.most_common(10):
        print(f"  '{val}': {count:,}")

    print()
    print("Bad Long values (top 10):")
    for val, count in lng_bad_values.most_common(10):
        print(f"  '{val}': {count:,}")

    # ===================================================================
    # 3. STREET column analysis (for geocoding fallback)
    # ===================================================================
    print()
    print("=" * 70)
    print("STREET / ADDRESS ANALYSIS")
    print("=" * 70)

    has_street = sum(1 for row in rows if not is_empty(row.get("STREET", "")))
    has_street_no_coords = sum(
        1 for row in rows
        if not is_empty(row.get("STREET", ""))
        and (is_bad_coordinate(row.get("Lat", "")) or is_bad_coordinate(row.get("Long", "")))
    )
    no_street_no_coords = sum(
        1 for row in rows
        if is_empty(row.get("STREET", ""))
        and (is_bad_coordinate(row.get("Lat", "")) or is_bad_coordinate(row.get("Long", "")))
    )

    print(f"Rows with street name:         {has_street:>10,} ({has_street / total * 100:.1f}%)")
    print(f"Has street but NO coords:      {has_street_no_coords:>10,} ({has_street_no_coords / total * 100:.1f}%)")
    print(f"  (these can be geocoded)")
    print(f"No street AND no coords:       {no_street_no_coords:>10,} ({no_street_no_coords / total * 100:.1f}%)")
    print(f"  (these are unmappable)")

    # ===================================================================
    # 4. OFFENSE_CODE_GROUP unique values
    # ===================================================================
    print()
    print("=" * 70)
    print("OFFENSE_CODE_GROUP VALUES (for category mapping)")
    print("=" * 70)

    offense_groups = Counter(
        row.get("OFFENSE_CODE_GROUP", "").strip()
        for row in rows
        if not is_empty(row.get("OFFENSE_CODE_GROUP", ""))
    )
    print(f"Unique offense groups: {len(offense_groups)}")
    print()
    print(f"{'Offense Group':<45} {'Count':>8}")
    print("-" * 55)
    for group, count in offense_groups.most_common():
        print(f"{group:<45} {count:>8,}")

    # ===================================================================
    # 5. Date analysis
    # ===================================================================
    print()
    print("=" * 70)
    print("DATE ANALYSIS")
    print("=" * 70)

    has_date = sum(1 for row in rows if not is_empty(row.get("OCCURRED_ON_DATE", "")))
    print(f"Rows with OCCURRED_ON_DATE:    {has_date:>10,} ({has_date / total * 100:.1f}%)")

    # Sample some dates to see format
    sample_dates = [
        row.get("OCCURRED_ON_DATE", "")
        for row in rows[:20]
        if not is_empty(row.get("OCCURRED_ON_DATE", ""))
    ]
    if sample_dates:
        print(f"Sample date formats: {sample_dates[:5]}")

    # Year distribution
    year_counts = Counter(row.get("YEAR", "").strip() for row in rows if not is_empty(row.get("YEAR", "")))
    print()
    print("Year distribution:")
    for year, count in sorted(year_counts.items()):
        print(f"  {year}: {count:,}")

    # ===================================================================
    # 6. Sample rows (first 3)
    # ===================================================================
    print()
    print("=" * 70)
    print("SAMPLE ROWS (first 3)")
    print("=" * 70)
    for i, row in enumerate(rows[:3]):
        print(f"\n--- Row {i + 1} ---")
        for col in columns:
            val = row.get(col, "")
            marker = " [EMPTY]" if is_empty(val) else ""
            if col in ("Lat", "Long") and is_bad_coordinate(val):
                marker = " [BAD COORD]"
            print(f"  {col:<25} = {val}{marker}")


if __name__ == "__main__":
    main()
