"""
Geocode Backfill
=================
Finds all incidents with a street address but no coordinates,
geocodes them via Google Maps (with caching), and updates the rows.

Usage: python scripts/geocode_backfill.py
       python scripts/geocode_backfill.py --limit 100    # test with 100
       python scripts/geocode_backfill.py --dry-run       # just count, don't geocode
"""

import argparse
import logging
import os
import time
from collections import Counter
from dataclasses import dataclass, field

import googlemaps
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class Stats:
    total_missing: int = 0
    geocoded_api: int = 0
    geocoded_cache: int = 0
    failed: int = 0
    no_street: int = 0
    updated: int = 0
    start_time: float = field(default_factory=time.time)

    def summary(self) -> str:
        elapsed = time.time() - self.start_time
        total_resolved = self.geocoded_api + self.geocoded_cache
        return (
            f"\n{'=' * 60}\n"
            f"Geocode Backfill Complete ({elapsed:.1f}s)\n"
            f"{'=' * 60}\n"
            f"  Incidents missing coords: {self.total_missing:>8,}\n"
            f"  Resolved via API:         {self.geocoded_api:>8,}\n"
            f"  Resolved via cache:       {self.geocoded_cache:>8,}\n"
            f"  Total resolved:           {total_resolved:>8,}\n"
            f"  Failed to geocode:        {self.failed:>8,}\n"
            f"  No street (skipped):      {self.no_street:>8,}\n"
            f"  DB rows updated:          {self.updated:>8,}\n"
            f"  Estimated API calls saved by cache: {self.geocoded_cache:,}\n"
            f"{'=' * 60}"
        )


def check_cache(supabase, full_address: str):
    """Check geocoding cache. Returns (lat, lng, quality) or None."""
    try:
        result = (
            supabase.table("geocoding_cache")
            .select("latitude, longitude, quality")
            .eq("address_input", full_address)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            if row["latitude"] and row["longitude"]:
                return (row["latitude"], row["longitude"], row["quality"])
            return "FAILED"  # Previously failed — don't retry
    except Exception as e:
        logger.debug(f"Cache error: {e}")
    return None


def geocode_and_cache(gmaps, supabase, full_address: str):
    """Call Google Maps API and cache the result. Returns (lat, lng, quality) or None."""
    try:
        results = gmaps.geocode(full_address)
        if results:
            loc = results[0]["geometry"]["location"]
            quality = results[0]["geometry"].get("location_type", "APPROXIMATE")
            formatted = results[0].get("formatted_address", full_address)

            # Cache success
            try:
                supabase.table("geocoding_cache").upsert({
                    "address_input": full_address,
                    "address_normalized": formatted,
                    "latitude": loc["lat"],
                    "longitude": loc["lng"],
                    "quality": quality,
                    "provider": "google",
                }).execute()
            except Exception:
                pass

            return (loc["lat"], loc["lng"], quality)
        else:
            # Cache failure
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
            return None

    except Exception as e:
        logger.error(f"API error for '{full_address}': {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Geocode backfill")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )
    gmaps = googlemaps.Client(key=os.environ["GOOGLE_MAPS_API_KEY"])
    stats = Stats()

    # Step 1: Find all incidents missing coordinates
    logger.info("Finding incidents without coordinates...")
    incidents_to_fix = []
    offset = 0
    page_size = 1000

    while True:
        result = (
            supabase.table("incidents")
            .select("id, address_raw, city, state")
            .eq("is_geocoded", False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        incidents_to_fix.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size

    stats.total_missing = len(incidents_to_fix)
    logger.info(f"Found {stats.total_missing:,} incidents without coordinates")

    if args.limit:
        incidents_to_fix = incidents_to_fix[:args.limit]
        logger.info(f"Limited to {args.limit}")

    if args.dry_run:
        # Just show unique addresses
        addresses = Counter()
        for inc in incidents_to_fix:
            street = (inc.get("address_raw") or "").strip()
            if street:
                addresses[street] += 1
            else:
                stats.no_street += 1
        logger.info(f"Unique street addresses: {len(addresses)}")
        logger.info(f"Without street: {stats.no_street}")
        logger.info(f"\nTop 20 addresses needing geocoding:")
        for addr, count in addresses.most_common(20):
            logger.info(f"  {addr:<50} {count:>5} incidents")
        return

    # Step 2: Geocode and update
    # Group by address so we geocode each unique address once
    by_address = {}
    for inc in incidents_to_fix:
        street = (inc.get("address_raw") or "").strip()
        if not street:
            stats.no_street += 1
            continue
        city = inc.get("city") or "Boston"
        state = inc.get("state") or "MA"
        full_address = f"{street}, {city}, {state}"
        if full_address not in by_address:
            by_address[full_address] = []
        by_address[full_address].append(inc["id"])

    logger.info(f"Unique addresses to geocode: {len(by_address):,}")
    logger.info(f"Incidents with no street (skipped): {stats.no_street}")

    processed = 0
    for full_address, incident_ids in by_address.items():
        # Check cache first
        cached = check_cache(supabase, full_address)

        if cached == "FAILED":
            stats.failed += len(incident_ids)
            processed += 1
            continue
        elif cached:
            lat, lng, quality = cached
            stats.geocoded_cache += len(incident_ids)
        else:
            # Call API
            result = geocode_and_cache(gmaps, supabase, full_address)
            if result:
                lat, lng, quality = result
                stats.geocoded_api += len(incident_ids)
            else:
                stats.failed += len(incident_ids)
                processed += 1
                continue

        # Update incidents in small batches
        for i in range(0, len(incident_ids), 20):
            batch_ids = incident_ids[i:i + 20]
            try:
                supabase.table("incidents").update({
                    "latitude": lat,
                    "longitude": lng,
                    "location": None,  # trigger will rebuild from lat/lng
                    "is_geocoded": True,
                    "geocode_quality": quality.lower() if quality else "geocoded",
                    "confidence_score": 0.7,
                }).in_("id", batch_ids).execute()
                stats.updated += len(batch_ids)
            except Exception as e:
                # One at a time fallback
                for single_id in batch_ids:
                    try:
                        supabase.table("incidents").update({
                            "latitude": lat,
                            "longitude": lng,
                            "is_geocoded": True,
                            "geocode_quality": quality.lower() if quality else "geocoded",
                            "confidence_score": 0.7,
                        }).eq("id", single_id).execute()
                        stats.updated += 1
                    except Exception:
                        pass

        processed += 1
        if processed % 100 == 0:
            logger.info(
                f"Progress: {processed:,}/{len(by_address):,} addresses | "
                f"API: {stats.geocoded_api:,} | Cache: {stats.geocoded_cache:,} | "
                f"Failed: {stats.failed:,}"
            )

    logger.info(stats.summary())


if __name__ == "__main__":
    main()
