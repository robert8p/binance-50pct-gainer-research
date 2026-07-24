import json
from pathlib import Path


def test_v7_schema_and_migration_set_eight_hour_defaults_without_rewriting_history() -> None:
    schema = Path("supabase/schema.sql").read_text(encoding="utf-8").lower()
    migration = Path("supabase/migrate_v6_to_v7.sql").read_text(encoding="utf-8").lower()
    for forbidden in ("drop table", "truncate table", "delete from", "drop column"):
        assert forbidden not in migration
    assert "set default 'v7_rolling_8h'" in migration
    assert "alter column window_minutes set default 480" in migration
    assert "alter column contamination_after_minutes set default 480" in migration
    assert "[15,30,60,120,180,480]" in migration
    assert "v7_h1_8h_fresh_confirmation_1" in migration
    assert "v7_continuous_executable_backtest_1" in migration
    assert "binance eight-hour 50% surge research v6 -> v7" in schema


def test_v7_protocol_separates_eight_hour_target_from_three_hour_trade_hold() -> None:
    protocol = json.loads(Path("docs/V7_PREREGISTERED_PROTOCOL.json").read_text(encoding="utf-8"))
    assert protocol["target_event"]["rolling_window_minutes"] == 480
    assert protocol["continuation_trigger"]["arm_window_minutes"] == 480
    assert protocol["execution"]["maximum_hold_minutes"] == 180
    assert protocol["fresh_confirmation_window_recommended"] == {
        "start_inclusive": "2025-11-01",
        "end_exclusive": "2026-01-01",
        "reason": "This period was not used for the opened three-hour confirmation or May-July exploratory work.",
    }
