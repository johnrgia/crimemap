"""
Boston Police Department Ingestion Pipeline (v2)
=================================================
Downloads crime incident CSVs from Analyze Boston (data.boston.gov),
normalizes offense types to our standard taxonomy using Claude,
and inserts into the CrimeMap database.

Data quality notes (from diagnostic run on 252,370 rows):
    - OFFENSE_CODE_GROUP: 100% empty in 2023+ data — we use OFFENSE_DESCRIPTION instead
    - UCR_PART: 100% empty — ignored
    - Lat/Long: 94.1% present, 5.9% missing (empty string, never -1)
    - STREET: 100% present (except 1 row)
    - OCCURRED_ON_DATE: 100% present, format "2023-01-27 22:44:00+00"
    - INCIDENT_NUMBER: 100% present, unique per incident
    - 121 unique OFFENSE_DESCRIPTION values

Usage:
    python -m backend.app.ingestion.boston_pd --limit 50    # test with 50 rows
    python -m backend.app.ingestion.boston_pd                # full ingestion
    python -m backend.app.ingestion.boston_pd --geocode      # also geocode missing coords
"""

import csv
import io
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import anthropic
import httpx
from supabase import create_client, Client

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ===========================================================================
# Configuration
# ===========================================================================

BOSTON_CSV_URL = (
    "https://data.boston.gov/dataset/6220d948-eae2-4e4b-8723-2dc8e67722a3"
    "/resource/b973d8cb-eeb2-4e7e-99da-c92938efc9c0/download/tmp9yqo5c_0.csv"
)

DEPARTMENT_INFO = {
    "name": "Boston Police Department",
    "city": "Boston",
    "state": "MA",
    "website_url": "https://police.boston.gov/",
    "data_source_url": "https://data.boston.gov/dataset/crime-incident-reports-august-2015-to-date-source-new-system",
    "data_format": "csv",
    "fetch_cadence": "weekly",
}


# ===========================================================================
# Stats tracking
# ===========================================================================

@dataclass
class IngestionStats:
    records_found: int = 0
    records_inserted: int = 0
    records_skipped: int = 0
    records_failed: int = 0
    duplicates: int = 0
    missing_location: int = 0
    geocoded: int = 0
    geocode_cached: int = 0
    geocode_failed: int = 0
    start_time: float = field(default_factory=time.time)

    def summary(self) -> str:
        elapsed = time.time() - self.start_time
        return (
            f"\n{'=' * 60}\n"
            f"Ingestion Complete ({elapsed:.1f}s)\n"
            f"{'=' * 60}\n"
            f"  Records in CSV:       {self.records_found:>8,}\n"
            f"  Inserted:             {self.records_inserted:>8,}\n"
            f"  Duplicates skipped:   {self.duplicates:>8,}\n"
            f"  Missing location:     {self.missing_location:>8,}\n"
            f"    - Geocoded (API):   {self.geocoded:>8,}\n"
            f"    - Geocoded (cache): {self.geocode_cached:>8,}\n"
            f"    - Geocode failed:   {self.geocode_failed:>8,}\n"
            f"  Failed:               {self.records_failed:>8,}\n"
            f"  Skipped (other):      {self.records_skipped:>8,}\n"
            f"{'=' * 60}"
        )


# ===========================================================================
# Helpers
# ===========================================================================

def is_empty(value: Optional[str]) -> bool:
    """Check if a cell value is effectively empty."""
    if value is None:
        return True
    v = value.strip()
    return v == "" or v.upper() in ("NA", "N/A", "NAN", "NULL", "NONE")


def parse_boston_date(date_str: str) -> Optional[str]:
    """
    Parse Boston PD date format into ISO 8601.
    Real format: "2023-01-27 22:44:00+00"
    """
    if is_empty(date_str):
        return None
    try:
        # Handle the "+00" timezone suffix (might be +00 or +00:00)
        cleaned = date_str.strip()
        # Python's fromisoformat needs +00:00, not +00
        if cleaned.endswith("+00"):
            cleaned = cleaned + ":00"
        dt = datetime.fromisoformat(cleaned)
        return dt.isoformat()
    except ValueError:
        # Fallback formats
        for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"):
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.isoformat()
            except ValueError:
                continue
    return None


