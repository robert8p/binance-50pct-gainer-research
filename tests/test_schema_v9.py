from pathlib import Path
import json


def test_v9_migration_allows_momentum_only_backtest() -> None:
    migration = Path("supabase/migrate_v8_to_v9.sql").read_text()
    assert "confirmation_job_id drop not null" in migration
    assert "v9_momentum_only_continuous_backtest_1" in migration
    assert "take_profit_pct set default 10" in migration


def test_v9_protocol_is_frozen() -> None:
    protocol = json.loads(Path("docs/V9_PREREGISTERED_PROTOCOL.json").read_text())
    assert protocol["signal_rule"]["minimum_components"] == 3
    assert protocol["execution"]["take_profit_pct"] == 10.0
    assert protocol["execution"]["stop_loss_pct"] == 5.0
    assert protocol["execution"]["maximum_hold_minutes"] == 180
    assert protocol["historical_window"]["start"] == "2025-07-01"
    assert protocol["historical_window"]["end_exclusive"] == "2025-11-01"
