"""FastAPI backend server for IPO & Micro-Cap AI Scouter + Paper Trading Auto-Pilot."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from config import settings
from scouter_pipeline import analyze_single_ticker, run_daily_pipeline
from services.autopilot import evaluate_and_auto_register, run_portfolio_monitor
from services.storage import storage

logger = logging.getLogger("scouter_api")
_monitor_wakeup = asyncio.Event()


async def _background_monitor_worker() -> None:
    """Wakeable background polling loop for Paper Trading Auto-Monitor."""
    while True:
        try:
            cfg = storage.get_autopilot_config()
            interval_mins = max(5, int(cfg.get("monitor_interval_minutes") or 60))
            if cfg.get("enabled") and cfg.get("background_monitor_enabled"):
                await asyncio.to_thread(run_portfolio_monitor, True, False)

            _monitor_wakeup.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(_monitor_wakeup.wait(), timeout=interval_mins * 60)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Background Auto-Monitor error: %s", exc)
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_background_monitor_worker())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="IPO & Micro-Cap AI Scouter API",
    version="1.1.0",
    description="API per screening post-IPO, analisi multi-agente, Diario Micro-Ordini e Paper Trading Auto-Pilot.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PipelineRunRequest(BaseModel):
    tickers: list[str] | None = None
    max_candidates: int = Field(default=8, ge=1, le=25)
    notify: bool = False
    auto_register: bool = False
    auto_monitor: bool = False


class MicroOrderCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    order_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount_eur: float = Field(..., gt=0, le=5000)
    entry_price_usd: float = Field(..., gt=0)
    broker: str = Field(default="Trading 212", max_length=60)
    fractional: bool = True
    mode: str = Field(default="PAPER_MANUAL", pattern="^(PAPER_AUTO|PAPER_MANUAL|REAL)$")
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000)
    stop_loss_pct: float | None = Field(default=None, lt=0, ge=-99)
    initial_thesis: str = Field(..., min_length=3, max_length=1000)
    invalidation_rule: str = Field(default="", max_length=500)
    initial_ai_score: int | None = Field(default=None, ge=1, le=100)
    override_monthly_limit: bool = False

    @field_validator("ticker", "initial_thesis", mode="before")
    @classmethod
    def strip_non_empty(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class MicroOrderUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(APERTO|CHIUSO)$")
    amount_eur: float | None = Field(default=None, gt=0, le=5000)
    entry_price_usd: float | None = Field(default=None, gt=0)
    exit_price_usd: float | None = Field(default=None, gt=0)
    broker: str | None = Field(default=None, max_length=60)
    mode: str | None = Field(default=None, pattern="^(PAPER_AUTO|PAPER_MANUAL|REAL)$")
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000)
    stop_loss_pct: float | None = Field(default=None, lt=0, ge=-99)
    initial_thesis: str | None = Field(default=None, min_length=3, max_length=1000)
    invalidation_rule: str | None = Field(default=None, max_length=500)


class AutopilotConfigUpdate(BaseModel):
    enabled: bool | None = None
    background_monitor_enabled: bool | None = None
    monitor_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    monthly_order_limit: int | None = Field(default=None, ge=1, le=30)
    virtual_budget_eur: float | None = Field(default=None, gt=0, le=1_000_000)
    portfolio_roi_target_pct: float | None = Field(default=None, gt=0, le=500)
    min_asymmetry_score: int | None = Field(default=None, ge=1, le=100)
    min_audit_score: int | None = Field(default=None, ge=0, le=100)
    min_runway_months: float | None = Field(default=None, ge=0, le=120)
    block_high_dilution_risk: bool | None = None
    default_ticket_eur: float | None = Field(default=None, gt=0, le=5000)
    default_broker: str | None = Field(default=None, min_length=2, max_length=60)
    max_positions_per_ticker: int | None = Field(default=None, ge=1, le=5)
    respect_monthly_5_limit: bool | None = None
    enable_partial_tp1: bool | None = None
    tp1_pct: float | None = Field(default=None, gt=0, le=500)
    tp1_sell_ratio_pct: float | None = Field(default=None, ge=10, le=90)
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000)
    stop_loss_pct: float | None = Field(default=None, lt=0, ge=-99)
    enable_trailing_stop: bool | None = None
    trailing_activation_pct: float | None = Field(default=None, gt=0, le=500)
    trailing_stop_pct: float | None = Field(default=None, ge=3, le=80)
    auto_close_on_tp_sl: bool | None = None
    auto_close_on_thesis_degrade: bool | None = None
    thesis_degrade_min_score: int | None = Field(default=None, ge=1, le=99)
    thesis_degrade_drop_pts: int | None = Field(default=None, ge=5, le=80)
    notify_telegram: bool | None = None


class MonitorRunRequest(BaseModel):
    refresh_live_prices: bool = True
    rescan_ai: bool = False


class AutoRegisterRequest(BaseModel):
    dry_run: bool = False
    force: bool = False


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "storage_mode": storage.backend_mode,
        "gemini_configured": bool(
            settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_")
        ),
        "alert_threshold": settings.ALERT_SCORE_THRESHOLD,
        "monthly_micro_order_limit": int(
            storage.get_autopilot_config().get("monthly_order_limit") or settings.MONTHLY_MICRO_ORDER_LIMIT
        ),
    }


@app.get("/api/opportunities")
def list_opportunities(
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    items = storage.list_opportunities(min_score=min_score, limit=limit)
    return {
        "count": len(items),
        "top_daily": [o for o in items if int(o.get("asymmetry_score", 0)) >= 55][:5],
        "items": items,
    }


@app.get("/api/opportunities/{ticker}")
def get_opportunity(ticker: str) -> dict[str, Any]:
    opp = storage.get_opportunity(ticker)
    if not opp:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker.upper()}' non trovato in archivio.")
    return opp


@app.delete("/api/opportunities/{ticker}")
def remove_opportunity(ticker: str) -> dict[str, Any]:
    deleted = storage.delete_opportunity(ticker)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker.upper()}' non trovato.")
    return {"deleted": ticker.upper()}


@app.post("/api/scan/{ticker}")
def scan_ticker_live(ticker: str, notify: bool = False) -> dict[str, Any]:
    try:
        return analyze_single_ticker(ticker, save_to_store=True, notify=notify)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore scansione {ticker.upper()}: {exc}") from exc


@app.post("/api/pipeline/run")
def trigger_pipeline(body: PipelineRunRequest) -> dict[str, Any]:
    try:
        return run_daily_pipeline(
            tickers=body.tickers,
            max_candidates=body.max_candidates,
            notify=body.notify,
            auto_register=body.auto_register,
            auto_monitor=body.auto_monitor,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore esecuzione pipeline: {exc}") from exc


@app.get("/api/pipeline/runs")
def get_pipeline_runs() -> dict[str, Any]:
    return {"runs": storage.list_pipeline_runs()}


@app.get("/api/journal")
def list_journal() -> dict[str, Any]:
    return storage.list_micro_orders()


@app.post("/api/journal", status_code=201)
def create_journal_order(body: MicroOrderCreate) -> dict[str, Any]:
    try:
        order = storage.add_micro_order(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"order": order, "journal": storage.list_micro_orders()}


@app.patch("/api/journal/{order_id}")
def patch_journal_order(order_id: str, body: MicroOrderUpdate) -> dict[str, Any]:
    updated = storage.update_micro_order(order_id, body.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Ordine non trovato.")
    return {"order": updated, "journal": storage.list_micro_orders()}


@app.delete("/api/journal/{order_id}")
def remove_journal_order(order_id: str) -> dict[str, Any]:
    deleted = storage.delete_micro_order(order_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ordine non trovato.")
    return {"deleted": order_id, "journal": storage.list_micro_orders()}


# ------------------------------------------------------------------
# Auto-Pilot Paper Trading Endpoints
# ------------------------------------------------------------------
@app.get("/api/autopilot/status")
def get_autopilot_status() -> dict[str, Any]:
    cfg = storage.get_autopilot_config()
    logs = storage.list_autopilot_logs(limit=40)
    journal = storage.list_micro_orders()
    monitor_logs = [lg for lg in logs if lg.get("action") == "MONITOR_CHECK"]
    last_monitor_at = monitor_logs[0]["ts"] if monitor_logs else None
    return {
        "config": cfg,
        "logs": logs,
        "last_monitor_at": last_monitor_at,
        "journal": journal,
    }


@app.put("/api/autopilot/config")
def put_autopilot_config(body: AutopilotConfigUpdate) -> dict[str, Any]:
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    current = storage.get_autopilot_config()
    merged = {**current, **updates}
    if int(merged["thesis_degrade_min_score"]) >= int(merged["min_asymmetry_score"]):
        raise HTTPException(
            status_code=400,
            detail="La soglia Thesis Stop deve essere inferiore al Min AI Score d'ingresso per evitare chiusure immediate.",
        )
    if merged.get("enable_partial_tp1") and float(merged["tp1_pct"]) >= float(merged["take_profit_pct"]):
        raise HTTPException(
            status_code=400,
            detail="Il target parziale TP1 deve essere inferiore al target finale TP2.",
        )

    updated = storage.update_autopilot_config(updates)
    storage.append_autopilot_log(
        "CONFIG_UPDATE",
        "SYSTEM",
        f"Aggiornate regole Auto-Pilot (Budget €{updated['virtual_budget_eur']:.0f}, Max {updated['monthly_order_limit']}/mese, TP1 +{updated['tp1_pct']}%, TP2 +{updated['take_profit_pct']}%, SL {updated['stop_loss_pct']}%).",
        updates,
    )
    _monitor_wakeup.set()
    return {
        "config": updated,
        "logs": storage.list_autopilot_logs(limit=40),
        "journal": storage.list_micro_orders(),
    }


@app.post("/api/autopilot/auto-register")
def run_auto_register(body: AutoRegisterRequest | None = None) -> dict[str, Any]:
    req = body or AutoRegisterRequest()
    try:
        return evaluate_and_auto_register(dry_run=req.dry_run, force=req.force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore Auto-Registrazione: {exc}") from exc


@app.post("/api/autopilot/monitor")
def run_monitor(body: MonitorRunRequest | None = None) -> dict[str, Any]:
    req = body or MonitorRunRequest()
    try:
        return run_portfolio_monitor(
            refresh_live_prices=req.refresh_live_prices,
            rescan_ai=req.rescan_ai,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore Auto-Monitoraggio: {exc}") from exc
