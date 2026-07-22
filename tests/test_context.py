from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.context import CONTEXT_WINDOWS, compute_context_feature_row


def make_frame(start: datetime, minutes: int) -> pd.DataFrame:
    index = pd.date_range(start, periods=minutes, freq="1min", tz="UTC")
    price = 100.0 * np.exp(np.arange(minutes) * 0.000001)
    frame = pd.DataFrame(index=index)
    frame["open"] = price
    frame["high"] = price * 1.0005
    frame["low"] = price * 0.9995
    frame["close"] = price
    frame["volume"] = 100.0
    frame["quote_volume"] = 10_000.0 + np.arange(minutes) % 1440
    frame["trade_count"] = 100
    frame["taker_buy_base_volume"] = 50.0
    frame["taker_buy_quote_volume"] = frame["quote_volume"] * 0.5
    frame["observed"] = True
    frame.index.name = "open_time"
    return frame


def sample(anchor: datetime) -> dict:
    return {
        "sample_id": "event:1",
        "match_group_id": "1",
        "sample_type": "event",
        "label": 1,
        "split": "discovery",
        "symbol": "TESTUSDT",
        "base_asset": "TEST",
        "quote_asset": "USDT",
        "event_id": "1",
        "control_id": None,
        "control_rank": None,
        "anchor_time": anchor.isoformat(),
    }


def test_context_contains_full_ten_day_windows() -> None:
    assert 14400 in CONTEXT_WINDOWS
    assert 10080 in CONTEXT_WINDOWS
    assert 7200 in CONTEXT_WINDOWS


def test_context_features_use_only_completed_bars_before_decision() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = make_frame(start, 15 * 1440)
    anchor = start + timedelta(days=14, hours=12)
    before = compute_context_feature_row(
        frame,
        sample=sample(anchor),
        horizon_minutes=60,
        prior_days=10,
        min_entry_notional=500,
        reference_frames={},
    )
    decision = anchor - timedelta(minutes=60)
    mutated = frame.copy()
    mutated.loc[decision:, ["open", "high", "low", "close", "quote_volume", "trade_count"]] = [999, 1200, 1, 1100, 10**12, 10**9]
    after = compute_context_feature_row(
        mutated,
        sample=sample(anchor),
        horizon_minutes=60,
        prior_days=10,
        min_entry_notional=500,
        reference_frames={},
    )
    for key, value in before.items():
        if key.startswith("outcome_"):
            continue
        assert after[key] == value, key
    assert before["last_complete_bar_open"] == (decision - timedelta(minutes=1)).isoformat()


def test_context_calculates_long_horizon_and_structural_features() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = make_frame(start, 15 * 1440)
    anchor = start + timedelta(days=14, hours=12)
    row = compute_context_feature_row(
        frame,
        sample=sample(anchor),
        horizon_minutes=15,
        prior_days=10,
        min_entry_notional=500,
        reference_frames={},
    )
    for key in (
        "ret_14400m_pct",
        "quote_volume_10080m",
        "log_price_trend_7200m_pct_per_day",
        "daily_quote_volume_trend_pct_per_day",
        "breakout_episode_count_10d",
        "quote_volume_60m_vs_prior_7d_same_time",
        "volatility_3d_to_10d_ratio",
        "return_acceleration_3d_vs_10d_pct_points_per_day",
    ):
        assert key in row
    assert row["feature_quality_status"] == "pass"
