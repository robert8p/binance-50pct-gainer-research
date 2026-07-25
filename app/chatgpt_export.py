from __future__ import annotations

import hashlib
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

from .binance import BinanceClient, sha256_file
from .backtest import BacktestMinuteArchiveCache
from .confirmation import (
    derive_algorithmic_baseline,
    duration_band,
    select_local_low_controls_for_event,
)
from .matched_controls import (
    REFERENCE_SYMBOLS,
    SPLITS,
    assign_temporal_splits,
    floor_minute,
    parse_datetime,
    deterministic_uuid,
)
from .supabase import SupabaseClient

PROTOCOL_VERSION = "v10_2026_full_universe_discovery_export_2"
BACKGROUND_SAMPLES_PER_SYMBOL = 1
CHUNK_TARGET_BYTES = 300 * 1024 * 1024
EXPORT_SPLITS = ("discovery",)
RAW_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
)


def safe_filename(value: str) -> str:
    """Return a collision-resistant ASCII filename stem."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    cleaned = "".join(ch if ch.isascii() and ch.isalnum() else "_" for ch in value)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    if cleaned and cleaned == value:
        return cleaned[:80]
    prefix = cleaned[:60] if cleaned else "symbol"
    return f"{prefix}_{digest}"


def extract_raw_window(
    frame: pd.DataFrame,
    baseline_time: datetime,
    *,
    prior_days: int,
    include_baseline_bar: bool,
    sample_id: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Extract raw minute bars without creating predictive features.

    The exported history ends at the selected baseline minute when
    include_baseline_bar is true, otherwise at the preceding completed minute.
    Relative minute 0 is the baseline bar; negative values are historical.
    """
    baseline_open = pd.Timestamp(floor_minute(baseline_time))
    end_open = baseline_open if include_baseline_bar else baseline_open - pd.Timedelta(minutes=1)
    start_open = baseline_open - pd.Timedelta(minutes=prior_days * 1440)
    window = frame.loc[start_open:end_open, list(RAW_COLUMNS) + ["observed"]].copy()
    expected_rows = prior_days * 1440 + (1 if include_baseline_bar else 0)
    if len(window) != expected_rows:
        raise ValueError(f"Expected {expected_rows} rows, found {len(window)}")
    observed_rows = int(window["observed"].fillna(False).sum())
    observed_fraction = observed_rows / expected_rows if expected_rows else 0.0
    window = window.reset_index().rename(columns={"index": "open_time"})
    window.insert(0, "sample_id", sample_id)
    window.insert(1, "relative_minute", (
        (pd.to_datetime(window["open_time"], utc=True) - baseline_open).dt.total_seconds() // 60
    ).astype("int32"))
    # Preserve missing rows explicitly rather than forward-filling or imputing.
    window["observed"] = window["observed"].fillna(False).astype(bool)
    window["trade_count"] = pd.to_numeric(window["trade_count"], errors="coerce").astype("Int64")
    return window, {
        "history_start": start_open.isoformat(),
        "history_end": end_open.isoformat(),
        "expected_rows": expected_rows,
        "observed_rows": observed_rows,
        "observed_fraction": observed_fraction,
        "complete_history": bool(observed_fraction >= 0.995),
    }


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
    split_dates = {split: set() for split in SPLITS}
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


def _history_quality(frame: pd.DataFrame, baseline: datetime, prior_days: int) -> tuple[bool, dict[str, Any]]:
    baseline_open = pd.Timestamp(floor_minute(baseline))
    start = baseline_open - pd.Timedelta(minutes=prior_days * 1440)
    end = baseline_open - pd.Timedelta(minutes=1)
    history = frame.loc[start:end]
    expected = prior_days * 1440
    observed = int(history["observed"].fillna(False).sum()) if len(history) else 0
    fraction = observed / expected if expected else 0.0
    five_minute = frame.loc[end - pd.Timedelta(minutes=4):end, "quote_volume"].sum(min_count=5)
    return len(history) == expected and fraction >= 0.995, {
        "history_observed_fraction": fraction,
        "pre_baseline_quote_volume_5m": float(five_minute) if pd.notna(five_minute) else None,
    }


