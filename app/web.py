from __future__ import annotations

import base64
import csv
import io
import uuid
from datetime import date, datetime, timezone
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from .config import Settings
from .supabase import SupabaseClient

settings = Settings.from_env()
db = SupabaseClient(settings.supabase_url, settings.supabase_service_role_key, settings.storage_bucket)
app = FastAPI(title="Binance 8-Hour 50% Surge Research", version="7.0.0")
templates = Jinja2Templates(directory="app/templates")


def _auth(request: Request) -> None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
    try:
        username, password = base64.b64decode(header[6:]).decode().split(":", 1)
    except Exception as exc:
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"}) from exc
    if username != "rob" or password != settings.app_password:
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "7.0.0"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    _auth(request)
    scans = db.select("binance_scan_jobs", order="created_at.desc", limit=25)
    research = db.select("binance_research_jobs", order="created_at.desc", limit=25)
    matched_jobs = db.select("binance_matched_control_jobs", order="created_at.desc", limit=25)
    context_jobs = db.select("binance_context_jobs", order="created_at.desc", limit=25)
    baseline_context_jobs = db.select("binance_baseline_context_jobs", order="created_at.desc", limit=25)
    confirmation_jobs = db.select("binance_confirmation_jobs", order="created_at.desc", limit=25)
    backtest_jobs = db.select("binance_backtest_jobs", order="created_at.desc", limit=25)
    heartbeat = db.select("binance_worker_heartbeats", filters={"worker_name": "eq.main"}, limit=1)
    files = db.select("binance_research_files", order="created_at.desc", limit=100)
    matched_files = db.select("binance_matched_control_files", order="created_at.desc", limit=100)
    context_files = db.select("binance_context_files", order="created_at.desc", limit=100)
    baseline_context_files = db.select("binance_baseline_context_files", order="created_at.desc", limit=100)
    confirmation_files = db.select("binance_confirmation_files", order="created_at.desc", limit=100)
    backtest_files = db.select("binance_backtest_files", order="created_at.desc", limit=100)
    completed_scans = [
        x for x in scans
        if x["status"] in {"completed", "completed_with_warnings"}
        and x.get("event_definition_version") == "v7_rolling_8h"
        and int(x.get("window_minutes") or 0) == 480
    ]
    v7_scan_ids = {str(x["id"]) for x in completed_scans}
    completed_matched_jobs = [
        x for x in matched_jobs
        if x["status"] in {"completed", "completed_with_warnings"}
        and str(x.get("scan_id")) in v7_scan_ids
    ]
    v7_matched_ids = {str(x["id"]) for x in completed_matched_jobs}
    completed_fresh_baseline_jobs = [
        x for x in baseline_context_jobs
        if x["status"] in {"completed", "completed_with_warnings"}
        and x.get("research_mode") == "fresh_staged"
        and str(x.get("matched_control_job_id")) in v7_matched_ids
    ]
    v7_baseline_ids = {str(x["id"]) for x in completed_fresh_baseline_jobs}
    passed_confirmation_jobs = [
        x for x in confirmation_jobs
        if x.get("status") == "completed"
        and bool(x.get("passed"))
        and x.get("protocol_version") == "v7_h1_8h_fresh_confirmation_1"
        and str(x.get("baseline_context_job_id")) in v7_baseline_ids
    ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "scans": scans,
            "research_jobs": research,
            "matched_jobs": matched_jobs,
            "context_jobs": context_jobs,
            "baseline_context_jobs": baseline_context_jobs,
            "confirmation_jobs": confirmation_jobs,
            "backtest_jobs": backtest_jobs,
            "completed_fresh_baseline_jobs": completed_fresh_baseline_jobs,
            "passed_confirmation_jobs": passed_confirmation_jobs,
            "completed_matched_jobs": completed_matched_jobs,
            "completed_scans": completed_scans,
            "heartbeat": heartbeat[0] if heartbeat else None,
            "files": files,
            "matched_files": matched_files,
            "context_files": context_files,
            "baseline_context_files": baseline_context_files,
            "confirmation_files": confirmation_files,
            "backtest_files": backtest_files,
        },
    )


