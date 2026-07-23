from pathlib import Path


def test_v6_schema_contains_confirmation_and_backtest_contracts() -> None:
    schema = Path("supabase/schema.sql").read_text(encoding="utf-8").lower()
    for table in (
        "binance_confirmation_jobs",
        "binance_confirmation_files",
        "binance_backtest_jobs",
        "binance_backtest_files",
        "binance_backtest_issues",
    ):
        assert f"create table if not exists {table}" in schema
        assert f"alter table {table} enable row level security" in schema
    assert "take_profit_pct" in schema
    assert "matched_permutation_p" in schema


def test_v5_to_v6_migration_is_additive_and_frozen() -> None:
    sql = Path("supabase/migrate_v5_to_v6.sql").read_text(encoding="utf-8").lower()
    for forbidden in ("drop table", "truncate table", "delete from", "drop column"):
        assert forbidden not in sql
    assert "check (take_profit_pct = 15)" in sql
    assert "check (stop_loss_pct = 5)" in sql
    assert "check (max_hold_minutes = 180)" in sql
