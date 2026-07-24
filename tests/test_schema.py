from pathlib import Path


def test_schema_is_additive_and_contains_required_tables():
    sql = Path("supabase/schema.sql").read_text(encoding="utf-8").lower()
    for forbidden in ("drop table", "truncate table", "delete from"):
        assert forbidden not in sql
    for table in (
        "binance_scan_jobs",
        "binance_symbol_snapshots",
        "binance_daily_bars",
        "binance_gainer_events",
        "binance_event_minute_bars",
        "binance_event_agg_trades",
        "binance_decision_observations",
        "binance_research_jobs",
        "binance_research_files",
    ):
        assert f"create table if not exists {table}" in sql


def test_schema_contains_v2_additive_migration_and_defaults():
    sql = Path("supabase/schema.sql").read_text(encoding="utf-8").lower()
    assert "lookback_days integer not null default 60" in sql
    assert "window_minutes integer not null default 480" in sql
    assert "alter table binance_scan_jobs add column if not exists candidates_found" in sql
    assert "alter table binance_gainer_events add column if not exists baseline_trade_time" in sql
    assert "alter table binance_gainer_events add column if not exists seller_taker_notional_any_price" in sql


def test_v1_to_v2_migration_is_non_destructive():
    sql = Path("supabase/migrate_v1_to_v2.sql").read_text(encoding="utf-8").lower()
    for forbidden in ("drop table", "truncate table", "delete from", "drop column"):
        assert forbidden not in sql
    assert "event_definition_version" in sql
    assert "seller_taker_notional_any_price" in sql