@app.post("/scans")
def create_scan(
    request: Request,
    lookback_days: int = Form(60),
    threshold_pct: float = Form(50),
    quote_assets: str = Form("USDT,USDC,FDUSD"),
    min_exit_notional: float = Form(500),
    confirmation_window_seconds: int = Form(300),
    window_start_date: str = Form(""),
    window_end_date_exclusive: str = Form(""),
) -> RedirectResponse:
    _auth(request)
    if not 1 <= lookback_days <= 180:
        raise HTTPException(400, "lookback_days must be between 1 and 180")
    start_value = window_start_date.strip() or None
    end_value = window_end_date_exclusive.strip() or None
    if bool(start_value) != bool(end_value):
        raise HTTPException(400, "Enter both historical start and end dates, or leave both blank")
    if start_value and end_value:
        try:
            start_day = date.fromisoformat(start_value)
            end_day = date.fromisoformat(end_value)
        except ValueError as exc:
            raise HTTPException(400, "Historical dates must use YYYY-MM-DD") from exc
        span = (end_day - start_day).days
        if not 1 <= span <= 180:
            raise HTTPException(400, "Historical window must contain 1 to 180 completed UTC days")
        if end_day > datetime.now(timezone.utc).date():
            raise HTTPException(400, "Historical end cannot be after today")
    if threshold_pct <= 0:
        raise HTTPException(400, "threshold_pct must be positive")
    quotes = [x.strip().upper() for x in quote_assets.split(",") if x.strip()]
    db.insert(
        "binance_scan_jobs",
        {
            "id": str(uuid.uuid4()),
            "status": "queued",
            "event_definition_version": "v7_rolling_8h",
            "lookback_days": lookback_days,
            "threshold_pct": threshold_pct,
            "window_minutes": 480,
            "quote_assets": quotes,
            "min_exit_notional": min_exit_notional,
            "confirmation_window_seconds": confirmation_window_seconds,
            "window_start_date": start_value,
            "window_end_date_exclusive": end_value,
        },
    )
    return RedirectResponse("/", status_code=303)


@app.post("/research")
def create_research(
    request: Request,
    scan_id: str = Form(...),
    prior_days: int = Form(10),
    maximum_events: int = Form(1),
    include_1s_klines: bool = Form(False),
    include_agg_trades: bool = Form(False),
    include_raw_trades: bool = Form(False),
) -> RedirectResponse:
    _auth(request)
    if not 1 <= prior_days <= 30:
        raise HTTPException(400, "prior_days must be between 1 and 30")
    db.insert(
        "binance_research_jobs",
        {
            "id": str(uuid.uuid4()),
            "scan_id": scan_id,
            "status": "queued",
            "prior_days": prior_days,
            "maximum_events": max(0, maximum_events),
            "include_1s_klines": include_1s_klines,
            "include_agg_trades": include_agg_trades,
            "include_raw_trades": include_raw_trades,
        },
    )
    return RedirectResponse("/", status_code=303)


@app.post("/matched-controls")
def create_matched_controls(
    request: Request,
    scan_id: str = Form(...),
    controls_per_event: int = Form(5),
    prior_days: int = Form(10),
    horizons_minutes: str = Form("15,30,60,120,180,480"),
    min_entry_notional: float = Form(500),
) -> RedirectResponse:
    _auth(request)
    if not 1 <= controls_per_event <= 10:
        raise HTTPException(400, "controls_per_event must be between 1 and 10")
    if not 1 <= prior_days <= 30:
        raise HTTPException(400, "prior_days must be between 1 and 30")
    try:
        horizons = sorted({int(value.strip()) for value in horizons_minutes.split(",") if value.strip()})
    except ValueError as exc:
        raise HTTPException(400, "horizons_minutes must be comma-separated integers") from exc
    if not horizons or any(value < 5 or value > 720 for value in horizons):
        raise HTTPException(400, "decision horizons must be between 5 and 720 minutes")
    if 480 not in horizons:
        raise HTTPException(400, "V7 matched controls must include the 480-minute horizon")
    if min_entry_notional < 0:
        raise HTTPException(400, "min_entry_notional cannot be negative")
    scan_rows = db.select("binance_scan_jobs", filters={"id": f"eq.{scan_id}"}, limit=1)
    if not scan_rows or scan_rows[0].get("event_definition_version") != "v7_rolling_8h" or int(scan_rows[0].get("window_minutes") or 0) != 480:
        raise HTTPException(400, "Select a completed V7 eight-hour scan")
    db.insert(
        "binance_matched_control_jobs",
        {
            "id": str(uuid.uuid4()),
            "scan_id": scan_id,
            "status": "queued",
            "controls_per_event": controls_per_event,
            "prior_days": prior_days,
            "horizons_minutes": horizons,
            "contamination_before_minutes": max(horizons),
            "contamination_after_minutes": 480,
            "min_entry_notional": min_entry_notional,
            "discovery_pct": 70,
            "validation_pct": 15,
        },
    )
    return RedirectResponse("/", status_code=303)


