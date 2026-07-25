from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from app.chatgpt_export import (
    PROTOCOL_VERSION,
    _split_calendar_days,
    _zip_directory,
    extract_raw_window,
    safe_filename,
)


def _frame(start: str, minutes: int) -> pd.DataFrame:
    index = pd.date_range(start, periods=minutes, freq="1min", tz="UTC")
    values = np.linspace(1.0, 2.0, minutes)
    frame = pd.DataFrame(index=index)
    frame.index.name = "open_time"
    frame["open"] = values
    frame["high"] = values * 1.001
    frame["low"] = values * 0.999
    frame["close"] = values
    frame["volume"] = 10.0
    frame["quote_volume"] = 20.0
    frame["trade_count"] = 5
    frame["taker_buy_base_volume"] = 6.0
    frame["taker_buy_quote_volume"] = 12.0
    frame["observed"] = True
    return frame


def test_extract_raw_window_stops_at_baseline_and_keeps_raw_data() -> None:
    frame = _frame("2025-01-01T00:00:00Z", 3 * 1440)
    baseline = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
    result, quality = extract_raw_window(
        frame,
        baseline,
        prior_days=1,
        include_baseline_bar=True,
        sample_id="sample-1",
    )
    assert len(result) == 1441
    assert result["relative_minute"].min() == -1440
    assert result["relative_minute"].max() == 0
    assert result["open_time"].max() == pd.Timestamp(baseline)
    assert quality["complete_history"] is True
    assert "ret_15m_pct" not in result.columns
    assert set(["open", "high", "low", "close", "quote_volume", "trade_count"]).issubset(result.columns)


def test_safe_filename_handles_non_latin_symbols() -> None:
    result = safe_filename("币安人生USDT")
    assert result.isascii()
    assert "/" not in result
    assert result
    assert safe_filename("BTC/USDT") == "BTC_USDT"


def test_temporal_splits_keep_whole_dates() -> None:
    events = [
        {"event_date": f"2025-01-{day:02d}"}
        for day in range(1, 11)
    ]
    mapping, split_dates, summary = _split_calendar_days(
        events,
        date(2025, 1, 1),
        date(2025, 1, 11),
        60,
        20,
    )
    assert set(mapping.values()) == {"discovery", "validation", "sealed_test"}
    assert not (split_dates["discovery"] & split_dates["validation"])
    assert not (split_dates["validation"] & split_dates["sealed_test"])
    assert sum(row["events"] for row in summary) == 10


