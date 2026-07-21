from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.matched_controls import (
    assign_temporal_splits,
    compute_feature_row,
    rolling_crossing_mask,
    select_controls_for_event,
)


def make_frame(start: datetime, minutes: int, price: float = 100.0) -> pd.DataFrame:
    index = pd.date_range(start, periods=minutes, freq="1min", tz="UTC")
    frame = pd.DataFrame(index=index)
    frame["open"] = price
    frame["high"] = price
    frame["low"] = price
    frame["close"] = price
    frame["volume"] = 100.0
    frame["quote_volume"] = 10_000.0
    frame["trade_count"] = 100
    frame["taker_buy_base_volume"] = 50.0
    frame["taker_buy_quote_volume"] = 5_000.0
    frame["observed"] = True
    frame.index.name = "open_time"
    return frame


def test_temporal_split_keeps_whole_dates_and_all_three_splits() -> None:
    events = []
    for day_index in range(12):
        for event_index in range(2 if day_index % 3 else 3):
            events.append(
                {
                    "id": f"{day_index}-{event_index}",
                    "event_date": (date(2026, 5, 1) + timedelta(days=day_index)).isoformat(),
                }
            )
    mapping, summary = assign_temporal_splits(events, 70, 15)
    assert set(mapping.values()) == {"discovery", "validation", "sealed_test"}
    assert [row["split"] for row in summary] == ["discovery", "validation", "sealed_test"]
    ordered = [mapping[day] for day in sorted(mapping)]
    assert ordered == sorted(ordered, key={"discovery": 0, "validation": 1, "sealed_test": 2}.get)


def test_rolling_crossing_uses_prior_minute_and_conservative_window() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = make_frame(start, 181, price=101.0)
    frame.loc[start, "low"] = 100.0
    frame.loc[start + timedelta(minutes=179), "high"] = 150.0
    mask = rolling_crossing_mask(frame, threshold_pct=50, window_minutes=180)
    assert bool(mask.loc[start + timedelta(minutes=179)]) is True

    frame.loc[start + timedelta(minutes=179), "high"] = 149.99
    frame.loc[start + timedelta(minutes=180), "high"] = 150.0
    mask = rolling_crossing_mask(frame, threshold_pct=50, window_minutes=180)
    # The t=0 baseline is now outside the conservative 179-minute open-time gap.
    assert bool(mask.loc[start + timedelta(minutes=180)]) is False


def test_features_do_not_use_current_or_future_minutes() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = make_frame(start, 13 * 1440)
    # Add deterministic pre-decision movement so returns are non-zero.
    frame["close"] = 100 + np.arange(len(frame)) * 0.001
    frame["open"] = frame["close"]
    frame["high"] = frame["close"] + 0.01
    frame["low"] = frame["close"] - 0.01
    anchor = start + timedelta(days=12, hours=12)
    sample = {
        "sample_id": "event:1",
        "match_group_id": "1",
        "sample_type": "event",
        "label": 1,
        "split": "discovery",
        "symbol": "TESTUSDT",
        "base_asset": "TEST",
        "quote_asset": "USDT",
        "event_id": "1",
        "control_rank": None,
        "anchor_time": anchor.isoformat(),
    }
    before = compute_feature_row(
        frame,
        sample=sample,
        horizon_minutes=60,
        prior_days=10,
        min_entry_notional=500,
        reference_frames={},
    )
    decision = anchor - timedelta(minutes=60)
    mutated = frame.copy()
    mutated.loc[decision:, ["open", "high", "low", "close", "quote_volume"]] = [999, 1200, 1, 1100, 10**12]
    after = compute_feature_row(
        mutated,
        sample=sample,
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


def test_control_selection_excludes_event_and_nearby_surge_windows() -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    frame = make_frame(start, 24 * 1440)
    # Create a genuine conservative crossing on May 10 at noon.
    surge_low_time = datetime(2026, 5, 10, 9, 1, tzinfo=timezone.utc)
    surge_cross_time = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    frame.loc[surge_low_time, "low"] = 100.0
    frame.loc[surge_cross_time, "high"] = 150.0
    crossing = rolling_crossing_mask(frame, threshold_pct=50, window_minutes=180)

    event_anchor = datetime(2026, 5, 18, 12, 0, 20, tzinfo=timezone.utc)
    event = {
        "id": "11111111-1111-1111-1111-111111111111",
        "symbol": "TESTUSDT",
        "base_asset": "TEST",
        "quote_asset": "USDT",
        "event_date": "2026-05-18",
        "first_cross_time": event_anchor.replace(second=0).isoformat(),
        "first_cross_trade_time": event_anchor.isoformat(),
    }
    dates = {date(2026, 5, 1) + timedelta(days=i) for i in range(24)}
    controls, reasons = select_controls_for_event(
        event=event,
        split="discovery",
        split_dates=dates,
        frame=frame,
        crossing_mask=crossing,
        known_event_anchors=[event_anchor],
        controls_per_event=5,
        horizons=(15, 30, 60, 120),
        prior_days=2,
        contamination_before_minutes=120,
        contamination_after_minutes=180,
        min_entry_notional=500,
        used_counts=Counter(),
    )
    assert len(controls) == 5
    assert all(row["symbol"] == "TESTUSDT" for row in controls)
    assert all(abs((datetime.fromisoformat(row["control_anchor_time"]) - event_anchor).total_seconds()) >= 24 * 3600 for row in controls)
    assert all(datetime.fromisoformat(row["control_anchor_time"]).date() != surge_cross_time.date() for row in controls)
    assert reasons["within_24h_of_known_event"] > 0
    assert reasons["near_50pct_crossing"] > 0
