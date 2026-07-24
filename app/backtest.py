from __future__ import annotations

import json
import math
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .binance import BinanceClient, archive_url, download_archive, normalize_archive_timestamp, sha256_file
from .classifier import classify_symbol
from .matched_controls import MinuteArchiveCache
from .supabase import SupabaseClient

BACKTEST_PROTOCOL: dict[str, Any] = {
    "version": "v8_h3_continuous_executable_backtest_1",
    "context_rule": {
        "id": "H3_VOLATILITY_REVERSAL",
        "volatility_1d_to_7d_ratio_min": 0.4,
        "ret_prior_1d_to_7d_pct_max": 5.0,
        "rising_edge_only": True,
    },
    "continuation_rule": {
        "arm_window_minutes": 480,
        "minimum_components": 3,
        "ret_15m_pct_min": 0.9,
        "quote_volume_15m_vs_prior_7d_same_time_min": 12.0,
        "position_in_1440m_range_min": 0.74,
        "max_runup_15m_pct_min": 3.3,
        "prior_5m_quote_volume_min": 500.0,
    },
    "execution": {
        "position_quote_notional": 500.0,
        "entry_fill_window_seconds": 60,
        "take_profit_pct": 15.0,
        "stop_loss_pct": 5.0,
        "maximum_hold_minutes": 180,
        "exit_fill_window_seconds": 300,
        "fee_bps_each_side": 10.0,
        "symbol_cooldown_minutes_after_exit_or_failure": 180,
        "maximum_filled_entries_per_utc_day": 5,
    },
    "integrity": {
        "parameters_tunable_after_run": False,
        "entry_time": "first aggregate trade after the completed continuation-signal minute",
        "fill_proxy": "buyer-initiated executions for entry; seller-initiated executions for exit",
        "target_event_window_minutes": 480,
        "maximum_trade_hold_minutes": 180,
        "current_universe_warning": "Uses coins tradeable at run time; historical delisted coins are absent.",
    },
}


AGG_COLUMNS = [
    "agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
    "timestamp", "is_buyer_maker", "is_best_match",
]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    return value



def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "t", "yes"}


def _read_agg_archive(path: Path, symbol: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if not name.endswith("/")]
        if not members:
            raise RuntimeError(f"Archive is empty: {path}")
        with archive.open(members[0]) as handle:
            raw = pd.read_csv(handle, header=None, dtype=str)
    raw = raw.iloc[:, : len(AGG_COLUMNS)].copy()
    raw.columns = AGG_COLUMNS[: raw.shape[1]]
    raw["agg_trade_id"] = pd.to_numeric(raw["agg_trade_id"], errors="coerce")
    raw = raw[raw["agg_trade_id"].notna()].copy()
    if raw.empty:
        return pd.DataFrame(columns=[*AGG_COLUMNS, "symbol", "time"])
    raw["timestamp"] = pd.to_numeric(raw["timestamp"], errors="coerce")
    raw = raw[raw["timestamp"].notna()].copy()
    raw["timestamp_ms"] = raw["timestamp"].astype("int64").map(normalize_archive_timestamp)
    raw["time"] = pd.to_datetime(raw["timestamp_ms"], unit="ms", utc=True)
    raw["price"] = pd.to_numeric(raw["price"], errors="coerce")
    raw["quantity"] = pd.to_numeric(raw["quantity"], errors="coerce")
    raw["is_buyer_maker"] = raw["is_buyer_maker"].map(_to_bool)
    raw["symbol"] = symbol
    raw = raw.dropna(subset=["price", "quantity", "time"]).sort_values(["time", "agg_trade_id"])
    return raw[["symbol", "agg_trade_id", "price", "quantity", "time", "is_buyer_maker"]]