def test_zip_directory_preserves_parquet_and_text(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("neutral", encoding="utf-8")
    (source / "data.parquet").write_bytes(b"PAR1synthetic")
    destination = tmp_path / "package.zip"
    _zip_directory(source, destination)
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {"README.md", "data.parquet"}


def test_protocol_is_neutral_export() -> None:
    assert PROTOCOL_VERSION == "v10_2026_discovery_export_1"


def test_exporter_builds_2026_discovery_package_without_feature_selection(tmp_path: Path, monkeypatch) -> None:
    from datetime import timedelta
    from collections import Counter
    from types import SimpleNamespace
    import shutil

    from app.chatgpt_export import ChatGPTResearchExporter

    scan_id = "00000000-0000-0000-0000-000000000001"
    events = []
    for index, day in enumerate(("2026-01-20", "2026-04-20", "2026-07-20"), start=1):
        baseline = datetime.fromisoformat(day + "T12:00:00+00:00")
        events.append({
            "id": f"00000000-0000-0000-0000-{index:012d}",
            "scan_id": scan_id,
            "event_date": day,
            "symbol": "TESTUSDT",
            "base_asset": "TEST",
            "quote_asset": "USDT",
            "baseline_time": baseline.isoformat(),
            "first_cross_time": (baseline + timedelta(hours=4)).isoformat(),
            "minutes_baseline_open_to_cross_open": 240,
            "rolling_gain_pct_at_cross_trade": 50.0,
            "sellability_pass": True,
            "exit_vwap": 1.5,
            "exit_vwap_vs_threshold_pct": -1.0,
        })

    frame = _frame("2025-12-20T00:00:00Z", 225 * 1440)

    class FakeDB:
        def __init__(self) -> None:
            self.uploads: dict[str, Path] = {}
            self.file_rows = []
            self.inserts = []

        def select(self, table, **kwargs):
            if table == "binance_scan_jobs":
                return [{
                    "id": scan_id,
                    "status": "completed",
                    "event_definition_version": "v7_rolling_8h",
                    "window_minutes": 480,
                    "window_start_date": "2026-01-01",
                    "window_end_date_exclusive": "2026-07-25",
                    "threshold_pct": 50,
                }]
            return []

        def select_all(self, table, **kwargs):
            if table == "binance_gainer_events":
                return [dict(row) for row in events]
            return []

        def update(self, *args, **kwargs):
            return None

        def insert(self, table, payload):
            self.inserts.append((table, payload))
            return payload if isinstance(payload, list) else [payload]

        def upsert(self, table, payload, **kwargs):
            self.file_rows.extend(payload)

        def upload_file(self, storage_path, local_path, content_type):
            destination = tmp_path / "uploads" / storage_path.replace("/", "__")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, destination)
            self.uploads[storage_path] = destination

    fake_db = FakeDB()
    exporter = ChatGPTResearchExporter(fake_db, object(), tmp_path)
    exporter.cache = SimpleNamespace(load_symbol=lambda symbol, start, end: SimpleNamespace(
        frame=frame,
        source_manifest=[{
            "symbol": symbol,
            "period": "2026-01",
            "granularity": "monthly",
            "source": "synthetic",
            "sha256": "abc",
        }],
    ))

    control_counter = {"value": 0}

    def fake_controls(**kwargs):
        event = kwargs["event"]
        baseline = datetime.fromisoformat(event["baseline_time"]) - timedelta(days=1)
        control_counter["value"] += 1
        control_id = f"10000000-0000-0000-0000-{control_counter['value']:012d}"
        return ([{
            "sample_id": control_id,
            "control_id": control_id,
            "event_id": event["id"],
            "match_group_id": event["id"],
            "base_asset": event["base_asset"],
            "quote_asset": event["quote_asset"],
            "control_rank": 1,
            "baseline_time": baseline.isoformat(),
            "pseudo_cross_time": (baseline + timedelta(hours=4)).isoformat(),
            "event_duration_minutes": 240,
            "event_duration_band": "gt_3h_to_6h",
            "selected_baseline_duration_minutes": 240,
            "selected_baseline_duration_band": "gt_3h_to_6h",
            "maximum_future_8h_gain_pct": 12.0,
            "clock_offset_minutes": 0,
            "calendar_distance_days": 1,
            "duration_difference_minutes": 0,
            "match_tier": "synthetic",
            "prior_global_reuse_count": 0,
        }], Counter())

    monkeypatch.setattr("app.chatgpt_export.select_local_low_controls_for_event", fake_controls)
    monkeypatch.setattr(pd.DataFrame, "to_parquet", lambda self, path, **kwargs: Path(path).write_bytes(b"PAR1synthetic"))

    result = exporter.run({
        "id": "20000000-0000-0000-0000-000000000001",
        "scan_id": scan_id,
        "protocol_version": PROTOCOL_VERSION,
        "controls_per_event": 5,
        "prior_days": 10,
        "discovery_pct": 60,
        "validation_pct": 20,
        "include_baseline_bar": True,
    })

    assert result["samples_exported"] == 6, (result, fake_db.inserts)
    assert result["controls_created"] == 3
    filenames = {row["filename"] for row in fake_db.file_rows}
    assert filenames == {
        "CHATGPT_RESEARCH_INDEX.zip",
        "DISCOVERY_2026_UPLOAD_TO_CHATGPT.zip",
    }
    discovery_path = next(path for key, path in fake_db.uploads.items() if key.endswith("DISCOVERY_2026_UPLOAD_TO_CHATGPT.zip"))
    with zipfile.ZipFile(discovery_path) as archive:
        assert "samples.csv" in archive.namelist()
        assert any(name.startswith("minute_data/") for name in archive.namelist())
        assert "DATA_DICTIONARY.md" in archive.namelist()
        dictionary = archive.read("DATA_DICTIONARY.md").decode()
        assert "no preferred predictor" in dictionary