@app.post("/ten-day-context")
def create_ten_day_context(
    request: Request,
    matched_control_job_id: str = Form(...),
    research_mode: str = Form("exploratory_reuse"),
    horizons_minutes: str = Form("15,30,60,120,180,480"),
    min_entry_notional: float = Form(500),
) -> RedirectResponse:
    _auth(request)
    if research_mode not in {"exploratory_reuse", "fresh_staged"}:
        raise HTTPException(400, "Invalid research mode")
    try:
        horizons = sorted({int(value.strip()) for value in horizons_minutes.split(",") if value.strip()})
    except ValueError as exc:
        raise HTTPException(400, "horizons_minutes must be comma-separated integers") from exc
    if not horizons or any(value < 5 or value > 720 for value in horizons):
        raise HTTPException(400, "decision horizons must be between 5 and 720 minutes")
    if min_entry_notional < 0:
        raise HTTPException(400, "min_entry_notional cannot be negative")
    db.insert(
        "binance_context_jobs",
        {
            "id": str(uuid.uuid4()),
            "matched_control_job_id": matched_control_job_id,
            "status": "queued",
            "research_mode": research_mode,
            "prior_days": 10,
            "horizons_minutes": horizons,
            "windows_minutes": [15,30,60,120,180,360,480,720,1440,2880,4320,7200,10080,14400],
            "min_entry_notional": min_entry_notional,
        },
    )
    return RedirectResponse("/", status_code=303)


@app.post("/baseline-context")
def create_baseline_context(
    request: Request,
    matched_control_job_id: str = Form(...),
    research_mode: str = Form("exploratory_reuse"),
    min_entry_notional: float = Form(500),
) -> RedirectResponse:
    _auth(request)
    if research_mode not in {"exploratory_reuse", "fresh_staged"}:
        raise HTTPException(400, "Invalid research mode")
    if min_entry_notional < 0:
        raise HTTPException(400, "min_entry_notional cannot be negative")
    db.insert(
        "binance_baseline_context_jobs",
        {
            "id": str(uuid.uuid4()),
            "matched_control_job_id": matched_control_job_id,
            "status": "queued",
            "research_mode": research_mode,
            "prior_days": 10,
            "snapshot_offsets_minutes": [14400,10080,7200,4320,2880,1440,720,480,360,180,60,0],
            "continuation_horizons_minutes": [15],
            "min_entry_notional": min_entry_notional,
        },
    )
    return RedirectResponse("/", status_code=303)


@app.post("/fresh-confirmation")
def create_fresh_confirmation(
    request: Request,
    baseline_context_job_id: str = Form(...),
) -> RedirectResponse:
    _auth(request)
    rows = db.select(
        "binance_baseline_context_jobs",
        filters={"id": f"eq.{baseline_context_job_id}"},
        limit=1,
    )
    if not rows or rows[0].get("status") not in {"completed", "completed_with_warnings"}:
        raise HTTPException(400, "Select a completed baseline-context job")
    if rows[0].get("research_mode") != "fresh_staged":
        raise HTTPException(400, "Fresh confirmation requires a fresh_staged baseline-context job")
    matched_rows = db.select(
        "binance_matched_control_jobs",
        filters={"id": f"eq.{rows[0]['matched_control_job_id']}"},
        limit=1,
    )
    scan_rows = db.select(
        "binance_scan_jobs",
        filters={"id": f"eq.{matched_rows[0]['scan_id']}"},
        limit=1,
    ) if matched_rows else []
    if not scan_rows or scan_rows[0].get("event_definition_version") != "v7_rolling_8h" or int(scan_rows[0].get("window_minutes") or 0) != 480:
        raise HTTPException(400, "Fresh confirmation requires V7 eight-hour baseline context")
    db.insert(
        "binance_confirmation_jobs",
        {
            "id": str(uuid.uuid4()),
            "baseline_context_job_id": baseline_context_job_id,
            "status": "queued",
            "protocol_version": "v7_h1_8h_fresh_confirmation_1",
        },
    )
    return RedirectResponse("/", status_code=303)


