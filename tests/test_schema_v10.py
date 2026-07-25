from pathlib import Path


def test_v10_migration_defines_neutral_export_tables() -> None:
    sql = Path("supabase/migrate_v9_to_v10.sql").read_text(encoding="utf-8")
    assert "create table if not exists binance_chatgpt_export_jobs" in sql
    assert "create table if not exists binance_chatgpt_export_files" in sql
    assert "create table if not exists binance_chatgpt_export_issues" in sql
    assert "v10_neutral_chatgpt_research_export_1" in sql
    assert "controls_per_event = 5" in sql
    assert "prior_days = 10" in sql
