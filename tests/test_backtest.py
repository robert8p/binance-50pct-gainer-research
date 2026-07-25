from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.backtest import (
    BACKTEST_PROTOCOL,
    _graduation_decision,
    candidate_signals,
    compute_signal_frame,
    simulate_execution,
)


def make_signal_history() -> pd.DataFrame:
    minutes = 12_000
    index = pd.date_range(datetime(2025, 6, 20, tzinfo=timezone.utc), periods=minutes, freq="1min")
    close = np.full(minutes, 100.0)
    close[-16:] = np.linspace(100.0, 104.0, 16)
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


def test_continuous_signal_is_lookahead_safe_and_finds_momentum_candidate() -> None:
    frame = make_signal_history()
    start = frame.index[-800].to_pydatetime()
    end = (frame.index[-1] + pd.Timedelta(minutes=1)).to_pydatetime()
    signals = compute_signal_frame(frame, start, end)
    assert signals["late_trigger"].any()
    candidates = candidate_signals("TESTUSDT", signals)
    assert candidates
    first = candidates[0]
    assert first["late_components_passed"] >= 3
    assert datetime.fromisoformat(first["signal_decision_time"]) > datetime.fromisoformat(first["signal_bar_open"])
    assert "h3_arm_bar_open" not in first


def test_execution_uses_aggressor_side_and_applies_fees() -> None:
    signal_time = datetime(2025, 7, 1, 12, 1, tzinfo=timezone.utc)
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
        "symbol": "TESTUSDT", "agg_trade_id": 20, "price": 110.1, "quantity": 0.01,
        "time": pd.Timestamp(trigger), "is_buyer_maker": False,
    })
    for i in range(10):
        rows.append({
            "symbol": "TESTUSDT", "agg_trade_id": 30 + i, "price": 109.8, "quantity": 0.5,
            "time": pd.Timestamp(trigger + timedelta(seconds=i + 1)), "is_buyer_maker": True,
        })
    result = simulate_execution(candidate, pd.DataFrame(rows).sort_values(["time", "agg_trade_id"]))
    assert result["execution_status"] == "completed"
    assert result["exit_reason"] == "take_profit"
    assert result["gross_return_pct"] > result["net_return_pct"]
    assert result["net_pnl_quote"] > 0
    assert result["maximum_favourable_excursion_pct"] >= 10.0
    assert BACKTEST_PROTOCOL["signal_rule"]["id"] == "FROZEN_LATE_MOMENTUM_3_OF_4"
    assert BACKTEST_PROTOCOL["execution"]["take_profit_pct"] == 10.0
    assert BACKTEST_PROTOCOL["execution"]["maximum_hold_minutes"] == 180
    assert BACKTEST_PROTOCOL["execution"]["maximum_filled_entries_per_utc_day"] == 5


def test_graduation_requires_every_frozen_criterion() -> None:
    overall = {
        "completed_trades": 120,
        "unique_symbols_traded": 25,
        "total_net_pnl_quote": 600.0,
        "expectancy_quote": 5.0,
        "profit_factor": 1.5,
        "maximum_drawdown_quote": -500.0,
        "maximum_consecutive_losses": 7,
        "largest_symbol_trade_share": 0.10,
    }
    thirds = [{"completed_trades": 40, "expectancy_quote": 2.0} for _ in range(3)]
    performance = {
        "overall": overall,
        "chronological_thirds": thirds,
        "symbol_cluster_bootstrap_expectancy": {"lower_95": 0.5},
    }
    quality = {"minute_archive_mean_coverage": 0.99, "symbol_failure_fraction": 0.01}
    passed = _graduation_decision(performance, quality)
    assert passed["passed"] is True
    performance["chronological_thirds"][2]["expectancy_quote"] = -0.1
    failed = _graduation_decision(performance, quality)
    assert failed["passed"] is False
    assert "positive_expectancy_each_third" in failed["failed_checks"]


def test_backtest_minute_cache_prefers_monthly_archives_for_complete_months(tmp_path, monkeypatch) -> None:
    from datetime import date
    from app.backtest import BacktestMinuteArchiveCache

    class FakeBinance:
        pass

    cache = BacktestMinuteArchiveCache(FakeBinance(), tmp_path)
    calls = []

    def frame_for(start: pd.Timestamp, periods: int) -> pd.DataFrame:
        idx = pd.date_range(start, periods=periods, freq="1min", tz="UTC")
        return pd.DataFrame({
            "symbol": "TESTUSDT", "open_time": idx, "open": 1.0, "high": 1.0,
            "low": 1.0, "close": 1.0, "volume": 1.0,
            "close_time": idx + pd.Timedelta(minutes=1), "quote_volume": 1.0,
            "trade_count": 1, "taker_buy_base_volume": 0.5,
            "taker_buy_quote_volume": 0.5,
        })

    def fake_daily(symbol, day):
        calls.append(("daily", day.isoformat()))
        return frame_for(pd.Timestamp(day, tz="UTC"), 1440), {
            "status": "available", "days_covered": 1,
        }

    def fake_monthly(symbol, month_start):
        calls.append(("monthly", month_start.isoformat()))
        days = (cache._next_month(month_start) - month_start).days
        return frame_for(pd.Timestamp(month_start, tz="UTC"), days * 1440), {
            "status": "available", "days_covered": days,
        }

    monkeypatch.setattr(cache, "_load_daily", fake_daily)
    monkeypatch.setattr(cache, "_load_monthly", fake_monthly)
    loaded = cache.load_symbol("TESTUSDT", date(2025, 6, 30), date(2025, 8, 1))
    assert calls == [("daily", "2025-06-30"), ("monthly", "2025-07-01")]
    assert len(loaded.frame) == 32 * 1440
