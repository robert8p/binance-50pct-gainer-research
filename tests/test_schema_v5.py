from pathlib import Path


def test_v5_schema_contains_baseline_context_contract() -> None:
    schema = Path("supabase/schema.sql").read_text(encoding="utf-8").lower()
    for table in (
        "binance_baseline_context_jobs",
        "binance_baseline_context_files",
        "binance_baseline_context_issues",
    ):
        assert f"create table if not exists {table}" in schema
        assert f"alter table {table} enable row level security" in schema
    assert "snapshot_offsets_minutes" in schema
    assert "continuation_horizons_minutes" in schema


def test_v4_to_v5_migration_is_additive() -> None:
    sql = Path("supabase/migrate_v4_to_v5.sql").read_text(encoding="utf-8").lower()
    for forbidden in ("drop table", "truncate table", "delete from", "drop column"):
        assert forbidden not in sql
    assert "binance_baseline_context_jobs" in sql
    assert "14400" in sql