def is_valid_coordinate(lat_str: str, lng_str: str) -> bool:
    """Check if lat/lng values are usable. Boston area: ~42.2-42.4, ~-71.2 to -70.9."""
    if is_empty(lat_str) or is_empty(lng_str):
        return False
    try:
        lat = float(lat_str)
        lng = float(lng_str)
        # Reject sentinel values and out-of-range
        if lat == 0.0 or lng == 0.0 or lat == -1.0 or lng == -1.0:
            return False
        return (40.0 < lat < 44.0) and (-73.0 < lng < -69.0)
    except (ValueError, TypeError):
        return False


# ===========================================================================
# Category mapping with Claude
# ===========================================================================

def build_category_mapping(
    offense_descriptions: list[str],
    claude_client: anthropic.Anthropic,
    existing_categories: dict[str, dict],
) -> dict[str, dict]:
    """
    Use Claude to map Boston PD OFFENSE_DESCRIPTION values to our taxonomy.
    With only 121 unique values, this fits in a single API call.
    """
    category_list = "\n".join(
        f"  - {cat['category']} / {cat['subcategory']}"
        for cat in existing_categories.values()
    )

    descriptions_str = "\n".join(f"  - {d}" for d in sorted(offense_descriptions))

    prompt = f"""You are mapping police incident descriptions from Boston Police Department 
to a standardized crime taxonomy. For each description, choose the BEST matching 
category/subcategory pair.

OUR STANDARDIZED TAXONOMY:
{category_list}

BOSTON PD OFFENSE DESCRIPTIONS TO MAP ({len(offense_descriptions)} total):
{descriptions_str}

Respond ONLY with a JSON object. Format:
{{"OFFENSE DESCRIPTION": {{"category": "...", "subcategory": "..."}}}}

Mapping rules:
- Every description MUST map to exactly one category/subcategory from the taxonomy above
- Use "Other / Other" only if truly nothing fits
- Larceny/shoplifting/theft/pick-pocket → "Property Crime / Theft"
- Auto theft / motor vehicle theft → "Property Crime / Motor Vehicle Theft"
- Burglary / B&E → "Property Crime / Burglary"
- Assault simple/aggravated → "Violent Crime / Assault"
- Robbery → "Violent Crime / Robbery"
- Murder/manslaughter/homicide → "Violent Crime / Homicide"
- Kidnapping → "Violent Crime / Kidnapping"
- Drug possession/sale/manufacturing → "Drug Offenses / Possession" or "Drug Offenses / Distribution"
- M/V accident, OUI → "Traffic / Accident" or "Traffic / DUI/OUI"
- Vandalism/graffiti → "Property Crime / Vandalism"
- Arson → "Property Crime / Arson"
- Fraud/forgery/embezzlement/extortion → "Fraud / ..." subcategory
- Weapon violations → "Weapons / Illegal Possession"
- Trespassing → "Disturbance / Trespassing"
- Harassment/threats → "Disturbance / Harassment"
- Noise/disorderly → "Disturbance / Disorderly Conduct"
- Verbal dispute → "Disturbance / Disorderly Conduct"
- Investigate person/property, sick assist, service calls → "Other / Other"
- Missing person → "Other / Missing Person"
- Warrant arrest → "Other / Warrant"
- Suspicious activity, bomb threat → "Other / Suspicious Activity"

Return ONLY the JSON object, no markdown fences, no explanation."""

    logger.info(f"Sending {len(offense_descriptions)} descriptions to Claude for mapping...")

    response = claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    mapping = {}
    try:
        raw_text = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            raw_text = raw_text.rsplit("```", 1)[0].strip()

        batch_mapping = json.loads(raw_text)

        for desc, match in batch_mapping.items():
            cat = match["category"]
            subcat = match["subcategory"]
            key = f"{cat}/{subcat}"
            if key in existing_categories:
                mapping[desc] = {
                    "category_id": existing_categories[key]["id"],
                    "category": cat,
                    "subcategory": subcat,
                }
            else:
                fallback_key = "Other/Other"
                mapping[desc] = {
                    "category_id": existing_categories[fallback_key]["id"],
                    "category": "Other",
                    "subcategory": "Other",
                }
                logger.warning(f"Unknown category '{cat}/{subcat}' for '{desc}', using Other/Other")

        logger.info(f"Successfully mapped {len(mapping)}/{len(offense_descriptions)} descriptions")

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse Claude response: {e}")
        logger.error(f"Raw response (first 500 chars): {response.content[0].text[:500]}")
        # Map everything to Other/Other as fallback
        fallback_key = "Other/Other"
        for desc in offense_descriptions:
            mapping[desc] = {
                "category_id": existing_categories[fallback_key]["id"],
                "category": "Other",
                "subcategory": "Other",
            }

    # Handle any unmapped descriptions
    for desc in offense_descriptions:
        if desc not in mapping:
            fallback_key = "Other/Other"
            mapping[desc] = {
                "category_id": existing_categories[fallback_key]["id"],
                "category": "Other",
                "subcategory": "Other",
            }
            logger.warning(f"Unmapped description: '{desc}', using Other/Other")

    return mapping


