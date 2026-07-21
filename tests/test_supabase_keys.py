from app.supabase import SupabaseClient


def test_modern_secret_key_is_not_sent_as_bearer_token():
    client = SupabaseClient("https://example.supabase.co", "sb_secret_example", "bucket")
    assert client.headers["apikey"] == "sb_secret_example"
    assert "Authorization" not in client.headers


def test_legacy_service_role_key_is_sent_as_bearer_token():
    client = SupabaseClient("https://example.supabase.co", "legacy.jwt.value", "bucket")
    assert client.headers["Authorization"] == "Bearer legacy.jwt.value"
