from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.baseline_context import BASELINE_SNAPSHOT_OFFSETS, BaselineContextBuilder


class FakeDb:
    def __init__(self) -> None:
        self.uploads: list[str] = []

    def select(self, table, filters=None, order=None, limit=None):
        if table == "binance_matched_control_jobs":
            return [{
                "id": "matched-1", "scan_id": "scan-1", "status": "completed",
                "discovery_pct": 70, "validation_pct": 15, "contamination_before_minutes": 180,
            }]
        if table == "binance_scan_jobs":
            return [{"id": "scan-1", "window_end_date_exclusive": "2026-05-01"}]
        return []

    def select_all(self, table, filters=None, order=None):
        if table == "binance_gainer_events":
            return [{
                "id": "event-1", "event_date": "2026-04-01", "symbol": "TESTUSDT",
                "base_asset": "TEST", "quote_asset": "USDT", "sellability_pass": True,
                "baseline_time": "2026-04-01T10:00:00+00:00",
                "baseline_trade_time": "2026-04-01T10:00:10+00:00",
                "baseline_trade_unresolved": False, "baseline_price": 100,
                "first_cross_time": "2026-04-01T12:00:00+00:00",
                "first_cross_trade_time": "2026-04-01T12:00:10+00:00",
                "crossing_trade_price": 150, "minutes_baseline_open_to_cross_open": 120,
                "exact_baseline_to_cross_seconds": 7200,
            }]
        if table == "binance_control_matches":
            return [{
                "control_id": "control-1", "event_id": "event-1", "split": "discovery",
                "symbol": "TESTUSDT", "control_rank": 1,
                "control_anchor_time": "2026-03-25T12:00:00+00:00",
            }]
        return []

    def update(self, *args, **kwargs): return []
    def insert(self, *args, **kwargs): return []
    def upsert(self, *args, **kwargs): return []
    def upload_file(self, storage_path, path, content_type): self.uploads.append(storage_path)


def make_frame() -> pd.DataFrame:
    index = pd.date_range(datetime(2026, 3, 1, tzinfo=timezone.utc), periods=40 * 1440, freq="1min", tz="UTC")
    prices = 100 * np.exp(np.arange(len(index)) * 1e-7)
    frame = pd.DataFrame(index=index)
    frame["open"] = prices
    frame["high"] = prices * 1.0005
    frame["low"] = prices * 0.9995
    frame["close"] = prices
    frame["volume"] = 100.0
    frame["quote_volume"] = 10_000.0
    frame["trade_count"] = 100
    frame["taker_buy_base_volume"] = 50.0
    frame["taker_buy_quote_volume"] = 5_000.0
    frame["observed"] = True
    frame.index.name = "open_time"
    return frame


class FakeCache:
    def __init__(self, frame: pd.DataFrame): self.frame = frame
    def load_symbol(self, symbol, start, end):
        return SimpleNamespace(
            frame=self.frame.copy(),
            source_manifest=[{
                "symbol": symbol, "date": "2026-03-01", "status": "available", "source": "fake",
                "source_url": "fake", "row_count": len(self.frame), "sha256": "abc", "cache_filename": "fake",
            }],
        )


def test_baseline_builder_creates_exploratory_and_index_packages(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        pd.DataFrame,
        "to_parquet",
        lambda self, path, *args, **kwargs: Path(path).write_text(self.head(2).to_csv(index=False), encoding="utf-8"),
    )
    db = FakeDb()
    builder = BaselineContextBuilder(db, object(), tmp_path)
    builder.cache = FakeCache(make_frame())
    result = builder.run({
        "id": "job-1", "matched_control_job_id": "matched-1", "research_mode": "exploratory_reuse",
        "prior_days": 10, "snapshot_offsets_minutes": list(BASELINE_SNAPSHOT_OFFSETS),
        "continuation_horizons_minutes": [15], "min_entry_notional": 500,
    })
    assert result["samples_total"] == 2
    assert result["feature_rows"] == 22
    assert result["continuation_rows"] == 2
    assert any(path.endswith("baseline_context_exploratory.zip") for path in db.uploads)
    assert any(path.endswith("baseline_context_index.zip") for path in db.uploads)