# ===========================================================================
# Geocoding (for the ~6% of rows missing coordinates)
# ===========================================================================

def geocode_address(
    street: str,
    supabase: Client,
    gmaps_client,
    stats: IngestionStats,
) -> Optional[dict]:
    """
    Geocode a street address in Boston. Checks cache first.

    Returns: {"latitude": float, "longitude": float, "quality": str} or None
    """
    if is_empty(street):
        return None

    full_address = f"{street.strip()}, Boston, MA"

    # Check cache first
    try:
        result = (
            supabase.table("geocoding_cache")
            .select("latitude, longitude, quality")
            .eq("address_input", full_address)
            .limit(1)
            .execute()
        )
        if result.data:
            stats.geocode_cached += 1
            row = result.data[0]
            if row["latitude"] and row["longitude"]:
                return {
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "quality": row["quality"] or "cached",
                }
            return None  # Previously failed geocode
    except Exception as e:
        logger.debug(f"Cache lookup error: {e}")

    # Cache miss — call Google Maps API
    if gmaps_client is None:
        return None

    try:
        results = gmaps_client.geocode(full_address)
        if results:
            location = results[0]["geometry"]["location"]
            quality = results[0]["geometry"].get("location_type", "APPROXIMATE")

            # Cache the result
            try:
                supabase.table("geocoding_cache").upsert({
                    "address_input": full_address,
                    "address_normalized": results[0].get("formatted_address", full_address),
                    "latitude": location["lat"],
                    "longitude": location["lng"],
                    "quality": quality,
                    "provider": "google",
                }).execute()
            except Exception as e:
                logger.debug(f"Cache write error: {e}")

            stats.geocoded += 1
            return {
                "latitude": location["lat"],
                "longitude": location["lng"],
                "quality": quality,
            }
        else:
            # Cache the failure so we don't retry
            try:
                supabase.table("geocoding_cache").upsert({
                    "address_input": full_address,
                    "latitude": None,
                    "longitude": None,
                    "quality": "failed",
                    "provider": "google",
                }).execute()
            except Exception:
                pass
            stats.geocode_failed += 1
            return None

    except Exception as e:
        logger.error(f"Geocoding API error for '{full_address}': {e}")
        stats.geocode_failed += 1
        return None


# ===========================================================================
# CSV Download and Parsing
# ===========================================================================

def download_csv(url: str) -> str:
    """Download CSV content from a URL."""
    logger.info(f"Downloading CSV from {url}...")
    response = httpx.get(url, follow_redirects=True, timeout=120.0)
    response.raise_for_status()
    logger.info(f"Downloaded {len(response.text):,} bytes")
    return response.text


