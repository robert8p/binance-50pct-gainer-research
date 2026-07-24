from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.backtest import BACKTEST_PROTOCOL, candidate_signals, compute_signal_frame, simulate_execution


def make_signal_history() -> pd.DataFrame:
    minutes = 16_000
    index = pd.date_range(datetime(2025, 12, 1, tzinfo=timezone.utc), periods=minutes, freq="1min")
    x = np.arange(minutes)
    # Small but non-zero seven-day background volatility.
    close = 100.0 * np.exp(0.00015 * np.sin(x / 17.0))
    # Material volatility activation begins within the final eight-hour arm window.
    active = np.arange(360)
    close[-360:] = close[-360] * np.exp(0.0040 * np.sin(active / 2.5))
    # Strong final 15-minute continuation.
    close[-16:] = np.linspace(close[-16], close[-16] * 1.035, 16)
    quote = np.full(minutes, 100.0)
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
    start = frame.index[-800].to_pydatetime()
    end = (frame.index[-1] + pd.Timedelta(minutes=1)).to_pydatetime()
    signals = compute_signal_frame(frame, start, end)
    assert signals["h3"].any()
    assert signals["late_trigger"].any()
    candidates = candidate_signals("TESTUSDT", signals)
    assert candidates
    first = candidates[0]
    assert first["late_components_passed"] >= 3
    assert first["volatility_1d_to_7d_ratio"] >= 0.4
    assert datetime.fromisoformat(first["signal_decision_time"]) > datetime.fromisoformat(first["signal_bar_open"])


def test_execution_uses_aggressor_side_and_applies_fees() -> None:
    signal_time = datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc)
    candidate = {
        "symbol": "TESTUSDT",
        "signal_decision_time": signal_time.isoformat(),
        "signal_close": 100.0,
        "late_components_passed": 4,
    }
    rows = []
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
    assert BACKTEST_PROTOCOL["context_rule"]["id"] == "H3_VOLATILITY_REVERSAL"
    assert BACKTEST_PROTOCOL["continuation_rule"]["arm_window_minutes"] == 480
    assert BACKTEST_PROTOCOL["execution"]["maximum_hold_minutes"] == 180
    assert BACKTEST_PROTOCOL["execution"]["maximum_filled_entries_per_utc_day"] == 5
