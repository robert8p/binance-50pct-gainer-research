from pathlib import Path


def test_v11_dashboard_exposes_25pct_full_universe_export_and_cancel() -> None:
    template = Path("app/templates/index.html").read_text(encoding="utf-8")
    assert "Binance 25% ChatGPT Research Exporter" in template
    assert 'action="/chatgpt-export"' in template
    assert 'action="/continuous-backtest"' not in template
    assert "Saleable ≥25% rise within 8 hours" in template
    assert 'name="threshold_pct" type="hidden" value="25"' in template
    assert "DISCOVERY_2026_25PCT_UNIVERSE_REFERENCE.zip" in template
    assert "DISCOVERY_2026_25PCT_SYMBOLS_PART_*.zip" in template
    assert "Full-universe symbols" in template
    assert "/cancel" in template
    assert "2026-01-01" in template
    assert "2026-07-25" in template


def test_v11_health_and_protocol_versions_are_declared() -> None:
    source = Path("app/web.py").read_text(encoding="utf-8")
    assert 'version="11.0.0"' in source
    assert '"version": "11.0.0"' in source
    assert "V9 is retired" in source
    assert "v11_2026_25pct_full_universe_discovery_export_1" in source
    assert "v11_rolling_8h_25pct" in source


def test_v11_allows_205_day_explicit_scan() -> None:
    web_source = Path("app/web.py").read_text(encoding="utf-8")
    scanner_source = Path("app/scanner.py").read_text(encoding="utf-8")
    assert "span <= 240" in web_source
    assert "span_days > 240" in scanner_source


def test_v11_scan_threshold_is_frozen_at_25pct() -> None:
    source = Path("app/web.py").read_text(encoding="utf-8")
    assert "V11 event threshold is frozen at 25%" in source
    assert 'threshold_pct: float = Form(25)' in source


def test_v11_saleability_and_quote_universe_are_frozen() -> None:
    source = Path("app/web.py").read_text(encoding="utf-8")
    assert "V11 saleability floor is frozen at 500 quote units" in source
    assert "V11 saleability window is frozen at 300 seconds" in source
    assert "V11 quote preference is frozen at USDT,USDC,FDUSD" in source
