from pathlib import Path


def test_v10_dashboard_exposes_neutral_export_not_v9_backtest() -> None:
    template = Path("app/templates/index.html").read_text(encoding="utf-8")
    assert "Binance ChatGPT Research Exporter" in template
    assert 'action="/chatgpt-export"' in template
    assert 'action="/continuous-backtest"' not in template
    assert "DISCOVERY_UPLOAD_TO_CHATGPT.zip" in template
    assert "VALIDATION_DO_NOT_OPEN.zip" in template
    assert "SEALED_TEST_DO_NOT_OPEN.zip" in template


def test_v10_health_version_is_declared() -> None:
    source = Path("app/web.py").read_text(encoding="utf-8")
    assert 'version="10.0.0"' in source
    assert '"version": "10.0.0"' in source
    assert "V9 is retired" in source
