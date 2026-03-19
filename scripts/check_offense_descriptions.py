"""
Quick check: how many unique OFFENSE_DESCRIPTION values exist?
And what are the OFFENSE_CODE -> OFFENSE_DESCRIPTION mappings?

Usage: python scripts/check_offense_descriptions.py
"""

import csv
import io
from collections import Counter

import httpx

CSV_URL = (
    "https://data.boston.gov/dataset/6220d948-eae2-4e4b-8723-2dc8e67722a3"
    "/resource/b973d8cb-eeb2-4e7e-99da-c92938efc9c0/download/tmp9yqo5c_0.csv"
)

print("Downloading CSV...")
response = httpx.get(CSV_URL, follow_redirects=True, timeout=120.0)
rows = list(csv.DictReader(io.StringIO(response.text)))
print(f"Total rows: {len(rows):,}")

# Count unique OFFENSE_DESCRIPTIONs
desc_counts = Counter(
    row.get("OFFENSE_DESCRIPTION", "").strip()
    for row in rows
    if row.get("OFFENSE_DESCRIPTION", "").strip()
)

print(f"\nUnique OFFENSE_DESCRIPTION values: {len(desc_counts)}")
print(f"\n{'OFFENSE_DESCRIPTION':<55} {'Count':>8}")
print("-" * 65)
for desc, count in desc_counts.most_common():
    print(f"{desc:<55} {count:>8,}")

# Also check OFFENSE_CODE -> DESCRIPTION mapping
print(f"\n\n{'='*65}")
print("OFFENSE_CODE -> OFFENSE_DESCRIPTION mapping")
print(f"{'='*65}")
code_to_desc = {}
for row in rows:
    code = row.get("OFFENSE_CODE", "").strip()
    desc = row.get("OFFENSE_DESCRIPTION", "").strip()
    if code and desc:
        if code not in code_to_desc:
            code_to_desc[code] = set()
        code_to_desc[code].add(desc)

print(f"Unique OFFENSE_CODEs: {len(code_to_desc)}")
# Flag any codes that map to multiple descriptions
multi = {k: v for k, v in code_to_desc.items() if len(v) > 1}
if multi:
    print(f"\nCodes with MULTIPLE descriptions ({len(multi)}):")
    for code, descs in sorted(multi.items()):
        print(f"  {code}: {descs}")
else:
    print("Each code maps to exactly one description (clean!)")
