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

from .baseline_context import add_baseline_derived_features, evaluate_preregistered_hypotheses
from .binance import BinanceClient, sha256_file
from .confirmation_v7 import FreshConfirmationBuilderV7
from .context import compute_context_feature_row
from .matched_controls import (
    MinuteArchiveCache,
    assign_temporal_splits,
    deterministic_tiebreak,
    deterministic_uuid,
    floor_minute,
    parse_datetime,
)
from .supabase import SupabaseClient

H3_COLUMN = "hypothesis_h3_volatility_reversal"
FROZEN_ACCEPTANCE: dict[str, Any] = {
    "version": "v8_h3_local_low_confirmation_1",
    "target": "saleable >=50% low-to-later-high rise within 480 minutes",
    "primary_population": (
        "event baselines and non-event pseudo-baselines selected by the same 480-minute "
        "rolling-minimum algorithm; complete ten-day history; prior five-minute quote volume >=500"
    ),
    "frozen_rule": {
        "volatility_1d_to_7d_ratio_min": 0.4,
        "ret_prior_1d_to_7d_pct_max": 5.0,
    },
    "controls_per_event": 5,
    "minimum_evaluable_events": 25,
    "minimum_event_signal_rate": 0.30,
    "maximum_control_signal_rate": 0.30,
    "minimum_event_to_control_rate_ratio": 1.50,
    "maximum_matched_permutation_p": 0.05,
    "minimum_unique_event_symbols_hit": 8,
    "symbol_cluster_rate_ratio_ci_low_must_exceed": 1.0,
    "validation_and_sealed_must_have_positive_direction": True,
    "minimum_positive_duration_bands_with_at_least_five_events": 2,
    "threshold_retuning_permitted": False,
}

DURATION_BANDS = (
    ("le_3h", 0, 180),
    ("gt_3h_to_6h", 181, 360),
    ("gt_6h_to_7h", 361, 420),
    ("gt_7h_to_8h", 421, 480),
)


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
    if pd.isna(value):
        return None
    return value


def duration_band(minutes: int | float | None) -> str:
    if minutes is None or not math.isfinite(float(minutes)):
        return "unknown"
    value = int(math.ceil(float(minutes)))
    for name, low, high in DURATION_BANDS:
        if low <= value <= high:
            return name
    return "outside_8h"


