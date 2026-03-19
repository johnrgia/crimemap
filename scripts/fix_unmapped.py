"""
Fix remaining unmapped categories — smaller batches to avoid URL limits.
Usage: python scripts/fix_unmapped_v2.py
"""

import os
import logging
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

# Load categories to get IDs
result = supabase.table("incident_categories").select("id, category, subcategory").execute()
cat_lookup = {}
for row in result.data:
    key = f"{row['category']}/{row['subcategory']}"
    cat_lookup[key] = row["id"]

# Direct mapping
FIXES = {
    "SICK ASSIST": "Medical/Service Call/Sick Assist",
    "INVESTIGATE PERSON": "Medical/Service Call/Investigate Person",
    "INVESTIGATE PROPERTY": "Medical/Service Call/Investigate Property",
    "PROPERTY - LOST/ MISSING": "Property (Non-Crime)/Lost/Missing Property",
    "SICK ASSIST - DRUG RELATED ILLNESS": "Medical/Service Call/Drug-Related Illness",
    "OTHER OFFENSE": "Other/Other",
    "FIREARM/WEAPON - LOST": "Other/Other",
    "CHILD REQUIRING ASSISTANCE (FOMERLY CHINS)": "Other/Other",
    "FIREARM/WEAPON - ACCIDENTAL INJURY / DEATH": "Other/Other",
    "PROSTITUTION - SOLICITING": "Other/Other",
    "PROSTITUTION": "Other/Other",
    "PROSTITUTION - ASSISTING OR PROMOTING": "Other/Other",
}

total_updated = 0

for source_desc, cat_key in FIXES.items():
    category_id = cat_lookup.get(cat_key)
    if not category_id:
        logger.error(f"Category not found: {cat_key}")
        continue

    logger.info(f"Updating '{source_desc}' → {cat_key}...")
    chunk_updated = 0

    while True:
        # Fetch a small batch of IDs
        batch = (
            supabase.table("incidents")
            .select("id")
            .eq("source_category", source_desc)
            .neq("category_id", category_id)
            .limit(50)
            .execute()
        )

        if not batch.data:
            break

        ids = [row["id"] for row in batch.data]

        try:
            result = (
                supabase.table("incidents")
                .update({"category_id": category_id})
                .in_("id", ids)
                .execute()
            )
            count = len(result.data) if result.data else 0
            chunk_updated += count
        except Exception as e:
            logger.error(f"  Batch of {len(ids)} failed: {e}")
            # Try one at a time
            for single_id in ids:
                try:
                    supabase.table("incidents").update(
                        {"category_id": category_id}
                    ).eq("id", single_id).execute()
                    chunk_updated += 1
                except Exception:
                    pass

        if chunk_updated % 500 == 0 and chunk_updated > 0:
            logger.info(f"  ... {chunk_updated:,} updated")

    logger.info(f"  Done: {chunk_updated:,} rows for '{source_desc}'")
    total_updated += chunk_updated

logger.info(f"\nTotal updated: {total_updated:,}")

# Verify
other_id = cat_lookup.get("Other/Other")
result = supabase.table("incidents").select("id", count="exact").eq("category_id", other_id).execute()
remaining = result.count if result.count is not None else "unknown"
logger.info(f"Remaining in Other/Other: {remaining}")
