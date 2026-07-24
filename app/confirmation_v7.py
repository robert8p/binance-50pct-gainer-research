from __future__ import annotations

import io
import json
import math
import shutil
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .binance import sha256_file
from .supabase import SupabaseClient

H1_COLUMN = "hypothesis_h1_weak_base_ignition"
FROZEN_ACCEPTANCE: dict[str, Any] = {
    "version": "v7_h1_8h_fresh_confirmation_1",
    "primary_population": "baseline offset 0; feature_quality_status=pass; entry_liquidity_pass=true; uncontaminated controls",
    "minimum_evaluable_events": 15,
    "minimum_event_signal_rate": 0.25,
    "maximum_control_signal_rate": 0.15,
    "minimum_event_to_control_rate_ratio": 2.0,
    "maximum_matched_permutation_p": 0.05,
    "minimum_unique_event_symbols_hit": 5,
    "sealed_split_must_have_event_rate_above_control_rate": True,
    "threshold_retuning_permitted": False,
}


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    text = series.astype(str).str.strip().str.lower()
    return text.map({"true": True, "false": False, "1": True, "0": False}).astype("boolean")


def _load_csv_from_zip(path: Path, member: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        match = next((name for name in names if name.endswith(member)), None)
        if not match:
            raise ValueError(f"{path.name} does not contain {member}")
        with archive.open(match) as handle:
            return pd.read_csv(handle)


def _matched_permutation_p(frame: pd.DataFrame, *, iterations: int = 100_000, seed: int = 560601) -> float | None:
    """Randomise the one event label within each matched set and compare rate gaps."""
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


class FreshConfirmationBuilderV7:
    def __init__(self, db: SupabaseClient, temp_root: Path):
        self.db = db
        self.temp_root = temp_root

    def _source_files(self, baseline_context_job_id: str) -> dict[str, dict[str, Any]]:
        rows = self.db.select_all(
            "binance_baseline_context_files",
            filters={"baseline_context_job_id": f"eq.{baseline_context_job_id}"},
            order="created_at.asc",
        )
        by_split: dict[str, dict[str, Any]] = {}
        for row in rows:
            split = row.get("split")
            if split in {"discovery", "validation", "sealed_test"} and str(row.get("role", "")).startswith("baseline_context_"):
                by_split[str(split)] = row
        missing = {"discovery", "validation", "sealed_test"} - set(by_split)
        if missing:
            raise ValueError(f"Fresh staged baseline packages missing: {sorted(missing)}")
        return by_split

    def run(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job["id"])
        if str(job.get("protocol_version") or FROZEN_ACCEPTANCE["version"]) != FROZEN_ACCEPTANCE["version"]:
            raise ValueError("Confirmation protocol does not match the frozen V7 eight-hour protocol")
        source_id = str(job["baseline_context_job_id"])
        source_rows = self.db.select(
            "binance_baseline_context_jobs",
            filters={"id": f"eq.{source_id}"},
            limit=1,
        )
        if not source_rows:
            raise ValueError("Source baseline-context job not found")
        source_job = source_rows[0]
        if source_job.get("status") not in {"completed", "completed_with_warnings"}:
            raise ValueError("Source baseline-context job is not complete")
        if source_job.get("research_mode") != "fresh_staged":
            raise ValueError("Confirmation requires a fresh_staged baseline-context job")
        matched_rows = self.db.select(
            "binance_matched_control_jobs",
            filters={"id": f"eq.{source_job['matched_control_job_id']}"},
            limit=1,
        )
        if not matched_rows:
            raise ValueError("Source matched-control job not found")
        scan_rows = self.db.select(
            "binance_scan_jobs",
            filters={"id": f"eq.{matched_rows[0]['scan_id']}"},
            limit=1,
        )
        if not scan_rows or scan_rows[0].get("event_definition_version") != "v7_rolling_8h" or int(scan_rows[0].get("window_minutes") or 0) != 480:
            raise ValueError("V7 confirmation requires baseline context derived from a 480-minute v7_rolling_8h scan")

        work = Path(tempfile.mkdtemp(prefix=f"confirmation-{job_id}-", dir=self.temp_root))
        try:
            source_files = self._source_files(source_id)
            frames: list[pd.DataFrame] = []
            manifest: list[dict[str, Any]] = []
            for split in ("discovery", "validation", "sealed_test"):
                record = source_files[split]
                local = work / str(record["filename"])
                self.db.download_file(str(record["storage_path"]), local)
                actual_sha = sha256_file(local)
                expected_sha = str(record["sha256"])
                if actual_sha != expected_sha:
                    raise ValueError(f"Source checksum mismatch for {record['filename']}")
                frame = _load_csv_from_zip(local, "baseline_context_features.csv")
                frame["split"] = split
                frames.append(frame)
                manifest.append({
                    "split": split,
                    "filename": record["filename"],
                    "storage_path": record["storage_path"],
                    "sha256": actual_sha,
                    "rows": int(len(frame)),
                })

            raw = pd.concat(frames, ignore_index=True)
            required = {
                "baseline_snapshot_offset_minutes", "feature_quality_status", "entry_liquidity_pass",
                "pseudo_window_contaminated_control", "label", "symbol", "match_group_id", H1_COLUMN,
            }
            missing_columns = required - set(raw.columns)
            if missing_columns:
                raise ValueError(f"Source features missing columns: {sorted(missing_columns)}")

            raw["entry_liquidity_pass"] = _bool_series(raw["entry_liquidity_pass"])
            raw["pseudo_window_contaminated_control"] = _bool_series(raw["pseudo_window_contaminated_control"]).fillna(False)
            raw[H1_COLUMN] = _bool_series(raw[H1_COLUMN])
            population = raw[
                (pd.to_numeric(raw["baseline_snapshot_offset_minutes"], errors="coerce") == 0)
                & (raw["feature_quality_status"].astype(str) == "pass")
                & (raw["entry_liquidity_pass"] == True)
                & (~raw["pseudo_window_contaminated_control"].astype(bool))
                & raw[H1_COLUMN].notna()
            ].copy()
            population["label"] = pd.to_numeric(population["label"], errors="raise").astype(int)
            population["signal"] = population[H1_COLUMN].astype(bool)

            results = [_evaluate(population, split) for split in ("discovery", "validation", "sealed_test", "overall")]
            overall = next(row for row in results if row["split"] == "overall")
            sealed = next(row for row in results if row["split"] == "sealed_test")
            checks = {
                "minimum_evaluable_events": overall["events"] >= FROZEN_ACCEPTANCE["minimum_evaluable_events"],
                "minimum_event_signal_rate": (overall["event_rate"] or 0) >= FROZEN_ACCEPTANCE["minimum_event_signal_rate"],
                "maximum_control_signal_rate": (overall["control_rate"] if overall["control_rate"] is not None else 1) <= FROZEN_ACCEPTANCE["maximum_control_signal_rate"],
                "minimum_event_to_control_rate_ratio": (overall["event_to_control_rate_ratio"] or 0) >= FROZEN_ACCEPTANCE["minimum_event_to_control_rate_ratio"],
                "maximum_matched_permutation_p": (overall["matched_permutation_p"] if overall["matched_permutation_p"] is not None else 1) <= FROZEN_ACCEPTANCE["maximum_matched_permutation_p"],
                "minimum_unique_event_symbols_hit": overall["unique_event_symbols_hit"] >= FROZEN_ACCEPTANCE["minimum_unique_event_symbols_hit"],
                "sealed_direction": (
                    sealed["event_rate"] is not None and sealed["control_rate"] is not None
                    and sealed["event_rate"] > sealed["control_rate"]
                ),
            }
            passed = bool(all(checks.values()))

            results_df = pd.DataFrame(results)
            results_df.to_csv(work / "fresh_confirmation_results.csv", index=False)
            population.to_csv(work / "fresh_confirmation_population.csv", index=False)
            pd.DataFrame(manifest).to_csv(work / "source_manifest.csv", index=False)
            decision = {
                "protocol": FROZEN_ACCEPTANCE,
                "checks": checks,
                "passed": passed,
                "backtest_unlocked": passed,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "source_baseline_context_job_id": source_id,
                "warning": "The software opened all three source splits automatically only after the rule and criteria were frozen in code.",
            }
            (work / "confirmation_decision.json").write_text(json.dumps(decision, indent=2, default=str), encoding="utf-8")
            (work / "README.md").write_text(
                "# Fresh H1 confirmation for the eight-hour surge target\n\n"
                f"Decision: **{'PASS — continuous sealed backtest unlocked' if passed else 'FAIL — do not run the trading backtest'}**.\n\n"
                "H1 thresholds and acceptance criteria were frozen before source packages were downloaded. No retuning is performed.\n",
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
                "role": "fresh_confirmation_results",
            }
            self.db.upsert("binance_confirmation_files", [record], on_conflict="confirmation_job_id,storage_path")
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
                "checks": checks,
                "storage_path": storage_path,
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)
