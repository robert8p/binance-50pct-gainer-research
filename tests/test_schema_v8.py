import json
from pathlib import Path


def test_v8_migration_is_additive_and_adds_local_low_confirmation_fields() -> None:
    schema = Path("supabase/schema.sql").read_text(encoding="utf-8").lower()
    migration = Path("supabase/migrate_v7_to_v8.sql").read_text(encoding="utf-8").lower()
    for forbidden in ("drop table", "truncate table", "delete from", "drop column"):
        assert forbidden not in migration
    assert "alter column baseline_context_job_id drop not null" in migration
    assert "add column if not exists scan_id" in migration
    assert "local_low_window_minutes" in migration
    assert "cluster_rr_ci_low" in migration
    assert "duration_bands_positive" in migration
    assert "v8_h3_local_low_confirmation_1" in migration
    assert "v8_h3_continuous_executable_backtest_1" in migration
    assert "binance_confirmation_issues" in schema


def test_v8_protocol_freezes_h3_and_keeps_three_hour_trade_hold_separate() -> None:
    protocol = json.loads(Path("docs/V8_PREREGISTERED_PROTOCOL.json").read_text(encoding="utf-8"))
    assert protocol["target_event"]["rolling_window_minutes"] == 480
    assert protocol["fresh_confirmation"]["precursor"]["id"] == "H3_VOLATILITY_REVERSAL"
    assert protocol["fresh_confirmation"]["control_design"] == "same_scanner_rolling_minimum"
    assert protocol["continuous_backtest"]["arm_window_minutes"] == 480
    assert protocol["continuous_backtest"]["maximum_hold_minutes"] == 180
