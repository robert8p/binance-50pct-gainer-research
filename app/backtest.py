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
from .matched_controls import LoadedSymbol, read_kline_archive, rest_rows_to_frame
from .supabase import SupabaseClient

BACKTEST_PROTOCOL: dict[str, Any] = {
    "version": "v9_momentum_only_continuous_backtest_1",
    "signal_rule": {
        "id": "FROZEN_LATE_MOMENTUM_3_OF_4",
        "minimum_components": 3,
        "ret_15m_pct_min": 0.9,
        "quote_volume_15m_vs_prior_7d_same_time_min": 12.0,
        "minimum_same_time_reference_days": 5,
        "position_in_1440m_range_min": 0.74,
        "max_runup_15m_pct_min": 3.3,
        "prior_5m_quote_volume_min": 500.0,
        "evaluation": "after every completed one-minute bar",
    },
    "execution": {
        "position_quote_notional": 500.0,
        "entry_fill_window_seconds": 60,
        "take_profit_pct": 10.0,
        "stop_loss_pct": 5.0,
        "maximum_hold_minutes": 180,
        "exit_fill_window_seconds": 300,
        "fee_bps_each_side": 10.0,
        "symbol_cooldown_minutes_after_exit_or_failure": 180,
        "maximum_filled_entries_per_utc_day": 5,
        "simulated_starting_equity_quote": 10_000.0,
        "same_timestamp_ranking": [
            "late_components_passed descending",
            "quote_volume_15m_vs_prior_7d_same_time descending",
            "symbol ascending",
        ],
    },
    "graduation_criteria": {
        "minimum_completed_trades": 100,
        "minimum_unique_symbols": 20,
        "minimum_total_net_pnl_quote_exclusive": 0.0,
        "minimum_expectancy_quote": 1.0,
        "minimum_profit_factor": 1.25,
        "maximum_drawdown_quote": 1500.0,
        "maximum_consecutive_losses": 10,
        "maximum_largest_symbol_trade_share": 0.15,
        "minimum_trades_each_chronological_third": 20,
        "require_positive_expectancy_each_chronological_third": True,
        "require_symbol_cluster_bootstrap_95pct_lower_expectancy_above_zero": True,
        "minimum_minute_archive_mean_coverage": 0.95,
        "maximum_symbol_failure_fraction": 0.05,
    },
    "integrity": {
        "parameters_tunable_after_run": False,
        "entry_time": "first aggregate trade after the completed signal minute",
        "fill_proxy": "buyer-initiated executions for entry; seller-initiated executions for exit",
        "maximum_trade_hold_minutes": 180,
        "current_universe_warning": "Uses coins tradeable at run time; historically delisted coins are absent.",
        "programme_decision": "PASS permits further robustness review; FAIL retires this OHLCV-only Binance surge programme.",
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


class BacktestMinuteArchiveCache:
    """Use monthly Binance archives for complete months and daily archives for partial months."""

    def __init__(self, binance: BinanceClient, root: Path):
        self.binance = binance
        self.root = root / "backtest-minute-cache"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _next_month(day: date) -> date:
        return date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)

    def _folder(self, symbol: str) -> Path:
        folder = self.root / symbol
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _load_daily(self, symbol: str, day: date) -> tuple[pd.DataFrame, dict[str, Any]]:
        folder = self._folder(symbol)
        stem = f"{symbol}-1m-{day.isoformat()}"
        archive_path = folder / f"{stem}.zip"
        fallback_path = folder / f"{stem}.parquet"
        missing_path = folder / f"{stem}.missing"
        url = archive_url("klines", symbol, day, "1m")
        frame = pd.DataFrame()
        source = ""
        status = "unavailable"
        try:
            if archive_path.exists() and zipfile.is_zipfile(archive_path):
                frame = read_kline_archive(archive_path, symbol)
                source = "official_daily_archive_cache"
                status = "available"
            elif fallback_path.exists():
                frame = pd.read_parquet(fallback_path)
                frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
                frame["close_time"] = pd.to_datetime(frame["close_time"], utc=True)
                source = "rest_fallback_cache"
                status = "available"
            elif missing_path.exists():
                source = "missing_marker"
            else:
                available = download_archive(url, archive_path)
                if available:
                    frame = read_kline_archive(archive_path, symbol)
                    source = "official_daily_archive"
                    status = "available"
                else:
                    start_ms = int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp() * 1000)
                    rows = self.binance.klines(symbol, "1m", start_ms, start_ms + 86_400_000)
                    frame = rest_rows_to_frame(rows, symbol)
                    if frame.empty:
                        missing_path.write_text("No archive or REST rows", encoding="utf-8")
                        source = "archive_and_rest_unavailable"
                    else:
                        frame.to_parquet(fallback_path, index=False, compression="zstd")
                        source = "public_rest_fallback"
                        status = "available"
            checksum_path = archive_path if archive_path.exists() else fallback_path
            manifest = {
                "symbol": symbol,
                "period": day.isoformat(),
                "granularity": "daily",
                "days_covered": 1,
                "status": status,
                "source": source,
                "source_url": url,
                "row_count": int(len(frame)),
                "sha256": sha256_file(checksum_path) if checksum_path.exists() else None,
            }
            return frame, manifest
        except Exception as exc:
            return pd.DataFrame(), {
                "symbol": symbol,
                "period": day.isoformat(),
                "granularity": "daily",
                "days_covered": 1,
                "status": "error",
                "source": source or "unknown",
                "source_url": url,
                "row_count": 0,
                "error": str(exc)[:1000],
            }

    def _load_monthly(self, symbol: str, month_start: date) -> tuple[pd.DataFrame, dict[str, Any]]:
        folder = self._folder(symbol)
        month = month_start.strftime("%Y-%m")
        stem = f"{symbol}-1m-{month}"
        archive_path = folder / f"{stem}.zip"
        missing_path = folder / f"{stem}.missing"
        url = (
            f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/1m/"
            f"{symbol}-1m-{month}.zip"
        )
        next_month = self._next_month(month_start)
        days_covered = (next_month - month_start).days
        source = ""
        try:
            if archive_path.exists() and zipfile.is_zipfile(archive_path):
                frame = read_kline_archive(archive_path, symbol)
                source = "official_monthly_archive_cache"
                status = "available"
            elif missing_path.exists():
                return pd.DataFrame(), {
                    "symbol": symbol, "period": month, "granularity": "monthly",
                    "days_covered": days_covered, "status": "unavailable",
                    "source": "missing_marker", "source_url": url, "row_count": 0,
                }
            else:
                available = download_archive(url, archive_path)
                if not available:
                    missing_path.write_text("Monthly archive unavailable", encoding="utf-8")
                    return pd.DataFrame(), {
                        "symbol": symbol, "period": month, "granularity": "monthly",
                        "days_covered": days_covered, "status": "unavailable",
                        "source": "archive_unavailable", "source_url": url, "row_count": 0,
                    }
                frame = read_kline_archive(archive_path, symbol)
                source = "official_monthly_archive"
                status = "available"
            return frame, {
                "symbol": symbol,
                "period": month,
                "granularity": "monthly",
                "days_covered": days_covered,
                "status": status,
                "source": source,
                "source_url": url,
                "row_count": int(len(frame)),
                "sha256": sha256_file(archive_path),
            }
        except Exception as exc:
            return pd.DataFrame(), {
                "symbol": symbol, "period": month, "granularity": "monthly",
                "days_covered": days_covered, "status": "error", "source": source or "unknown",
                "source_url": url, "row_count": 0, "error": str(exc)[:1000],
            }

    def load_symbol(self, symbol: str, start_day: date, end_day_exclusive: date) -> LoadedSymbol:
        frames: list[pd.DataFrame] = []
        manifest: list[dict[str, Any]] = []
        cursor = start_day
        while cursor < end_day_exclusive:
            month_start = date(cursor.year, cursor.month, 1)
            next_month = self._next_month(month_start)
            segment_end = min(next_month, end_day_exclusive)
            full_month = cursor == month_start and segment_end == next_month
            if full_month:
                frame, item = self._load_monthly(symbol, month_start)
                if item.get("status") == "available":
                    if not frame.empty:
                        frames.append(frame)
                    manifest.append(item)
                else:
                    # Monthly files can be absent for newly listed symbols; fall back day by day.
                    day = cursor
                    while day < segment_end:
                        daily, daily_item = self._load_daily(symbol, day)
                        if not daily.empty:
                            frames.append(daily)
                        manifest.append(daily_item)
                        day += timedelta(days=1)
                cursor = segment_end
                continue
            daily, item = self._load_daily(symbol, cursor)
            if not daily.empty:
                frames.append(daily)
            manifest.append(item)
            cursor += timedelta(days=1)

        start_ts = pd.Timestamp(datetime.combine(start_day, time.min, tzinfo=timezone.utc))
        end_ts = pd.Timestamp(datetime.combine(end_day_exclusive, time.min, tzinfo=timezone.utc))
        index = pd.date_range(start_ts, end_ts - pd.Timedelta(minutes=1), freq="1min", tz="UTC")
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            combined = combined.sort_values("open_time").drop_duplicates("open_time", keep="last")
            combined = combined.set_index("open_time").reindex(index)
        else:
            combined = pd.DataFrame(index=index)
        for column in ["open", "high", "low", "close", "volume", "quote_volume", "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume"]:
            if column not in combined:
                combined[column] = np.nan
        combined["observed"] = combined["close"].notna()
        combined.index.name = "open_time"
        return LoadedSymbol(combined, manifest)


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
    """Vectorised, look-ahead-safe implementation of the frozen V9 momentum signal."""
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    quote = pd.to_numeric(frame["quote_volume"], errors="coerce")
    observed = frame["observed"].fillna(False).astype(bool)

    cfg = BACKTEST_PROTOCOL["signal_rule"]
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
        "late_return": ret_15 >= float(cfg["ret_15m_pct_min"]),
        "late_volume": (
            (volume_15_ratio >= float(cfg["quote_volume_15m_vs_prior_7d_same_time_min"]))
            & (same_time_count >= int(cfg["minimum_same_time_reference_days"]))
        ),
        "late_range_position": range_position >= float(cfg["position_in_1440m_range_min"]),
        "late_runup": runup_15 >= float(cfg["max_runup_15m_pct_min"]),
    }).fillna(False)
    component_count = components.sum(axis=1)
    late = (
        (component_count >= int(cfg["minimum_components"]))
        & (liquidity_5 >= float(cfg["prior_5m_quote_volume_min"]))
        & observed
    ).fillna(False)

    result = pd.DataFrame(index=frame.index)
    result["late_trigger"] = late
    result["late_components_passed"] = component_count
    result["ret_15m_pct"] = ret_15
    result["quote_volume_15m_vs_prior_7d_same_time"] = volume_15_ratio
    result["same_time_reference_days"] = same_time_count
    result["position_in_1440m_range"] = range_position
    result["max_runup_15m_pct"] = runup_15
    result["entry_quote_volume_5m"] = liquidity_5
    result["signal_close"] = close
    result["component_return_pass"] = components["late_return"]
    result["component_volume_pass"] = components["late_volume"]
    result["component_range_pass"] = components["late_range_position"]
    result["component_runup_pass"] = components["late_runup"]
    mask = (result.index >= pd.Timestamp(start)) & (result.index < pd.Timestamp(end_exclusive))
    return result.loc[mask].copy()


