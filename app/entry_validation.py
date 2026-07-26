from __future__ import annotations

import json
import math
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .backtest import (
    AggTradeArchiveCache,
    BacktestMinuteArchiveCache,
    _basic_performance,
    _fill_by_aggressor,
    _json_safe,
    _symbol_cluster_bootstrap_expectancy,
)
from .binance import BinanceClient, sha256_file
from .classifier import classify_symbol
from .supabase import SupabaseClient


ENTRY_VALIDATION_PROTOCOL: dict[str, Any] = {
    "version": "v12_exact_entry_validation_1",
    "research_status": "untouched_validation_only",
    "window": {
        "start_inclusive": "2025-01-01",
        "end_exclusive": "2025-07-01",
        "sealed_data_not_accessed": "2025-07-01 to 2025-11-01",
    },
    "universe": {
        "quote_assets": ["USDT", "USDC", "FDUSD"],
        "canonical_one_pair_per_base": True,
        "warning": "Uses the currently tradeable canonical universe; historically delisted symbols are absent.",
    },
    "signal_evaluation": "after every completed one-minute bar",
    "same_time_reference": {
        "days": 7,
        "minimum_reference_days": 5,
    },
    "liquidity_proxy": {
        "median_one_minute_quote_volume_60m_min": 500.0,
        "total_quote_volume_60m_min": 30_000.0,
        "trade_count_60m_min": 120.0,
    },
    "confirmation_components": {
        "T3_RETURN_PLUS_TRADES": {
            "return_60m_pct_min": 1.0,
            "second_30m_trade_count_vs_first_30m_min": 1.25,
            "trade_count_60m_vs_prior_7d_same_time_min": 1.5,
        },
        "T4_VOLUME_EXPANSION": {
            "return_60m_pct_min": 0.5,
            "quote_volume_60m_vs_prior_7d_same_time_min": 3.0,
            "second_30m_quote_volume_vs_first_30m_min": 1.25,
        },
        "T5_REACCELERATION_AFTER_PULLBACK": {
            "max_runup_360m_pct_min": 8.0,
            "max_drawdown_360m_pct_max": -4.0,
            "return_60m_pct_min": 1.5,
            "position_in_60m_range_min": 0.75,
        },
    },
    "strategies": {
        "E1_BROAD_MOMENTUM_CONFIRMATION": {
            "entry": "first transition into any T3/T4/T5 confirmation while liquidity proxy passes",
        },
        "E2_R48_ARMED_THEN_CONFIRM": {
            "arming": {
                "price_above_prior_3d_low_pct_min": 20.75,
                "quote_volume_360m_vs_prior_7d_same_time_min": 2.43,
                "arming_ttl_minutes": 2880,
            },
            "entry": "first later transition into any T3/T4/T5 confirmation while armed and liquidity proxy passes",
        },
    },
    "portfolio": {
        "position_quote_notional": 500.0,
        "maximum_selected_signals_per_utc_day_per_strategy": 5,
        "symbol_signal_cooldown_minutes": 1440,
        "same_timestamp_ranking": [
            "confirmation_components_passed descending",
            "maximum of volume/trade same-time ratios descending",
            "symbol ascending",
        ],
    },
    "execution": {
        "entry_fill_window_seconds": 60,
        "entry_proxy": "first buyer-initiated aggregate trades after signal, accumulated to 500 quote units",
        "take_profit_pct": 15.0,
        "stop_loss": None,
        "maximum_hold_minutes": 1440,
        "exit_fill_window_seconds": 300,
        "exit_proxy": "seller-initiated aggregate trades after target touch or time expiry",
        "fee_bps_each_side": 10.0,
        "diagnostic_path_minutes": 1920,
        "diagnostic_targets_pct": [10.0, 15.0, 25.0, 50.0],
        "diagnostic_horizons_minutes": [480, 1440, 1920],
    },
    "graduation": {
        "common": {
            "positive_total_net_pnl": True,
            "minimum_expectancy_quote": 1.0,
            "minimum_profit_factor": 1.25,
            "maximum_drawdown_quote": 5000.0,
            "maximum_consecutive_losses": 10,
            "maximum_largest_symbol_trade_share": 0.15,
            "minimum_exact_entry_fill_rate": 0.90,
            "positive_expectancy_each_chronological_half": True,
            "symbol_cluster_bootstrap_95pct_lower_expectancy_above_zero": True,
            "minimum_minute_archive_mean_coverage": 0.95,
            "maximum_symbol_failure_fraction": 0.05,
        },
        "E1_BROAD_MOMENTUM_CONFIRMATION": {
            "minimum_completed_trades": 100,
            "minimum_unique_symbols": 25,
            "minimum_completed_trades_each_half": 30,
        },
        "E2_R48_ARMED_THEN_CONFIRM": {
            "minimum_completed_trades": 30,
            "minimum_unique_symbols": 15,
            "minimum_completed_trades_each_half": 10,
        },
        "decision": "A failed strategy is retired without threshold retuning. A passing strategy may proceed to the separately sealed period.",
    },
}



class EntryValidationCancelled(RuntimeError):
    pass


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_json_safe(payload), default=str), encoding="utf-8")
    temporary.replace(path)


def _same_time_ratio(series: pd.Series, reference_days: int = 7) -> tuple[pd.Series, pd.Series]:
    refs = pd.concat([series.shift(1440 * day) for day in range(1, reference_days + 1)], axis=1)
    count = refs.notna().sum(axis=1)
    median = refs.median(axis=1, skipna=True)
    return series / median.replace(0, np.nan), count


