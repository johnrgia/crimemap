"""
Quick check: what's in the database after ingestion?
Usage: python scripts/verify_ingestion.py
"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)

# 1. Check departments
print("=" * 60)
print("DEPARTMENTS")
print("=" * 60)
result = supabase.table("departments").select("*").execute()
for dept in result.data:
    print(f"  {dept['name']} ({dept['city']}, {dept['state']}) - active: {dept['is_active']}")
print(f"  Total: {len(result.data)}")

# 2. Check ingestion runs
print(f"\n{'=' * 60}")
print("INGESTION RUNS")
print("=" * 60)
result = supabase.table("ingestion_runs").select("*").order("started_at", desc=True).limit(5).execute()
for run in result.data:
    print(f"  [{run['status']}] Found: {run['records_found']}, Inserted: {run['records_inserted']}, "
          f"Skipped: {run['records_skipped']}")
    if run.get('error_message'):
        print(f"    Error: {run['error_message'][:200]}")

# 3. Count incidents
print(f"\n{'=' * 60}")
print("INCIDENTS")
print("=" * 60)
result = supabase.table("incidents").select("id", count="exact").execute()
total = result.count if result.count is not None else len(result.data)
print(f"  Total incidents: {total}")

# Count with/without coordinates
result_geocoded = supabase.table("incidents").select("id", count="exact").eq("is_geocoded", True).execute()
geocoded = result_geocoded.count if result_geocoded.count is not None else len(result_geocoded.data)
print(f"  With coordinates: {geocoded}")
print(f"  Without coordinates: {total - geocoded}")

# 4. Sample incidents
print(f"\n{'=' * 60}")
print("SAMPLE INCIDENTS (first 5)")
print("=" * 60)
result = supabase.table("incidents").select(
    "case_number, incident_date, description, source_category, "
    "address_raw, city, latitude, longitude, is_geocoded, confidence_score"
).order("incident_date", desc=True).limit(5).execute()

for inc in result.data:
    print(f"\n  Case: {inc['case_number']}")
    print(f"    Date:        {inc['incident_date']}")
    print(f"    Description: {inc['description']}")
    print(f"    Source cat:   {inc['source_category']}")
    print(f"    Address:     {inc['address_raw']}, {inc['city']}")
    print(f"    Coords:      {inc['latitude']}, {inc['longitude']}")
    print(f"    Geocoded:    {inc['is_geocoded']} (confidence: {inc['confidence_score']})")

# 5. Category distribution
print(f"\n{'=' * 60}")
print("CATEGORY DISTRIBUTION")
print("=" * 60)
result = supabase.rpc("search_incidents_by_radius", {
    "search_lat": 42.3601,
    "search_lng": -71.0589,
    "radius_miles": 50,
    "result_limit": 1000,
}).execute()

from collections import Counter
cats = Counter(f"{r['category']} / {r['subcategory']}" for r in result.data)
for cat, count in cats.most_common():
    print(f"  {cat:<40} {count:>5}")
