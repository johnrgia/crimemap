"""
Geocoding service with database-level caching.
Checks geocoding_cache before hitting Google Maps API to avoid duplicate lookups.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import googlemaps
from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class GeocodingResult:
    """Result of a geocoding lookup."""
    latitude: float
    longitude: float
    address_normalized: str
    quality: str  # 'ROOFTOP', 'RANGE_INTERPOLATED', 'GEOMETRIC_CENTER', 'APPROXIMATE'
    from_cache: bool = False


class GeocodingService:
    """Geocodes addresses with a database cache layer."""

    def __init__(self, google_api_key: str, supabase_client: Client):
        self.gmaps = googlemaps.Client(key=google_api_key)
        self.supabase = supabase_client
        self._stats = {"cache_hits": 0, "api_calls": 0, "failures": 0}

    async def geocode(self, address: str, city: str = "", state: str = "MA") -> Optional[GeocodingResult]:
        """
        Geocode an address. Checks cache first, falls back to Google API.

        Args:
            address: Raw address string from the police report
            city: City name (helps Google disambiguate)
            state: State abbreviation

        Returns:
            GeocodingResult or None if geocoding failed
        """
        # Build a full address string for lookup
        full_address = self._build_full_address(address, city, state)
        if not full_address:
            return None

        # 1. Check cache first
        cached = self._check_cache(full_address)
        if cached:
            self._stats["cache_hits"] += 1
            logger.debug(f"Cache hit for: {full_address}")
            return cached

        # 2. Cache miss — call Google API
        result = self._call_google_api(full_address)
        if result:
            self._stats["api_calls"] += 1
            # 3. Store in cache for next time
            self._store_in_cache(full_address, result)
            return result

        self._stats["failures"] += 1
        logger.warning(f"Geocoding failed for: {full_address}")
        return None

    def _build_full_address(self, address: str, city: str, state: str) -> str:
        """Build a normalized address string for consistent cache keys."""
        parts = [p.strip() for p in [address, city, state] if p and p.strip()]
        return ", ".join(parts) if parts else ""

    def _check_cache(self, address: str) -> Optional[GeocodingResult]:
        """Check the geocoding_cache table for a previous result."""
        try:
            response = (
                self.supabase.table("geocoding_cache")
                .select("latitude, longitude, address_normalized, quality")
                .eq("address_input", address)
                .limit(1)
                .execute()
            )
            if response.data:
                row = response.data[0]
                return GeocodingResult(
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                    address_normalized=row["address_normalized"] or address,
                    quality=row["quality"] or "unknown",
                    from_cache=True,
                )
        except Exception as e:
            logger.error(f"Cache lookup failed: {e}")
        return None

    def _call_google_api(self, address: str) -> Optional[GeocodingResult]:
        """Call Google Maps Geocoding API."""
        try:
            results = self.gmaps.geocode(address)
            if not results:
                return None

            result = results[0]
            location = result["geometry"]["location"]
            quality = result["geometry"].get("location_type", "APPROXIMATE")

            return GeocodingResult(
                latitude=location["lat"],
                longitude=location["lng"],
                address_normalized=result.get("formatted_address", address),
                quality=quality,
                from_cache=False,
            )
        except Exception as e:
            logger.error(f"Google geocoding API error: {e}")
            return None

    def _store_in_cache(self, address: str, result: GeocodingResult) -> None:
        """Store a geocoding result in the cache table."""
        try:
            self.supabase.table("geocoding_cache").upsert({
                "address_input": address,
                "address_normalized": result.address_normalized,
                "latitude": result.latitude,
                "longitude": result.longitude,
                "quality": result.quality,
                "provider": "google",
            }).execute()
        except Exception as e:
            # Cache write failure is non-fatal — log and move on
            logger.error(f"Failed to cache geocoding result: {e}")

    @property
    def stats(self) -> dict:
        """Return geocoding statistics for monitoring."""
        total = sum(self._stats.values())
        return {
            **self._stats,
            "total": total,
            "cache_hit_rate": (
                self._stats["cache_hits"] / total if total > 0 else 0
            ),
        }