@app.post("/continuous-backtest")
def create_continuous_backtest(
    request: Request,
    confirmation_job_id: str = Form(...),
    window_start_date: str = Form("2026-03-01"),
    window_end_date_exclusive: str = Form("2026-05-22"),
    quote_assets: str = Form("USDT,USDC,FDUSD"),
) -> RedirectResponse:
    _auth(request)
    confirmation = db.select(
        "binance_confirmation_jobs", filters={"id": f"eq.{confirmation_job_id}"}, limit=1
    )
    if not confirmation or confirmation[0].get("status") != "completed" or not bool(confirmation[0].get("passed")):
        raise HTTPException(400, "A completed passing fresh-confirmation job is required")
    if confirmation[0].get("protocol_version") != "v7_h1_8h_fresh_confirmation_1":
        raise HTTPException(400, "Select a passing V7 eight-hour confirmation job")
    try:
        start_day = date.fromisoformat(window_start_date)
        end_day = date.fromisoformat(window_end_date_exclusive)
    except ValueError as exc:
        raise HTTPException(400, "Backtest dates must use YYYY-MM-DD") from exc
    if start_day >= end_day or end_day > date(2026, 5, 22):
        raise HTTPException(400, "Use a non-empty untouched window ending no later than 2026-05-22")
    quotes = [value.strip().upper() for value in quote_assets.split(",") if value.strip()]
    db.insert(
        "binance_backtest_jobs",
        {
            "id": str(uuid.uuid4()),
            "confirmation_job_id": confirmation_job_id,
            "status": "queued",
            "protocol_version": "v7_continuous_executable_backtest_1",
            "window_start_date": start_day.isoformat(),
            "window_end_date_exclusive": end_day.isoformat(),
            "quote_assets": quotes,
            "position_quote_notional": 500,
            "take_profit_pct": 15,
            "stop_loss_pct": 5,
            "max_hold_minutes": 180,
            "fee_bps": 10,
            "max_trades_per_day": 5,
        },
    )
    return RedirectResponse("/", status_code=303)


def _csv_response(rows: list[dict[str, Any]], filename: str) -> StreamingResponse:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=sorted({key for row in rows for key in row.keys()}))
        writer.writeheader()
        writer.writerows(rows)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/exports/events/{scan_id}.csv")
def events_csv(request: Request, scan_id: str) -> StreamingResponse:
    """Primary result: only exact-window events that passed saleability."""
    _auth(request)
    rows = db.select_all(
        "binance_gainer_events",
        filters={"scan_id": f"eq.{scan_id}", "sellability_pass": "eq.true"},
        order="event_date.asc,symbol.asc",
    )
    return _csv_response(rows, f"binance_saleable_8h_gainer_events_{scan_id}.csv")


@app.get("/exports/candidates/{scan_id}.csv")
def candidates_csv(request: Request, scan_id: str) -> StreamingResponse:
    """Audit result: includes detected surges that failed saleability or exact-trade proof."""
    _auth(request)
    rows = db.select_all(
        "binance_gainer_events", filters={"scan_id": f"eq.{scan_id}"}, order="event_date.asc,symbol.asc"
    )
    return _csv_response(rows, f"binance_all_8h_gainer_candidates_{scan_id}.csv")


@app.get("/exports/decisions/{scan_id}.csv")
def decisions_csv(request: Request, scan_id: str) -> StreamingResponse:
    _auth(request)
    rows = db.select_all(
        "binance_decision_observations",
        filters={"scan_id": f"eq.{scan_id}"},
        order="symbol.asc,decision_time_utc.asc",
    )
    return _csv_response(rows, f"binance_decisions_{scan_id}.csv")


