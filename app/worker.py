from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from .binance import BinanceClient
from .config import Settings
from .research import ResearchBuilder
from .matched_controls import MatchedControlBuilder
from .context import TenDayContextBuilder
from .baseline_context import BaselineContextBuilder
from .confirmation import FreshConfirmationBuilder
from .backtest import ContinuousBacktestBuilder
from .chatgpt_export import ChatGPTResearchExporter
from .scanner import Scanner
from .supabase import SupabaseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _claim(db: SupabaseClient, table: str) -> dict | None:
    rows = db.select(table, filters={"status": "eq.queued"}, order="created_at.asc", limit=1)
    if not rows:
        return None
    row = rows[0]
    db.update(
        table,
        {"id": f"eq.{row['id']}", "status": "eq.queued"},
        {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error_message": None,
        },
    )
    fresh = db.select(table, filters={"id": f"eq.{row['id']}"}, limit=1)
    return fresh[0] if fresh and fresh[0]["status"] == "running" else None


def _recover_interrupted_jobs(db: SupabaseClient) -> None:
    """Requeue jobs left running by a worker restart; all writes are idempotent."""
    for table in ("binance_scan_jobs", "binance_research_jobs", "binance_matched_control_jobs", "binance_context_jobs", "binance_baseline_context_jobs", "binance_confirmation_jobs", "binance_backtest_jobs", "binance_chatgpt_export_jobs"):
        db.update(
            table,
            {"status": "eq.running"},
            {
                "status": "queued",
                "started_at": None,
                "heartbeat_at": None,
                "error_message": "Requeued automatically after worker restart",
            },
        )


