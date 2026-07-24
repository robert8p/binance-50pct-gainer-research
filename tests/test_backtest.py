from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.backtest import BACKTEST_PROTOCOL, candidate_signals, compute_signal_frame, simulate_execution


def make_signal_history() -> pd.DataFrame:
    minutes = 16_000
    index = pd.date_range(datetime(2026, 1, 1, tzinfo=timezone.utc), periods=minutes, freq="1min")
    close = np.full(minutes, 100.0)
    # Latest day ignites by 6%; the earlier week is flat.
    close[-1441:] = np.linspace(100.0, 106.0, 1441)
    # Strong last-15-minute continuation.
    close[-16:] = np.linspace(103.5, 106.0, 16)
    quote = np.full(minutes, 100.0)
    quote[-1440:] = 220.0
    quote[-15:] = 5_000.0
    frame = pd.DataFrame(index=index)
    frame["open"] = close
    frame["high"] = close * 1.001
    frame["low"] = close * 0.999
    frame["close"] = close
    frame["volume"] = quote / close
    frame["quote_volume"] = quote
    frame["trade_count"] = 10
    frame["taker_buy_base_volume"] = frame["volume"] / 2
    frame["taker_buy_quote_volume"] = quote / 2
    frame["observed"] = True
    return frame


def test_continuous_signal_is_lookahead_safe_and_finds_two_stage_candidate() -> None:
    frame = make_signal_history()
    start = frame.index[-500].to_pydatetime()
    end = (frame.index[-1] + pd.Timedelta(minutes=1)).to_pydatetime()
    signals = compute_signal_frame(frame, start, end)
    assert signals["h1"].any()
    assert signals["late_trigger"].any()
    candidates = candidate_signals("TESTUSDT", signals)
    assert candidates
    first = candidates[0]
    assert first["late_components_passed"] >= 3
    assert datetime.fromisoformat(first["signal_decision_time"]) > datetime.fromisoformat(first["signal_bar_open"])


def test_execution_uses_aggressor_side_and_applies_fees() -> None:
    signal_time = datetime(2026, 3, 1, 12, 1, tzinfo=timezone.utc)
    candidate = {
        "symbol": "TESTUSDT",
        "signal_decision_time": signal_time.isoformat(),
        "signal_close": 100.0,
        "late_components_passed": 4,
    }
    rows = []
    # Buyer-initiated executions prove a 500 quote-unit entry.
    for i in range(10):
        rows.append({
            "symbol": "TESTUSDT", "agg_trade_id": i, "price": 100.0, "quantity": 0.5,
            "time": pd.Timestamp(signal_time + timedelta(seconds=i + 1)), "is_buyer_maker": False,
        })
    trigger = signal_time + timedelta(minutes=10)
    rows.append({
        "symbol": "TESTUSDT", "agg_trade_id": 20, "price": 115.1, "quantity": 0.01,
        "time": pd.Timestamp(trigger), "is_buyer_maker": False,
    })
    # Seller-initiated executions prove the market-sell exit.
    for i in range(10):
        rows.append({
            "symbol": "TESTUSDT", "agg_trade_id": 30 + i, "price": 114.8, "quantity": 0.5,
            "time": pd.Timestamp(trigger + timedelta(seconds=i + 1)), "is_buyer_maker": True,
        })
    result = simulate_execution(candidate, pd.DataFrame(rows).sort_values(["time", "agg_trade_id"]))
    assert result["execution_status"] == "completed"
    assert result["exit_reason"] == "take_profit"
    assert result["gross_return_pct"] > result["net_return_pct"]
    assert result["net_pnl_quote"] > 0
    assert BACKTEST_PROTOCOL["continuation_rule"]["arm_window_minutes"] == 480
    assert BACKTEST_PROTOCOL["execution"]["maximum_hold_minutes"] == 180
    assert BACKTEST_PROTOCOL["execution"]["maximum_filled_entries_per_utc_day"] == 5