def derive_algorithmic_baseline(
    frame: pd.DataFrame,
    pseudo_cross: datetime,
    *,
    window_minutes: int = 480,
    threshold_pct: float = 50.0,
) -> dict[str, Any] | None:
    """Apply the scanner's rolling-minimum baseline logic at a pseudo-cross minute.

    The scanner keeps the latest occurrence of the minimum low in the prior
    window_minutes - 1 completed minute bars. Controls use the identical rule,
    then are rejected if that selected low actually produces a >=threshold move
    at any point in the following window.
    """
    cross_open = pd.Timestamp(floor_minute(pseudo_cross))
    prior_start = cross_open - pd.Timedelta(minutes=window_minutes - 1)
    prior_end = cross_open - pd.Timedelta(minutes=1)
    prior = frame.loc[prior_start:prior_end]
    expected_prior = window_minutes - 1
    if len(prior) != expected_prior or int(prior["observed"].sum()) != expected_prior:
        return None
    lows = pd.to_numeric(prior["low"], errors="coerce")
    if lows.isna().any() or lows.empty:
        return None
    minimum = float(lows.min())
    tolerance = max(abs(minimum) * 1e-12, 1e-15)
    matches = prior.index[(lows - minimum).abs() <= tolerance]
    if len(matches) == 0:
        return None
    baseline_open = pd.Timestamp(matches[-1])  # scanner retains the latest equal low
    duration_minutes = int((cross_open - baseline_open).total_seconds() // 60)
    if duration_minutes < 1 or duration_minutes >= window_minutes:
        return None

    path_start = baseline_open + pd.Timedelta(minutes=1)
    path_end = baseline_open + pd.Timedelta(minutes=window_minutes - 1)
    path = frame.loc[path_start:path_end]
    expected_path = window_minutes - 1
    if len(path) != expected_path or int(path["observed"].sum()) != expected_path:
        return None
    highs = pd.to_numeric(path["high"], errors="coerce")
    if highs.isna().any():
        return None
    maximum_gain_pct = (float(highs.max()) / minimum - 1.0) * 100.0
    crossing_rows = path[highs >= minimum * (1.0 + threshold_pct / 100.0)]
    first_future_cross = crossing_rows.index[0] if not crossing_rows.empty else None
    return {
        "pseudo_cross_time": cross_open.to_pydatetime(),
        "baseline_time": baseline_open.to_pydatetime(),
        "baseline_price": minimum,
        "duration_minutes": duration_minutes,
        "duration_band": duration_band(duration_minutes),
        "maximum_future_8h_gain_pct": maximum_gain_pct,
        "contaminated": bool(maximum_gain_pct + 1e-12 >= threshold_pct),
        "first_future_cross_time": first_future_cross.to_pydatetime() if first_future_cross is not None else None,
    }


def _matched_permutation_p(
    frame: pd.DataFrame,
    *,
    iterations: int = 50_000,
    seed: int = 805601,
) -> float | None:
    groups: list[np.ndarray] = []
    observed_event: list[float] = []
    observed_control: list[float] = []
    for _, group in frame.groupby("match_group_id", sort=False):
        event = group[group["label"] == 1]
        controls = group[group["label"] == 0]
        if len(event) != 1 or controls.empty:
            continue
        values = group["signal"].astype(float).to_numpy()
        groups.append(values)
        observed_event.append(float(event.iloc[0]["signal"]))
        observed_control.extend(controls["signal"].astype(float).tolist())
    if not groups or not observed_control:
        return None
    observed = float(np.mean(observed_event) - np.mean(observed_control))
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(iterations):
        event_values: list[float] = []
        control_values: list[float] = []
        for values in groups:
            chosen = int(rng.integers(0, len(values)))
            event_values.append(float(values[chosen]))
            if len(values) > 1:
                control_values.extend(np.delete(values, chosen).tolist())
        statistic = float(np.mean(event_values) - np.mean(control_values))
        if statistic >= observed - 1e-15:
            exceed += 1
    return (exceed + 1.0) / (iterations + 1.0)


def _symbol_cluster_rate_ratio_ci(
    frame: pd.DataFrame,
    *,
    iterations: int = 20_000,
    seed: int = 805602,
) -> tuple[float | None, float | None]:
    symbols = sorted(frame["symbol"].dropna().astype(str).unique())
    if len(symbols) < 2:
        return None, None
    clusters = {symbol: frame[frame["symbol"].astype(str) == symbol] for symbol in symbols}
    rng = np.random.default_rng(seed)
    ratios: list[float] = []
    for _ in range(iterations):
        sampled = rng.choice(symbols, size=len(symbols), replace=True)
        event_hits = event_count = control_hits = control_count = 0
        for symbol in sampled:
            cluster = clusters[str(symbol)]
            events = cluster[cluster["label"] == 1]
            controls = cluster[cluster["label"] == 0]
            event_hits += int(events["signal"].sum())
            event_count += int(len(events))
            control_hits += int(controls["signal"].sum())
            control_count += int(len(controls))
        if event_count == 0 or control_count == 0:
            continue
        event_rate = event_hits / event_count
        control_rate = control_hits / control_count
        if control_rate == 0:
            if event_rate > 0:
                ratios.append(math.inf)
        else:
            ratios.append(event_rate / control_rate)
    finite = np.asarray([value for value in ratios if math.isfinite(value)], dtype=float)
    if finite.size < 100:
        return None, None
    return float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))


def _evaluate(frame: pd.DataFrame, split: str) -> dict[str, Any]:
    subset = frame if split == "overall" else frame[frame["split"] == split]
    events = subset[subset["label"] == 1]
    controls = subset[subset["label"] == 0]
    event_hits = int(events["signal"].sum())
    control_hits = int(controls["signal"].sum())
    event_rate = event_hits / len(events) if len(events) else None
    control_rate = control_hits / len(controls) if len(controls) else None
    rate_ratio = (
        event_rate / control_rate
        if event_rate is not None and control_rate not in (None, 0)
        else (math.inf if event_rate and control_rate == 0 else None)
    )
    return {
        "split": split,
        "events": int(len(events)),
        "event_hits": event_hits,
        "event_rate": event_rate,
        "controls": int(len(controls)),
        "control_hits": control_hits,
        "control_rate": control_rate,
        "event_to_control_rate_ratio": rate_ratio,
        "unique_event_symbols_hit": int(events.loc[events["signal"], "symbol"].nunique()) if len(events) else 0,
        "matched_permutation_p": _matched_permutation_p(subset) if split == "overall" else None,
    }


