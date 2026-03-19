"""
Check what's still in Other/Other and what failed to remap.
Usage: python scripts/check_unmapped.py
"""

import os
from collections import Counter
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

# Get the Other/Other category ID
result = supabase.table("incident_categories").select("id").eq("category", "Other").eq("subcategory", "Other").execute()
other_id = result.data[0]["id"] if result.data else None
print(f"Other/Other category ID: {other_id}")

# Count incidents still in Other/Other
result = supabase.table("incidents").select("id", count="exact").eq("category_id", other_id).execute()
other_count = result.count if result.count is not None else "unknown"
print(f"\nIncidents still in Other/Other: {other_count}")

# Get source_category breakdown for Other/Other incidents
print("\nSource categories still mapped to Other/Other:")
offset = 0
page_size = 1000
source_cats = Counter()

while True:
    result = (
        supabase.table("incidents")
        .select("source_category")
        .eq("category_id", other_id)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    if not result.data:
        break
    for row in result.data:
        source_cats[row["source_category"] or "(empty)"] += 1
    if len(result.data) < page_size:
        break
    offset += page_size

for src, count in source_cats.most_common():
    print(f"  {src:<60} {count:>8,}")

# Also check: are there any incidents with NULL category_id?
result = supabase.table("incidents").select("id", count="exact").is_("category_id", "null").execute()
null_count = result.count if result.count is not None else "unknown"
print(f"\nIncidents with NULL category_id: {null_count}")
