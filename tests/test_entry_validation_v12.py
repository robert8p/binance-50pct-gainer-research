from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.entry_validation import (
    ENTRY_VALIDATION_PROTOCOL,
    candidate_rows,
    compute_entry_signal_frame,
    select_portfolio_candidates,
    simulate_exact_entry,
)


def _frame(start: str = "2024-12-20", days: int = 14) -> pd.DataFrame:
    index = pd.date_range(start, periods=days * 1440, freq="1min", tz="UTC")
    close = np.full(len(index), 100.0)
    quote = np.full(len(index), 600.0)
    trades = np.full(len(index), 3.0)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": quote / close,
            "quote_volume": quote,
            "trade_count": trades,
            "taker_buy_base_volume": 0.0,
            "taker_buy_quote_volume": 0.0,
            "observed": True,
        },
        index=index,
    )


def test_protocol_is_frozen_no_stop_validation_only() -> None:
    assert ENTRY_VALIDATION_PROTOCOL["window"]["start_inclusive"] == "2025-01-01"
    assert ENTRY_VALIDATION_PROTOCOL["window"]["end_exclusive"] == "2025-07-01"
    assert ENTRY_VALIDATION_PROTOCOL["execution"]["stop_loss"] is None
    assert ENTRY_VALIDATION_PROTOCOL["execution"]["take_profit_pct"] == 15.0
    assert ENTRY_VALIDATION_PROTOCOL["execution"]["maximum_hold_minutes"] == 1440


def test_t3_produces_one_rising_edge() -> None:
    frame = _frame()
    end_bar = frame.index.get_loc(pd.Timestamp("2025-01-01 12:00:00Z"))
    start_bar = end_bar - 60
    base = frame.iloc[start_bar]["close"]
    frame.iloc[start_bar + 1 : end_bar + 1, frame.columns.get_loc("close")] = np.linspace(base, base * 1.02, 60)
    frame.iloc[start_bar + 1 : end_bar + 1, frame.columns.get_loc("open")] = frame.iloc[start_bar + 1 : end_bar + 1]["close"]
    frame.iloc[start_bar + 1 : end_bar + 1, frame.columns.get_loc("high")] = frame.iloc[start_bar + 1 : end_bar + 1]["close"] * 1.001
    frame.iloc[start_bar + 1 : end_bar + 1, frame.columns.get_loc("low")] = frame.iloc[start_bar + 1 : end_bar + 1]["close"] * 0.999
    frame.iloc[end_bar - 29 : end_bar + 1, frame.columns.get_loc("trade_count")] = 10.0
    result = compute_entry_signal_frame(
        frame,
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    rows = candidate_rows("TESTUSDT", result)
    assert any(row["e1_trigger"] and row["t3_pass"] for row in rows)
    assert sum(row["e1_trigger"] for row in rows) == 1


def test_r48_arm_can_precede_e2_confirmation() -> None:
    frame = _frame(days=15)
    arm_end = frame.index.get_loc(pd.Timestamp("2025-01-01 00:00:00Z"))
    # Put the current price >20.75% above a three-day low and create a 6h volume shock.
    frame.iloc[arm_end - 4319 : arm_end - 4000, frame.columns.get_loc("low")] = 70.0
    frame.iloc[arm_end - 359 : arm_end + 1, frame.columns.get_loc("quote_volume")] = 2000.0
    frame.iloc[arm_end, frame.columns.get_loc("close")] = 100.0
    frame.iloc[arm_end, frame.columns.get_loc("high")] = 100.1
    frame.iloc[arm_end, frame.columns.get_loc("low")] = 99.9

    confirm_end = frame.index.get_loc(pd.Timestamp("2025-01-01 06:00:00Z"))
    base = frame.iloc[confirm_end - 60]["close"]
    frame.iloc[confirm_end - 59 : confirm_end + 1, frame.columns.get_loc("close")] = np.linspace(base, base * 1.02, 60)
    frame.iloc[confirm_end - 59 : confirm_end + 1, frame.columns.get_loc("open")] = frame.iloc[confirm_end - 59 : confirm_end + 1]["close"]
    frame.iloc[confirm_end - 59 : confirm_end + 1, frame.columns.get_loc("high")] = frame.iloc[confirm_end - 59 : confirm_end + 1]["close"] * 1.001
    frame.iloc[confirm_end - 59 : confirm_end + 1, frame.columns.get_loc("low")] = frame.iloc[confirm_end - 59 : confirm_end + 1]["close"] * 0.999
    frame.iloc[confirm_end - 29 : confirm_end + 1, frame.columns.get_loc("trade_count")] = 10.0

    result = compute_entry_signal_frame(
        frame,
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    rows = candidate_rows("TESTUSDT", result)
    assert any(row["e2_trigger"] and row["r48_armed_recent"] for row in rows)


def test_selection_enforces_symbol_cooldown_and_daily_cap() -> None:
    rows = []
    for i in range(8):
        rows.append(
            {
                "symbol": "AAAUSDT" if i < 2 else f"S{i}USDT",
                "signal_decision_time": pd.Timestamp("2025-01-01 00:00:00Z") + pd.Timedelta(hours=i),
                "e1_trigger": True,
                "e2_trigger": False,
                "confirmation_components_passed": 1,
                "activity_rank_value": float(10 - i),
            }
        )
    selected, audit = select_portfolio_candidates(pd.DataFrame(rows), "E1_BROAD_MOMENTUM_CONFIRMATION")
    assert len(selected) == 5
    assert (audit["selection_status"] == "suppressed_symbol_cooldown").sum() == 1
    assert (audit["selection_status"] == "suppressed_daily_cap").sum() == 2


def test_exact_execution_hits_target_without_stop() -> None:
    candidate = {
        "symbol": "TESTUSDT",
        "signal_decision_time": "2025-01-01T12:00:00+00:00",
        "signal_close": 100.0,
    }
    rows = []
    for i in range(6):
        rows.append(
            {
                "symbol": "TESTUSDT",
                "agg_trade_id": i,
                "price": 100.0,
                "quantity": 1.0,
                "time": pd.Timestamp("2025-01-01T12:00:01Z") + pd.Timedelta(seconds=i),
                "is_buyer_maker": False,
            }
        )
    # Price first falls 20%, then recovers to +15%; no stop should exit it early.
    rows.append({"symbol": "TESTUSDT", "agg_trade_id": 100, "price": 80.0, "quantity": 1.0, "time": pd.Timestamp("2025-01-01T12:30:00Z"), "is_buyer_maker": False})
    rows.append({"symbol": "TESTUSDT", "agg_trade_id": 101, "price": 115.0, "quantity": 1.0, "time": pd.Timestamp("2025-01-01T13:00:00Z"), "is_buyer_maker": False})
    for i in range(6):
        rows.append(
            {
                "symbol": "TESTUSDT",
                "agg_trade_id": 200 + i,
                "price": 115.0,
                "quantity": 1.0,
                "time": pd.Timestamp("2025-01-01T13:00:01Z") + pd.Timedelta(seconds=i),
                "is_buyer_maker": True,
            }
        )
    result = simulate_exact_entry(candidate, pd.DataFrame(rows))
    assert result["execution_status"] == "completed"
    assert result["exit_reason"] == "take_profit_15pct"
    assert result["mae_480m_pct"] <= -19.9
    assert result["net_return_pct"] > 14.0
