"""
Quick connectivity test for all CrimeMap services.
Run from the project root: python scripts/test_connections.py
"""

import os
import sys

# Add project root to path so we can import our config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

def test_supabase():
    """Test Supabase connection by querying the departments table."""
    print("Testing Supabase...", end=" ")
    try:
        from supabase import create_client
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        client = create_client(url, key)
        result = client.table("departments").select("id").limit(1).execute()
        print(f"OK (departments table accessible, {len(result.data)} rows)")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_postgres():
    """Test direct Postgres/PostGIS connection."""
    print("Testing Postgres + PostGIS...", end=" ")
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("SELECT PostGIS_Version();")
        version = cur.fetchone()[0]
        cur.close()
        conn.close()
        print(f"OK (PostGIS {version})")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_google_maps():
    """Test Google Maps Geocoding API with a known address."""
    print("Testing Google Maps Geocoding...", end=" ")
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=os.environ["GOOGLE_MAPS_API_KEY"])
        result = gmaps.geocode("1 Beacon St, Boston, MA")
        if result:
            loc = result[0]["geometry"]["location"]
            print(f"OK (1 Beacon St → {loc['lat']:.4f}, {loc['lng']:.4f})")
            return True
        else:
            print("FAILED: No results returned")
            return False
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_anthropic():
    """Test Anthropic API with a simple prompt."""
    print("Testing Anthropic (Claude API)...", end=" ")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=50,
            messages=[{"role": "user", "content": "Reply with only: CONNECTION_OK"}],
        )
        text = response.content[0].text.strip()
        print(f"OK (response: {text})")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_incident_categories():
    """Verify the seed data was loaded."""
    print("Testing seed data...", end=" ")
    try:
        from supabase import create_client
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        client = create_client(url, key)
        result = client.table("incident_categories").select("category, subcategory").execute()
        count = len(result.data)
        if count > 0:
            categories = set(row["category"] for row in result.data)
            print(f"OK ({count} categories loaded: {', '.join(sorted(categories))})")
            return True
        else:
            print("FAILED: No categories found — did you run the migration?")
            return False
    except Exception as e:
        print(f"FAILED: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("CrimeMap Connection Tests")
    print("=" * 60)
    print()

    results = {
        "Supabase": test_supabase(),
        "Postgres + PostGIS": test_postgres(),
        "Google Maps": test_google_maps(),
        "Anthropic": test_anthropic(),
        "Seed Data": test_incident_categories(),
    }

    print()
    print("=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    if passed == total:
        print("All systems go! Ready to build the ingestion pipeline.")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"Fix these before proceeding: {', '.join(failed)}")

    print("=" * 60)
