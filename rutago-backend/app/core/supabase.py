from supabase import create_client, Client
from app.core.config import get_settings
from functools import lru_cache


@lru_cache
def get_supabase() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def get_supabase_anon() -> Client:
    """Cliente con clave anónima — para operaciones de auth del usuario."""
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_anon_key)