class AggTradeArchiveCache:
    def __init__(self, root: Path):
        self.root = root / "backtest-agg-cache"
        self.root.mkdir(parents=True, exist_ok=True)

    def _paths(self, symbol: str, day: date) -> tuple[Path, Path]:
        folder = self.root / symbol
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{symbol}-aggTrades-{day.isoformat()}"
        return folder / f"{stem}.zip", folder / f"{stem}.missing"

    def load_range(self, symbol: str, start: datetime, end_inclusive: datetime) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        frames: list[pd.DataFrame] = []
        manifest: list[dict[str, Any]] = []
        day = start.date()
        while day <= end_inclusive.date():
            archive_path, missing_path = self._paths(symbol, day)
            url = archive_url("aggTrades", symbol, day)
            try:
                if archive_path.exists() and zipfile.is_zipfile(archive_path):
                    frame = _read_agg_archive(archive_path, symbol)
                    source = "official_daily_archive_cache"
                    status = "available"
                elif missing_path.exists():
                    frame = pd.DataFrame()
                    source = "missing_marker"
                    status = "unavailable"
                else:
                    available = download_archive(url, archive_path)
                    if available:
                        frame = _read_agg_archive(archive_path, symbol)
                        source = "official_daily_archive"
                        status = "available"
                    else:
                        missing_path.write_text("archive unavailable", encoding="utf-8")
                        frame = pd.DataFrame()
                        source = "archive_unavailable"
                        status = "unavailable"
                if not frame.empty:
                    frames.append(frame)
                manifest.append({
                    "symbol": symbol,
                    "date": day.isoformat(),
                    "status": status,
                    "source": source,
                    "source_url": url,
                    "row_count": int(len(frame)),
                    "sha256": sha256_file(archive_path) if archive_path.exists() else None,
                })
            except Exception as exc:
                manifest.append({
                    "symbol": symbol,
                    "date": day.isoformat(),
                    "status": "error",
                    "source": "official_daily_archive",
                    "source_url": url,
                    "row_count": 0,
                    "error": str(exc)[:1000],
                })
            day += timedelta(days=1)
        if not frames:
            return pd.DataFrame(columns=["symbol", "agg_trade_id", "price", "quantity", "time", "is_buyer_maker"]), manifest
        combined = pd.concat(frames, ignore_index=True).drop_duplicates(["agg_trade_id"], keep="last")
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end_inclusive)
        combined = combined[(combined["time"] >= start_ts) & (combined["time"] <= end_ts)].copy()
        return combined.sort_values(["time", "agg_trade_id"]), manifest

    def clear_symbol(self, symbol: str) -> None:
        shutil.rmtree(self.root / symbol, ignore_errors=True)


def _rolling_runup(values: np.ndarray) -> float:
    if len(values) < 2 or np.any(~np.isfinite(values)) or np.any(values <= 0):
        return np.nan
    running_min = np.minimum.accumulate(values)
    return float(np.max(values / running_min - 1.0) * 100.0)


