from pathlib import Path


def test_v10_dashboard_exposes_full_universe_export_and_cancel() -> None:
    template = Path("app/templates/index.html").read_text(encoding="utf-8")
    assert "Binance ChatGPT Research Exporter" in template
    assert 'action="/chatgpt-export"' in template
    assert 'action="/continuous-backtest"' not in template
    assert "DISCOVERY_2026_UNIVERSE_REFERENCE.zip" in template
    assert "DISCOVERY_2026_SYMBOLS_PART_*.zip" in template
    assert "Full-universe symbols" in template
    assert "/cancel" in template
    assert "2026-01-01" in template
    assert "2026-07-25" in template


def test_v10_health_version_is_declared() -> None:
    source = Path("app/web.py").read_text(encoding="utf-8")
    assert 'version="10.2.0"' in source
    assert '"version": "10.2.0"' in source
    assert "V9 is retired" in source
    assert "v10_2026_full_universe_discovery_export_2" in source


def test_v10_allows_205_day_explicit_scan() -> None:
    web_source = Path("app/web.py").read_text(encoding="utf-8")
    scanner_source = Path("app/scanner.py").read_text(encoding="utf-8")
    assert "span <= 240" in web_source
    assert "span_days > 240" in scanner_source
