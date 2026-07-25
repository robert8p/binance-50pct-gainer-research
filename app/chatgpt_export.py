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
from .confirmation import duration_band, select_local_low_controls_for_event
from .matched_controls import (
    REFERENCE_SYMBOLS,
    SPLITS,
    assign_temporal_splits,
    floor_minute,
    parse_datetime,
)
from .supabase import SupabaseClient

PROTOCOL_VERSION = "v10_2026_discovery_export_1"
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
    """Return an ASCII-safe, deterministic filename stem.

    Binance symbols can contain non-Latin characters. Supabase object paths and
    downstream ZIP tooling are more reliable when paths remain ASCII-only.
    """
    cleaned = "".join(ch if ch.isascii() and ch.isalnum() else "_" for ch in value)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    if cleaned:
        return cleaned[:80]
    return f"symbol_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


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
One row per event or algorithmically matched non-event sample. `label=1` identifies a saleable >=50% eight-hour event; `label=0` identifies a same-coin control selected with the same rolling-local-low procedure.

## minute_data/*.parquet
Raw Binance one-minute kline fields stored once per physical symbol/time. Use `symbol`, `history_start`, `history_end` and `baseline_time` from samples.csv to reconstruct each labelled ten-day window. No missing values are imputed.

Columns: open_time, open, high, low, close, base volume, quote volume, trade count, taker-buy base volume, taker-buy quote volume, and observed.

## analysis_loader.py
A neutral helper that reconstructs one labelled sample window from samples.csv and the deduplicated symbol Parquet file. It creates no predictive features.

## reference_data/*.parquet
Raw one-minute BTCUSDT, ETHUSDT and BNBUSDT data covering the 2026 discovery period. These are provided for ChatGPT to construct market-relative patterns without the app deciding how to combine them.

## Integrity rules
Event and control baselines use the same 480-minute rolling-minimum algorithm. Controls are rejected when the selected low subsequently gains 50% within eight hours or lies within 24 hours of a known event. All 2026 samples are exported as exploratory discovery evidence. Fresh validation and sealed periods are not created from this opened year.
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


