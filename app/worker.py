from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from .binance import BinanceClient
from .config import Settings
from .research import ResearchBuilder
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
    for table in ("binance_scan_jobs", "binance_research_jobs"):
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