def _duration_results(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, _, _ in DURATION_BANDS:
        subset = frame[frame["event_duration_band"] == name]
        events = subset[subset["label"] == 1]
        controls = subset[subset["label"] == 0]
        event_rate = float(events["signal"].mean()) if len(events) else None
        control_rate = float(controls["signal"].mean()) if len(controls) else None
        rows.append({
            "duration_band": name,
            "events": int(len(events)),
            "event_hits": int(events["signal"].sum()),
            "event_rate": event_rate,
            "controls": int(len(controls)),
            "control_hits": int(controls["signal"].sum()),
            "control_rate": control_rate,
            "positive_direction": bool(
                event_rate is not None and control_rate is not None and event_rate > control_rate
            ),
        })
    return rows


def _split_calendar_days(
    events: list[dict[str, Any]],
    scan_start: date,
    scan_end_exclusive: date,
    discovery_pct: int,
    validation_pct: int,
) -> tuple[dict[date, str], dict[str, set[date]], list[dict[str, Any]]]:
    split_map, summary = assign_temporal_splits(events, discovery_pct, validation_pct)
    discovery_dates = sorted(day for day, value in split_map.items() if value == "discovery")
    validation_dates = sorted(day for day, value in split_map.items() if value == "validation")
    discovery_end = max(discovery_dates) if discovery_dates else scan_start
    validation_end = max(validation_dates) if validation_dates else discovery_end
    split_dates = {"discovery": set(), "validation": set(), "sealed_test": set()}
    day = scan_start
    while day < scan_end_exclusive:
        if day <= discovery_end:
            split_dates["discovery"].add(day)
        elif day <= validation_end:
            split_dates["validation"].add(day)
        else:
            split_dates["sealed_test"].add(day)
        day += timedelta(days=1)
    return split_map, split_dates, summary


def _candidate_offsets() -> tuple[int, ...]:
    values = [0]
    for distance in (15, 30, 45, 60, 90, 120, 150, 180, 210, 240):
        values.extend((-distance, distance))
    return tuple(values)


def _quality_at_baseline(
    frame: pd.DataFrame,
    baseline: datetime,
    *,
    prior_days: int,
    min_entry_notional: float,
) -> tuple[bool, str, dict[str, Any]]:
    baseline_open = pd.Timestamp(floor_minute(baseline))
    end_open = baseline_open - pd.Timedelta(minutes=1)
    history_start = end_open - pd.Timedelta(minutes=prior_days * 1440 - 1)
    history = frame.loc[history_start:end_open]
    expected = prior_days * 1440
    observed = int(history["observed"].sum()) if len(history) else 0
    fraction = observed / expected if expected else 0.0
    if len(history) != expected or fraction < 0.995:
        return False, "insufficient_prior_history", {"observed_fraction": fraction}
    liquidity = frame.loc[end_open - pd.Timedelta(minutes=4):end_open, "quote_volume"].sum(min_count=5)
    if pd.isna(liquidity):
        return False, "missing_entry_liquidity", {"observed_fraction": fraction}
    if float(liquidity) < min_entry_notional:
        return False, "below_entry_liquidity_floor", {
            "observed_fraction": fraction,
            "entry_quote_volume_5m": float(liquidity),
        }
    return True, "pass", {
        "observed_fraction": fraction,
        "entry_quote_volume_5m": float(liquidity),
    }


def _feature_row(
    frame: pd.DataFrame,
    *,
    sample: dict[str, Any],
    prior_days: int,
    min_entry_notional: float,
) -> dict[str, Any]:
    adapted = {
        "sample_id": sample["sample_id"],
        "match_group_id": sample["match_group_id"],
        "sample_type": sample["sample_type"],
        "label": sample["label"],
        "split": sample["split"],
        "symbol": sample["symbol"],
        "base_asset": sample.get("base_asset"),
        "quote_asset": sample.get("quote_asset"),
        "event_id": sample.get("event_id"),
        "control_id": sample.get("control_id"),
        "control_rank": sample.get("control_rank"),
        "anchor_time": sample["baseline_time"],
    }
    row = compute_context_feature_row(
        frame,
        sample=adapted,
        horizon_minutes=0,
        prior_days=prior_days,
        min_entry_notional=min_entry_notional,
        reference_frames={},
    )
    add_baseline_derived_features(row)
    row.update(evaluate_preregistered_hypotheses(row))
    row.update({
        "control_design": "same_scanner_rolling_minimum",
        "baseline_time": sample["baseline_time"],
        "pseudo_cross_time": sample["pseudo_cross_time"],
        "event_duration_minutes": sample["event_duration_minutes"],
        "event_duration_band": sample["event_duration_band"],
        "selected_baseline_duration_minutes": sample["selected_baseline_duration_minutes"],
        "selected_baseline_duration_band": sample["selected_baseline_duration_band"],
        "maximum_future_8h_gain_pct": sample.get("maximum_future_8h_gain_pct"),
        "clock_offset_minutes": sample.get("clock_offset_minutes"),
        "calendar_distance_days": sample.get("calendar_distance_days"),
        "duration_difference_minutes": sample.get("duration_difference_minutes"),
        "match_tier": sample.get("match_tier"),
    })
    row["signal"] = bool(row.get(H3_COLUMN)) if row.get(H3_COLUMN) is not None else None
    return row


def select_local_low_controls_for_event(
    *,
    event: dict[str, Any],
    split: str,
    split_dates: set[date],
    frame: pd.DataFrame,
    known_event_times: list[datetime],
    controls_per_event: int,
    prior_days: int,
    min_entry_notional: float,
    threshold_pct: float,
    window_minutes: int,
    used_baselines: Counter[tuple[str, datetime]],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    event_cross = parse_datetime(event.get("first_cross_time") or event["first_cross_trade_time"])
    event_baseline = parse_datetime(event["baseline_time"])
    event_duration = int(event.get("minutes_baseline_open_to_cross_open") or max(1, (event_cross - event_baseline).total_seconds() // 60))
    event_band = duration_band(event_duration)
    rejection = Counter()
    candidates: list[dict[str, Any]] = []
    for candidate_day in sorted(split_dates):
        base = datetime.combine(candidate_day, event_cross.timetz().replace(tzinfo=None), tzinfo=timezone.utc)
        for offset in _candidate_offsets():
            pseudo_cross = base + timedelta(minutes=offset)
            if pseudo_cross.date() not in split_dates:
                continue
            if any(abs((pseudo_cross - known).total_seconds()) < 24 * 3600 for known in known_event_times):
                rejection["within_24h_of_known_event"] += 1
                continue
            derived = derive_algorithmic_baseline(
                frame,
                pseudo_cross,
                window_minutes=window_minutes,
                threshold_pct=threshold_pct,
            )
            if derived is None:
                rejection["incomplete_algorithm_window"] += 1
                continue
            if derived["contaminated"]:
                rejection["future_50pct_contamination"] += 1
                continue
            if derived["duration_band"] != event_band:
                rejection["duration_band_mismatch"] += 1
                continue
            baseline = derived["baseline_time"]
            if any(abs((baseline - known).total_seconds()) < 24 * 3600 for known in known_event_times):
                rejection["baseline_within_24h_of_known_event"] += 1
                continue
            valid, reason, quality = _quality_at_baseline(
                frame,
                baseline,
                prior_days=prior_days,
                min_entry_notional=min_entry_notional,
            )
            if not valid:
                rejection[reason] += 1
                continue
            key = (str(event["symbol"]), floor_minute(baseline))
            duration_difference = abs(int(derived["duration_minutes"]) - event_duration)
            clock_distance = abs(offset)
            weekday_match = pseudo_cross.weekday() == event_cross.weekday()
            tier = (
                "same_clock_same_duration_30m" if clock_distance == 0 and duration_difference <= 30
                else "same_clock_same_band" if clock_distance == 0
                else "within_60m_same_duration_30m" if clock_distance <= 60 and duration_difference <= 30
                else "within_60m_same_band" if clock_distance <= 60
                else "within_240m_same_band"
            )
            tier_rank = {
                "same_clock_same_duration_30m": 0,
                "same_clock_same_band": 1,
                "within_60m_same_duration_30m": 2,
                "within_60m_same_band": 3,
                "within_240m_same_band": 4,
            }[tier]
            candidates.append({
                "pseudo_cross": pseudo_cross,
                "baseline": baseline,
                "derived": derived,
                "key": key,
                "offset": offset,
                "duration_difference": duration_difference,
                "weekday_match": weekday_match,
                "calendar_distance": abs((candidate_day - event_cross.date()).days),
                "tier": tier,
                "tier_rank": tier_rank,
                "quality": quality,
                "tie": deterministic_tiebreak(event["id"], pseudo_cross.isoformat(), baseline.isoformat()),
            })

    best_by_day: dict[date, dict[str, Any]] = {}
    for candidate in sorted(
        candidates,
        key=lambda row: (
            used_baselines[row["key"]] > 0,
            used_baselines[row["key"]],
            row["tier_rank"],
            row["duration_difference"],
            0 if row["weekday_match"] else 1,
            row["calendar_distance"],
            row["tie"],
        ),
    ):
        best_by_day.setdefault(candidate["pseudo_cross"].date(), candidate)
    ranked = sorted(
        best_by_day.values(),
        key=lambda row: (
            used_baselines[row["key"]] > 0,
            used_baselines[row["key"]],
            row["tier_rank"],
            row["duration_difference"],
            0 if row["weekday_match"] else 1,
            row["calendar_distance"],
            row["tie"],
        ),
    )
    selected = ranked[:controls_per_event]
    rows: list[dict[str, Any]] = []
    for rank, candidate in enumerate(selected, start=1):
        prior_reuse = used_baselines[candidate["key"]]
        used_baselines[candidate["key"]] += 1
        derived = candidate["derived"]
        control_id = deterministic_uuid(
            "v8-local-low-control",
            event["id"],
            candidate["pseudo_cross"].isoformat(),
            candidate["baseline"].isoformat(),
        )
        rows.append({
            "sample_id": control_id,
            "control_id": control_id,
            "event_id": str(event["id"]),
            "match_group_id": str(event["id"]),
            "sample_type": "control",
            "label": 0,
            "split": split,
            "symbol": str(event["symbol"]),
            "base_asset": event.get("base_asset"),
            "quote_asset": event.get("quote_asset"),
            "control_rank": rank,
            "baseline_time": candidate["baseline"].isoformat(),
            "pseudo_cross_time": candidate["pseudo_cross"].isoformat(),
            "event_duration_minutes": event_duration,
            "event_duration_band": event_band,
            "selected_baseline_duration_minutes": int(derived["duration_minutes"]),
            "selected_baseline_duration_band": str(derived["duration_band"]),
            "maximum_future_8h_gain_pct": float(derived["maximum_future_8h_gain_pct"]),
            "clock_offset_minutes": int(candidate["offset"]),
            "calendar_distance_days": int(candidate["calendar_distance"]),
            "duration_difference_minutes": int(candidate["duration_difference"]),
            "weekday_match": bool(candidate["weekday_match"]),
            "match_tier": candidate["tier"],
            "prior_global_reuse_count": prior_reuse,
            "entry_quote_volume_5m_precheck": candidate["quality"].get("entry_quote_volume_5m"),
            "quality_status": "pass" if prior_reuse == 0 else "reused_control_baseline",
        })
    return rows, rejection


class FreshConfirmationBuilder:
    """Dispatch legacy V7 jobs and execute the corrected V8 local-low protocol."""

    def __init__(self, db: SupabaseClient, binance: BinanceClient, temp_root: Path):
        self.db = db
        self.binance = binance
        self.temp_root = temp_root
        self.cache = MinuteArchiveCache(binance, temp_root)
        self.legacy = FreshConfirmationBuilderV7(db, temp_root)

    def run(self, job: dict[str, Any]) -> dict[str, Any]:
        protocol = str(job.get("protocol_version") or FROZEN_ACCEPTANCE["version"])
        if protocol == "v7_h1_8h_fresh_confirmation_1":
            return self.legacy.run(job)
        if protocol != FROZEN_ACCEPTANCE["version"]:
            raise ValueError("Confirmation protocol does not match a supported frozen protocol")
        return self._run_v8(job)

    def _run_v8(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job["id"])
        scan_id = str(job.get("scan_id") or "")
        if not scan_id:
            raise ValueError("V8 confirmation requires a source scan_id")
        scan_rows = self.db.select("binance_scan_jobs", filters={"id": f"eq.{scan_id}"}, limit=1)
        if not scan_rows:
            raise ValueError("Source scan not found")
        scan = scan_rows[0]
        if scan.get("status") not in {"completed", "completed_with_warnings"}:
            raise ValueError("Source scan is not complete")
        if int(scan.get("window_minutes") or 0) != 480 or scan.get("event_definition_version") != "v7_rolling_8h":
            raise ValueError("V8 confirmation requires a completed eight-hour v7_rolling_8h scan")
        end_text = scan.get("window_end_date_exclusive") or (scan.get("result_json") or {}).get("window_end_exclusive")
        start_text = scan.get("window_start_date") or (scan.get("result_json") or {}).get("window_start")
        if not start_text or not end_text:
            raise ValueError("V8 confirmation requires an explicit historical scan window")
        scan_start = parse_datetime(start_text).date() if "T" in str(start_text) else date.fromisoformat(str(start_text))
        scan_end = parse_datetime(end_text).date() if "T" in str(end_text) else date.fromisoformat(str(end_text))
        if scan_end > date(2026, 1, 1):
            raise ValueError("Fresh V8 confirmation scan must end no later than 2026-01-01")

        controls_per_event = int(job.get("controls_per_event") or FROZEN_ACCEPTANCE["controls_per_event"])
        prior_days = int(job.get("prior_days") or 10)
        min_entry_notional = float(job.get("min_entry_notional") or 500)
        discovery_pct = int(job.get("discovery_pct") or 70)
        validation_pct = int(job.get("validation_pct") or 15)
        threshold_pct = float(scan.get("threshold_pct") or 50)
        window_minutes = int(scan.get("window_minutes") or 480)

        events = self.db.select_all(
            "binance_gainer_events",
            filters={"scan_id": f"eq.{scan_id}", "sellability_pass": "eq.true"},
            order="event_date.asc,symbol.asc",
        )
        if not events:
            raise RuntimeError("The source scan has no saleable events")
        split_map, split_dates, split_summary = _split_calendar_days(
            events,
            scan_start,
            scan_end,
            discovery_pct,
            validation_pct,
        )
        for event in events:
            event["split"] = split_map[date.fromisoformat(str(event["event_date"]))]

        load_start = scan_start - timedelta(days=prior_days + 1)
        load_end = scan_end + timedelta(days=1)
        events_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            events_by_symbol[str(event["symbol"])].append(event)

        self.db.update(
            "binance_confirmation_jobs",
            {"id": f"eq.{job_id}"},
            {
                "events_total": len(events),
                "symbols_total": len(events_by_symbol),
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        work = Path(tempfile.mkdtemp(prefix=f"v8-confirmation-{job_id}-", dir=self.temp_root))
        feature_rows: list[dict[str, Any]] = []
        match_rows: list[dict[str, Any]] = []
        source_manifest: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        rejections: Counter[str] = Counter()
        used_baselines: Counter[tuple[str, datetime]] = Counter()
        failures = 0
        try:
            processed = 0
            for symbol, symbol_events in sorted(events_by_symbol.items()):
                try:
                    loaded = self.cache.load_symbol(symbol, load_start, load_end)
                    frame = loaded.frame
                    source_manifest.extend(loaded.source_manifest)
                    known_times = []
                    for item in symbol_events:
                        known_times.extend([
                            parse_datetime(item["baseline_time"]),
                            parse_datetime(item.get("first_cross_time") or item["first_cross_trade_time"]),
                        ])
                    for event in symbol_events:
                        split = str(event["split"])
                        baseline = parse_datetime(event["baseline_time"])
                        cross = parse_datetime(event.get("first_cross_time") or event["first_cross_trade_time"])
                        event_duration = int(event.get("minutes_baseline_open_to_cross_open") or max(1, (cross - baseline).total_seconds() // 60))
                        valid, reason, quality = _quality_at_baseline(
                            frame,
                            baseline,
                            prior_days=prior_days,
                            min_entry_notional=min_entry_notional,
                        )
                        if not valid:
                            issues.append({
                                "confirmation_job_id": job_id,
                                "symbol": symbol,
                                "stage": "event_baseline_quality",
                                "message": f"{event['id']}: {reason}",
                            })
                            continue
                        event_sample = {
                            "sample_id": str(event["id"]),
                            "event_id": str(event["id"]),
                            "control_id": None,
                            "match_group_id": str(event["id"]),
                            "sample_type": "event",
                            "label": 1,
                            "split": split,
                            "symbol": symbol,
                            "base_asset": event.get("base_asset"),
                            "quote_asset": event.get("quote_asset"),
                            "control_rank": None,
                            "baseline_time": baseline.isoformat(),
                            "pseudo_cross_time": cross.isoformat(),
                            "event_duration_minutes": event_duration,
                            "event_duration_band": duration_band(event_duration),
                            "selected_baseline_duration_minutes": event_duration,
                            "selected_baseline_duration_band": duration_band(event_duration),
                            "maximum_future_8h_gain_pct": float(event.get("rolling_gain_pct_at_cross_trade") or threshold_pct),
                            "clock_offset_minutes": 0,
                            "calendar_distance_days": 0,
                            "duration_difference_minutes": 0,
                            "match_tier": "event",
                            "entry_quote_volume_5m_precheck": quality.get("entry_quote_volume_5m"),
                            "quality_status": "pass",
                        }
                        event_row = _feature_row(
                            frame,
                            sample=event_sample,
                            prior_days=prior_days,
                            min_entry_notional=min_entry_notional,
                        )
                        if event_row.get("feature_quality_status") != "pass" or event_row.get("signal") is None:
                            issues.append({
                                "confirmation_job_id": job_id,
                                "symbol": symbol,
                                "stage": "event_feature_quality",
                                "message": f"{event['id']}: {event_row.get('feature_quality_status')}",
                            })
                            continue
                        controls, rejected = select_local_low_controls_for_event(
                            event=event,
                            split=split,
                            split_dates=split_dates[split],
                            frame=frame,
                            known_event_times=known_times,
                            controls_per_event=controls_per_event,
                            prior_days=prior_days,
                            min_entry_notional=min_entry_notional,
                            threshold_pct=threshold_pct,
                            window_minutes=window_minutes,
                            used_baselines=used_baselines,
                        )
                        rejections.update(rejected)
                        if not controls:
                            issues.append({
                                "confirmation_job_id": job_id,
                                "symbol": symbol,
                                "stage": "control_matching",
                                "message": f"{event['id']}: no algorithmically matched controls",
                            })
                            continue
                        feature_rows.append(event_row)
                        for control in controls:
                            control_row = _feature_row(
                                frame,
                                sample=control,
                                prior_days=prior_days,
                                min_entry_notional=min_entry_notional,
                            )
                            if control_row.get("feature_quality_status") != "pass" or control_row.get("signal") is None:
                                issues.append({
                                    "confirmation_job_id": job_id,
                                    "symbol": symbol,
                                    "stage": "control_feature_quality",
                                    "message": f"{control['control_id']}: {control_row.get('feature_quality_status')}",
                                })
                                continue
                            feature_rows.append(control_row)
                            match_rows.append(control)
                except Exception as exc:
                    failures += 1
                    issues.append({
                        "confirmation_job_id": job_id,
                        "symbol": symbol,
                        "stage": "symbol_confirmation",
                        "message": str(exc)[:4000],
                    })
                processed += 1
                self.db.update(
                    "binance_confirmation_jobs",
                    {"id": f"eq.{job_id}"},
                    {
                        "symbols_processed": processed,
                        "controls_created": len(match_rows),
                        "failures": failures,
                        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

            if issues:
                self.db.insert("binance_confirmation_issues", issues)
            population = pd.DataFrame(feature_rows)
            if population.empty:
                raise RuntimeError("No evaluable event/control matched sets were produced")
            population["label"] = pd.to_numeric(population["label"], errors="raise").astype(int)
            population["signal"] = population["signal"].astype(bool)
            # Retain only groups with exactly one event and at least one valid control.
            valid_groups = []
            for group_id, group in population.groupby("match_group_id", sort=False):
                if int((group["label"] == 1).sum()) == 1 and int((group["label"] == 0).sum()) >= 1:
                    valid_groups.append(group_id)
            population = population[population["match_group_id"].isin(valid_groups)].copy()
            if population.empty:
                raise RuntimeError("No complete matched groups remained after quality filtering")

            results = [_evaluate(population, split) for split in ("discovery", "validation", "sealed_test", "overall")]
            overall = next(row for row in results if row["split"] == "overall")
            validation = next(row for row in results if row["split"] == "validation")
            sealed = next(row for row in results if row["split"] == "sealed_test")
            cluster_low, cluster_high = _symbol_cluster_rate_ratio_ci(population)
            duration_results = _duration_results(population)
            positive_duration_bands = sum(
                1 for row in duration_results
                if row["events"] >= 5 and row["positive_direction"]
            )
            checks = {
                "minimum_evaluable_events": overall["events"] >= FROZEN_ACCEPTANCE["minimum_evaluable_events"],
                "minimum_event_signal_rate": (overall["event_rate"] or 0) >= FROZEN_ACCEPTANCE["minimum_event_signal_rate"],
                "maximum_control_signal_rate": (
                    overall["control_rate"] if overall["control_rate"] is not None else 1
                ) <= FROZEN_ACCEPTANCE["maximum_control_signal_rate"],
                "minimum_event_to_control_rate_ratio": (
                    overall["event_to_control_rate_ratio"] or 0
                ) >= FROZEN_ACCEPTANCE["minimum_event_to_control_rate_ratio"],
                "maximum_matched_permutation_p": (
                    overall["matched_permutation_p"] if overall["matched_permutation_p"] is not None else 1
                ) <= FROZEN_ACCEPTANCE["maximum_matched_permutation_p"],
                "minimum_unique_event_symbols_hit": (
                    overall["unique_event_symbols_hit"] >= FROZEN_ACCEPTANCE["minimum_unique_event_symbols_hit"]
                ),
                "symbol_cluster_ci_low": (
                    cluster_low is not None
                    and cluster_low > FROZEN_ACCEPTANCE["symbol_cluster_rate_ratio_ci_low_must_exceed"]
                ),
                "validation_direction": (
                    validation["event_rate"] is not None
                    and validation["control_rate"] is not None
                    and validation["event_rate"] > validation["control_rate"]
                ),
                "sealed_direction": (
                    sealed["event_rate"] is not None
                    and sealed["control_rate"] is not None
                    and sealed["event_rate"] > sealed["control_rate"]
                ),
                "duration_band_stability": (
                    positive_duration_bands
                    >= FROZEN_ACCEPTANCE["minimum_positive_duration_bands_with_at_least_five_events"]
                ),
            }
            passed = bool(all(checks.values()))

            pd.DataFrame(results).to_csv(work / "fresh_confirmation_results.csv", index=False)
            pd.DataFrame(duration_results).to_csv(work / "duration_band_results.csv", index=False)
            population.to_csv(work / "fresh_confirmation_population.csv", index=False)
            pd.DataFrame(match_rows).to_csv(work / "algorithmic_local_low_controls.csv", index=False)
            pd.DataFrame(source_manifest).to_csv(work / "source_manifest.csv", index=False)
            pd.DataFrame(
                [{"rejection_reason": key, "count": value} for key, value in rejections.most_common()]
            ).to_csv(work / "control_rejections.csv", index=False)
            pd.DataFrame(split_summary).to_csv(work / "split_summary.csv", index=False)
            decision = {
                "protocol": FROZEN_ACCEPTANCE,
                "checks": checks,
                "passed": passed,
                "backtest_unlocked": passed,
                "symbol_cluster_rate_ratio_ci": [cluster_low, cluster_high],
                "positive_duration_bands": positive_duration_bands,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "source_scan_id": scan_id,
                "source_window": {"start": scan_start.isoformat(), "end_exclusive": scan_end.isoformat()},
                "control_design": (
                    "For each pseudo-cross minute, select the latest minimum low in the prior 479 minutes, "
                    "exactly matching the scanner; reject if that low rises 50% within the following 480 minutes."
                ),
                "warning": "No thresholds are altered after this run. A failure keeps the trading backtest locked.",
            }
            (work / "confirmation_decision.json").write_text(
                json.dumps(_json_safe(decision), indent=2), encoding="utf-8"
            )
            (work / "V8_PREREGISTERED_PROTOCOL.json").write_text(
                json.dumps(FROZEN_ACCEPTANCE, indent=2), encoding="utf-8"
            )
            (work / "README.md").write_text(
                "# V8 fresh H3 confirmation with algorithmically matched local-low controls\n\n"
                f"Decision: **{'PASS — continuous sealed backtest unlocked' if passed else 'FAIL — do not run the trading backtest'}**.\n\n"
                "The volatility-reversal rule and all acceptance criteria were frozen before the source scan was processed. "
                "Event and control baselines use the same rolling-minimum selection algorithm.\n",
                encoding="utf-8",
            )

            package = work / "fresh_confirmation_results.zip"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(work.iterdir()):
                    if path.is_file() and path != package:
                        archive.write(path, path.name)
            storage_path = f"fresh-confirmation/{job_id}/{package.name}"
            self.db.upload_file(storage_path, package, "application/zip")
            record = {
                "confirmation_job_id": job_id,
                "storage_path": storage_path,
                "filename": package.name,
                "size_bytes": package.stat().st_size,
                "sha256": sha256_file(package),
                "content_type": "application/zip",
                "role": "v8_h3_local_low_confirmation_results",
            }
            self.db.upsert(
                "binance_confirmation_files",
                [record],
                on_conflict="confirmation_job_id,storage_path",
            )
            return {
                "passed": passed,
                "events_evaluable": overall["events"],
                "controls_evaluable": overall["controls"],
                "event_hits": overall["event_hits"],
                "control_hits": overall["control_hits"],
                "event_rate": overall["event_rate"],
                "control_rate": overall["control_rate"],
                "matched_permutation_p": overall["matched_permutation_p"],
                "unique_event_symbols_hit": overall["unique_event_symbols_hit"],
                "cluster_rr_ci_low": cluster_low,
                "cluster_rr_ci_high": cluster_high,
                "duration_bands_positive": positive_duration_bands,
                "controls_created": int((population["label"] == 0).sum()),
                "symbols_processed": len(events_by_symbol),
                "failures": failures,
                "checks": checks,
                "storage_path": storage_path,
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)
