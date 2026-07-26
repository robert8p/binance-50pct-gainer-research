from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import shutil
import zipfile

import numpy as np
import pandas as pd

from app.chatgpt_export import (
    PROTOCOL_VERSION,
    _background_candidate_times,
    _chunk_symbols,
    _split_calendar_days,
    _zip_directory,
    _prepare_reference_frame,
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


def test_safe_filename_is_ascii_and_collision_resistant() -> None:
    non_latin = safe_filename("币安人生USDT")
    assert non_latin.isascii()
    assert non_latin.startswith("USDT_")
    assert safe_filename("BTC/USDT").startswith("BTC_USDT_")
    assert safe_filename("BTCUSDT") == "BTCUSDT"




def test_prepare_reference_frame_reuses_existing_symbol_column() -> None:
    frame = _frame("2026-01-01T00:00:00Z", 5)
    frame["symbol"] = "BTCUSDT"
    result = _prepare_reference_frame(frame, "ETHUSDT")
    assert list(result.columns) == ["symbol", "open_time", *list((
        "open", "high", "low", "close", "volume", "quote_volume",
        "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume"
    )), "observed"]
    assert set(result["symbol"]) == {"ETHUSDT"}

def test_temporal_splits_keep_whole_dates() -> None:
    events = [{"event_date": f"2025-01-{day:02d}"} for day in range(1, 11)]
    mapping, split_dates, summary = _split_calendar_days(
        events, date(2025, 1, 1), date(2025, 1, 11), 60, 20
    )
    assert set(mapping.values()) == {"discovery", "validation", "sealed_test"}
    assert not (split_dates["discovery"] & split_dates["validation"])
    assert sum(row["events"] for row in summary) == 10


def test_background_candidates_are_deterministic_and_in_range() -> None:
    first = _background_candidate_times(
        "TESTUSDT", date(2026, 1, 1), date(2026, 7, 25), prior_days=10, sample_index=0
    )
    second = _background_candidate_times(
        "TESTUSDT", date(2026, 1, 1), date(2026, 7, 25), prior_days=10, sample_index=0
    )
    assert first == second
    assert len(first) > 100
    assert min(value.date() for value in first) >= date(2026, 1, 13)
    assert max(value.date() for value in first) <= date(2026, 7, 23)


def test_chunk_symbols_respects_target(tmp_path: Path) -> None:
    files = {}
    for symbol, size in (("A", 6), ("B", 6), ("C", 2)):
        path = tmp_path / f"{symbol}.parquet"
        path.write_bytes(b"x" * size)
        files[symbol] = path
    assert _chunk_symbols(files, 10) == [["A"], ["B", "C"]]


def test_zip_directory_preserves_parquet_and_text(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("neutral", encoding="utf-8")
    (source / "data.parquet").write_bytes(b"PAR1synthetic")
    destination = tmp_path / "package.zip"
    _zip_directory(source, destination)
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {"README.md", "data.parquet"}


def test_protocol_is_full_universe_neutral_export() -> None:
    assert PROTOCOL_VERSION == "v11_2026_25pct_full_universe_discovery_export_1"


def test_exporter_builds_full_universe_chunks(tmp_path: Path, monkeypatch) -> None:
    from app.chatgpt_export import ChatGPTResearchExporter

    scan_id = "00000000-0000-0000-0000-000000000001"
    job_id = "20000000-0000-0000-0000-000000000001"
    baseline = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
    events = [{
        "id": "00000000-0000-0000-0000-000000000101",
        "scan_id": scan_id,
        "event_date": "2026-04-20",
        "symbol": "EVENTUSDT",
        "base_asset": "EVENT",
        "quote_asset": "USDT",
        "baseline_time": baseline.isoformat(),
        "first_cross_time": (baseline + timedelta(hours=4)).isoformat(),
        "minutes_baseline_open_to_cross_open": 240,
        "rolling_gain_pct_at_cross_trade": 25.0,
        "sellability_pass": True,
        "exit_vwap": 1.5,
        "exit_vwap_vs_threshold_pct": -1.0,
    }]
    snapshots = [
        {"symbol": "EVENTUSDT", "base_asset": "EVENT", "quote_asset": "USDT", "status": "TRADING", "stablecoin_like": False, "leveraged_token_like": False},
        {"symbol": "NEVERUSDT", "base_asset": "NEVER", "quote_asset": "USDT", "status": "TRADING", "stablecoin_like": False, "leveraged_token_like": False},
    ]
    frame = _frame("2025-12-20T00:00:00Z", 225 * 1440)

    class FakeDB:
        def __init__(self) -> None:
            self.uploads: dict[str, Path] = {}
            self.file_rows = []
            self.inserts = []
            self.job_status = "running"

        def select(self, table, **kwargs):
            if table == "binance_scan_jobs":
                return [{
                    "id": scan_id,
                    "status": "completed",
                    "event_definition_version": "v11_rolling_8h_25pct",
                    "window_minutes": 480,
                    "window_start_date": "2026-01-01",
                    "window_end_date_exclusive": "2026-07-25",
                    "threshold_pct": 25,
                }]
            if table == "binance_chatgpt_export_jobs":
                return [{"id": job_id, "status": self.job_status}]
            return []

        def select_all(self, table, **kwargs):
            if table == "binance_gainer_events":
                return [dict(row) for row in events]
            if table == "binance_symbol_snapshots":
                return [dict(row) for row in snapshots]
            if table == "binance_daily_bars":
                return [{"scan_id": scan_id, "symbol": row["symbol"], "open_time": "2026-01-01T00:00:00+00:00", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "quote_volume": 1, "trade_count": 1, "taker_buy_base_volume": 1, "taker_buy_quote_volume": 1} for row in snapshots]
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
        source_manifest=[{"symbol": symbol, "period": "2026-01", "granularity": "monthly", "source": "synthetic", "sha256": "abc"}],
    ))

    control_id = "10000000-0000-0000-0000-000000000001"
    monkeypatch.setattr(
        "app.chatgpt_export.select_local_low_controls_for_event",
        lambda **kwargs: ([{
            "sample_id": control_id,
            "control_id": control_id,
            "event_id": events[0]["id"],
            "match_group_id": events[0]["id"],
            "base_asset": "EVENT",
            "quote_asset": "USDT",
            "control_rank": 1,
            "baseline_time": (baseline - timedelta(days=1)).isoformat(),
            "pseudo_cross_time": (baseline - timedelta(days=1) + timedelta(hours=4)).isoformat(),
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
        }], Counter()),
    )

    def fake_background(**kwargs):
        symbol = kwargs["symbol_info"]["symbol"]
        b = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        sample_id = f"bg-{symbol}"
        return ([{
            "sample_id": sample_id,
            "match_group_id": sample_id,
            "event_id": None,
            "control_id": sample_id,
            "control_rank": 1,
            "sample_type": "universe_background",
            "control_scope": "full_universe",
            "label": 0,
            "split": "discovery",
            "symbol": symbol,
            "minute_data_file": f"minute_data/{safe_filename(symbol)}.parquet",
            "base_asset": kwargs["symbol_info"]["base_asset"],
            "quote_asset": "USDT",
            "baseline_time": b.isoformat(),
            "cross_or_pseudo_cross_time": (b + timedelta(hours=4)).isoformat(),
            "event_duration_minutes": 240,
            "event_duration_band": "gt_3h_to_6h",
            "selected_baseline_duration_minutes": 240,
            "selected_baseline_duration_band": "gt_3h_to_6h",
            "outcome_maximum_future_8h_gain_pct": 10.0,
            "outcome_sellability_pass": False,
            "outcome_exit_vwap": None,
            "outcome_exit_vwap_vs_threshold_pct": None,
            "match_tier": "synthetic_background",
            "calendar_distance_days": None,
            "clock_offset_minutes": None,
            "duration_difference_minutes": None,
            "history_observed_fraction": 1.0,
            "pre_baseline_quote_volume_5m": 100.0,
        }], Counter())

    monkeypatch.setattr("app.chatgpt_export.select_universe_background_samples", fake_background)
    monkeypatch.setattr(pd.DataFrame, "to_parquet", lambda self, path, **kwargs: Path(path).write_bytes(b"PAR1synthetic"))

    result = exporter.run({
        "id": job_id,
        "scan_id": scan_id,
        "protocol_version": PROTOCOL_VERSION,
        "controls_per_event": 5,
        "prior_days": 10,
        "include_baseline_bar": True,
    })

    assert result["canonical_symbols"] == 2
    assert result["event_bearing_symbols"] == 1
    assert result["full_universe_backgrounds_created"] == 2
    assert result["same_coin_controls_created"] == 1
    filenames = {row["filename"] for row in fake_db.file_rows}
    assert "CHATGPT_25PCT_RESEARCH_INDEX.zip" in filenames
    assert "DISCOVERY_2026_25PCT_UNIVERSE_REFERENCE.zip" in filenames
    assert any(name.startswith("DISCOVERY_2026_25PCT_SYMBOLS_PART_") for name in filenames)
    symbol_zip = next(path for key, path in fake_db.uploads.items() if "SYMBOLS_PART" in key)
    with zipfile.ZipFile(symbol_zip) as archive:
        assert "samples.csv" in archive.namelist()
        assert any(name.startswith("minute_data/") for name in archive.namelist())
        assert "DATA_DICTIONARY.md" in archive.namelist()