def _zip_directory(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w") as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            # Parquet is already compressed; storing avoids wasting CPU and disk.
            compression = zipfile.ZIP_STORED if path.suffix == ".parquet" else zipfile.ZIP_DEFLATED
            archive.write(path, path.relative_to(source), compress_type=compression)


def _write_data_dictionary(path: Path) -> None:
    text = """# Data dictionary

This package is deliberately a neutral evidence export. It contains no preferred predictor, signal or trading rule.

## samples.csv
One row per event or neutral non-event sample. `label=1` identifies a saleable >=50% eight-hour event. `label=0` includes both same-coin scanner-equivalent controls and deterministic full-universe background samples, including coins with no 50% event in 2026.

## minute_data/*.parquet
Raw Binance one-minute kline fields stored once per physical symbol/time. Use `symbol`, `history_start`, `history_end` and `baseline_time` from samples.csv to reconstruct each labelled ten-day window. No missing values are imputed.

Columns: open_time, open, high, low, close, base volume, quote volume, trade count, taker-buy base volume, taker-buy quote volume, and observed.

## analysis_loader.py
A neutral helper that reconstructs one labelled sample window from samples.csv and the deduplicated symbol Parquet file. It creates no predictive features.

## reference_data/*.parquet
The separate universe-reference package contains raw one-minute BTCUSDT, ETHUSDT and BNBUSDT data, the complete canonical-symbol inventory, and full-universe daily bars.

## Integrity rules
Event, same-coin control and full-universe background baselines use the same 480-minute rolling-minimum algorithm. Negative samples are rejected when the selected low subsequently gains 50% within eight hours or lies within 24 hours of a known event in that coin. All 2026 samples are exploratory discovery evidence.
"""
    path.write_text(text, encoding="utf-8")


def _write_analysis_loader(path: Path) -> None:
    path.write_text(
        '''from __future__ import annotations

from pathlib import Path
import pandas as pd


def load_samples(package_root: str | Path = ".") -> pd.DataFrame:
    root = Path(package_root)
    return pd.read_csv(root / "samples.csv")


def load_sample(sample_id: str, package_root: str | Path = ".") -> tuple[pd.Series, pd.DataFrame]:
    root = Path(package_root)
    samples = load_samples(root)
    match = samples[samples["sample_id"].astype(str) == str(sample_id)]
    if len(match) != 1:
        raise KeyError(f"Expected exactly one sample_id={sample_id}, found {len(match)}")
    sample = match.iloc[0]
    minutes = pd.read_parquet(root / str(sample["minute_data_file"]))
    minutes["open_time"] = pd.to_datetime(minutes["open_time"], utc=True)
    start = pd.Timestamp(sample["history_start"])
    end = pd.Timestamp(sample["history_end"])
    frame = minutes[(minutes["open_time"] >= start) & (minutes["open_time"] <= end)].copy()
    baseline = pd.Timestamp(sample["baseline_time"])
    frame["relative_minute"] = ((frame["open_time"] - baseline).dt.total_seconds() // 60).astype("int32")
    return sample, frame.sort_values("open_time").reset_index(drop=True)
''',
        encoding="utf-8",
    )


class ExportCancelled(RuntimeError):
    pass


def _stable_int(*values: Any) -> int:
    payload = "|".join(str(value) for value in values).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


def _background_candidate_times(
    symbol: str,
    scan_start: date,
    scan_end_exclusive: date,
    *,
    prior_days: int,
    sample_index: int,
) -> list[datetime]:
    """Deterministic calendar candidates chosen without market outcomes."""
    first_day = scan_start + timedelta(days=prior_days + 2)
    last_day = scan_end_exclusive - timedelta(days=2)
    span = (last_day - first_day).days + 1
    if span <= 0:
        return []
    seed = _stable_int(PROTOCOL_VERSION, symbol, sample_index)
    centre = seed % span
    minute_of_day = (seed // max(span, 1)) % 1440
    offsets = [0]
    for distance in range(1, span):
        offsets.extend((-distance, distance))
    candidates: list[datetime] = []
    seen: set[date] = set()
    for delta in offsets:
        index = (centre + delta) % span
        candidate_day = first_day + timedelta(days=index)
        if candidate_day in seen:
            continue
        seen.add(candidate_day)
        candidates.append(
            datetime.combine(candidate_day, time.min, tzinfo=timezone.utc)
            + timedelta(minutes=int(minute_of_day))
        )
    return candidates


def select_universe_background_samples(
    *,
    symbol_info: dict[str, Any],
    frame: pd.DataFrame,
    scan_start: date,
    scan_end_exclusive: date,
    known_event_times: list[datetime],
    prior_days: int,
    threshold_pct: float,
    window_minutes: int,
    used_baselines: Counter[tuple[str, datetime]],
    count: int = BACKGROUND_SAMPLES_PER_SYMBOL,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Choose neutral scanner-equivalent negatives for every canonical symbol."""
    symbol = str(symbol_info["symbol"])
    rejection: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for sample_index in range(count):
        selected: dict[str, Any] | None = None
        for candidate_rank, pseudo_cross in enumerate(
            _background_candidate_times(
                symbol,
                scan_start,
                scan_end_exclusive,
                prior_days=prior_days,
                sample_index=sample_index,
            ),
            start=1,
        ):
            if any(abs((pseudo_cross - known).total_seconds()) < 24 * 3600 for known in known_event_times):
                rejection["background_within_24h_of_known_event"] += 1
                continue
            derived = derive_algorithmic_baseline(
                frame,
                pseudo_cross,
                window_minutes=window_minutes,
                threshold_pct=threshold_pct,
            )
            if derived is None:
                rejection["background_incomplete_algorithm_window"] += 1
                continue
            if derived["contaminated"]:
                rejection["background_future_50pct_contamination"] += 1
                continue
            baseline = parse_datetime(derived["baseline_time"])
            if any(abs((baseline - known).total_seconds()) < 24 * 3600 for known in known_event_times):
                rejection["background_baseline_within_24h_of_known_event"] += 1
                continue
            valid, quality = _history_quality(frame, baseline, prior_days)
            if not valid:
                rejection["background_incomplete_ten_day_history"] += 1
                continue
            key = (symbol, floor_minute(baseline))
            if used_baselines[key] > 0:
                rejection["background_reused_baseline"] += 1
                continue
            used_baselines[key] += 1
            selected = {
                "derived": derived,
                "quality": quality,
                "candidate_rank": candidate_rank,
                "pseudo_cross": pseudo_cross,
            }
            break
        if selected is None:
            continue
        derived = selected["derived"]
        sample_id = deterministic_uuid(
            "v10.2-full-universe-background",
            symbol,
            sample_index,
            selected["pseudo_cross"].isoformat(),
            derived["baseline_time"].isoformat(),
        )
        rows.append({
            "sample_id": sample_id,
            "match_group_id": sample_id,
            "event_id": None,
            "control_id": sample_id,
            "control_rank": sample_index + 1,
            "sample_type": "universe_background",
            "control_scope": "full_universe",
            "label": 0,
            "split": "discovery",
            "symbol": symbol,
            "minute_data_file": f"minute_data/{safe_filename(symbol)}.parquet",
            "base_asset": symbol_info.get("base_asset"),
            "quote_asset": symbol_info.get("quote_asset"),
            "baseline_time": parse_datetime(derived["baseline_time"]).isoformat(),
            "cross_or_pseudo_cross_time": parse_datetime(derived["pseudo_cross_time"]).isoformat(),
            "event_duration_minutes": int(derived["duration_minutes"]),
            "event_duration_band": str(derived["duration_band"]),
            "selected_baseline_duration_minutes": int(derived["duration_minutes"]),
            "selected_baseline_duration_band": str(derived["duration_band"]),
            "outcome_maximum_future_8h_gain_pct": float(derived["maximum_future_8h_gain_pct"]),
            "outcome_sellability_pass": False,
            "outcome_exit_vwap": None,
            "outcome_exit_vwap_vs_threshold_pct": None,
            "match_tier": "deterministic_full_universe_background",
            "calendar_distance_days": None,
            "clock_offset_minutes": None,
            "duration_difference_minutes": None,
            "background_candidate_rank": int(selected["candidate_rank"]),
            **selected["quality"],
        })
    return rows, rejection


def _chunk_symbols(symbol_files: dict[str, Path], target_bytes: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_size = 0
    for symbol in sorted(symbol_files):
        size = symbol_files[symbol].stat().st_size
        if current and current_size + size > target_bytes:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(symbol)
        current_size += size
    if current:
        chunks.append(current)
    return chunks


def _write_symbol_chunk(
    destination: Path,
    *,
    symbols: list[str],
    symbol_files: dict[str, Path],
    samples: pd.DataFrame,
    dictionary_path: Path,
    loader_path: Path,
    part_number: int,
    total_parts: int,
) -> dict[str, Any]:
    subset = samples[samples["symbol"].astype(str).isin(symbols)].copy()
    temp_csv = destination.with_suffix(".samples.csv")
    temp_meta = destination.with_suffix(".metadata.json")
    subset.to_csv(temp_csv, index=False)
    metadata = {
        "protocol_version": PROTOCOL_VERSION,
        "part_number": part_number,
        "total_parts": total_parts,
        "symbols": len(symbols),
        "samples": int(len(subset)),
        "events": int((subset["label"] == 1).sum()),
        "same_coin_controls": int((subset.get("control_scope") == "same_coin").sum()),
        "full_universe_backgrounds": int((subset.get("control_scope") == "full_universe").sum()),
        "warning": "Exploratory 2026 discovery evidence only.",
    }
    temp_meta.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    try:
        with zipfile.ZipFile(destination, "w") as archive:
            archive.write(temp_csv, "samples.csv", compress_type=zipfile.ZIP_DEFLATED)
            archive.write(temp_meta, "chunk_metadata.json", compress_type=zipfile.ZIP_DEFLATED)
            archive.write(dictionary_path, "DATA_DICTIONARY.md", compress_type=zipfile.ZIP_DEFLATED)
            archive.write(loader_path, "analysis_loader.py", compress_type=zipfile.ZIP_DEFLATED)
            for symbol in symbols:
                archive.write(
                    symbol_files[symbol],
                    f"minute_data/{symbol_files[symbol].name}",
                    compress_type=zipfile.ZIP_STORED,
                )
    finally:
        temp_csv.unlink(missing_ok=True)
        temp_meta.unlink(missing_ok=True)
    return metadata


class ChatGPTResearchExporter:
    def __init__(self, db: SupabaseClient, binance: BinanceClient, temp_root: Path):
        self.db = db
        self.binance = binance
        self.temp_root = temp_root
        self.cache_root = temp_root / "chatgpt-export-cache"
        self.cache = BacktestMinuteArchiveCache(binance, self.cache_root)

    def _assert_active(self, job_id: str) -> None:
        rows = self.db.select(
            "binance_chatgpt_export_jobs",
            filters={"id": f"eq.{job_id}"},
            limit=1,
        )
        if not rows or rows[0].get("status") != "running":
            raise ExportCancelled("ChatGPT research export cancelled")

    def run(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job["id"])
        if str(job.get("protocol_version") or PROTOCOL_VERSION) != PROTOCOL_VERSION:
            raise ValueError("Unsupported full-universe research-export protocol")
        scan_id = str(job["scan_id"])
        scan_rows = self.db.select("binance_scan_jobs", filters={"id": f"eq.{scan_id}"}, limit=1)
        if not scan_rows:
            raise ValueError("Source scan not found")
        scan = scan_rows[0]
        if scan.get("status") not in {"completed", "completed_with_warnings"}:
            raise ValueError("Source scan is not complete")
        if scan.get("event_definition_version") != "v7_rolling_8h" or int(scan.get("window_minutes") or 0) != 480:
            raise ValueError("Neutral exporter requires a completed eight-hour scan")
        start_text = scan.get("window_start_date") or (scan.get("result_json") or {}).get("window_start")
        end_text = scan.get("window_end_date_exclusive") or (scan.get("result_json") or {}).get("window_end_exclusive")
        if not start_text or not end_text:
            raise ValueError("Use an explicit historical scan window for staged research")
        scan_start = date.fromisoformat(str(start_text)[:10])
        scan_end = date.fromisoformat(str(end_text)[:10])
        if scan_start != date(2026, 1, 1) or scan_end != date(2026, 7, 25):
            raise ValueError("V10.2 discovery export is frozen to 2026-01-01 through 2026-07-25 exclusive")

        controls_per_event = int(job.get("controls_per_event") or 5)
        prior_days = int(job.get("prior_days") or 10)
        include_baseline_bar = bool(job.get("include_baseline_bar", True))
        threshold_pct = float(scan.get("threshold_pct") or 50)
        window_minutes = int(scan.get("window_minutes") or 480)

        events = self.db.select_all(
            "binance_gainer_events",
            filters={"scan_id": f"eq.{scan_id}", "sellability_pass": "eq.true"},
            order="event_date.asc,symbol.asc",
        )
        if not events:
            raise RuntimeError("Source scan has no saleable events")
        snapshots = self.db.select_all(
            "binance_symbol_snapshots",
            filters={"scan_id": f"eq.{scan_id}", "selected_canonical": "eq.true"},
            order="symbol.asc",
        )
        if not snapshots:
            raise RuntimeError("Source scan has no canonical symbol snapshot")
        universe_by_symbol = {str(row["symbol"]): row for row in snapshots}
        events_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            event["split"] = "discovery"
            events_by_symbol[str(event["symbol"])].append(event)
        all_symbols = sorted(universe_by_symbol)
        all_days = {
            scan_start + timedelta(days=offset)
            for offset in range((scan_end - scan_start).days)
        }

        self.db.update(
            "binance_chatgpt_export_jobs",
            {"id": f"eq.{job_id}"},
            {
                "events_total": len(events),
                "symbols_total": len(all_symbols),
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        load_start = scan_start - timedelta(days=prior_days + 1)
        load_end = scan_end + timedelta(days=1)
        work = Path(tempfile.mkdtemp(prefix=f"chatgpt-export-{job_id}-", dir=self.temp_root))
        staging = work / "staging"
        minute_dir = staging / "minute_data"
        minute_dir.mkdir(parents=True, exist_ok=True)
        dictionary_path = staging / "DATA_DICTIONARY.md"
        loader_path = staging / "analysis_loader.py"
        _write_data_dictionary(dictionary_path)
        _write_analysis_loader(loader_path)

        sample_rows: list[dict[str, Any]] = []
        source_manifest: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        rejections: Counter[str] = Counter()
        used_baselines: Counter[tuple[str, datetime]] = Counter()
        symbol_files: dict[str, Path] = {}
        symbol_audit: dict[str, dict[str, Any]] = {}
        failures = 0
        same_controls_created = 0
        background_created = 0
        minute_rows = 0

        try:
            for processed, symbol in enumerate(all_symbols, start=1):
                self._assert_active(job_id)
                symbol_info = universe_by_symbol[symbol]
                symbol_events = events_by_symbol.get(symbol, [])
                frames: list[pd.DataFrame] = []
                audit = {
                    "symbol": symbol,
                    "base_asset": symbol_info.get("base_asset"),
                    "quote_asset": symbol_info.get("quote_asset"),
                    "status": symbol_info.get("status"),
                    "stablecoin_like": bool(symbol_info.get("stablecoin_like")),
                    "leveraged_token_like": bool(symbol_info.get("leveraged_token_like")),
                    "event_count": len(symbol_events),
                    "same_coin_controls": 0,
                    "full_universe_backgrounds": 0,
                    "minute_file_exported": False,
                    "export_status": "pending",
                }
                try:
                    loaded = self.cache.load_symbol(symbol, load_start, load_end)
                    frame = loaded.frame
                    source_manifest.extend(loaded.source_manifest)
                    known_times: list[datetime] = []
                    for item in symbol_events:
                        known_times.extend([
                            parse_datetime(item["baseline_time"]),
                            parse_datetime(item.get("first_cross_time") or item["first_cross_trade_time"]),
                        ])

                    for event in symbol_events:
                        baseline = parse_datetime(event["baseline_time"])
                        cross = parse_datetime(event.get("first_cross_time") or event["first_cross_trade_time"])
                        valid, quality = _history_quality(frame, baseline, prior_days)
                        if not valid:
                            issues.append({
                                "chatgpt_export_job_id": job_id,
                                "symbol": symbol,
                                "stage": "event_history",
                                "message": f"{event['id']}: insufficient ten-day history",
                            })
                            continue
                        duration = int(event.get("minutes_baseline_open_to_cross_open") or max(1, (cross - baseline).total_seconds() // 60))
                        event_sample = {
                            "sample_id": str(event["id"]),
                            "match_group_id": str(event["id"]),
                            "event_id": str(event["id"]),
                            "control_id": None,
                            "control_rank": None,
                            "sample_type": "event",
                            "control_scope": "event",
                            "label": 1,
                            "split": "discovery",
                            "symbol": symbol,
                            "minute_data_file": f"minute_data/{safe_filename(symbol)}.parquet",
                            "base_asset": event.get("base_asset"),
                            "quote_asset": event.get("quote_asset"),
                            "baseline_time": baseline.isoformat(),
                            "cross_or_pseudo_cross_time": cross.isoformat(),
                            "event_duration_minutes": duration,
                            "event_duration_band": duration_band(duration),
                            "selected_baseline_duration_minutes": duration,
                            "selected_baseline_duration_band": duration_band(duration),
                            "outcome_maximum_future_8h_gain_pct": float(event.get("rolling_gain_pct_at_cross_trade") or threshold_pct),
                            "outcome_sellability_pass": bool(event.get("sellability_pass")),
                            "outcome_exit_vwap": event.get("exit_vwap"),
                            "outcome_exit_vwap_vs_threshold_pct": event.get("exit_vwap_vs_threshold_pct"),
                            "match_tier": "event",
                            "calendar_distance_days": 0,
                            "clock_offset_minutes": 0,
                            "duration_difference_minutes": 0,
                            **quality,
                        }
                        controls, rejected = select_local_low_controls_for_event(
                            event=event,
                            split="discovery",
                            split_dates=all_days,
                            frame=frame,
                            known_event_times=known_times,
                            controls_per_event=controls_per_event,
                            prior_days=prior_days,
                            min_entry_notional=0.0,
                            threshold_pct=threshold_pct,
                            window_minutes=window_minutes,
                            used_baselines=used_baselines,
                        )
                        rejections.update(rejected)
                        controls = [row for row in controls if int(row.get("prior_global_reuse_count") or 0) == 0]
                        samples = [event_sample]
                        for control in controls:
                            control_baseline = parse_datetime(control["baseline_time"])
                            _, control_quality = _history_quality(frame, control_baseline, prior_days)
                            samples.append({
                                "sample_id": control["sample_id"],
                                "match_group_id": control["match_group_id"],
                                "event_id": control["event_id"],
                                "control_id": control["control_id"],
                                "control_rank": control["control_rank"],
                                "sample_type": "same_coin_control",
                                "control_scope": "same_coin",
                                "label": 0,
                                "split": "discovery",
                                "symbol": symbol,
                                "minute_data_file": f"minute_data/{safe_filename(symbol)}.parquet",
                                "base_asset": control.get("base_asset"),
                                "quote_asset": control.get("quote_asset"),
                                "baseline_time": control["baseline_time"],
                                "cross_or_pseudo_cross_time": control["pseudo_cross_time"],
                                "event_duration_minutes": control["event_duration_minutes"],
                                "event_duration_band": control["event_duration_band"],
                                "selected_baseline_duration_minutes": control["selected_baseline_duration_minutes"],
                                "selected_baseline_duration_band": control["selected_baseline_duration_band"],
                                "outcome_maximum_future_8h_gain_pct": control["maximum_future_8h_gain_pct"],
                                "outcome_sellability_pass": False,
                                "outcome_exit_vwap": None,
                                "outcome_exit_vwap_vs_threshold_pct": None,
                                "match_tier": control["match_tier"],
                                "calendar_distance_days": control["calendar_distance_days"],
                                "clock_offset_minutes": control["clock_offset_minutes"],
                                "duration_difference_minutes": control["duration_difference_minutes"],
                                **control_quality,
                            })
                        if not controls:
                            issues.append({
                                "chatgpt_export_job_id": job_id,
                                "symbol": symbol,
                                "stage": "control_matching",
                                "message": f"{event['id']}: no scanner-equivalent same-coin controls; event retained for cross-universe analysis",
                            })
                        for sample in samples:
                            raw, raw_quality = extract_raw_window(
                                frame,
                                parse_datetime(sample["baseline_time"]),
                                prior_days=prior_days,
                                include_baseline_bar=include_baseline_bar,
                                sample_id=str(sample["sample_id"]),
                            )
                            sample.update(raw_quality)
                            sample_rows.append(sample)
                            frames.append(raw)
                        same_controls_created += len(controls)
                        audit["same_coin_controls"] += len(controls)

                    backgrounds, rejected = select_universe_background_samples(
                        symbol_info=symbol_info,
                        frame=frame,
                        scan_start=scan_start,
                        scan_end_exclusive=scan_end,
                        known_event_times=known_times,
                        prior_days=prior_days,
                        threshold_pct=threshold_pct,
                        window_minutes=window_minutes,
                        used_baselines=used_baselines,
                        count=BACKGROUND_SAMPLES_PER_SYMBOL,
                    )
                    rejections.update(rejected)
                    for sample in backgrounds:
                        raw, raw_quality = extract_raw_window(
                            frame,
                            parse_datetime(sample["baseline_time"]),
                            prior_days=prior_days,
                            include_baseline_bar=include_baseline_bar,
                            sample_id=str(sample["sample_id"]),
                        )
                        sample.update(raw_quality)
                        sample_rows.append(sample)
                        frames.append(raw)
                    background_created += len(backgrounds)
                    audit["full_universe_backgrounds"] = len(backgrounds)
                    if not backgrounds:
                        issues.append({
                            "chatgpt_export_job_id": job_id,
                            "symbol": symbol,
                            "stage": "full_universe_background",
                            "message": "No complete uncontaminated deterministic background window found",
                        })

                    if frames:
                        sample_windows = pd.concat(frames, ignore_index=True)
                        symbol_frame = (
                            sample_windows.drop(columns=["sample_id", "relative_minute"])
                            .sort_values("open_time")
                            .drop_duplicates("open_time", keep="last")
                            .reset_index(drop=True)
                        )
                        destination = minute_dir / f"{safe_filename(symbol)}.parquet"
                        symbol_frame.to_parquet(destination, index=False, compression="zstd")
                        symbol_files[symbol] = destination
                        minute_rows += len(symbol_frame)
                        audit["minute_file_exported"] = True
                    audit["export_status"] = "ok" if frames else "daily_only"
                except Exception as exc:
                    failures += 1
                    audit["export_status"] = "failed"
                    audit["error"] = str(exc)[:1000]
                    issues.append({
                        "chatgpt_export_job_id": job_id,
                        "symbol": symbol,
                        "stage": "symbol_export",
                        "message": str(exc)[:4000],
                    })
                symbol_audit[symbol] = audit
                self.db.update(
                    "binance_chatgpt_export_jobs",
                    {"id": f"eq.{job_id}"},
                    {
                        "symbols_processed": processed,
                        "samples_exported": len(sample_rows),
                        "controls_created": same_controls_created + background_created,
                        "minute_rows_exported": minute_rows,
                        "failures": failures,
                        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

            self._assert_active(job_id)
            samples_frame = pd.DataFrame(sample_rows)
            if samples_frame.empty:
                raise RuntimeError("No raw samples could be exported")

            reference_dir = work / "universe_reference"
            (reference_dir / "reference_data").mkdir(parents=True, exist_ok=True)
            for reference_symbol in REFERENCE_SYMBOLS:
                loaded = self.cache.load_symbol(reference_symbol, load_start, scan_end)
                source_manifest.extend(loaded.source_manifest)
                ref = loaded.frame.reset_index()
                ref.insert(0, "symbol", reference_symbol)
                ref = ref[["symbol", "open_time", *RAW_COLUMNS, "observed"]]
                ref.to_parquet(
                    reference_dir / "reference_data" / f"{reference_symbol}.parquet",
                    index=False,
                    compression="zstd",
                )

            daily_rows = self.db.select_all(
                "binance_daily_bars",
                filters={"scan_id": f"eq.{scan_id}"},
                order="symbol.asc,open_time.asc",
            )
            daily_frame = pd.DataFrame(daily_rows)
            if not daily_frame.empty:
                for column in (
                    "open", "high", "low", "close", "volume", "quote_volume",
                    "taker_buy_base_volume", "taker_buy_quote_volume",
                ):
                    if column in daily_frame:
                        daily_frame[column] = pd.to_numeric(daily_frame[column], errors="coerce")
                daily_frame.to_parquet(
                    reference_dir / "universe_daily_data.parquet",
                    index=False,
                    compression="zstd",
                )
            universe_frame = pd.DataFrame([symbol_audit[symbol] for symbol in all_symbols])
            universe_frame.to_csv(reference_dir / "universe_symbols.csv", index=False)
            (reference_dir / "README.md").write_text(
                "# Full-universe 2026 reference package\n\n"
                "Contains every canonical Binance Spot symbol from the source scan, full-universe daily bars, "
                "and raw BTC/ETH/BNB one-minute references. Symbols without a complete raw background window "
                "remain listed with their export status.\n",
                encoding="utf-8",
            )

            file_records: list[dict[str, Any]] = []
            checksums: list[dict[str, Any]] = []
            chunk_manifest: list[dict[str, Any]] = []
            chunks = _chunk_symbols(symbol_files, CHUNK_TARGET_BYTES)
            for part_number, symbols in enumerate(chunks, start=1):
                self._assert_active(job_id)
                zip_name = f"DISCOVERY_2026_SYMBOLS_PART_{part_number:03d}.zip"
                zip_path = work / zip_name
                chunk_meta = _write_symbol_chunk(
                    zip_path,
                    symbols=symbols,
                    symbol_files=symbol_files,
                    samples=samples_frame,
                    dictionary_path=dictionary_path,
                    loader_path=loader_path,
                    part_number=part_number,
                    total_parts=len(chunks),
                )
                storage_path = f"chatgpt-research/{job_id}/{zip_name}"
                self.db.upload_file(storage_path, zip_path, "application/zip")
                record = {
                    "chatgpt_export_job_id": job_id,
                    "storage_path": storage_path,
                    "filename": zip_name,
                    "size_bytes": zip_path.stat().st_size,
                    "sha256": sha256_file(zip_path),
                    "content_type": "application/zip",
                    "role": "neutral_full_universe_symbol_chunk",
                    "split": "discovery",
                }
                file_records.append(record)
                checksums.append({"filename": zip_name, "sha256": record["sha256"], "size_bytes": record["size_bytes"]})
                chunk_manifest.append(chunk_meta | {
                    "filename": zip_name,
                    "size_bytes": record["size_bytes"],
                    "first_symbol": symbols[0],
                    "last_symbol": symbols[-1],
                })
                zip_path.unlink(missing_ok=True)

            reference_zip = work / "DISCOVERY_2026_UNIVERSE_REFERENCE.zip"
            _zip_directory(reference_dir, reference_zip)
            reference_storage = f"chatgpt-research/{job_id}/{reference_zip.name}"
            self.db.upload_file(reference_storage, reference_zip, "application/zip")
            reference_record = {
                "chatgpt_export_job_id": job_id,
                "storage_path": reference_storage,
                "filename": reference_zip.name,
                "size_bytes": reference_zip.stat().st_size,
                "sha256": sha256_file(reference_zip),
                "content_type": "application/zip",
                "role": "neutral_full_universe_reference",
                "split": "discovery",
            }
            file_records.append(reference_record)
            checksums.append({"filename": reference_zip.name, "sha256": reference_record["sha256"], "size_bytes": reference_record["size_bytes"]})

            if issues:
                self.db.insert("binance_chatgpt_export_issues", issues)
            index_dir = work / "index"
            index_dir.mkdir()
            samples_frame.to_csv(index_dir / "all_samples.csv", index=False)
            universe_frame.to_csv(index_dir / "universe_symbols.csv", index=False)
            pd.DataFrame(chunk_manifest).to_csv(index_dir / "chunk_manifest.csv", index=False)
            manifest_frame = pd.DataFrame(source_manifest)
            if not manifest_frame.empty:
                dedupe_columns = [
                    column for column in ("symbol", "date", "period", "granularity", "source", "sha256")
                    if column in manifest_frame.columns
                ]
                if dedupe_columns:
                    manifest_frame = manifest_frame.drop_duplicates(subset=dedupe_columns, keep="last")
            manifest_frame.to_csv(index_dir / "source_manifest.csv", index=False)
            pd.DataFrame(issues).to_csv(index_dir / "issues.csv", index=False)
            pd.DataFrame(
                [{"rejection_reason": key, "count": value} for key, value in rejections.most_common()]
            ).to_csv(index_dir / "control_rejections.csv", index=False)
            pd.DataFrame(checksums).to_csv(index_dir / "package_checksums.csv", index=False)
            result = {
                "protocol_version": PROTOCOL_VERSION,
                "source_scan_id": scan_id,
                "source_window": {"start": scan_start.isoformat(), "end_exclusive": scan_end.isoformat()},
                "event_definition": "saleable >=50% rise within eight hours",
                "research_design": "neutral full-universe raw-data export for ChatGPT-led discovery",
                "canonical_symbols": len(all_symbols),
                "symbols_processed": len(all_symbols),
                "event_bearing_symbols": len(events_by_symbol),
                "non_event_symbols": len(all_symbols) - len(events_by_symbol),
                "events_source": len(events),
                "events_exported": int((samples_frame["label"] == 1).sum()),
                "same_coin_controls_created": same_controls_created,
                "full_universe_backgrounds_created": background_created,
                "controls_created": same_controls_created + background_created,
                "samples_exported": len(samples_frame),
                "minute_rows_exported": minute_rows,
                "symbol_chunk_count": len(chunks),
                "failures": failures,
                "hard_rule_status": "none; the app exports evidence only",
                "warning": "All 2026 evidence is exploratory discovery data.",
            }
            (index_dir / "research_index.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            (index_dir / "README.md").write_text(
                "# ChatGPT full-universe research index\n\n"
                "Upload this index, `DISCOVERY_2026_UNIVERSE_REFERENCE.zip`, and every "
                "`DISCOVERY_2026_SYMBOLS_PART_*.zip` file to ChatGPT. The app selected no predictor or rule.\n",
                encoding="utf-8",
            )
            index_zip = work / "CHATGPT_RESEARCH_INDEX.zip"
            _zip_directory(index_dir, index_zip)
            index_storage = f"chatgpt-research/{job_id}/{index_zip.name}"
            self.db.upload_file(index_storage, index_zip, "application/zip")
            index_record = {
                "chatgpt_export_job_id": job_id,
                "storage_path": index_storage,
                "filename": index_zip.name,
                "size_bytes": index_zip.stat().st_size,
                "sha256": sha256_file(index_zip),
                "content_type": "application/zip",
                "role": "neutral_research_index",
                "split": None,
            }
            file_records.append(index_record)
            self.db.upsert(
                "binance_chatgpt_export_files",
                file_records,
                on_conflict="chatgpt_export_job_id,storage_path",
            )
            result["index_storage_path"] = index_storage
            self._assert_active(job_id)
            shutil.rmtree(self.cache_root, ignore_errors=True)
            return result
        finally:
            shutil.rmtree(work, ignore_errors=True)