@app.get("/exports/minutes/{event_id}.csv")
def minutes_csv(request: Request, event_id: str) -> StreamingResponse:
    _auth(request)
    rows = db.select_all(
        "binance_event_minute_bars", filters={"event_id": f"eq.{event_id}"}, order="open_time.asc"
    )
    return _csv_response(rows, f"binance_event_minutes_{event_id}.csv")


@app.get("/exports/agg-trades/{event_id}.csv")
def agg_trades_csv(request: Request, event_id: str) -> StreamingResponse:
    _auth(request)
    rows = db.select_all(
        "binance_event_agg_trades", filters={"event_id": f"eq.{event_id}"}, order="trade_time.asc"
    )
    return _csv_response(rows, f"binance_event_agg_trades_{event_id}.csv")


@app.get("/files/{file_id}")
def download_file(request: Request, file_id: str) -> RedirectResponse:
    _auth(request)
    rows = db.select("binance_research_files", filters={"id": f"eq.{file_id}"}, limit=1)
    if not rows:
        raise HTTPException(404, "File not found")
    return RedirectResponse(db.signed_url(rows[0]["storage_path"], expires_in=3600), status_code=302)


@app.get("/matched-files/{file_id}")
def download_matched_file(request: Request, file_id: str) -> RedirectResponse:
    _auth(request)
    rows = db.select("binance_matched_control_files", filters={"id": f"eq.{file_id}"}, limit=1)
    if not rows:
        raise HTTPException(404, "Matched-control file not found")
    return RedirectResponse(db.signed_url(rows[0]["storage_path"], expires_in=3600), status_code=302)


@app.get("/context-files/{file_id}")
def download_context_file(request: Request, file_id: str) -> RedirectResponse:
    _auth(request)
    rows = db.select("binance_context_files", filters={"id": f"eq.{file_id}"}, limit=1)
    if not rows:
        raise HTTPException(404, "Ten-day context file not found")
    return RedirectResponse(db.signed_url(rows[0]["storage_path"], expires_in=3600), status_code=302)


@app.get("/baseline-context-files/{file_id}")
def download_baseline_context_file(request: Request, file_id: str) -> RedirectResponse:
    _auth(request)
    rows = db.select("binance_baseline_context_files", filters={"id": f"eq.{file_id}"}, limit=1)
    if not rows:
        raise HTTPException(404, "Baseline-context file not found")
    return RedirectResponse(db.signed_url(rows[0]["storage_path"], expires_in=3600), status_code=302)



@app.get("/confirmation-files/{file_id}")
def download_confirmation_file(request: Request, file_id: str) -> RedirectResponse:
    _auth(request)
    rows = db.select("binance_confirmation_files", filters={"id": f"eq.{file_id}"}, limit=1)
    if not rows:
        raise HTTPException(404, "Confirmation file not found")
    return RedirectResponse(db.signed_url(rows[0]["storage_path"], expires_in=3600), status_code=302)


@app.get("/backtest-files/{file_id}")
def download_backtest_file(request: Request, file_id: str) -> RedirectResponse:
    _auth(request)
    rows = db.select("binance_backtest_files", filters={"id": f"eq.{file_id}"}, limit=1)
    if not rows:
        raise HTTPException(404, "Backtest file not found")
    return RedirectResponse(db.signed_url(rows[0]["storage_path"], expires_in=3600), status_code=302)

@app.get("/api/status")
def api_status(request: Request) -> dict[str, Any]:
    _auth(request)
    return {
        "scans": db.select("binance_scan_jobs", order="created_at.desc", limit=20),
        "research_jobs": db.select("binance_research_jobs", order="created_at.desc", limit=20),
        "matched_control_jobs": db.select("binance_matched_control_jobs", order="created_at.desc", limit=20),
        "context_jobs": db.select("binance_context_jobs", order="created_at.desc", limit=20),
        "baseline_context_jobs": db.select("binance_baseline_context_jobs", order="created_at.desc", limit=20),
        "confirmation_jobs": db.select("binance_confirmation_jobs", order="created_at.desc", limit=20),
        "backtest_jobs": db.select("binance_backtest_jobs", order="created_at.desc", limit=20),
        "worker": db.select("binance_worker_heartbeats", filters={"worker_name": "eq.main"}, limit=1),
    }
