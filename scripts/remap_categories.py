"""
Re-map all incidents to the expanded category taxonomy.
============================================================
This script:
1. Loads the expanded categories from the database
2. Gets all unique source_category values from incidents
3. Asks Claude to map them to the new taxonomy
4. Updates all incident rows in bulk

Run AFTER executing 003_expand_categories.sql in Supabase.

Usage: python scripts/remap_categories.py
"""

import json
import logging
import os
import time

import anthropic
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Step 1: Load all categories
    logger.info("Loading categories from database...")
    result = supabase.table("incident_categories").select("*").execute()
    categories = {}
    for row in result.data:
        key = f"{row['category']}/{row['subcategory']}"
        categories[key] = row
    logger.info(f"Loaded {len(categories)} categories")

    # Step 2: Get all unique source_category values from incidents
    logger.info("Getting unique source categories from incidents...")
    unique_sources = set()
    offset = 0
    page_size = 1000
    while True:
        result = (
            supabase.table("incidents")
            .select("source_category")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        for row in result.data:
            if row["source_category"]:
                unique_sources.add(row["source_category"])
        if len(result.data) < page_size:
            break
        offset += page_size

    unique_sources = sorted(unique_sources)
    logger.info(f"Found {len(unique_sources)} unique source categories to map")

    # Step 3: Ask Claude to map them
    category_list = "\n".join(
        f"  - {cat['category']} / {cat['subcategory']}"
        for cat in sorted(categories.values(), key=lambda c: f"{c['category']}/{c['subcategory']}")
    )

    descriptions_str = "\n".join(f"  - {d}" for d in unique_sources)

    prompt = f"""You are mapping police incident descriptions from Boston Police Department 
to a standardized crime/incident taxonomy. For each description, choose the BEST matching 
category/subcategory pair from our taxonomy.

OUR STANDARDIZED TAXONOMY:
{category_list}

BOSTON PD DESCRIPTIONS TO MAP ({len(unique_sources)} total):
{descriptions_str}

Respond ONLY with a JSON object. Format:
{{"DESCRIPTION": {{"category": "...", "subcategory": "..."}}}}

Mapping rules — be PRECISE and use the EXPANDED categories:
- SICK ASSIST → "Medical/Service Call / Sick Assist"
- SICK ASSIST - DRUG RELATED ILLNESS → "Medical/Service Call / Drug-Related Illness"
- SICK/INJURED/MEDICAL - PERSON → "Medical/Service Call / Medical Emergency"
- SICK/INJURED/MEDICAL - POLICE → "Medical/Service Call / Medical Emergency"
- INVESTIGATE PERSON → "Medical/Service Call / Investigate Person"
- INVESTIGATE PROPERTY → "Medical/Service Call / Investigate Property"
- SERVICE TO OTHER AGENCY → "Medical/Service Call / Service to Agency"

- PROPERTY - LOST/MISSING → "Property (Non-Crime) / Lost/Missing Property"
- PROPERTY - FOUND → "Property (Non-Crime) / Found Property"
- PROPERTY - ACCIDENTAL DAMAGE → "Property (Non-Crime) / Accidental Damage"
- PROPERTY - LOST THEN LOCATED → "Property (Non-Crime) / Recovered Property"
- PROPERTY - STOLEN THEN RECOVERED → "Property (Non-Crime) / Recovered Property"
- M/V PLATES - LOST → "Property (Non-Crime) / Lost Plates"

- FIRE REPORT → "Fire/Hazard / Fire Report"
- FIRE REPORT/ALARM - FALSE → "Fire/Hazard / False Alarm"
- DANGEROUS OR HAZARDOUS CONDITION → "Fire/Hazard / Hazardous Condition"
- EXPLOSIVES - * → "Fire/Hazard / Explosives"

- SUDDEN DEATH → "Death Investigation / Sudden Death"
- DEATH INVESTIGATION → "Death Investigation / Death Investigation"
- SUICIDE / SUICIDE ATTEMPT → "Death Investigation / Suicide/Attempt"
- PRISONER - SUICIDE / SUICIDE ATTEMPT → "Death Investigation / Suicide/Attempt"

- TOWED MOTOR VEHICLE → "Traffic / Towed Vehicle"
- M/V - LEAVING SCENE - * → "Traffic / Leaving Scene"
- M/V ACCIDENT - * → "Traffic / Accident"
- OPERATING UNDER THE INFLUENCE * → "Traffic / DUI/OUI"
- VAL - * (auto law violations) → "Traffic / Traffic Violation"

- LARCENY * → "Property Crime / Theft"
- AUTO THEFT * → "Property Crime / Motor Vehicle Theft"
- BURGLARY * → "Property Crime / Burglary"
- BREAKING AND ENTERING * → "Property Crime / Burglary"
- VANDALISM / GRAFFITI → "Property Crime / Vandalism"
- ARSON → "Property Crime / Arson"
- STOLEN PROPERTY - BUYING/RECEIVING → "Property Crime / Receiving Stolen Property"

- ASSAULT - SIMPLE/AGGRAVATED → "Violent Crime / Assault"
- THREATS TO DO BODILY HARM → "Violent Crime / Assault"
- ROBBERY → "Violent Crime / Robbery"
- MURDER/MANSLAUGHTER/Justifiable Homicide → "Violent Crime / Homicide"
- KIDNAPPING * → "Violent Crime / Kidnapping"
- INTIMIDATING WITNESS → "Violent Crime / Intimidation"

- DRUGS - POSSESSION/SALE/MANUFACTURING → "Drug Offenses / Distribution"
- DRUGS - POSSESSION OF PARAPHERNALIA → "Drug Offenses / Paraphernalia"

- FRAUD - FALSE PRETENSE → "Fraud / Fraud"
- FRAUD - CREDIT CARD/ATM → "Fraud / Fraud"
- FRAUD - WIRE → "Fraud / Wire Fraud"
- FRAUD - WELFARE → "Fraud / Welfare Fraud"
- FRAUD - IMPERSONATION → "Fraud / Impersonation"
- FORGERY/COUNTERFEITING → "Fraud / Forgery"
- EMBEZZLEMENT → "Fraud / Embezzlement"
- EXTORTION OR BLACKMAIL → "Fraud / Extortion"

- HARASSMENT/CRIMINAL HARASSMENT → "Disturbance / Harassment"
- VERBAL DISPUTE → "Disturbance / Disorderly Conduct"
- DISTURBING THE PEACE * → "Disturbance / Disorderly Conduct"
- NOISY PARTY * → "Disturbance / Noise Complaint"
- TRESPASSING → "Disturbance / Trespassing"
- LANDLORD - TENANT → "Disturbance / Landlord-Tenant"
- AFFRAY → "Disturbance / Disorderly Conduct"
- LIQUOR * → "Disturbance / Disorderly Conduct"
- DRUNKENNESS → "Disturbance / Disorderly Conduct"

- WEAPON VIOLATION * → "Weapons / Illegal Possession"
- FIREARM/WEAPON - FOUND/CONFISCATED → "Weapons / Illegal Possession"
- FIREARM/WEAPON - LOST → "Other / Other"
- FIREARM/WEAPON - ACCIDENTAL INJURY → "Other / Other"
- BALLISTICS EVIDENCE → "Other / Ballistics Evidence"

- MISSING PERSON * → "Other / Missing Person"
- WARRANT ARREST * → "Other / Warrant"
- ANIMAL * → "Other / Animal Complaint"
- BOMB THREAT → "Other / Suspicious Activity"
- RECOVERED - MV * → "Other / Recovered Vehicle"
- SEARCH WARRANT → "Other / Search Warrant"
- LICENSE PREMISE VIOLATION → "Other / License Violation"
- FUGITIVE FROM JUSTICE → "Other / Fugitive"
- TRUANCY/RUNAWAY → "Other / Truancy/Runaway"
- EVADING FARE → "Other / Evading Fare"
- HARBOR INCIDENT → "Other / Harbor Incident"
- AIRCRAFT INCIDENTS → "Other / Aircraft Incident"
- PROTECTIVE CUSTODY → "Other / Protective Custody"
- CHILD REQUIRING ASSISTANCE → "Other / Other"
- OBSCENE PHONE CALLS → "Disturbance / Harassment"
- PROSTITUTION * → "Other / Other"
- POSSESSION OF BURGLARIOUS TOOLS → "Property Crime / Burglary"
- OTHER OFFENSE → "Other / Other"
- VIOLATION - CITY ORDINANCE → "Other / License Violation"
- INJURY BICYCLE NO M/V → "Traffic / Accident"

Every description MUST map to a category/subcategory pair that exists in the taxonomy above.
Return ONLY the JSON object."""

    logger.info("Sending descriptions to Claude for mapping...")
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("```", 1)[0].strip()

    try:
        mapping = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response: {e}")
        logger.error(f"Response: {raw_text[:1000]}")
        return

    logger.info(f"Claude mapped {len(mapping)} descriptions")

    # Resolve to category IDs
    resolved = {}
    unmapped = []
    for desc, match in mapping.items():
        cat = match["category"]
        subcat = match["subcategory"]
        key = f"{cat}/{subcat}"
        if key in categories:
            resolved[desc] = categories[key]["id"]
        else:
            unmapped.append(f"{desc} → {cat}/{subcat}")
            # Fall back to Other/Other
            resolved[desc] = categories.get("Other/Other", {}).get("id")

    if unmapped:
        logger.warning(f"{len(unmapped)} descriptions mapped to unknown categories:")
        for u in unmapped:
            logger.warning(f"  {u}")

    # Step 4: Update incidents in bulk, grouped by source_category
    logger.info("Updating incidents in database...")
    updated_total = 0
    failed_total = 0

    for desc, category_id in resolved.items():
        if not category_id:
            continue

        try:
            result = (
                supabase.table("incidents")
                .update({"category_id": category_id})
                .eq("source_category", desc)
                .execute()
            )
            count = len(result.data) if result.data else 0
            updated_total += count
            if count > 0:
                logger.info(f"  Updated {count:>6,} rows: {desc}")
        except Exception as e:
            logger.error(f"  Failed to update '{desc}': {e}")
            failed_total += 1

    logger.info(f"\nDone! Updated {updated_total:,} incidents, {failed_total} failures")

    # Step 5: Verify — show new distribution
    logger.info("\nNew category distribution (top 30):")
    result = supabase.rpc("search_incidents_by_radius", {
        "search_lat": 42.3601,
        "search_lng": -71.0589,
        "radius_miles": 50,
        "result_limit": 5000,
    }).execute()

    from collections import Counter
    cats = Counter(f"{r['category']} / {r['subcategory']}" for r in result.data)
    for cat, count in cats.most_common(30):
        logger.info(f"  {cat:<50} {count:>5}")


if __name__ == "__main__":
    main()