def main() -> None:
    settings = Settings.from_env()
    db = SupabaseClient(settings.supabase_url, settings.supabase_service_role_key, settings.storage_bucket)
    binance = BinanceClient(settings.binance_api_base_urls)
    scanner = Scanner(db, binance)
    research = ResearchBuilder(db, binance, settings.temp_data_dir)
    matched_controls = MatchedControlBuilder(db, binance, settings.temp_data_dir)
    context_builder = TenDayContextBuilder(db, binance, settings.temp_data_dir)
    baseline_context_builder = BaselineContextBuilder(db, binance, settings.temp_data_dir)
    confirmation_builder = FreshConfirmationBuilder(db, binance, settings.temp_data_dir)
    backtest_builder = ContinuousBacktestBuilder(db, binance, settings.temp_data_dir)
    chatgpt_exporter = ChatGPTResearchExporter(db, binance, settings.temp_data_dir)
    _recover_interrupted_jobs(db)
    logger.info("Worker started; interrupted jobs recovered")
    while True:
        try:
            db.upsert(
                "binance_worker_heartbeats",
                [{"worker_name": "main", "heartbeat_at": datetime.now(timezone.utc).isoformat()}],
                on_conflict="worker_name",
            )
            scan_job = _claim(db, "binance_scan_jobs")
            if scan_job:
                job_id = scan_job["id"]
                try:
                    result = scanner.run(scan_job)
                    db.update(
                        "binance_scan_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "completed_with_warnings" if result["failures"] else "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "result_json": result,
                        },
                    )
                except Exception as exc:
                    logger.exception("Scan failed")
                    db.update(
                        "binance_scan_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "failed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": str(exc)[:4000],
                        },
                    )
                continue


            matched_job = _claim(db, "binance_matched_control_jobs")
            if matched_job:
                job_id = matched_job["id"]
                try:
                    result = matched_controls.run(matched_job)
                    has_warnings = (
                        result["failures"] > 0
                        or result["controls_created"] < result["controls_target"]
                        or result.get("quality_report", {}).get("event_entry_liquidity_failures", 0) > 0
                    )
                    db.update(
                        "binance_matched_control_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "completed_with_warnings" if has_warnings else "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "events_processed": result["events_processed"],
                            "controls_created": result["controls_created"],
                            "feature_rows": result["feature_rows"],
                            "failures": result["failures"],
                            "result_json": result,
                        },
                    )
                except Exception as exc:
                    logger.exception("Matched-control job failed")
                    db.update(
                        "binance_matched_control_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "failed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": str(exc)[:4000],
                        },
                    )
                continue

            context_job = _claim(db, "binance_context_jobs")
            if context_job:
                job_id = context_job["id"]
                try:
                    result = context_builder.run(context_job)
                    has_warnings = result.get("failures", 0) > 0 or any(
                        key != "pass" and value
                        for key, value in (result.get("quality_report", {}).get("quality_counts", {}) or {}).items()
                    )
                    db.update(
                        "binance_context_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "completed_with_warnings" if has_warnings else "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "samples_processed": result["samples_processed"],
                            "feature_rows": result["feature_rows"],
                            "failures": result["failures"],
                            "result_json": result,
                        },
                    )
                except Exception as exc:
                    logger.exception("Ten-day context job failed")
                    db.update(
                        "binance_context_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "failed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": str(exc)[:4000],
                        },
                    )
                continue

            baseline_context_job = _claim(db, "binance_baseline_context_jobs")
            if baseline_context_job:
                job_id = baseline_context_job["id"]
                try:
                    result = baseline_context_builder.run(baseline_context_job)
                    has_warnings = result.get("failures", 0) > 0 or any(
                        key != "pass" and value
                        for key, value in (result.get("quality_report", {}).get("quality_counts", {}) or {}).items()
                    ) or result.get("quality_report", {}).get("contaminated_controls", 0) > 0
                    db.update(
                        "binance_baseline_context_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "completed_with_warnings" if has_warnings else "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "samples_processed": result["samples_processed"],
                            "feature_rows": result["feature_rows"],
                            "continuation_rows": result["continuation_rows"],
                            "failures": result["failures"],
                            "result_json": result,
                        },
                    )
                except Exception as exc:
                    logger.exception("Baseline-aligned context job failed")
                    db.update(
                        "binance_baseline_context_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "failed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": str(exc)[:4000],
                        },
                    )
                continue

            confirmation_job = _claim(db, "binance_confirmation_jobs")
            if confirmation_job:
                job_id = confirmation_job["id"]
                try:
                    result = confirmation_builder.run(confirmation_job)
                    db.update(
                        "binance_confirmation_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "passed": result["passed"],
                            "events_evaluable": result["events_evaluable"],
                            "controls_evaluable": result["controls_evaluable"],
                            "event_hits": result["event_hits"],
                            "control_hits": result["control_hits"],
                            "event_rate": result["event_rate"],
                            "control_rate": result["control_rate"],
                            "matched_permutation_p": result["matched_permutation_p"],
                            "unique_event_symbols_hit": result["unique_event_symbols_hit"],
                            "cluster_rr_ci_low": result.get("cluster_rr_ci_low"),
                            "cluster_rr_ci_high": result.get("cluster_rr_ci_high"),
                            "duration_bands_positive": result.get("duration_bands_positive", 0),
                            "controls_created": result.get("controls_created", result.get("controls_evaluable", 0)),
                            "symbols_processed": result.get("symbols_processed", 0),
                            "failures": result.get("failures", 0),
                            "result_json": result,
                        },
                    )
                except Exception as exc:
                    logger.exception("Fresh confirmation job failed")
                    db.update(
                        "binance_confirmation_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "failed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": str(exc)[:4000],
                        },
                    )
                continue

            chatgpt_export_job = _claim(db, "binance_chatgpt_export_jobs")
            if chatgpt_export_job:
                job_id = chatgpt_export_job["id"]
                try:
                    result = chatgpt_exporter.run(chatgpt_export_job)
                    db.update(
                        "binance_chatgpt_export_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "completed_with_warnings" if result.get("failures", 0) else "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "symbols_processed": result["symbols_processed"],
                            "samples_exported": result["samples_exported"],
                            "controls_created": result["controls_created"],
                            "minute_rows_exported": result["minute_rows_exported"],
                            "failures": result["failures"],
                            "result_json": result,
                        },
                    )
                except Exception as exc:
                    logger.exception("ChatGPT research-export job failed")
                    db.update(
                        "binance_chatgpt_export_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "failed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": str(exc)[:4000],
                        },
                    )
                continue

            backtest_job = _claim(db, "binance_backtest_jobs")
            if backtest_job:
                job_id = backtest_job["id"]
                try:
                    result = backtest_builder.run(backtest_job)
                    db.update(
                        "binance_backtest_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "completed_with_warnings" if result.get("failures", 0) else "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "symbols_processed": result["symbols_processed"],
                            "candidate_signals": result["candidate_signals"],
                            "completed_trades": result["completed_trades"],
                            "failures": result["failures"],
                            "result_json": result,
                        },
                    )
                except Exception as exc:
                    logger.exception("Continuous backtest job failed")
                    db.update(
                        "binance_backtest_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "failed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": str(exc)[:4000],
                        },
                    )
                continue

            research_job = _claim(db, "binance_research_jobs")
            if research_job:
                job_id = research_job["id"]
                try:
                    result = research.run(research_job)
                    db.update(
                        "binance_research_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "completed_with_warnings" if result["events_failed"] else "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "result_json": result,
                        },
                    )
                except Exception as exc:
                    logger.exception("Research job failed")
                    db.update(
                        "binance_research_jobs",
                        {"id": f"eq.{job_id}"},
                        {
                            "status": "failed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": str(exc)[:4000],
                        },
                    )
                continue
        except Exception:
            logger.exception("Worker loop error")
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