def compute_signal_frame(frame: pd.DataFrame, start: datetime, end_exclusive: datetime) -> pd.DataFrame:
    """Vectorised, look-ahead-safe implementation of the frozen V8 two-stage signal."""
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    quote = pd.to_numeric(frame["quote_volume"], errors="coerce")
    observed = frame["observed"].fillna(False).astype(bool)

    # H3 uses exactly the same definitions as the baseline-context engine.
    log_returns = np.log(close.where(close > 0)).diff()
    rv_1d = log_returns.rolling(1439, min_periods=1152).std(ddof=1) * math.sqrt(1440) * 100.0
    rv_7d = log_returns.rolling(10079, min_periods=8064).std(ddof=1) * math.sqrt(10080) * 100.0
    volatility_ratio = rv_1d / rv_7d.replace(0, np.nan)
    prior_week = (close.shift(1440) / close.shift(10080) - 1.0) * 100.0
    completeness_10d = observed.rolling(14400, min_periods=14400).mean()
    h3 = (
        (volatility_ratio >= 0.4)
        & (prior_week <= 5.0)
        & (completeness_10d >= 0.995)
    ).fillna(False)
    h3_rising = h3 & ~h3.shift(1, fill_value=False)

    ret_15 = (close / close.shift(15) - 1.0) * 100.0
    volume_15 = quote.rolling(15, min_periods=15).sum()
    historical_same_time = pd.concat([volume_15.shift(1440 * day) for day in range(1, 8)], axis=1)
    same_time_median = historical_same_time.median(axis=1, skipna=True)
    same_time_count = historical_same_time.notna().sum(axis=1)
    volume_15_ratio = volume_15 / same_time_median.replace(0, np.nan)
    rolling_high_24h = high.rolling(1440, min_periods=1430).max()
    rolling_low_24h = low.rolling(1440, min_periods=1430).min()
    range_position = (close - rolling_low_24h) / (rolling_high_24h - rolling_low_24h).replace(0, np.nan)
    runup_15 = close.rolling(15, min_periods=15).apply(_rolling_runup, raw=True)
    liquidity_5 = quote.rolling(5, min_periods=5).sum()

    components = pd.DataFrame({
        "late_return": ret_15 >= 0.9,
        "late_volume": (volume_15_ratio >= 12.0) & (same_time_count >= 5),
        "late_range_position": range_position >= 0.74,
        "late_runup": runup_15 >= 3.3,
    }).fillna(False)
    component_count = components.sum(axis=1)
    late = ((component_count >= 3) & (liquidity_5 >= 500.0) & observed).fillna(False)

    result = pd.DataFrame(index=frame.index)
    result["h3"] = h3
    result["h3_rising"] = h3_rising
    result["ret_prior_1d_to_7d_pct"] = prior_week
    result["realized_vol_1440m_pct"] = rv_1d
    result["realized_vol_10080m_pct"] = rv_7d
    result["volatility_1d_to_7d_ratio"] = volatility_ratio
    result["late_trigger"] = late
    result["late_components_passed"] = component_count
    result["ret_15m_pct"] = ret_15
    result["quote_volume_15m_vs_prior_7d_same_time"] = volume_15_ratio
    result["position_in_1440m_range"] = range_position
    result["max_runup_15m_pct"] = runup_15
    result["entry_quote_volume_5m"] = liquidity_5
    result["signal_close"] = close
    mask = (result.index >= pd.Timestamp(start)) & (result.index < pd.Timestamp(end_exclusive))
    return result.loc[mask].copy()


