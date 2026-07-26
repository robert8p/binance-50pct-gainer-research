from pathlib import Path


def test_v12_migration_has_frozen_validation_tables() -> None:
    sql = Path("supabase/migrate_v10_to_v12.sql").read_text(encoding="utf-8")
    assert "binance_entry_validation_jobs" in sql
    assert "v12_exact_entry_validation_1" in sql
    assert "2025-01-01" in sql
    assert "2025-07-01" in sql
    assert "binance_entry_validation_files" in sql
    assert "binance_entry_validation_issues" in sql
