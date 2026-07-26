from pathlib import Path


def test_v12_dashboard_exposes_exact_entry_validation_and_cancel() -> None:
    template = Path("app/templates/index.html").read_text(encoding="utf-8")
    assert "Binance Exact Entry Validation" in template
    assert "/entry-validation" in template
    assert "Queue V12 validation" in template
    assert "No stop-loss is used" in template
    assert "ENTRY_VALIDATION_2025_RESULTS.zip" in template
    assert "/entry-validation/{{ job.id }}/cancel" in template


def test_v12_health_version_is_declared() -> None:
    source = Path("app/web.py").read_text(encoding="utf-8")
    assert 'version="12.0.0"' in source
    assert '"version": "12.0.0"' in source