def _runup_drawdown(values: np.ndarray) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or np.any(~np.isfinite(values)) or np.any(values <= 0):
        return np.nan, np.nan
    running_min = np.minimum.accumulate(values)
    running_max = np.maximum.accumulate(values)
    runup = float(np.max(values / running_min - 1.0) * 100.0)
    drawdown = float(np.min(values / running_max - 1.0) * 100.0)
    return runup, drawdown


def compute_entry_signal_frame(frame: pd.DataFrame, start: datetime, end_exclusive: datetime) -> pd.DataFrame:
    """Compute the frozen V12 signals with no future information."""
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    quote = pd.to_numeric(frame["quote_volume"], errors="coerce")
    trades = pd.to_numeric(frame["trade_count"], errors="coerce")
    observed = frame["observed"].fillna(False).astype(bool)

    q60 = quote.rolling(60, min_periods=60).sum()
    q30 = quote.rolling(30, min_periods=30).sum()
    q_prev30 = q60 - q30
    t60 = trades.rolling(60, min_periods=60).sum()
    t30 = trades.rolling(30, min_periods=30).sum()
    t_prev30 = t60 - t30
    q60_ratio, q60_ref_days = _same_time_ratio(q60)
    t60_ratio, t60_ref_days = _same_time_ratio(t60)
    ret60 = (close / close.shift(60) - 1.0) * 100.0
    low60 = low.rolling(60, min_periods=60).min()
    high60 = high.rolling(60, min_periods=60).max()
    pos60 = (close - low60) / (high60 - low60).replace(0, np.nan)

    liquidity = (
        (quote.rolling(60, min_periods=60).median() >= 500.0)
        & (q60 >= 30_000.0)
        & (t60 >= 120.0)
        & (observed.rolling(60, min_periods=60).sum() == 60)
    ).fillna(False)

    enough_refs_q = q60_ref_days >= 5
    enough_refs_t = t60_ref_days >= 5
    t3 = (
        (ret60 >= 1.0)
        & (t30 >= 1.25 * t_prev30.replace(0, np.nan))
        & (t60_ratio >= 1.5)
        & enough_refs_t
    ).fillna(False)
    t4 = (
        (ret60 >= 0.5)
        & (q60_ratio >= 3.0)
        & (q30 >= 1.25 * q_prev30.replace(0, np.nan))
        & enough_refs_q
    ).fillna(False)

    # T5's rolling path extrema are evaluated only at bars that pass its cheap prefilter.
    t5_prefilter = (
        (ret60 >= 1.5)
        & (pos60 >= 0.75)
        & (observed.rolling(360, min_periods=360).sum() == 360)
    ).fillna(False)
    t5 = pd.Series(False, index=frame.index)
    runup360 = pd.Series(np.nan, index=frame.index, dtype=float)
    drawdown360 = pd.Series(np.nan, index=frame.index, dtype=float)
    values = close.to_numpy(dtype=float)
    positions = np.flatnonzero(t5_prefilter.to_numpy(dtype=bool))
    for idx in positions:
        if idx < 359:
            continue
        runup, drawdown = _runup_drawdown(values[idx - 359 : idx + 1])
        runup360.iat[idx] = runup
        drawdown360.iat[idx] = drawdown
        if np.isfinite(runup) and np.isfinite(drawdown) and runup >= 8.0 and drawdown <= -4.0:
            t5.iat[idx] = True

    confirmation = liquidity & (t3 | t4 | t5)

    q360 = quote.rolling(360, min_periods=360).sum()
    q360_ratio, q360_ref_days = _same_time_ratio(q360)
    low3d = low.rolling(4320, min_periods=4320).min()
    above_3d_low_pct = (close / low3d - 1.0) * 100.0
    r48_arm = (
        (above_3d_low_pct >= 20.75)
        & (q360_ratio >= 2.43)
        & (q360_ref_days >= 5)
        & (observed.rolling(4320, min_periods=4320).sum() == 4320)
    ).fillna(False)
    armed_recent = (
        r48_arm.astype(bool).shift(1, fill_value=False).astype(int).rolling(2880, min_periods=1).max().fillna(0).astype(bool)
    )

    e1_state = confirmation.fillna(False)
    e2_state = (confirmation & armed_recent).fillna(False)
    e1_edge = e1_state & ~e1_state.shift(1, fill_value=False)
    e2_edge = e2_state & ~e2_state.shift(1, fill_value=False)

    result = pd.DataFrame(index=frame.index)
    result["signal_close"] = close
    result["liquidity_pass"] = liquidity
    result["t3_pass"] = t3
    result["t4_pass"] = t4
    result["t5_pass"] = t5
    result["confirmation_components_passed"] = pd.concat([t3, t4, t5], axis=1).sum(axis=1)
    result["e1_edge"] = e1_edge
    result["r48_arm"] = r48_arm
    result["armed_recent"] = armed_recent
    result["e2_edge"] = e2_edge
    result["return_60m_pct"] = ret60
    result["quote_volume_60m"] = q60
    result["quote_volume_60m_ratio"] = q60_ratio
    result["trade_count_60m"] = t60
    result["trade_count_60m_ratio"] = t60_ratio
    result["quote_volume_second_vs_first_half"] = q30 / q_prev30.replace(0, np.nan)
    result["trade_count_second_vs_first_half"] = t30 / t_prev30.replace(0, np.nan)
    result["position_in_60m_range"] = pos60
    result["max_runup_360m_pct"] = runup360
    result["max_drawdown_360m_pct"] = drawdown360
    result["above_prior_3d_low_pct"] = above_3d_low_pct
    result["quote_volume_360m_ratio"] = q360_ratio
    result["activity_rank_value"] = pd.concat([q60_ratio, t60_ratio], axis=1).max(axis=1)

    mask = (result.index >= pd.Timestamp(start)) & (result.index < pd.Timestamp(end_exclusive))
    return result.loc[mask].copy()


