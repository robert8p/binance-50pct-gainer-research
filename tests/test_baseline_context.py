from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.baseline_context import (
    BASELINE_SNAPSHOT_OFFSETS,
    compute_baseline_feature_row,
    control_sample,
    evaluate_frozen_continuation_trigger,
    evaluate_preregistered_hypotheses,
    event_sample,
    pseudo_window_audit,
)


def make_frame(start: datetime, minutes: int) -> pd.DataFrame:
    index = pd.date_range(start, periods=minutes, freq="1min", tz="UTC")
    price = 100.0 * np.exp(np.arange(minutes) * 0.000001)
    frame = pd.DataFrame(index=index)
    frame["open"] = price
    frame["high"] = price * 1.0005
    frame["low"] = price * 0.9995
    frame["close"] = price
    frame["volume"] = 100.0
    frame["quote_volume"] = 10_000.0
    frame["trade_count"] = 100
    frame["taker_buy_base_volume"] = 50.0
    frame["taker_buy_quote_volume"] = 5_000.0
    frame["observed"] = True
    frame.index.name = "open_time"
    return frame


def source_event() -> dict:
    return {
        "id": "event-1",
        "event_date": "2026-04-01",
        "symbol": "TESTUSDT",
        "base_asset": "TEST",
        "quote_asset": "USDT",
        "baseline_time": "2026-04-01T10:00:00+00:00",
        "baseline_trade_time": "2026-04-01T10:00:33.100+00:00",
        "baseline_trade_unresolved": False,
        "baseline_price": 1.0,
        "first_cross_time": "2026-04-01T12:30:00+00:00",
        "first_cross_trade_time": "2026-04-01T12:30:08+00:00",
        "crossing_trade_price": 1.5,
        "minutes_baseline_open_to_cross_open": 150,
        "exact_baseline_to_cross_seconds": 8967.0,
    }


def test_event_and_control_use_symmetric_minute_level_baselines() -> None:
    event = source_event()
    positive = event_sample(event, "discovery")
    assert positive["baseline_anchor_time"] == "2026-04-01T10:00:00+00:00"
    assert positive["cross_anchor_time"] == "2026-04-01T12:30:00+00:00"
    match = {
        "control_id": "control-1",
        "event_id": "event-1",
        "split": "discovery",
        "symbol": "TESTUSDT",
        "control_rank": 1,
        "control_anchor_time": "2026-03-20T18:45:59+00:00",
    }
    control = control_sample(match, event)
    assert control["cross_anchor_time"] == "2026-03-20T18:45:00+00:00"
    assert control["baseline_anchor_time"] == "2026-03-20T16:15:00+00:00"
    assert control["baseline_to_cross_minutes"] == 150


def test_fixed_snapshot_offsets_cover_ten_days_to_baseline() -> None:
    assert BASELINE_SNAPSHOT_OFFSETS == (14400, 10080, 7200, 4320, 2880, 1440, 720, 480, 360, 180, 60, 0)


def test_baseline_features_do_not_use_baseline_or_later_bars() -> None:
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    frame = make_frame(start, 35 * 1440)
    event = event_sample(source_event(), "discovery")
    before = compute_baseline_feature_row(
        frame,
        sample=event,
        snapshot_offset_minutes=0,
        prior_days=10,
        min_entry_notional=500,
        reference_frames={},
    )
    baseline = datetime.fromisoformat(event["baseline_anchor_time"])
    mutated = frame.copy()
    mutated.loc[baseline:, ["open", "high", "low", "close", "quote_volume", "trade_count"]] = [999, 1200, 1, 1100, 10**12, 10**9]
    after = compute_baseline_feature_row(
        mutated,
        sample=event,
        snapshot_offset_minutes=0,
        prior_days=10,
        min_entry_notional=500,
        reference_frames={},
    )
    for key, value in before.items():
        if key.startswith("outcome_") or key.startswith("pseudo_window_"):
            continue
        assert after[key] == value, key
    assert before["last_complete_bar_open"] == (baseline - timedelta(minutes=1)).isoformat()


def test_control_contamination_audit_detects_a_50pct_pseudo_event() -> None:
    start = datetime(2026, 3, 20, 15, 0, tzinfo=timezone.utc)
    frame = make_frame(start, 300)
    event = source_event()
    match = {
        "control_id": "control-1",
        "event_id": "event-1",
        "split": "discovery",
        "symbol": "TESTUSDT",
        "control_rank": 1,
        "control_anchor_time": "2026-03-20T18:45:00+00:00",
    }
    control = control_sample(match, event)
    baseline = pd.Timestamp(control["baseline_anchor_time"])
    cross = pd.Timestamp(control["cross_anchor_time"])
    frame.loc[baseline, "low"] = 100.0
    frame.loc[cross, "high"] = 151.0
    audit = pseudo_window_audit(frame, control)
    assert audit["pseudo_window_crossing_detected"] is True
    assert audit["pseudo_window_contaminated_control"] is True


def test_frozen_hypotheses_and_continuation_rule_are_machine_readable() -> None:
    hypotheses = evaluate_preregistered_hypotheses(
        {
            "ret_prior_1d_to_7d_pct": -2.0,
            "ret_1440m_pct": 8.0,
            "volume_last1d_vs_prior2d_daily_rate": 2.0,
            "ret_1440m_minus_market_proxy_pct_points": 7.0,
            "return_acceleration_1d_vs_prior_2d_pct_points_per_day": 6.0,
            "volatility_1d_to_7d_ratio": 0.5,
        }
    )
    assert all(value is True for value in hypotheses.values())
    continuation = evaluate_frozen_continuation_trigger(
        {
            "entry_liquidity_pass": True,
            "ret_15m_pct": 1.0,
            "quote_volume_15m_vs_prior_7d_same_time": 15.0,
            "position_in_1440m_range": 0.8,
            "max_runup_15m_pct": 2.0,
        }
    )
    assert continuation["late_components_passed"] == 3
    assert continuation["frozen_late_trigger_pass"] is True