def parse_csv_rows(csv_text: str) -> list[dict]:
    """Parse CSV text into a list of row dicts."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    logger.info(f"Parsed {len(rows):,} rows from CSV")
    return rows


# ===========================================================================
# Database Operations
# ===========================================================================

def get_or_create_department(supabase: Client) -> str:
    """Get or create Boston PD department record. Returns department ID."""
    result = (
        supabase.table("departments")
        .select("id")
        .eq("name", DEPARTMENT_INFO["name"])
        .eq("city", DEPARTMENT_INFO["city"])
        .limit(1)
        .execute()
    )

    if result.data:
        dept_id = result.data[0]["id"]
        logger.info(f"Found existing department: {dept_id}")
        return dept_id

    result = supabase.table("departments").insert(DEPARTMENT_INFO).execute()
    dept_id = result.data[0]["id"]
    logger.info(f"Created new department: {dept_id}")
    return dept_id


def create_ingestion_run(supabase: Client, department_id: str) -> str:
    """Create a new ingestion run record. Returns run ID."""
    result = (
        supabase.table("ingestion_runs")
        .insert({
            "department_id": department_id,
            "status": "running",
        })
        .execute()
    )
    run_id = result.data[0]["id"]
    logger.info(f"Created ingestion run: {run_id}")
    return run_id


def complete_ingestion_run(
    supabase: Client,
    run_id: str,
    stats: IngestionStats,
    error: Optional[str] = None,
) -> None:
    """Update ingestion run with final stats."""
    status = "failed" if error else "success"
    if not error and stats.records_failed > 0:
        status = "partial"

    supabase.table("ingestion_runs").update({
        "completed_at": datetime.utcnow().isoformat(),
        "status": status,
        "records_found": stats.records_found,
        "records_inserted": stats.records_inserted,
        "records_skipped": stats.records_skipped + stats.duplicates,
        "error_message": error,
    }).eq("id", run_id).execute()


def load_categories(supabase: Client) -> dict[str, dict]:
    """Load all incident categories into a lookup dict keyed by 'Category/Subcategory'."""
    result = supabase.table("incident_categories").select("*").execute()
    categories = {}
    for row in result.data:
        key = f"{row['category']}/{row['subcategory']}"
        categories[key] = row
    logger.info(f"Loaded {len(categories)} categories from database")
    return categories


def get_existing_case_numbers(supabase: Client, department_id: str) -> set:
    """Get all existing case numbers for duplicate detection."""
    case_numbers = set()
    offset = 0
    page_size = 1000

    while True:
        result = (
            supabase.table("incidents")
            .select("case_number")
            .eq("department_id", department_id)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        for row in result.data:
            if row["case_number"]:
                case_numbers.add(row["case_number"])
        if len(result.data) < page_size:
            break
        offset += page_size

    logger.info(f"Found {len(case_numbers):,} existing case numbers")
    return case_numbers


def insert_incidents_batch(supabase: Client, incidents: list[dict]) -> int:
    """Insert a batch of incidents. Returns count of successfully inserted records."""
    if not incidents:
        return 0

    try:
        result = supabase.table("incidents").upsert(
            incidents,
            on_conflict="department_id,case_number",
        ).execute()
        return len(result.data)
    except Exception as e:
        logger.error(f"Batch insert failed ({len(incidents)} records): {e}")
        # Retry one at a time to salvage what we can
        inserted = 0
        for incident in incidents:
            try:
                supabase.table("incidents").upsert(
                    incident,
                    on_conflict="department_id,case_number",
                ).execute()
                inserted += 1
            except Exception as e2:
                logger.error(
                    f"Single insert failed for {incident.get('case_number')}: {e2}"
                )
        return inserted


# ===========================================================================
# Row transformation
# ===========================================================================

def transform_row(
    row: dict,
    department_id: str,
    category_mapping: dict[str, dict],
    fallback_category: dict,
) -> Optional[dict]:
    """
    Transform a raw CSV row into a normalized incident record.

    Returns None if the row should be skipped (no case number).
    """
    case_number = row.get("INCIDENT_NUMBER", "").strip()
    if not case_number:
        return None

    # Parse coordinates
    lat_str = row.get("Lat", "")
    lng_str = row.get("Long", "")
    has_coords = is_valid_coordinate(lat_str, lng_str)
    lat = float(lat_str) if has_coords else None
    lng = float(lng_str) if has_coords else None

    # Map offense description to our category
    offense_desc = row.get("OFFENSE_DESCRIPTION", "").strip()
    cat_info = category_mapping.get(offense_desc, fallback_category)

    # Parse date
    incident_date = parse_boston_date(row.get("OCCURRED_ON_DATE", ""))

    # Street address
    street = row.get("STREET", "").strip() or None

    # Description
    description = offense_desc or None

    # Shooting flag
    shooting_raw = row.get("SHOOTING", "").strip()
    is_shooting = shooting_raw == "1" or shooting_raw.upper() == "Y"

    # Build the incident record
    incident = {
        "department_id": department_id,
        "case_number": case_number,
        "category_id": cat_info.get("category_id"),
        "incident_date": incident_date,
        "description": f"{description} (SHOOTING)" if is_shooting and description else description,
        "address_raw": street,
        "address_normalized": f"{street}, Boston, MA" if street else None,
        "city": "Boston",
        "state": "MA",
        "latitude": lat,
        "longitude": lng,
        "source_category": offense_desc or None,
        "confidence_score": 0.9 if has_coords else 0.3,
        "is_geocoded": has_coords,
        "geocode_quality": "department_provided" if has_coords else None,
    }

    return incident


# ===========================================================================
# Main Pipeline
# ===========================================================================

def run_ingestion(limit: Optional[int] = None, do_geocode: bool = False):
    """
    Run the full Boston PD ingestion pipeline.

    Args:
        limit: If set, only process this many rows (for testing)
        do_geocode: If True, geocode rows that are missing coordinates
    """
    stats = IngestionStats()

    # Initialize clients
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )
    claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Optional: Google Maps client for geocoding
    gmaps_client = None
    if do_geocode:
        try:
            import googlemaps
            gmaps_client = googlemaps.Client(key=os.environ["GOOGLE_MAPS_API_KEY"])
            logger.info("Geocoding enabled — will resolve missing coordinates")
        except Exception as e:
            logger.warning(f"Geocoding disabled: {e}")

    # Step 1: Set up department and ingestion run
    department_id = get_or_create_department(supabase)
    run_id = create_ingestion_run(supabase, department_id)

    try:
        # Step 2: Download and parse CSV
        csv_text = download_csv(BOSTON_CSV_URL)
        rows = parse_csv_rows(csv_text)
        stats.records_found = len(rows)

        if limit:
            rows = rows[:limit]
            logger.info(f"Limited to {limit} rows for testing")

        # Step 3: Get existing case numbers to skip duplicates
        existing_cases = get_existing_case_numbers(supabase, department_id)

        # Step 4: Build category mapping using Claude
        categories = load_categories(supabase)
        fallback_category = {
            "category_id": categories.get("Other/Other", {}).get("id"),
            "category": "Other",
            "subcategory": "Other",
        }

        # Extract unique offense descriptions from the data
        unique_descriptions = sorted(set(
            row.get("OFFENSE_DESCRIPTION", "").strip()
            for row in rows
            if not is_empty(row.get("OFFENSE_DESCRIPTION", ""))
        ))
        logger.info(f"Found {len(unique_descriptions)} unique offense descriptions")

        category_mapping = build_category_mapping(
            unique_descriptions, claude, categories
        )

        # Step 5: Transform and insert rows in batches
        batch = []
        batch_size = 100

        for i, row in enumerate(rows):
            case_number = row.get("INCIDENT_NUMBER", "").strip()

            # Skip if no case number
            if not case_number:
                stats.records_skipped += 1
                continue

            # Skip duplicates
            if case_number in existing_cases:
                stats.duplicates += 1
                continue

            # Transform the row
            incident = transform_row(row, department_id, category_mapping, fallback_category)
            if incident is None:
                stats.records_skipped += 1
                continue

            # Geocode if missing coordinates and geocoding is enabled
            if not incident["is_geocoded"]:
                stats.missing_location += 1
                if do_geocode and incident["address_raw"]:
                    geo_result = geocode_address(
                        incident["address_raw"], supabase, gmaps_client, stats
                    )
                    if geo_result:
                        incident["latitude"] = geo_result["latitude"]
                        incident["longitude"] = geo_result["longitude"]
                        incident["is_geocoded"] = True
                        incident["geocode_quality"] = geo_result["quality"]
                        incident["confidence_score"] = 0.7

            batch.append(incident)

            # Insert when batch is full
            if len(batch) >= batch_size:
                inserted = insert_incidents_batch(supabase, batch)
                stats.records_inserted += inserted
                stats.records_failed += len(batch) - inserted
                batch = []

                # Progress logging every 1000 rows
                processed = i + 1
                if processed % 1000 == 0:
                    logger.info(
                        f"Progress: {processed:,}/{len(rows):,} rows | "
                        f"{stats.records_inserted:,} inserted | "
                        f"{stats.duplicates:,} dupes | "
                        f"{stats.missing_location:,} no coords"
                    )

        # Insert remaining batch
        if batch:
            inserted = insert_incidents_batch(supabase, batch)
            stats.records_inserted += inserted
            stats.records_failed += len(batch) - inserted

        # Complete the ingestion run
        complete_ingestion_run(supabase, run_id, stats)
        logger.info(stats.summary())

    except Exception as e:
        logger.exception(f"Ingestion failed: {e}")
        complete_ingestion_run(supabase, run_id, stats, error=str(e))
        raise


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Boston PD crime data")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of rows to process (for testing)",
    )
    parser.add_argument(
        "--geocode",
        action="store_true",
        help="Geocode rows missing coordinates (costs Google API credits)",
    )
    args = parser.parse_args()

    run_ingestion(limit=args.limit, do_geocode=args.geocode)