def candidate_signals(symbol: str, signal_frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Return every completed-minute momentum trigger; portfolio rules suppress duplicates later."""
    candidates: list[dict[str, Any]] = []
    late_rows = signal_frame[signal_frame["late_trigger"].fillna(False)]
    for signal_bar, row in late_rows.iterrows():
        candidates.append({
            "symbol": symbol,
            "signal_bar_open": signal_bar.isoformat(),
            "signal_decision_time": (signal_bar + pd.Timedelta(minutes=1)).isoformat(),
            "signal_close": float(row["signal_close"]),
            "late_components_passed": int(row["late_components_passed"]),
            "ret_15m_pct": float(row["ret_15m_pct"]),
            "quote_volume_15m_vs_prior_7d_same_time": float(row["quote_volume_15m_vs_prior_7d_same_time"]),
            "same_time_reference_days": int(row["same_time_reference_days"]),
            "position_in_1440m_range": float(row["position_in_1440m_range"]),
            "max_runup_15m_pct": float(row["max_runup_15m_pct"]),
            "entry_quote_volume_5m": float(row["entry_quote_volume_5m"]),
            "component_return_pass": bool(row["component_return_pass"]),
            "component_volume_pass": bool(row["component_volume_pass"]),
            "component_range_pass": bool(row["component_range_pass"]),
            "component_runup_pass": bool(row["component_runup_pass"]),
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

    realised_path = trades[(trades["time"] > pd.Timestamp(entry_fill_time)) & (trades["time"] <= pd.Timestamp(trigger_time))]
    path_prices = pd.to_numeric(realised_path.get("price", pd.Series(dtype=float)), errors="coerce").dropna()
    maximum_favourable_excursion_pct = (
        float((path_prices.max() / entry_vwap - 1.0) * 100.0) if not path_prices.empty else 0.0
    )
    maximum_adverse_excursion_pct = (
        float((path_prices.min() / entry_vwap - 1.0) * 100.0) if not path_prices.empty else 0.0
    )
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
        "exit_trigger_to_vwap_slippage_pct": (
            (float(exit_fill["vwap"]) / float(trigger_price) - 1.0) * 100.0
            if trigger_price not in (None, 0) else None
        ),
        "exit_fill_completed_at": exit_fill["fill_completed_at"],
        "holding_minutes_to_trigger": (trigger_time - entry_fill_time).total_seconds() / 60.0,
        "maximum_favourable_excursion_pct": maximum_favourable_excursion_pct,
        "maximum_adverse_excursion_pct": maximum_adverse_excursion_pct,
        "exit_trades_used": exit_fill["trades_used"],
        "gross_return_pct": gross_return,
        "net_return_pct": net_return,
        "net_pnl_quote": net_pnl,
        "fees_quote": float(cfg["position_quote_notional"]) * fee_rate + exit_quote * fee_rate,
    }


def _basic_performance(completed: pd.DataFrame, starting_equity: float) -> dict[str, Any]:
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
    completed = completed.sort_values("entry_fill_completed_at").copy()
    pnl = pd.to_numeric(completed["net_pnl_quote"], errors="coerce").fillna(0.0)
    equity = float(starting_equity) + pnl.cumsum()
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
        "maximum_drawdown_pct_of_starting_equity": float(drawdown.min() / starting_equity * 100.0),
        "maximum_consecutive_losses": int(max_losses),
        "unique_symbols_traded": int(completed["symbol"].nunique()),
        "largest_symbol_trade_share": float(symbol_counts.iloc[0] / len(completed)) if len(symbol_counts) else None,
        "exit_reason_counts": completed["exit_reason"].value_counts().to_dict(),
    }


def _symbol_cluster_bootstrap_expectancy(completed: pd.DataFrame, iterations: int = 10_000) -> dict[str, Any]:
    if completed.empty or completed["symbol"].nunique() < 2:
        return {"iterations": 0, "lower_95": None, "median": None, "upper_95": None}
    grouped = {
        str(symbol): pd.to_numeric(group["net_pnl_quote"], errors="coerce").dropna().to_numpy(dtype=float)
        for symbol, group in completed.groupby("symbol")
    }
    symbols = sorted(grouped)
    rng = np.random.default_rng(20260725)
    means = np.empty(iterations, dtype=float)
    for idx in range(iterations):
        sampled = rng.choice(symbols, size=len(symbols), replace=True)
        values = np.concatenate([grouped[str(symbol)] for symbol in sampled])
        means[idx] = float(values.mean()) if len(values) else np.nan
    finite = means[np.isfinite(means)]
    if not len(finite):
        return {"iterations": 0, "lower_95": None, "median": None, "upper_95": None}
    return {
        "iterations": int(len(finite)),
        "lower_95": float(np.quantile(finite, 0.025)),
        "median": float(np.quantile(finite, 0.5)),
        "upper_95": float(np.quantile(finite, 0.975)),
    }


def _performance(trades: pd.DataFrame, start: date, end_exclusive: date) -> dict[str, Any]:
    cfg = BACKTEST_PROTOCOL["execution"]
    starting_equity = float(cfg["simulated_starting_equity_quote"])
    completed = trades[trades["execution_status"] == "completed"].copy() if not trades.empty else pd.DataFrame()
    overall = _basic_performance(completed, starting_equity)
    span_days = max(1, (end_exclusive - start).days)
    overall["trades_per_calendar_day"] = float(len(completed) / span_days)
    if completed.empty:
        return {"overall": overall, "chronological_thirds": [], "monthly": [], "by_symbol": [], "daily": [], "symbol_cluster_bootstrap_expectancy": _symbol_cluster_bootstrap_expectancy(completed)}

    completed["entry_time"] = pd.to_datetime(completed["entry_fill_completed_at"], utc=True)
    total_seconds = (datetime.combine(end_exclusive, time.min, tzinfo=timezone.utc) - datetime.combine(start, time.min, tzinfo=timezone.utc)).total_seconds()
    boundaries = [
        datetime.combine(start, time.min, tzinfo=timezone.utc) + timedelta(seconds=total_seconds * i / 3)
        for i in range(4)
    ]
    thirds: list[dict[str, Any]] = []
    for i in range(3):
        subset = completed[(completed["entry_time"] >= boundaries[i]) & (completed["entry_time"] < boundaries[i + 1])]
        metrics = _basic_performance(subset, starting_equity)
        metrics.update({"segment": i + 1, "start": boundaries[i].isoformat(), "end_exclusive": boundaries[i + 1].isoformat()})
        thirds.append(metrics)

    monthly: list[dict[str, Any]] = []
    completed["month"] = completed["entry_time"].dt.strftime("%Y-%m")
    for month, subset in completed.groupby("month", sort=True):
        metrics = _basic_performance(subset, starting_equity)
        metrics["month"] = month
        monthly.append(metrics)

    by_symbol: list[dict[str, Any]] = []
    for symbol, subset in completed.groupby("symbol"):
        metrics = _basic_performance(subset, starting_equity)
        metrics["symbol"] = str(symbol)
        by_symbol.append(metrics)
    by_symbol.sort(key=lambda row: (-int(row["completed_trades"]), str(row["symbol"])))

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
    return {
        "overall": overall,
        "chronological_thirds": thirds,
        "monthly": monthly,
        "by_symbol": by_symbol,
        "daily": daily,
        "symbol_cluster_bootstrap_expectancy": _symbol_cluster_bootstrap_expectancy(completed),
    }


def _graduation_decision(performance: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    criteria = BACKTEST_PROTOCOL["graduation_criteria"]
    overall = performance["overall"]
    thirds = performance["chronological_thirds"]
    bootstrap = performance["symbol_cluster_bootstrap_expectancy"]
    pf = overall.get("profit_factor")
    checks = {
        "minimum_completed_trades": int(overall.get("completed_trades") or 0) >= int(criteria["minimum_completed_trades"]),
        "minimum_unique_symbols": int(overall.get("unique_symbols_traded") or 0) >= int(criteria["minimum_unique_symbols"]),
        "positive_total_net_pnl": float(overall.get("total_net_pnl_quote") or 0.0) > float(criteria["minimum_total_net_pnl_quote_exclusive"]),
        "minimum_expectancy": overall.get("expectancy_quote") is not None and float(overall["expectancy_quote"]) >= float(criteria["minimum_expectancy_quote"]),
        "minimum_profit_factor": pf is not None and float(pf) >= float(criteria["minimum_profit_factor"]),
        "maximum_drawdown": overall.get("maximum_drawdown_quote") is not None and abs(float(overall["maximum_drawdown_quote"])) <= float(criteria["maximum_drawdown_quote"]),
        "maximum_consecutive_losses": int(overall.get("maximum_consecutive_losses") or 0) <= int(criteria["maximum_consecutive_losses"]),
        "maximum_symbol_concentration": overall.get("largest_symbol_trade_share") is not None and float(overall["largest_symbol_trade_share"]) <= float(criteria["maximum_largest_symbol_trade_share"]),
        "minimum_trades_each_third": len(thirds) == 3 and all(int(row.get("completed_trades") or 0) >= int(criteria["minimum_trades_each_chronological_third"]) for row in thirds),
        "positive_expectancy_each_third": len(thirds) == 3 and all(row.get("expectancy_quote") is not None and float(row["expectancy_quote"]) > 0 for row in thirds),
        "bootstrap_lower_expectancy_above_zero": bootstrap.get("lower_95") is not None and float(bootstrap["lower_95"]) > 0,
        "minimum_minute_archive_coverage": quality.get("minute_archive_mean_coverage") is not None and float(quality["minute_archive_mean_coverage"]) >= float(criteria["minimum_minute_archive_mean_coverage"]),
        "maximum_symbol_failure_fraction": float(quality.get("symbol_failure_fraction") or 0.0) <= float(criteria["maximum_symbol_failure_fraction"]),
    }
    return {
        "passed": all(checks.values()),
        "decision": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


class ContinuousBacktestBuilder:
    def __init__(self, db: SupabaseClient, binance: BinanceClient, temp_root: Path):
        self.db = db
        self.binance = binance
        self.temp_root = temp_root
        self.minute_cache = BacktestMinuteArchiveCache(binance, temp_root)
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
            raise ValueError("Backtest protocol does not match the frozen V9 protocol")
        start = date.fromisoformat(str(job["window_start_date"]))
        end = date.fromisoformat(str(job["window_end_date_exclusive"]))
        if start >= end:
            raise ValueError("Backtest start must be before end")
        if start < date(2025, 7, 1) or end > date(2025, 11, 1):
            raise ValueError("V9 is frozen to the untouched 2025-07-01 through 2025-11-01 window")
        if start != date(2025, 7, 1) or end != date(2025, 11, 1):
            raise ValueError("V9 dates are frozen at 2025-07-01 to 2025-11-01 exclusive")
        for key, expected in {
            "position_quote_notional": 500.0,
            "take_profit_pct": 10.0,
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
        load_start = start_day - timedelta(days=8)
        work = Path(tempfile.mkdtemp(prefix=f"backtest-{job_id}-", dir=self.temp_root))
        try:
            all_candidates: list[dict[str, Any]] = []
            coverage_rows: list[dict[str, Any]] = []
            failures = 0
            signal_generation_failures = 0
            execution_failures = 0
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
                    requested_days = sum(int(row.get("days_covered") or 1) for row in loaded.source_manifest)
                    available_days = sum(
                        int(row.get("days_covered") or 1)
                        for row in loaded.source_manifest
                        if row.get("status") == "available"
                    )
                    observed_fraction = float(frame["observed"].mean()) if len(frame) else 0.0
                    coverage_rows.append({
                        "symbol": symbol,
                        "candidate_signals": len(candidates),
                        "archive_days_requested": requested_days,
                        "archive_days_available": available_days,
                        "archive_coverage_fraction": available_days / requested_days if requested_days else 0.0,
                        "coverage_fraction": observed_fraction,
                        "archive_manifest_entries": len(loaded.source_manifest),
                    })
                except Exception as exc:
                    failures += 1
                    signal_generation_failures += 1
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
                    execution_failures += 1
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
                "symbols_with_signal_generation_failures": signal_generation_failures,
                "execution_failures": execution_failures,
                "candidate_signals": len(candidates_df),
                "candidate_signals_excluded_for_outcome_cutoff": candidates_excluded_for_outcome_cutoff,
                "execution_status_counts": executions_df["execution_status"].value_counts().to_dict() if not executions_df.empty else {},
                "minute_archive_mean_coverage": float(pd.DataFrame(coverage_rows).get("coverage_fraction", pd.Series(dtype=float)).mean()) if coverage_rows else None,
                "current_tradeable_universe_survivorship_bias": True,
            }
            quality["symbol_failure_fraction"] = signal_generation_failures / len(symbols) if symbols else 1.0
            graduation = _graduation_decision(performance, quality)
            performance = _json_safe(performance)
            quality = _json_safe(quality)
            graduation = _json_safe(graduation)
            decision = {
                "protocol": BACKTEST_PROTOCOL,
                "performance": performance,
                "quality": quality,
                "graduation": graduation,
                "programme_decision": (
                    "PASS — momentum continuation merits a separate robustness and implementation review"
                    if graduation["passed"]
                    else "FAIL — retire the OHLCV-only Binance surge programme without parameter retuning"
                ),
            }

            candidates_df.to_csv(work / "candidate_signals.csv", index=False)
            executions_df.to_csv(work / "executed_trades.csv", index=False)
            pd.DataFrame(coverage_rows).to_csv(work / "minute_data_coverage.csv", index=False)
            pd.DataFrame(agg_manifest_summary).to_csv(work / "aggregate_trade_coverage.csv", index=False)
            pd.DataFrame(performance.get("chronological_thirds", [])).to_csv(work / "performance_by_chronological_third.csv", index=False)
            pd.DataFrame(performance.get("monthly", [])).to_csv(work / "performance_by_month.csv", index=False)
            pd.DataFrame(performance.get("by_symbol", [])).to_csv(work / "performance_by_symbol.csv", index=False)
            pd.DataFrame(performance.get("daily", [])).to_csv(work / "daily_performance.csv", index=False)
            (work / "backtest_protocol.json").write_text(json.dumps(BACKTEST_PROTOCOL, indent=2), encoding="utf-8")
            (work / "backtest_results.json").write_text(json.dumps(decision, indent=2, default=str), encoding="utf-8")
            (work / "README.md").write_text(
                "# V9 momentum-only continuous executable historical backtest\n\n"
                "This package evaluates the frozen late-momentum signal after every completed one-minute bar, without any precursor filter. "
                "The historical window and all trading and graduation parameters were frozen before results were opened. "
                "Entries and exits are reconstructed from Binance aggregate trades. The current-universe survivorship warning remains material.\n",
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
                "completed_trades": performance.get("overall", {}).get("completed_trades", 0),
                "failures": failures,
                "performance": performance,
                "quality": quality,
                "graduation": graduation,
                "programme_decision": decision["programme_decision"],
                "storage_path": storage_path,
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)
