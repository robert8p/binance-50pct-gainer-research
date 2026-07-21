from pathlib import Path


def test_v3_schema_contains_matched_control_contract() -> None:
    schema = Path("supabase/schema.sql").read_text(encoding="utf-8")
    for table in (
        "binance_matched_control_jobs",
        "binance_control_matches",
        "binance_matched_control_files",
        "binance_matched_control_issues",
    ):
        assert f"create table if not exists {table}" in schema
        assert f"alter table {table} enable row level security" in schema
    assert "horizons_minutes jsonb" in schema
    assert "sealed_test" in schema
