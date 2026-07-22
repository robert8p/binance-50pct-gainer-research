from pathlib import Path


def test_v4_schema_contains_context_contract_and_historical_dates() -> None:
    schema = Path("supabase/schema.sql").read_text(encoding="utf-8").lower()
    assert "window_start_date date" in schema
    assert "window_end_date_exclusive date" in schema
    for table in ("binance_context_jobs", "binance_context_files", "binance_context_issues"):
        assert f"create table if not exists {table}" in schema
        assert f"alter table {table} enable row level security" in schema
    assert "research_mode" in schema
    assert "14400" in schema


def test_v3_to_v4_migration_is_additive() -> None:
    sql = Path("supabase/migrate_v3_to_v4.sql").read_text(encoding="utf-8").lower()
    for forbidden in ("drop table", "truncate table", "delete from", "drop column"):
        assert forbidden not in sql
    assert "binance_context_jobs" in sql
    assert "window_start_date" in sql