class ChatGPTResearchExporter:
    def __init__(self, db: SupabaseClient, binance: BinanceClient, temp_root: Path):
        self.db = db
        self.binance = binance
        self.temp_root = temp_root
        self.cache_root = temp_root / "chatgpt-export-cache"
        self.cache = BacktestMinuteArchiveCache(binance, self.cache_root)

    def run(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job["id"])
        if str(job.get("protocol_version") or PROTOCOL_VERSION) != PROTOCOL_VERSION:
            raise ValueError("Unsupported neutral research-export protocol")
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
            raise ValueError("V10.1 discovery export is frozen to 2026-01-01 through 2026-07-25 exclusive")

        controls_per_event = int(job.get("controls_per_event") or 5)
        prior_days = int(job.get("prior_days") or 10)
        discovery_pct = int(job.get("discovery_pct") or 60)
        validation_pct = int(job.get("validation_pct") or 20)
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
        # All 2026 evidence is exploratory because portions of the year have already
        # been inspected in earlier research rounds. Do not manufacture validation
        # or sealed evidence from an opened period.
        split_map = {date.fromisoformat(str(event["event_date"])): "discovery" for event in events}
        all_days: set[date] = set()
        day_cursor = scan_start
        while day_cursor < scan_end:
            all_days.add(day_cursor)
            day_cursor += timedelta(days=1)
        split_dates = {"discovery": all_days}
        split_summary = [{
            "split": "discovery",
            "events": len(events),
            "warning": "Exploratory 2026 evidence only; not untouched validation.",
        }]
        for event in events:
            event["split"] = "discovery"

        load_start = scan_start - timedelta(days=prior_days + 1)
        load_end = scan_end + timedelta(days=1)
        events_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            events_by_symbol[str(event["symbol"])].append(event)

        self.db.update(
            "binance_chatgpt_export_jobs",
            {"id": f"eq.{job_id}"},
            {
                "events_total": len(events),
                "symbols_total": len(events_by_symbol),
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        work = Path(tempfile.mkdtemp(prefix=f"chatgpt-export-{job_id}-", dir=self.temp_root))
        split_dirs = {split: work / split for split in EXPORT_SPLITS}
        for split, folder in split_dirs.items():
            (folder / "minute_data").mkdir(parents=True, exist_ok=True)
            (folder / "reference_data").mkdir(parents=True, exist_ok=True)
            _write_data_dictionary(folder / "DATA_DICTIONARY.md")
            _write_analysis_loader(folder / "analysis_loader.py")

        sample_rows: dict[str, list[dict[str, Any]]] = {split: [] for split in EXPORT_SPLITS}
        source_manifest: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        rejections: Counter[str] = Counter()
        used_baselines: Counter[tuple[str, datetime]] = Counter()
        split_ranges: dict[str, list[datetime]] = {split: [] for split in EXPORT_SPLITS}
        failures = 0
        controls_created = 0
        minute_rows = 0

        try:
            processed = 0
            for symbol, symbol_events in sorted(events_by_symbol.items()):
                per_split_frames: dict[str, list[pd.DataFrame]] = {split: [] for split in EXPORT_SPLITS}
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
                        split = str(event["split"])
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
                            "label": 1,
                            "split": split,
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
                            split=split,
                            split_dates=split_dates[split],
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
                        # Never reuse one control baseline across matched groups in the research export.
                        controls = [row for row in controls if int(row.get("prior_global_reuse_count") or 0) == 0]
                        if not controls:
                            issues.append({
                                "chatgpt_export_job_id": job_id,
                                "symbol": symbol,
                                "stage": "control_matching",
                                "message": f"{event['id']}: no scanner-equivalent controls",
                            })
                            continue

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
                                "sample_type": "control",
                                "label": 0,
                                "split": split,
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
                        # Keep the event only when at least one valid control exists.
                        for sample in samples:
                            baseline_value = parse_datetime(sample["baseline_time"])
                            raw, raw_quality = extract_raw_window(
                                frame,
                                baseline_value,
                                prior_days=prior_days,
                                include_baseline_bar=include_baseline_bar,
                                sample_id=str(sample["sample_id"]),
                            )
                            sample.update(raw_quality)
                            sample_rows[split].append(sample)
                            per_split_frames[split].append(raw)
                            split_ranges[split].extend([parse_datetime(raw_quality["history_start"]), parse_datetime(raw_quality["history_end"])])
                        controls_created += len(controls)

                    for split, frames in per_split_frames.items():
                        if not frames:
                            continue
                        sample_windows = pd.concat(frames, ignore_index=True)
                        # Store each physical market minute once. samples.csv contains the
                        # history bounds needed to reconstruct every labelled sample.
                        symbol_frame = (
                            sample_windows.drop(columns=["sample_id", "relative_minute"])
                            .sort_values("open_time")
                            .drop_duplicates("open_time", keep="last")
                            .reset_index(drop=True)
                        )
                        destination = split_dirs[split] / "minute_data" / f"{safe_filename(symbol)}.parquet"
                        symbol_frame.to_parquet(destination, index=False, compression="zstd")
                        minute_rows += len(symbol_frame)
                except Exception as exc:
                    failures += 1
                    issues.append({
                        "chatgpt_export_job_id": job_id,
                        "symbol": symbol,
                        "stage": "symbol_export",
                        "message": str(exc)[:4000],
                    })
                processed += 1
                self.db.update(
                    "binance_chatgpt_export_jobs",
                    {"id": f"eq.{job_id}"},
                    {
                        "symbols_processed": processed,
                        "samples_exported": sum(len(rows) for rows in sample_rows.values()),
                        "controls_created": controls_created,
                        "minute_rows_exported": minute_rows,
                        "failures": failures,
                        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

            # Export independent raw market references for each chronological split.
            for split in EXPORT_SPLITS:
                if not split_ranges[split]:
                    continue
                ref_start = min(split_ranges[split]).date()
                ref_end = max(split_ranges[split]).date() + timedelta(days=1)
                for reference_symbol in REFERENCE_SYMBOLS:
                    try:
                        loaded = self.cache.load_symbol(reference_symbol, ref_start, ref_end)
                        source_manifest.extend(loaded.source_manifest)
                        ref = loaded.frame.reset_index()
                        ref.insert(0, "symbol", reference_symbol)
                        ref = ref[["symbol", "open_time", *RAW_COLUMNS, "observed"]]
                        destination = split_dirs[split] / "reference_data" / f"{reference_symbol}.parquet"
                        ref.to_parquet(destination, index=False, compression="zstd")
                    except Exception as exc:
                        failures += 1
                        issues.append({
                            "chatgpt_export_job_id": job_id,
                            "symbol": reference_symbol,
                            "stage": f"{split}_reference_export",
                            "message": str(exc)[:4000],
                        })

            if issues:
                self.db.insert("binance_chatgpt_export_issues", issues)

            file_records: list[dict[str, Any]] = []
            checksums: list[dict[str, Any]] = []
            split_output_names = {
                "discovery": "DISCOVERY_2026_UPLOAD_TO_CHATGPT.zip",
            }
            split_summaries: list[dict[str, Any]] = []
            for split in EXPORT_SPLITS:
                folder = split_dirs[split]
                rows = sample_rows[split]
                samples_frame = pd.DataFrame(rows)
                samples_frame.to_csv(folder / "samples.csv", index=False)
                metadata = {
                    "protocol_version": PROTOCOL_VERSION,
                    "split": split,
                    "source_scan_id": scan_id,
                    "event_definition": ">=50% low-to-later-high rise within 480 minutes; saleability proven",
                    "controls": "same symbol, same 2026 discovery pool, same scanner-equivalent local-low algorithm, no future 50% contamination",
                    "prior_days": prior_days,
                    "include_baseline_bar": include_baseline_bar,
                    "samples": len(rows),
                    "events": sum(1 for row in rows if row["label"] == 1),
                    "controls": sum(1 for row in rows if row["label"] == 0),
                    "warning": (
                        "This entire 2026 package is exploratory discovery evidence. "
                        "Fresh validation and sealed evidence must be collected from separate periods."
                    ),
                }
                (folder / "split_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                (folder / "README.md").write_text(
                    "# 2026 exploratory discovery evidence package\n\n"
                    "This package contains raw one-minute evidence and sample labels. The app has not selected a predictor or trading rule.\n\n"
                    "Upload this package to ChatGPT for blank-canvas discovery. It is exploratory only; do not use it as untouched validation.\n",
                    encoding="utf-8",
                )
                zip_name = split_output_names[split]
                zip_path = work / zip_name
                _zip_directory(folder, zip_path)
                storage_path = f"chatgpt-research/{job_id}/{zip_name}"
                self.db.upload_file(storage_path, zip_path, "application/zip")
                record = {
                    "chatgpt_export_job_id": job_id,
                    "storage_path": storage_path,
                    "filename": zip_name,
                    "size_bytes": zip_path.stat().st_size,
                    "sha256": sha256_file(zip_path),
                    "content_type": "application/zip",
                    "role": f"neutral_raw_{split}",
                    "split": split,
                }
                file_records.append(record)
                checksums.append({"filename": zip_name, "sha256": record["sha256"], "size_bytes": record["size_bytes"]})
                split_summaries.append(metadata | {"filename": zip_name, "size_bytes": zip_path.stat().st_size})

            index_dir = work / "index"
            index_dir.mkdir()
            pd.DataFrame(split_summaries).to_csv(index_dir / "split_summary.csv", index=False)
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
            (index_dir / "research_index.json").write_text(json.dumps({
                "protocol_version": PROTOCOL_VERSION,
                "source_scan_id": scan_id,
                "source_window": {"start": scan_start.isoformat(), "end_exclusive": scan_end.isoformat()},
                "event_definition": "saleable >=50% rise within eight hours",
                "research_design": "neutral raw-data export for ChatGPT-led pattern discovery",
                "events_source": len(events),
                "samples_exported": sum(len(rows) for rows in sample_rows.values()),
                "controls_created": controls_created,
                "minute_rows_exported": minute_rows,
                "failures": failures,
                "split_summary": split_summaries,
                "hard_rule_status": "none; the app exports evidence only",
            }, indent=2), encoding="utf-8")
            (index_dir / "README.md").write_text(
                "# ChatGPT research export index\n\n"
                "Download `DISCOVERY_2026_UPLOAD_TO_CHATGPT.zip` and upload it to ChatGPT together with this index. "
                "All 2026 evidence is exploratory; fresh validation and sealed evidence will be collected separately.\n",
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
            result = {
                "events_source": len(events),
                "samples_exported": sum(len(rows) for rows in sample_rows.values()),
                "controls_created": controls_created,
                "minute_rows_exported": minute_rows,
                "symbols_processed": len(events_by_symbol),
                "failures": failures,
                "split_summary": split_summaries,
                "index_storage_path": index_storage,
            }
            # The official archives are only a resumable cache. Supabase contains
            # the durable packages, so remove V10's private cache after success.
            shutil.rmtree(self.cache_root, ignore_errors=True)
            return result
        finally:
            shutil.rmtree(work, ignore_errors=True)
