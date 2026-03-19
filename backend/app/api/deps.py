"""
Supabase client dependency for FastAPI.
"""

from functools import lru_cache

from supabase import create_client, Client

from backend.app.config import get_settings


@lru_cache()
def get_supabase() -> Client:
    """Return a cached Supabase client."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
