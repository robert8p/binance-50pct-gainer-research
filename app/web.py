from __future__ import annotations

import base64
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from .config import Settings
from .supabase import SupabaseClient

settings = Settings.from_env()
db = SupabaseClient(settings.supabase_url, settings.supabase_service_role_key, settings.storage_bucket)
app = FastAPI(title="Binance 3-Hour 50% Surge Research", version="2.0.0")
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
    return {"status": "ok", "version": "2.0.0"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    _auth(request)
    scans = db.select("binance_scan_jobs", order="created_at.desc", limit=25)
    research = db.select("binance_research_jobs", order="created_at.desc", limit=25)
    heartbeat = db.select("binance_worker_heartbeats", filters={"worker_name": "eq.main"}, limit=1)
    files = db.select("binance_research_files", order="created_at.desc", limit=100)
    completed_scans = [
        x for x in scans
        if x["status"] in {"completed", "completed_with_warnings"}
        and x.get("event_definition_version") == "v2_rolling_3h"
    ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "scans": scans,
            "research_jobs": research,
            "completed_scans": completed_scans,
            "heartbeat": heartbeat[0] if heartbeat else None,
            "files": files,
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
) -> RedirectResponse:
    _auth(request)
    if not 1 <= lookback_days <= 60:
        raise HTTPException(400, "lookback_days must be between 1 and 60")
    if threshold_pct <= 0:
        raise HTTPException(400, "threshold_pct must be positive")
    quotes = [x.strip().upper() for x in quote_assets.split(",") if x.strip()]
    db.insert(
        "binance_scan_jobs",
        {
            "id": str(uuid.uuid4()),
            "status": "queued",
            "event_definition_version": "v2_rolling_3h",
            "lookback_days": lookback_days,
            "threshold_pct": threshold_pct,
            "window_minutes": 180,
            "quote_assets": quotes,
            "min_exit_notional": min_exit_notional,
            "confirmation_window_seconds": confirmation_window_seconds,
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
    return _csv_response(rows, f"binance_saleable_3h_gainer_events_{scan_id}.csv")


@app.get("/exports/candidates/{scan_id}.csv")
def candidates_csv(request: Request, scan_id: str) -> StreamingResponse:
    """Audit result: includes detected surges that failed saleability or exact-trade proof."""
    _auth(request)
    rows = db.select_all(
        "binance_gainer_events", filters={"scan_id": f"eq.{scan_id}"}, order="event_date.asc,symbol.asc"
    )
    return _csv_response(rows, f"binance_all_3h_gainer_candidates_{scan_id}.csv")


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


@app.get("/api/status")
def api_status(request: Request) -> dict[str, Any]:
    _auth(request)
    return {
        "scans": db.select("binance_scan_jobs", order="created_at.desc", limit=20),
        "research_jobs": db.select("binance_research_jobs", order="created_at.desc", limit=20),
        "worker": db.select("binance_worker_heartbeats", filters={"worker_name": "eq.main"}, limit=1),
    }