def candidate_signals(symbol: str, signal_frame: pd.DataFrame, arm_minutes: int = 480) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    next_arm_allowed: pd.Timestamp | None = None
    rising_times = signal_frame.index[signal_frame["h3_rising"].fillna(False)]
    for arm_bar in rising_times:
        if next_arm_allowed is not None and arm_bar < next_arm_allowed:
            continue
        window = signal_frame.loc[arm_bar : arm_bar + pd.Timedelta(minutes=arm_minutes - 1)]
        late_rows = window[window["late_trigger"].fillna(False)]
        next_arm_allowed = arm_bar + pd.Timedelta(minutes=arm_minutes)
        if late_rows.empty:
            continue
        signal_bar = late_rows.index[0]
        row = late_rows.iloc[0]
        candidates.append({
            "symbol": symbol,
            "h3_arm_bar_open": arm_bar.isoformat(),
            "signal_bar_open": signal_bar.isoformat(),
            "signal_decision_time": (signal_bar + pd.Timedelta(minutes=1)).isoformat(),
            "arm_to_signal_minutes": int((signal_bar - arm_bar).total_seconds() // 60),
            "signal_close": float(row["signal_close"]),
            "late_components_passed": int(row["late_components_passed"]),
            "ret_prior_1d_to_7d_pct": float(row["ret_prior_1d_to_7d_pct"]),
            "realized_vol_1440m_pct": float(row["realized_vol_1440m_pct"]),
            "realized_vol_10080m_pct": float(row["realized_vol_10080m_pct"]),
            "volatility_1d_to_7d_ratio": float(row["volatility_1d_to_7d_ratio"]),
            "ret_15m_pct": float(row["ret_15m_pct"]),
            "quote_volume_15m_vs_prior_7d_same_time": float(row["quote_volume_15m_vs_prior_7d_same_time"]),
            "position_in_1440m_range": float(row["position_in_1440m_range"]),
            "max_runup_15m_pct": float(row["max_runup_15m_pct"]),
            "entry_quote_volume_5m": float(row["entry_quote_volume_5m"]),
        })
    return candidates


def _fill_by_aggressor(
    trades: pd.DataFrame,
    *,
    start: datetime,
    end: datetime,
    buyer_initiated: bool,
    target_quote: float | None = None,
    target_base: float | None = None,
) -> dict[str, Any] | None:
    if (target_quote is None) == (target_base is None):
        raise ValueError("Specify exactly one fill target")
    subset = trades[(trades["time"] >= pd.Timestamp(start)) & (trades["time"] <= pd.Timestamp(end))]
    # is_buyer_maker=False means the taker bought; True means the taker sold.
    subset = subset[subset["is_buyer_maker"] == (not buyer_initiated)]
    if subset.empty:
        return None
    used_quote = 0.0
    used_base = 0.0
    last_time: pd.Timestamp | None = None
    trades_used = 0
    for row in subset.itertuples(index=False):
        price = float(row.price)
        quantity = float(row.quantity)
        if price <= 0 or quantity <= 0:
            continue
        if target_quote is not None:
            remaining_quote = target_quote - used_quote
            if remaining_quote <= 1e-12:
                break
            quantity_used = min(quantity, remaining_quote / price)
        else:
            remaining_base = float(target_base) - used_base
            if remaining_base <= 1e-15:
                break
            quantity_used = min(quantity, remaining_base)
        used_base += quantity_used
        used_quote += quantity_used * price
        last_time = row.time
        trades_used += 1
    complete = (
        used_quote >= float(target_quote) - 1e-8 if target_quote is not None
        else used_base >= float(target_base) - 1e-12
    )
    if not complete or used_base <= 0 or last_time is None:
        return None
    return {
        "base_quantity": used_base,
        "quote_notional": used_quote,
        "vwap": used_quote / used_base,
        "fill_completed_at": pd.Timestamp(last_time).to_pydatetime().isoformat(),
        "trades_used": trades_used,
    }


def simulate_execution(candidate: dict[str, Any], trades: pd.DataFrame) -> dict[str, Any]:
    cfg = BACKTEST_PROTOCOL["execution"]
    signal_time = datetime.fromisoformat(candidate["signal_decision_time"])
    entry_end = signal_time + timedelta(seconds=float(cfg["entry_fill_window_seconds"]))
    entry = _fill_by_aggressor(
        trades,
        start=signal_time,
        end=entry_end,
        buyer_initiated=True,
        target_quote=float(cfg["position_quote_notional"]),
    )
    if entry is None:
        return {**candidate, "execution_status": "entry_not_filled"}

    entry_fill_time = datetime.fromisoformat(entry["fill_completed_at"])
    entry_vwap = float(entry["vwap"])
    base_qty = float(entry["base_quantity"])
    tp_price = entry_vwap * (1.0 + float(cfg["take_profit_pct"]) / 100.0)
    sl_price = entry_vwap * (1.0 - float(cfg["stop_loss_pct"]) / 100.0)
    hold_end = entry_fill_time + timedelta(minutes=int(cfg["maximum_hold_minutes"]))
    path = trades[(trades["time"] > pd.Timestamp(entry_fill_time)) & (trades["time"] <= pd.Timestamp(hold_end))]
    reason = "time"
    trigger_time = hold_end
    trigger_price = None
    for row in path.itertuples(index=False):
        price = float(row.price)
        if price <= sl_price:
            reason = "stop"
            trigger_time = pd.Timestamp(row.time).to_pydatetime()
            trigger_price = price
            break
        if price >= tp_price:
            reason = "take_profit"
            trigger_time = pd.Timestamp(row.time).to_pydatetime()
            trigger_price = price
            break
    exit_end = trigger_time + timedelta(seconds=float(cfg["exit_fill_window_seconds"]))
    exit_fill = _fill_by_aggressor(
        trades,
        start=trigger_time,
        end=exit_end,
        buyer_initiated=False,
        target_base=base_qty,
    )
    if exit_fill is None:
        return {
            **candidate,
            "execution_status": "exit_not_filled",
            "entry_vwap": entry_vwap,
            "entry_fill_completed_at": entry["fill_completed_at"],
            "base_quantity": base_qty,
            "exit_reason": reason,
            "exit_trigger_time": trigger_time.isoformat(),
            "exit_trigger_price": trigger_price,
        }

    exit_quote = float(exit_fill["quote_notional"])
    fee_rate = float(cfg["fee_bps_each_side"]) / 10_000.0
    entry_cost = float(cfg["position_quote_notional"]) * (1.0 + fee_rate)
    exit_proceeds = exit_quote * (1.0 - fee_rate)
    net_pnl = exit_proceeds - entry_cost
    net_return = net_pnl / entry_cost * 100.0
    gross_return = (exit_quote / float(cfg["position_quote_notional"]) - 1.0) * 100.0
    return {
        **candidate,
        "execution_status": "completed",
        "entry_vwap": entry_vwap,
        "entry_signal_close_slippage_pct": (entry_vwap / float(candidate["signal_close"]) - 1.0) * 100.0,
        "entry_fill_completed_at": entry["fill_completed_at"],
        "entry_trades_used": entry["trades_used"],
        "base_quantity": base_qty,
        "take_profit_price": tp_price,
        "stop_loss_price": sl_price,
        "exit_reason": reason,
        "exit_trigger_time": trigger_time.isoformat(),
        "exit_trigger_price": trigger_price,
        "exit_vwap": float(exit_fill["vwap"]),
        "exit_fill_completed_at": exit_fill["fill_completed_at"],
        "exit_trades_used": exit_fill["trades_used"],
        "gross_return_pct": gross_return,
        "net_return_pct": net_return,
        "net_pnl_quote": net_pnl,
        "fees_quote": float(cfg["position_quote_notional"]) * fee_rate + exit_quote * fee_rate,
    }


def _performance(trades: pd.DataFrame, start: date, end_exclusive: date) -> dict[str, Any]:
    completed = trades[trades["execution_status"] == "completed"].copy() if not trades.empty else pd.DataFrame()
    if completed.empty:
        return {
            "completed_trades": 0,
            "total_net_pnl_quote": 0.0,
            "win_rate": None,
            "expectancy_quote": None,
            "profit_factor": None,
            "maximum_drawdown_quote": None,
            "maximum_consecutive_losses": 0,
        }
    pnl = pd.to_numeric(completed["net_pnl_quote"], errors="coerce").fillna(0.0)
    equity = 10_000.0 + pnl.cumsum()
    drawdown = equity - equity.cummax()
    wins = pnl > 0
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(-pnl[pnl < 0].sum())
    max_losses = 0
    current = 0
    for won in wins:
        if won:
            current = 0
        else:
            current += 1
            max_losses = max(max_losses, current)
    symbol_counts = completed["symbol"].value_counts()
    span_days = max(1, (end_exclusive - start).days)
    return {
        "completed_trades": int(len(completed)),
        "winning_trades": int(wins.sum()),
        "losing_trades": int((~wins).sum()),
        "win_rate": float(wins.mean()),
        "average_net_return_pct": float(pd.to_numeric(completed["net_return_pct"]).mean()),
        "median_net_return_pct": float(pd.to_numeric(completed["net_return_pct"]).median()),
        "expectancy_quote": float(pnl.mean()),
        "total_net_pnl_quote": float(pnl.sum()),
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else math.inf,
        "maximum_drawdown_quote": float(drawdown.min()),
        "maximum_drawdown_pct_of_10000": float(drawdown.min() / 10_000.0 * 100.0),
        "maximum_consecutive_losses": int(max_losses),
        "trades_per_calendar_day": float(len(completed) / span_days),
        "unique_symbols_traded": int(completed["symbol"].nunique()),
        "largest_symbol_trade_share": float(symbol_counts.iloc[0] / len(completed)) if len(symbol_counts) else None,
        "exit_reason_counts": completed["exit_reason"].value_counts().to_dict(),
    }


class ContinuousBacktestBuilder:
    def __init__(self, db: SupabaseClient, binance: BinanceClient, temp_root: Path):
        self.db = db
        self.binance = binance
        self.temp_root = temp_root
        self.minute_cache = MinuteArchiveCache(binance, temp_root)
        self.agg_cache = AggTradeArchiveCache(temp_root)

    def _canonical_symbols(self, quotes: list[str]) -> list[str]:
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

    def _validate_job(self, job: dict[str, Any]) -> tuple[date, date]:
        if str(job.get("protocol_version") or BACKTEST_PROTOCOL["version"]) != BACKTEST_PROTOCOL["version"]:
            raise ValueError("Backtest protocol does not match the frozen V8 protocol")
        confirmation_id = str(job["confirmation_job_id"])
        rows = self.db.select("binance_confirmation_jobs", filters={"id": f"eq.{confirmation_id}"}, limit=1)
        if not rows or rows[0].get("status") != "completed" or not bool(rows[0].get("passed")):
            raise ValueError("A completed passing fresh-confirmation job is required")
        start = date.fromisoformat(str(job["window_start_date"]))
        end = date.fromisoformat(str(job["window_end_date_exclusive"]))
        if start >= end:
            raise ValueError("Backtest start must be before end")
        if end > date(2026, 5, 22):
            raise ValueError("Sealed historical backtest must end on or before 2026-05-22")
        # Ensure the backtest does not overlap the fresh-confirmation source scan.
        confirmation = rows[0]
        if confirmation.get("protocol_version") != "v8_h3_local_low_confirmation_1":
            raise ValueError("V8 backtest requires a passing V8 H3 local-low confirmation")
        scan_rows = self.db.select(
            "binance_scan_jobs", filters={"id": f"eq.{confirmation['scan_id']}"}, limit=1,
        ) if confirmation.get("scan_id") else []
        if not scan_rows or scan_rows[0].get("event_definition_version") != "v7_rolling_8h" or int(scan_rows[0].get("window_minutes") or 0) != 480:
            raise ValueError("V8 backtest requires a passing confirmation derived from the 480-minute event definition")
        if scan_rows[0].get("window_end_date_exclusive"):
            confirmation_end = date.fromisoformat(str(scan_rows[0]["window_end_date_exclusive"]))
            if start < confirmation_end:
                raise ValueError(
                    f"Backtest must start on or after fresh-confirmation end {confirmation_end.isoformat()} to avoid overlap"
                )
        for key, expected in {
            "position_quote_notional": 500.0,
            "take_profit_pct": 15.0,
            "stop_loss_pct": 5.0,
            "max_hold_minutes": 180,
            "fee_bps": 10.0,
            "max_trades_per_day": 5,
        }.items():
            actual = float(job.get(key) if job.get(key) is not None else expected)
            if abs(actual - expected) > 1e-12:
                raise ValueError(f"{key} is frozen at {expected}")
        return start, end

    def run(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job["id"])
        start_day, end_day = self._validate_job(job)
        quotes = [str(x).upper() for x in (job.get("quote_assets") or ["USDT", "USDC", "FDUSD"])]
        symbols = self._canonical_symbols(quotes)
        load_start = start_day - timedelta(days=10)
        work = Path(tempfile.mkdtemp(prefix=f"backtest-{job_id}-", dir=self.temp_root))
        try:
            all_candidates: list[dict[str, Any]] = []
            coverage_rows: list[dict[str, Any]] = []
            failures = 0
            for idx, symbol in enumerate(symbols, start=1):
                try:
                    loaded = self.minute_cache.load_symbol(symbol, load_start, end_day)
                    frame = loaded.frame
                    signal_frame = compute_signal_frame(
                        frame,
                        datetime.combine(start_day, time.min, tzinfo=timezone.utc),
                        datetime.combine(end_day, time.min, tzinfo=timezone.utc),
                    )
                    candidates = candidate_signals(symbol, signal_frame)
                    all_candidates.extend(candidates)
                    available_days = sum(row.get("status") == "available" for row in loaded.source_manifest)
                    coverage_rows.append({
                        "symbol": symbol,
                        "candidate_signals": len(candidates),
                        "archive_days_requested": len(loaded.source_manifest),
                        "archive_days_available": available_days,
                        "coverage_fraction": available_days / len(loaded.source_manifest) if loaded.source_manifest else 0.0,
                    })
                except Exception as exc:
                    failures += 1
                    coverage_rows.append({"symbol": symbol, "error": str(exc)[:1000]})
                    self.db.insert("binance_backtest_issues", {
                        "backtest_job_id": job_id,
                        "symbol": symbol,
                        "stage": "signal_generation",
                        "message": str(exc)[:4000],
                    })
                finally:
                    # Keep the persistent disk bounded. Interrupted jobs can safely redownload.
                    shutil.rmtree(self.minute_cache.root / symbol, ignore_errors=True)
                heartbeat_at = datetime.now(timezone.utc).isoformat()
                self.db.update("binance_backtest_jobs", {"id": f"eq.{job_id}"}, {
                    "symbols_total": len(symbols),
                    "symbols_processed": idx,
                    "candidate_signals": len(all_candidates),
                    "failures": failures,
                    "heartbeat_at": heartbeat_at,
                })
                self.db.upsert(
                    "binance_worker_heartbeats",
                    [{"worker_name": "main", "heartbeat_at": heartbeat_at}],
                    on_conflict="worker_name",
                )

            candidates_df = pd.DataFrame(all_candidates)
            candidates_excluded_for_outcome_cutoff = 0
            if candidates_df.empty:
                candidates_df = pd.DataFrame(columns=["symbol", "signal_decision_time"])
            else:
                candidates_df["signal_decision_time"] = pd.to_datetime(candidates_df["signal_decision_time"], utc=True)
                # Keep every entry and possible fixed three-hour exit strictly inside the sealed window.
                outcome_buffer = pd.Timedelta(
                    minutes=int(BACKTEST_PROTOCOL["execution"]["maximum_hold_minutes"]),
                    seconds=int(BACKTEST_PROTOCOL["execution"]["entry_fill_window_seconds"])
                    + int(BACKTEST_PROTOCOL["execution"]["exit_fill_window_seconds"])
                    + 60,
                )
                latest_allowed = pd.Timestamp(datetime.combine(end_day, time.min, tzinfo=timezone.utc)) - outcome_buffer
                eligible = candidates_df["signal_decision_time"] <= latest_allowed
                candidates_excluded_for_outcome_cutoff = int((~eligible).sum())
                candidates_df = candidates_df[eligible].copy()
                candidates_df = candidates_df.sort_values(
                    ["signal_decision_time", "late_components_passed", "quote_volume_15m_vs_prior_7d_same_time", "symbol"],
                    ascending=[True, False, False, True],
                ).reset_index(drop=True)

            executions: list[dict[str, Any]] = []
            daily_filled: Counter[date] = Counter()
            symbol_available: defaultdict[str, datetime] = defaultdict(lambda: datetime.min.replace(tzinfo=timezone.utc))
            agg_manifest_summary: list[dict[str, Any]] = []
            cfg = BACKTEST_PROTOCOL["execution"]
            for execution_index, row in enumerate(candidates_df.to_dict("records"), start=1):
                symbol = str(row["symbol"])
                signal_time = pd.Timestamp(row["signal_decision_time"]).to_pydatetime()
                if signal_time < symbol_available[symbol]:
                    executions.append({**row, "signal_decision_time": signal_time.isoformat(), "execution_status": "suppressed_symbol_cooldown"})
                    continue
                if daily_filled[signal_time.date()] >= int(cfg["maximum_filled_entries_per_utc_day"]):
                    executions.append({**row, "signal_decision_time": signal_time.isoformat(), "execution_status": "suppressed_daily_trade_cap"})
                    continue
                range_end = signal_time + timedelta(
                    minutes=int(cfg["maximum_hold_minutes"]),
                    seconds=int(cfg["exit_fill_window_seconds"] + cfg["entry_fill_window_seconds"] + 60),
                )
                try:
                    agg, manifest = self.agg_cache.load_range(symbol, signal_time, range_end)
                    available = sum(item.get("status") == "available" for item in manifest)
                    agg_manifest_summary.append({
                        "symbol": symbol,
                        "signal_decision_time": signal_time.isoformat(),
                        "days_requested": len(manifest),
                        "days_available": available,
                        "rows_loaded": int(len(agg)),
                    })
                    execution = simulate_execution({**row, "signal_decision_time": signal_time.isoformat()}, agg)
                except Exception as exc:
                    failures += 1
                    execution = {**row, "signal_decision_time": signal_time.isoformat(), "execution_status": "execution_error", "error": str(exc)[:1000]}
                    self.db.insert("binance_backtest_issues", {
                        "backtest_job_id": job_id,
                        "symbol": symbol,
                        "stage": "execution_simulation",
                        "message": str(exc)[:4000],
                    })
                finally:
                    self.agg_cache.clear_symbol(symbol)
                executions.append(execution)
                if execution.get("execution_status") == "completed":
                    daily_filled[signal_time.date()] += 1
                    exit_time = datetime.fromisoformat(str(execution["exit_fill_completed_at"]))
                    symbol_available[symbol] = exit_time + timedelta(minutes=int(cfg["symbol_cooldown_minutes_after_exit_or_failure"]))
                elif execution.get("execution_status") in {"entry_not_filled", "exit_not_filled", "execution_error"}:
                    symbol_available[symbol] = signal_time + timedelta(minutes=int(cfg["symbol_cooldown_minutes_after_exit_or_failure"]))
                if execution_index % 5 == 0 or execution_index == len(candidates_df):
                    heartbeat_at = datetime.now(timezone.utc).isoformat()
                    completed_so_far = sum(item.get("execution_status") == "completed" for item in executions)
                    self.db.update("binance_backtest_jobs", {"id": f"eq.{job_id}"}, {
                        "candidate_signals": len(candidates_df),
                        "completed_trades": completed_so_far,
                        "failures": failures,
                        "heartbeat_at": heartbeat_at,
                    })
                    self.db.upsert(
                        "binance_worker_heartbeats",
                        [{"worker_name": "main", "heartbeat_at": heartbeat_at}],
                        on_conflict="worker_name",
                    )

            executions_df = pd.DataFrame(executions)
            performance = _performance(executions_df, start_day, end_day)
            quality = {
                "symbols_total": len(symbols),
                "symbols_with_failures": failures,
                "candidate_signals": len(candidates_df),
                "candidate_signals_excluded_for_outcome_cutoff": candidates_excluded_for_outcome_cutoff,
                "execution_status_counts": executions_df["execution_status"].value_counts().to_dict() if not executions_df.empty else {},
                "minute_archive_mean_coverage": float(pd.DataFrame(coverage_rows).get("coverage_fraction", pd.Series(dtype=float)).mean()) if coverage_rows else None,
                "current_tradeable_universe_survivorship_bias": True,
            }
            performance = _json_safe(performance)
            quality = _json_safe(quality)
            decision = {
                "protocol": BACKTEST_PROTOCOL,
                "performance": performance,
                "quality": quality,
                "automatic_trading_decision": "research_output_only",
                "pass_fail_not_preregistered": "V8 measures the fixed strategy; no profitability threshold is used to retune it.",
            }

            candidates_df.to_csv(work / "candidate_signals.csv", index=False)
            executions_df.to_csv(work / "executed_trades.csv", index=False)
            pd.DataFrame(coverage_rows).to_csv(work / "minute_data_coverage.csv", index=False)
            pd.DataFrame(agg_manifest_summary).to_csv(work / "aggregate_trade_coverage.csv", index=False)
            (work / "backtest_protocol.json").write_text(json.dumps(BACKTEST_PROTOCOL, indent=2), encoding="utf-8")
            (work / "backtest_results.json").write_text(json.dumps(decision, indent=2, default=str), encoding="utf-8")
            (work / "README.md").write_text(
                "# Continuous executable historical backtest\n\n"
                "This package evaluates the frozen H3-volatility-reversal-plus-continuation sequence for the eight-hour target event after every completed one-minute bar. "
                "Entries and exits are reconstructed from historical aggregate trades. Treat the current-universe survivorship warning as material.\n",
                encoding="utf-8",
            )
            package = work / "continuous_backtest_results.zip"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(work.iterdir()):
                    if path.is_file() and path != package:
                        archive.write(path, path.name)
            storage_path = f"continuous-backtest/{job_id}/{package.name}"
            self.db.upload_file(storage_path, package, "application/zip")
            record = {
                "backtest_job_id": job_id,
                "storage_path": storage_path,
                "filename": package.name,
                "size_bytes": package.stat().st_size,
                "sha256": sha256_file(package),
                "content_type": "application/zip",
                "role": "continuous_backtest_results",
            }
            self.db.upsert("binance_backtest_files", [record], on_conflict="backtest_job_id,storage_path")
            return {
                "symbols_total": len(symbols),
                "symbols_processed": len(symbols),
                "candidate_signals": len(candidates_df),
                "completed_trades": performance.get("completed_trades", 0),
                "failures": failures,
                "performance": performance,
                "quality": quality,
                "storage_path": storage_path,
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)