def candidate_rows(symbol: str, signal_frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mask = signal_frame["e1_edge"].fillna(False) | signal_frame["e2_edge"].fillna(False)
    for bar, row in signal_frame[mask].iterrows():
        rows.append({
            "symbol": symbol,
            "signal_bar_open": bar.isoformat(),
            "signal_decision_time": (bar + pd.Timedelta(minutes=1)).isoformat(),
            "signal_close": float(row["signal_close"]),
            "e1_trigger": bool(row["e1_edge"]),
            "e2_trigger": bool(row["e2_edge"]),
            "r48_armed_recent": bool(row["armed_recent"]),
            "confirmation_components_passed": int(row["confirmation_components_passed"]),
            "t3_pass": bool(row["t3_pass"]),
            "t4_pass": bool(row["t4_pass"]),
            "t5_pass": bool(row["t5_pass"]),
            "return_60m_pct": float(row["return_60m_pct"]),
            "quote_volume_60m": float(row["quote_volume_60m"]),
            "quote_volume_60m_ratio": float(row["quote_volume_60m_ratio"]) if pd.notna(row["quote_volume_60m_ratio"]) else None,
            "trade_count_60m": float(row["trade_count_60m"]),
            "trade_count_60m_ratio": float(row["trade_count_60m_ratio"]) if pd.notna(row["trade_count_60m_ratio"]) else None,
            "quote_volume_second_vs_first_half": float(row["quote_volume_second_vs_first_half"]) if pd.notna(row["quote_volume_second_vs_first_half"]) else None,
            "trade_count_second_vs_first_half": float(row["trade_count_second_vs_first_half"]) if pd.notna(row["trade_count_second_vs_first_half"]) else None,
            "position_in_60m_range": float(row["position_in_60m_range"]) if pd.notna(row["position_in_60m_range"]) else None,
            "max_runup_360m_pct": float(row["max_runup_360m_pct"]) if pd.notna(row["max_runup_360m_pct"]) else None,
            "max_drawdown_360m_pct": float(row["max_drawdown_360m_pct"]) if pd.notna(row["max_drawdown_360m_pct"]) else None,
            "above_prior_3d_low_pct": float(row["above_prior_3d_low_pct"]) if pd.notna(row["above_prior_3d_low_pct"]) else None,
            "quote_volume_360m_ratio": float(row["quote_volume_360m_ratio"]) if pd.notna(row["quote_volume_360m_ratio"]) else None,
            "activity_rank_value": float(row["activity_rank_value"]) if pd.notna(row["activity_rank_value"]) else 0.0,
        })
    return rows


def select_portfolio_candidates(candidates: pd.DataFrame, strategy: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    trigger_col = "e1_trigger" if strategy == "E1_BROAD_MOMENTUM_CONFIRMATION" else "e2_trigger"
    if candidates.empty or trigger_col not in candidates:
        return pd.DataFrame(), pd.DataFrame()
    pool = candidates[candidates[trigger_col].fillna(False)].copy()
    if pool.empty:
        return pool, pool
    pool["signal_decision_time"] = pd.to_datetime(pool["signal_decision_time"], utc=True)
    pool = pool.sort_values(
        ["signal_decision_time", "confirmation_components_passed", "activity_rank_value", "symbol"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    selected: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    daily_count: Counter[date] = Counter()
    available: defaultdict[str, pd.Timestamp] = defaultdict(lambda: pd.Timestamp.min.tz_localize("UTC"))
    cooldown = pd.Timedelta(minutes=1440)
    for row in pool.to_dict("records"):
        ts = pd.Timestamp(row["signal_decision_time"])
        status = "selected"
        if ts < available[str(row["symbol"])]:
            status = "suppressed_symbol_cooldown"
        elif daily_count[ts.date()] >= 5:
            status = "suppressed_daily_cap"
        else:
            selected.append(row)
            daily_count[ts.date()] += 1
            available[str(row["symbol"])] = ts + cooldown
        audit.append({**row, "selection_status": status, "strategy": strategy})
    return pd.DataFrame(selected), pd.DataFrame(audit)


def _first_target_time(path: pd.DataFrame, entry_vwap: float, target_pct: float, end: datetime) -> datetime | None:
    threshold = entry_vwap * (1.0 + target_pct / 100.0)
    subset = path[(path["time"] <= pd.Timestamp(end)) & (pd.to_numeric(path["price"], errors="coerce") >= threshold)]
    if subset.empty:
        return None
    return pd.Timestamp(subset.iloc[0]["time"]).to_pydatetime()


def simulate_exact_entry(candidate: dict[str, Any], trades: pd.DataFrame) -> dict[str, Any]:
    cfg = ENTRY_VALIDATION_PROTOCOL["execution"]
    signal_time = pd.Timestamp(candidate["signal_decision_time"]).to_pydatetime()
    entry_end = signal_time + timedelta(seconds=int(cfg["entry_fill_window_seconds"]))
    entry = _fill_by_aggressor(
        trades,
        start=signal_time,
        end=entry_end,
        buyer_initiated=True,
        target_quote=500.0,
    )
    if entry is None:
        return {**candidate, "execution_status": "entry_not_filled"}

    entry_time = datetime.fromisoformat(str(entry["fill_completed_at"]))
    entry_vwap = float(entry["vwap"])
    base_qty = float(entry["base_quantity"])
    diagnostic_end = entry_time + timedelta(minutes=int(cfg["diagnostic_path_minutes"]))
    path = trades[(trades["time"] > pd.Timestamp(entry_time)) & (trades["time"] <= pd.Timestamp(diagnostic_end))].copy()
    path["price"] = pd.to_numeric(path["price"], errors="coerce")
    path = path[path["price"].notna() & (path["price"] > 0)].sort_values("time")

    result: dict[str, Any] = {
        **candidate,
        "entry_vwap": entry_vwap,
        "entry_fill_completed_at": entry["fill_completed_at"],
        "entry_trades_used": int(entry["trades_used"]),
        "entry_signal_close_slippage_pct": (entry_vwap / float(candidate["signal_close"]) - 1.0) * 100.0,
        "base_quantity": base_qty,
    }
    for horizon in (480, 1440, 1920):
        end = entry_time + timedelta(minutes=horizon)
        subset = path[path["time"] <= pd.Timestamp(end)]
        prices = subset["price"]
        result[f"mfe_{horizon}m_pct"] = float((prices.max() / entry_vwap - 1.0) * 100.0) if not prices.empty else None
        result[f"mae_{horizon}m_pct"] = float((prices.min() / entry_vwap - 1.0) * 100.0) if not prices.empty else None
        for target in (10, 15, 25, 50):
            hit = _first_target_time(path, entry_vwap, float(target), end)
            result[f"hit_{target}pct_within_{horizon}m"] = hit is not None
            result[f"first_{target}pct_time_within_{horizon}m"] = hit.isoformat() if hit else None

    hold_end = entry_time + timedelta(minutes=1440)
    target_time = _first_target_time(path, entry_vwap, 15.0, hold_end)
    if target_time is not None:
        exit_reason = "take_profit_15pct"
        exit_trigger_time = target_time
        exit_trigger_price = entry_vwap * 1.15
    else:
        exit_reason = "time_24h"
        exit_trigger_time = hold_end
        exit_trigger_price = None
    exit = _fill_by_aggressor(
        trades,
        start=exit_trigger_time,
        end=exit_trigger_time + timedelta(seconds=300),
        buyer_initiated=False,
        target_base=base_qty,
    )
    if exit is None:
        return {
            **result,
            "execution_status": "exit_not_filled",
            "exit_reason": exit_reason,
            "exit_trigger_time": exit_trigger_time.isoformat(),
        }

    exit_quote = float(exit["quote_notional"])
    fee_rate = 10.0 / 10_000.0
    entry_cost = 500.0 * (1.0 + fee_rate)
    exit_proceeds = exit_quote * (1.0 - fee_rate)
    pnl = exit_proceeds - entry_cost
    result.update({
        "execution_status": "completed",
        "exit_reason": exit_reason,
        "exit_trigger_time": exit_trigger_time.isoformat(),
        "exit_trigger_price": exit_trigger_price,
        "exit_vwap": float(exit["vwap"]),
        "exit_fill_completed_at": exit["fill_completed_at"],
        "exit_trades_used": int(exit["trades_used"]),
        "holding_minutes": (datetime.fromisoformat(str(exit["fill_completed_at"])) - entry_time).total_seconds() / 60.0,
        "gross_return_pct": (exit_quote / 500.0 - 1.0) * 100.0,
        "net_return_pct": pnl / entry_cost * 100.0,
        "net_pnl_quote": pnl,
        "fees_quote": 500.0 * fee_rate + exit_quote * fee_rate,
    })
    return result


def _max_concurrency(completed: pd.DataFrame) -> dict[str, Any]:
    if completed.empty:
        return {"maximum_concurrent_positions": 0, "maximum_deployed_quote": 0.0}
    events: list[tuple[pd.Timestamp, int]] = []
    for row in completed.itertuples(index=False):
        events.append((pd.Timestamp(row.entry_fill_completed_at), 1))
        events.append((pd.Timestamp(row.exit_fill_completed_at), -1))
    events.sort(key=lambda x: (x[0], x[1]))
    count = 0
    maximum = 0
    for _, delta in events:
        count += delta
        maximum = max(maximum, count)
    return {"maximum_concurrent_positions": int(maximum), "maximum_deployed_quote": float(maximum * 500.0)}


def performance_report(executions: pd.DataFrame, start: date, end: date) -> dict[str, Any]:
    completed = executions[executions["execution_status"] == "completed"].copy() if not executions.empty else pd.DataFrame()
    overall = _basic_performance(completed, 10_000.0)
    overall.update(_max_concurrency(completed))
    if executions.empty:
        exact_fill_rate = None
    else:
        exact_fill_rate = float((executions["execution_status"] != "entry_not_filled").mean())
    overall["exact_entry_fill_rate"] = exact_fill_rate
    if completed.empty:
        return {
            "overall": overall,
            "chronological_halves": [],
            "monthly": [],
            "by_symbol": [],
            "daily": [],
            "diagnostics": {},
            "symbol_cluster_bootstrap_expectancy": _symbol_cluster_bootstrap_expectancy(completed),
        }
    completed["entry_time"] = pd.to_datetime(completed["entry_fill_completed_at"], utc=True)
    midpoint = datetime.combine(start, time.min, tzinfo=timezone.utc) + (
        datetime.combine(end, time.min, tzinfo=timezone.utc) - datetime.combine(start, time.min, tzinfo=timezone.utc)
    ) / 2
    halves = []
    for label, lo, hi in [
        (1, datetime.combine(start, time.min, tzinfo=timezone.utc), midpoint),
        (2, midpoint, datetime.combine(end, time.min, tzinfo=timezone.utc)),
    ]:
        subset = completed[(completed["entry_time"] >= lo) & (completed["entry_time"] < hi)]
        row = _basic_performance(subset, 10_000.0)
        row.update({"half": label, "start": lo.isoformat(), "end_exclusive": hi.isoformat()})
        halves.append(row)
    monthly = []
    completed["month"] = completed["entry_time"].dt.strftime("%Y-%m")
    for month, subset in completed.groupby("month", sort=True):
        row = _basic_performance(subset, 10_000.0)
        row["month"] = month
        monthly.append(row)
    by_symbol = []
    for symbol, subset in completed.groupby("symbol"):
        row = _basic_performance(subset, 10_000.0)
        row["symbol"] = str(symbol)
        by_symbol.append(row)
    completed["entry_day"] = completed["entry_time"].dt.date.astype(str)
    daily = []
    for day, subset in completed.groupby("entry_day", sort=True):
        pnl = pd.to_numeric(subset["net_pnl_quote"], errors="coerce").fillna(0.0)
        daily.append({
            "date": day,
            "completed_trades": int(len(subset)),
            "net_pnl_quote": float(pnl.sum()),
            "winning_trades": int((pnl > 0).sum()),
            "losing_trades": int((pnl <= 0).sum()),
        })
    diagnostics: dict[str, Any] = {}
    for horizon in (480, 1440, 1920):
        diagnostics[f"horizon_{horizon}m"] = {
            "median_mfe_pct": float(pd.to_numeric(completed[f"mfe_{horizon}m_pct"], errors="coerce").median()),
            "median_mae_pct": float(pd.to_numeric(completed[f"mae_{horizon}m_pct"], errors="coerce").median()),
            "mae_10th_percentile_pct": float(pd.to_numeric(completed[f"mae_{horizon}m_pct"], errors="coerce").quantile(0.10)),
            "worst_mae_pct": float(pd.to_numeric(completed[f"mae_{horizon}m_pct"], errors="coerce").min()),
            **{
                f"hit_{target}pct_rate": float(completed[f"hit_{target}pct_within_{horizon}m"].fillna(False).mean())
                for target in (10, 15, 25, 50)
            },
        }
    return {
        "overall": overall,
        "chronological_halves": halves,
        "monthly": monthly,
        "by_symbol": by_symbol,
        "daily": daily,
        "diagnostics": diagnostics,
        "symbol_cluster_bootstrap_expectancy": _symbol_cluster_bootstrap_expectancy(completed),
    }


def graduation_decision(strategy: str, performance: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    common = ENTRY_VALIDATION_PROTOCOL["graduation"]["common"]
    specific = ENTRY_VALIDATION_PROTOCOL["graduation"][strategy]
    overall = performance["overall"]
    halves = performance["chronological_halves"]
    bootstrap = performance["symbol_cluster_bootstrap_expectancy"]
    pf = overall.get("profit_factor")
    checks = {
        "minimum_completed_trades": int(overall.get("completed_trades") or 0) >= int(specific["minimum_completed_trades"]),
        "minimum_unique_symbols": int(overall.get("unique_symbols_traded") or 0) >= int(specific["minimum_unique_symbols"]),
        "positive_total_net_pnl": float(overall.get("total_net_pnl_quote") or 0.0) > 0.0,
        "minimum_expectancy": overall.get("expectancy_quote") is not None and float(overall["expectancy_quote"]) >= float(common["minimum_expectancy_quote"]),
        "minimum_profit_factor": pf is not None and float(pf) >= float(common["minimum_profit_factor"]),
        "maximum_drawdown": overall.get("maximum_drawdown_quote") is not None and abs(float(overall["maximum_drawdown_quote"])) <= float(common["maximum_drawdown_quote"]),
        "maximum_consecutive_losses": int(overall.get("maximum_consecutive_losses") or 0) <= int(common["maximum_consecutive_losses"]),
        "maximum_symbol_concentration": overall.get("largest_symbol_trade_share") is not None and float(overall["largest_symbol_trade_share"]) <= float(common["maximum_largest_symbol_trade_share"]),
        "minimum_entry_fill_rate": overall.get("exact_entry_fill_rate") is not None and float(overall["exact_entry_fill_rate"]) >= float(common["minimum_exact_entry_fill_rate"]),
        "minimum_trades_each_half": len(halves) == 2 and all(int(row.get("completed_trades") or 0) >= int(specific["minimum_completed_trades_each_half"]) for row in halves),
        "positive_expectancy_each_half": len(halves) == 2 and all(row.get("expectancy_quote") is not None and float(row["expectancy_quote"]) > 0 for row in halves),
        "bootstrap_lower_expectancy_above_zero": bootstrap.get("lower_95") is not None and float(bootstrap["lower_95"]) > 0,
        "minimum_minute_archive_coverage": quality.get("minute_archive_mean_coverage") is not None and float(quality["minute_archive_mean_coverage"]) >= float(common["minimum_minute_archive_mean_coverage"]),
        "maximum_symbol_failure_fraction": float(quality.get("symbol_failure_fraction") or 0.0) <= float(common["maximum_symbol_failure_fraction"]),
    }
    return {
        "passed": all(checks.values()),
        "decision": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": [key for key, passed in checks.items() if not passed],
        "risk_note": "No stop-loss was used. Profitability PASS does not imply compatibility with a 5% maximum loss per position.",
    }


class ExactEntryValidationBuilder:
    def __init__(self, db: SupabaseClient, binance: BinanceClient, temp_root: Path):
        self.db = db
        self.binance = binance
        self.temp_root = temp_root / "entry-validation-v12"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.minute_cache = BacktestMinuteArchiveCache(binance, self.temp_root)
        self.agg_cache = AggTradeArchiveCache(self.temp_root)

    def _canonical_symbols(self) -> list[str]:
        quotes = ENTRY_VALIDATION_PROTOCOL["universe"]["quote_assets"]
        rank = {quote: idx for idx, quote in enumerate(quotes)}
        by_base: dict[str, dict[str, Any]] = {}
        for raw in self.binance.exchange_info().get("symbols", []):
            item = classify_symbol(raw)
            if item["quote_asset"] not in rank:
                continue
            if item["status"] != "TRADING" or not item["spot_permission"] or not item["is_spot_trading_allowed"]:
                continue
            if "LIMIT" not in item["order_types"]:
                continue
            item["quote_priority"] = rank[item["quote_asset"]]
            current = by_base.get(item["base_asset"])
            if current is None or (item["quote_priority"], item["symbol"]) < (current["quote_priority"], current["symbol"]):
                by_base[item["base_asset"]] = item
        return sorted(item["symbol"] for item in by_base.values())

    @staticmethod
    def _validate_job(job: dict[str, Any]) -> tuple[date, date]:
        if str(job.get("protocol_version")) != ENTRY_VALIDATION_PROTOCOL["version"]:
            raise ValueError("Entry-validation protocol version mismatch")
        start = date.fromisoformat(str(job["window_start_date"]))
        end = date.fromisoformat(str(job["window_end_date_exclusive"]))
        if start != date(2025, 1, 1) or end != date(2025, 7, 1):
            raise ValueError("V12 validation is frozen at 2025-01-01 to 2025-07-01 exclusive")
        return start, end

    def _assert_running(self, job_id: str) -> None:
        rows = self.db.select("binance_entry_validation_jobs", filters={"id": f"eq.{job_id}"}, limit=1)
        if not rows or rows[0].get("status") != "running":
            raise EntryValidationCancelled("Entry-validation job was cancelled or is no longer running")

    def run(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job["id"])
        start_day, end_day = self._validate_job(job)
        load_start = start_day - timedelta(days=11)
        work = Path(tempfile.mkdtemp(prefix=f"entry-validation-{job_id}-", dir=self.temp_root))
        checkpoint = self.temp_root / "checkpoints" / job_id
        signal_checkpoint_dir = checkpoint / "signals"
        execution_checkpoint_dir = checkpoint / "executions"
        checkpoint.mkdir(parents=True, exist_ok=True)
        universe_path = checkpoint / "canonical_universe.json"
        if universe_path.exists():
            symbols = [str(value) for value in json.loads(universe_path.read_text(encoding="utf-8"))]
        else:
            symbols = self._canonical_symbols()
            _write_json_atomic(universe_path, symbols)
        protocol_marker = checkpoint / "protocol_version.txt"
        if protocol_marker.exists() and protocol_marker.read_text(encoding="utf-8").strip() != ENTRY_VALIDATION_PROTOCOL["version"]:
            raise ValueError("Existing checkpoint belongs to a different protocol version")
        protocol_marker.write_text(ENTRY_VALIDATION_PROTOCOL["version"], encoding="utf-8")
        try:
            candidate_records: list[dict[str, Any]] = []
            coverage_rows: list[dict[str, Any]] = []
            signal_failures = 0
            execution_failures = 0

            for idx, symbol in enumerate(symbols, start=1):
                self._assert_running(job_id)
                checkpoint_path = signal_checkpoint_dir / f"{symbol}.json"
                if checkpoint_path.exists():
                    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                    rows = payload.get("rows") or []
                    coverage = payload.get("coverage") or {"symbol": symbol}
                    failed = bool(payload.get("failed"))
                    candidate_records.extend(rows)
                    coverage_rows.append(coverage)
                    signal_failures += int(failed)
                else:
                    rows: list[dict[str, Any]] = []
                    failed = False
                    try:
                        loaded = self.minute_cache.load_symbol(symbol, load_start, end_day)
                        frame = loaded.frame
                        signals = compute_entry_signal_frame(
                            frame,
                            datetime.combine(start_day, time.min, tzinfo=timezone.utc),
                            datetime.combine(end_day, time.min, tzinfo=timezone.utc),
                        )
                        rows = candidate_rows(symbol, signals)
                        requested_days = sum(int(item.get("days_covered") or 1) for item in loaded.source_manifest)
                        available_days = sum(
                            int(item.get("days_covered") or 1)
                            for item in loaded.source_manifest
                            if item.get("status") == "available"
                        )
                        validation_mask = (
                            (frame.index >= pd.Timestamp(datetime.combine(start_day, time.min, tzinfo=timezone.utc)))
                            & (frame.index < pd.Timestamp(datetime.combine(end_day, time.min, tzinfo=timezone.utc)))
                        )
                        validation_observed = frame.loc[validation_mask, "observed"].fillna(False).astype(bool)
                        if validation_observed.any():
                            observed_positions = np.flatnonzero(validation_observed.to_numpy(dtype=bool))
                            active_slice = validation_observed.iloc[observed_positions[0] : observed_positions[-1] + 1]
                            active_span_coverage = float(active_slice.mean())
                            calendar_availability = float(validation_observed.mean())
                            eligible_in_window = True
                        else:
                            active_span_coverage = None
                            calendar_availability = 0.0
                            eligible_in_window = False
                        coverage = {
                            "symbol": symbol,
                            "raw_candidate_edges": len(rows),
                            "archive_days_requested": requested_days,
                            "archive_days_available": available_days,
                            "archive_coverage_fraction": available_days / requested_days if requested_days else 0.0,
                            "eligible_in_validation_window": eligible_in_window,
                            "calendar_availability_fraction": calendar_availability,
                            "coverage_fraction": active_span_coverage,
                        }
                    except EntryValidationCancelled:
                        raise
                    except Exception as exc:
                        failed = True
                        signal_failures += 1
                        coverage = {"symbol": symbol, "error": str(exc)[:1000]}
                        self.db.insert("binance_entry_validation_issues", {
                            "entry_validation_job_id": job_id,
                            "symbol": symbol,
                            "stage": "signal_generation",
                            "message": str(exc)[:4000],
                        })
                    finally:
                        shutil.rmtree(self.minute_cache.root / symbol, ignore_errors=True)
                    _write_json_atomic(checkpoint_path, {"rows": rows, "coverage": coverage, "failed": failed})
                    candidate_records.extend(rows)
                    coverage_rows.append(coverage)

                heartbeat = datetime.now(timezone.utc).isoformat()
                self.db.update("binance_entry_validation_jobs", {"id": f"eq.{job_id}"}, {
                    "symbols_total": len(symbols),
                    "symbols_processed": idx,
                    "candidate_edges": len(candidate_records),
                    "failures": signal_failures + execution_failures,
                    "heartbeat_at": heartbeat,
                })
                self.db.upsert(
                    "binance_worker_heartbeats",
                    [{"worker_name": "main", "heartbeat_at": heartbeat}],
                    on_conflict="worker_name",
                )

            all_candidates = pd.DataFrame(candidate_records)
            if not all_candidates.empty:
                all_candidates["signal_decision_time"] = pd.to_datetime(all_candidates["signal_decision_time"], utc=True)
                latest = pd.Timestamp(datetime.combine(end_day, time.min, tzinfo=timezone.utc)) - pd.Timedelta(minutes=1925)
                all_candidates = all_candidates[all_candidates["signal_decision_time"] <= latest].copy()

            selections: dict[str, pd.DataFrame] = {}
            selection_audits: list[pd.DataFrame] = []
            for strategy in ("E1_BROAD_MOMENTUM_CONFIRMATION", "E2_R48_ARMED_THEN_CONFIRM"):
                selected, audit = select_portfolio_candidates(all_candidates, strategy)
                selections[strategy] = selected
                selection_audits.append(audit)
            selection_audit = pd.concat(selection_audits, ignore_index=True) if selection_audits else pd.DataFrame()

            union: dict[tuple[str, str], dict[str, Any]] = {}
            for selected in selections.values():
                for row in selected.to_dict("records"):
                    key = (str(row["symbol"]), pd.Timestamp(row["signal_decision_time"]).isoformat())
                    union.setdefault(key, row)
            union_by_symbol: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in union.values():
                union_by_symbol[str(row["symbol"])].append(row)

            self.db.update("binance_entry_validation_jobs", {"id": f"eq.{job_id}"}, {
                "selected_signals": len(union),
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            })

            exact_by_key: dict[tuple[str, str], dict[str, Any]] = {}
            agg_coverage_rows: list[dict[str, Any]] = []
            processed_exact = 0
            for symbol, rows in sorted(union_by_symbol.items()):
                self._assert_running(job_id)
                for row in sorted(rows, key=lambda item: pd.Timestamp(item["signal_decision_time"])):
                    self._assert_running(job_id)
                    signal_timestamp = pd.Timestamp(row["signal_decision_time"])
                    signal_time = signal_timestamp.to_pydatetime()
                    stamp = signal_timestamp.strftime("%Y%m%dT%H%M%SZ")
                    execution_path = execution_checkpoint_dir / symbol / f"{stamp}.json"
                    if execution_path.exists():
                        payload = json.loads(execution_path.read_text(encoding="utf-8"))
                        execution = payload.get("execution") or {**row, "execution_status": "execution_missing"}
                        coverage = payload.get("coverage") or {
                            "symbol": symbol,
                            "signal_decision_time": signal_time.isoformat(),
                            "error": "checkpoint missing coverage",
                        }
                        failed = bool(payload.get("failed"))
                        execution_failures += int(failed)
                    else:
                        failed = False
                        try:
                            end_time = signal_time + timedelta(minutes=1925, seconds=60)
                            agg, manifest = self.agg_cache.load_range(symbol, signal_time, end_time)
                            coverage = {
                                "symbol": symbol,
                                "signal_decision_time": signal_time.isoformat(),
                                "days_requested": len(manifest),
                                "days_available": sum(item.get("status") == "available" for item in manifest),
                                "aggregate_trade_rows": int(len(agg)),
                            }
                            execution = simulate_exact_entry(row, agg)
                        except EntryValidationCancelled:
                            raise
                        except Exception as exc:
                            failed = True
                            execution_failures += 1
                            coverage = {
                                "symbol": symbol,
                                "signal_decision_time": signal_time.isoformat(),
                                "error": str(exc)[:1000],
                            }
                            execution = {**row, "execution_status": "execution_error", "error": str(exc)[:1000]}
                            self.db.insert("binance_entry_validation_issues", {
                                "entry_validation_job_id": job_id,
                                "symbol": symbol,
                                "stage": "exact_execution",
                                "message": str(exc)[:4000],
                            })
                        finally:
                            # Signals are at least 24 hours apart per strategy. Clearing after each
                            # candidate bounds persistent-disk usage even for high-volume symbols.
                            self.agg_cache.clear_symbol(symbol)
                        _write_json_atomic(
                            execution_path,
                            {"execution": execution, "coverage": coverage, "failed": failed},
                        )

                    key = (symbol, signal_timestamp.isoformat())
                    exact_by_key[key] = execution
                    agg_coverage_rows.append(coverage)
                    processed_exact += 1
                    if processed_exact % 5 == 0 or processed_exact == len(union):
                        heartbeat = datetime.now(timezone.utc).isoformat()
                        self.db.update("binance_entry_validation_jobs", {"id": f"eq.{job_id}"}, {
                            "selected_signals": len(union),
                            "executions_processed": processed_exact,
                            "failures": signal_failures + execution_failures,
                            "heartbeat_at": heartbeat,
                        })
                        self.db.upsert(
                            "binance_worker_heartbeats",
                            [{"worker_name": "main", "heartbeat_at": heartbeat}],
                            on_conflict="worker_name",
                        )

            execution_frames: dict[str, pd.DataFrame] = {}
            reports: dict[str, Any] = {}
            for strategy, selected in selections.items():
                strategy_rows: list[dict[str, Any]] = []
                for row in selected.to_dict("records"):
                    key = (str(row["symbol"]), pd.Timestamp(row["signal_decision_time"]).isoformat())
                    execution = exact_by_key.get(key)
                    if execution is None:
                        execution = {**row, "execution_status": "execution_missing"}
                    strategy_rows.append({**execution, "strategy": strategy})
                executions = pd.DataFrame(strategy_rows)
                execution_frames[strategy] = executions
                reports[strategy] = _json_safe(performance_report(executions, start_day, end_day))

            coverage_df = pd.DataFrame(coverage_rows)
            quality = _json_safe({
                "symbols_total": len(symbols),
                "signal_generation_failures": signal_failures,
                "execution_failures": execution_failures,
                "total_failures": signal_failures + execution_failures,
                "symbol_failure_fraction": signal_failures / len(symbols) if symbols else 1.0,
                "symbols_with_validation_data": int(coverage_df.get("eligible_in_validation_window", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not coverage_df.empty else 0,
                "minute_archive_mean_coverage": (
                    float(pd.to_numeric(coverage_df.get("coverage_fraction", pd.Series(dtype=float)), errors="coerce").dropna().mean())
                    if not coverage_df.empty and pd.to_numeric(coverage_df.get("coverage_fraction", pd.Series(dtype=float)), errors="coerce").notna().any()
                    else None
                ),
                "current_tradeable_universe_survivorship_bias": True,
                "raw_candidate_edges": int(len(all_candidates)),
                "selected_signal_union": int(len(union)),
                "aggregate_trade_execution_rows": int(processed_exact),
                "resumable_checkpoint_used": True,
            })
            decisions = {
                strategy: graduation_decision(strategy, report, quality)
                for strategy, report in reports.items()
            }
            overall_decision = {
                "any_strategy_passed": any(item["passed"] for item in decisions.values()),
                "passing_strategies": [name for name, item in decisions.items() if item["passed"]],
                "next_step": "Open no sealed data unless at least one strategy passes. Freeze any passing strategy unchanged before a separate sealed job is built.",
            }

            pd.DataFrame({"symbol": symbols}).to_csv(work / "canonical_universe.csv", index=False)
            all_candidates.to_csv(work / "all_continuous_candidate_edges.csv", index=False)
            selection_audit.to_csv(work / "portfolio_selection_audit.csv", index=False)
            coverage_df.to_csv(work / "minute_archive_coverage.csv", index=False)
            pd.DataFrame(agg_coverage_rows).to_csv(work / "aggregate_trade_coverage.csv", index=False)
            for strategy, executions in execution_frames.items():
                executions.to_csv(work / f"{strategy}_exact_trades.csv", index=False)
                report = reports[strategy]
                pd.DataFrame(report.get("chronological_halves", [])).to_csv(work / f"{strategy}_chronological_halves.csv", index=False)
                pd.DataFrame(report.get("monthly", [])).to_csv(work / f"{strategy}_monthly.csv", index=False)
                pd.DataFrame(report.get("by_symbol", [])).to_csv(work / f"{strategy}_by_symbol.csv", index=False)
                pd.DataFrame(report.get("daily", [])).to_csv(work / f"{strategy}_daily.csv", index=False)

            package_result = {
                "protocol": ENTRY_VALIDATION_PROTOCOL,
                "quality": quality,
                "performance": reports,
                "graduation": decisions,
                "overall_decision": overall_decision,
            }
            (work / "V12_PREREGISTERED_PROTOCOL.json").write_text(
                json.dumps(ENTRY_VALIDATION_PROTOCOL, indent=2), encoding="utf-8"
            )
            (work / "validation_results.json").write_text(
                json.dumps(_json_safe(package_result), indent=2), encoding="utf-8"
            )
            (work / "README.md").write_text(
                "# V12 exact-entry continuous validation\n\n"
                "This package evaluates two frozen 2026-discovered entry triggers continuously on 2025-01-01 through 2025-06-30. "
                "The sealed 2025-07-01 through 2025-10-31 evidence is not accessed. Entries and exits use Binance aggregate-trade execution proxies. "
                "The primary exit is +15% or 24 hours, with no stop-loss. No parameter may be retuned after viewing these results.\n",
                encoding="utf-8",
            )
            package = work / "ENTRY_VALIDATION_2025_RESULTS.zip"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(work.iterdir()):
                    if path.is_file() and path != package:
                        archive.write(path, path.name)
            storage_path = f"entry-validation/{job_id}/{package.name}"
            self.db.upload_file(storage_path, package, "application/zip")
            self.db.upsert("binance_entry_validation_files", [{
                "entry_validation_job_id": job_id,
                "storage_path": storage_path,
                "filename": package.name,
                "size_bytes": package.stat().st_size,
                "sha256": sha256_file(package),
                "content_type": "application/zip",
                "role": "entry_validation_results",
            }], on_conflict="entry_validation_job_id,storage_path")

            result = {
                "symbols_total": len(symbols),
                "symbols_processed": len(symbols),
                "candidate_edges": len(all_candidates),
                "selected_signals": len(union),
                "executions_processed": processed_exact,
                "failures": signal_failures + execution_failures,
                "quality": quality,
                "graduation": decisions,
                "overall_decision": overall_decision,
                "storage_path": storage_path,
            }
            shutil.rmtree(checkpoint, ignore_errors=True)
            return result
        finally:
            shutil.rmtree(work, ignore_errors=True)

