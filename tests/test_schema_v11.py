import json
from pathlib import Path


def test_v11_protocol_freezes_25pct_target_and_neutral_export() -> None:
    protocol = json.loads(Path("docs/V11_2026_25PCT_DISCOVERY_PROTOCOL.json").read_text())
    assert protocol["version"] == "v11_2026_25pct_full_universe_discovery_export_1"
    assert protocol["event_definition"]["threshold_pct"] == 25
    assert protocol["event_definition"]["window_minutes"] == 480
    assert protocol["event_definition"]["persistence_required"] is False
    assert protocol["negative_selection"]["reject_future_25pct_within_8h"] is True
    assert protocol["feature_generation_by_app"] is False
    assert protocol["trading_rule_by_app"] is False
    assert protocol["previous_50pct_results_reusable"] is False


def test_v11_requires_no_new_supabase_migration() -> None:
    assert not Path("supabase/migrate_v10_to_v11.sql").exists()
