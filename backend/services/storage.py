"""Dual persistence layer: Firebase Firestore (optional) + Thread-Safe Local JSON Store."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:
    firebase_admin = None
    credentials = None
    firestore = None


DEFAULT_AUTOPILOT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "background_monitor_enabled": False,
    "monitor_interval_minutes": 60,
    "min_asymmetry_score": 75,
    "min_audit_score": 80,
    "min_runway_months": 12.0,
    "block_high_dilution_risk": False,
    "default_ticket_eur": 35.0,
    "default_broker": "Trading 212 (Paper)",
    "max_positions_per_ticker": 1,
    "respect_monthly_5_limit": True,
    "take_profit_pct": 60.0,
    "stop_loss_pct": -35.0,
    "auto_close_on_tp_sl": True,
    "auto_close_on_thesis_degrade": True,
    "thesis_degrade_min_score": 55,
    "thesis_degrade_drop_pts": 18,
    "notify_telegram": True,
}


def _default_store() -> dict[str, Any]:
    return {
        "opportunities": {},
        "micro_orders": [],
        "pipeline_runs": [],
        "autopilot_config": dict(DEFAULT_AUTOPILOT_CONFIG),
        "autopilot_logs": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class ScouterStorage:
    """Manages opportunities, pipeline runs, Micro-Order Journal, and Auto-Pilot state across Firestore & JSON."""

    def __init__(self, store_path: Path | None = None) -> None:
        self.store_path = store_path or settings.STORE_PATH
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = self._init_firestore()

    def _init_firestore(self) -> Any:
        cred_path = settings.FIREBASE_SERVICE_ACCOUNT_PATH
        if not (firebase_admin and cred_path and Path(cred_path).exists()):
            return None
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            return firestore.client()
        except Exception:
            return None

    @property
    def backend_mode(self) -> str:
        return "firestore+local_json" if self._db is not None else "local_json"

    def _read_local(self) -> dict[str, Any]:
        with self._lock:
            if not self.store_path.exists():
                data = _default_store()
                self._write_local(data)
                return data
            try:
                return json.loads(self.store_path.read_text(encoding="utf-8"))
            except Exception:
                return _default_store()

    def _write_local(self, data: dict[str, Any]) -> None:
        with self._lock:
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            tmp_path = self.store_path.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            os.replace(tmp_path, self.store_path)

    # ------------------------------------------------------------------
    # Opportunities
    # ------------------------------------------------------------------
    def list_opportunities(self, min_score: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read_local()
            opps = list((data.get("opportunities") or {}).values())
            if self._db is not None and not opps:
                try:
                    docs = self._db.collection("opportunities").stream()
                    opps = [d.to_dict() for d in docs if d.to_dict()]
                    if opps:
                        data["opportunities"] = {o["ticker"]: o for o in opps if "ticker" in o}
                        self._write_local(data)
                except Exception:
                    pass
        filtered = [o for o in opps if int(o.get("asymmetry_score", 0)) >= min_score]
        filtered.sort(key=lambda o: (o.get("asymmetry_score", 0), o.get("analyzed_at", "")), reverse=True)
        return filtered[:limit]

    def get_opportunity(self, ticker: str) -> dict[str, Any] | None:
        sym = ticker.strip().upper()
        data = self._read_local()
        opp = (data.get("opportunities") or {}).get(sym)
        if opp:
            return opp
        if self._db is not None:
            try:
                snap = self._db.collection("opportunities").document(sym).get()
                if snap.exists:
                    return snap.to_dict()
            except Exception:
                pass
        return None

    def upsert_opportunity(self, record: dict[str, Any]) -> dict[str, Any]:
        sym = record["ticker"].strip().upper()
        with self._lock:
            data = self._read_local()
            data.setdefault("opportunities", {})[sym] = record
            self._write_local(data)

        if self._db is not None:
            try:
                self._db.collection("opportunities").document(sym).set(record)
            except Exception:
                pass
        return record

    def delete_opportunity(self, ticker: str) -> bool:
        sym = ticker.strip().upper()
        with self._lock:
            data = self._read_local()
            opps = data.get("opportunities") or {}
            if sym not in opps:
                return False
            del opps[sym]
            self._write_local(data)

        if self._db is not None:
            try:
                self._db.collection("opportunities").document(sym).delete()
            except Exception:
                pass
        return True

    # ------------------------------------------------------------------
    # Pipeline Run Logs
    # ------------------------------------------------------------------
    def record_pipeline_run(self, summary: dict[str, Any]) -> None:
        with self._lock:
            data = self._read_local()
            runs = data.setdefault("pipeline_runs", [])
            runs.insert(0, summary)
            data["pipeline_runs"] = runs[:20]
            self._write_local(data)

        if self._db is not None:
            try:
                self._db.collection("pipeline_runs").add(summary)
            except Exception:
                pass

    def list_pipeline_runs(self) -> list[dict[str, Any]]:
        data = self._read_local()
        runs = data.get("pipeline_runs", [])
        if self._db is not None and not runs:
            try:
                docs = self._db.collection("pipeline_runs").stream()
                runs = sorted(
                    [d.to_dict() for d in docs if d.to_dict()],
                    key=lambda r: r.get("run_at", ""),
                    reverse=True,
                )[:20]
            except Exception:
                pass
        return runs

    # ------------------------------------------------------------------
    # Auto-Pilot Config & Audit Logs
    # ------------------------------------------------------------------
    def get_autopilot_config(self) -> dict[str, Any]:
        data = self._read_local()
        saved = data.get("autopilot_config") or {}
        if self._db is not None and "autopilot_config" not in data:
            try:
                snap = self._db.collection("autopilot").document("config").get()
                if snap.exists:
                    saved = snap.to_dict() or {}
            except Exception:
                pass
        return {**DEFAULT_AUTOPILOT_CONFIG, **saved}

    def update_autopilot_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read_local()
            current = {**DEFAULT_AUTOPILOT_CONFIG, **(data.get("autopilot_config") or {})}
            for key in DEFAULT_AUTOPILOT_CONFIG:
                if key in updates and updates[key] is not None:
                    current[key] = updates[key]
            data["autopilot_config"] = current
            self._write_local(data)

        if self._db is not None:
            try:
                self._db.collection("autopilot").document("config").set(current)
            except Exception:
                pass
        return current

    def append_autopilot_log(
        self,
        action: str,
        ticker: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": str(uuid.uuid4())[:8],
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "ticker": ticker.upper(),
            "summary": summary,
            "details": details or {},
        }
        with self._lock:
            data = self._read_local()
            logs = data.setdefault("autopilot_logs", [])
            logs.insert(0, entry)
            data["autopilot_logs"] = logs[:60]
            self._write_local(data)

        if self._db is not None:
            try:
                self._db.collection("autopilot_logs").document(entry["id"]).set(entry)
            except Exception:
                pass
        return entry

    def list_autopilot_logs(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read_local()
            logs = data.get("autopilot_logs") or []
            if self._db is not None and not logs:
                try:
                    docs = self._db.collection("autopilot_logs").stream()
                    logs = sorted(
                        [d.to_dict() for d in docs if d.to_dict()],
                        key=lambda x: x.get("ts", ""),
                        reverse=True,
                    )[:60]
                    if logs:
                        data["autopilot_logs"] = logs
                        self._write_local(data)
                except Exception:
                    pass
        return logs[:limit]

    # ------------------------------------------------------------------
    # Micro-Order Journal ("Diario di Bordo Micro-Ordini" + Paper Auto)
    # ------------------------------------------------------------------
    def list_micro_orders(self) -> dict[str, Any]:
        with self._lock:
            data = self._read_local()
            orders: list[dict[str, Any]] = data.get("micro_orders", [])
            if self._db is not None and not orders:
                try:
                    docs = self._db.collection("micro_orders").stream()
                    orders = [d.to_dict() for d in docs if d.to_dict()]
                    if orders:
                        data["micro_orders"] = orders
                        self._write_local(data)
                except Exception:
                    pass

        opps = data.get("opportunities", {})
        cfg = {**DEFAULT_AUTOPILOT_CONFIG, **(data.get("autopilot_config") or {})}
        now_ym = datetime.now(timezone.utc).strftime("%Y-%m")

        monthly_count = 0
        monthly_eur = 0.0
        total_invested_eur = 0.0
        total_current_eur = 0.0
        realized_pnl_eur = 0.0
        unrealized_pnl_eur = 0.0
        paper_realized_pnl_eur = 0.0
        paper_unrealized_pnl_eur = 0.0
        open_count = 0
        closed_count = 0
        auto_orders_count = 0
        closed_wins = 0
        paper_open_count = 0
        paper_closed_count = 0
        paper_wins = 0
        paper_invested_eur = 0.0
        paper_current_eur = 0.0

        enriched: list[dict[str, Any]] = []
        for order in orders:
            sym = (order.get("ticker") or "").upper()
            opp = opps.get(sym)
            entry_price = float(order.get("entry_price_usd") or 0.0)
            amount_eur = float(order.get("amount_eur") or 0.0)
            status = order.get("status", "APERTO")
            mode = order.get("mode") or ("PAPER_AUTO" if order.get("auto_registered") else "PAPER_MANUAL")
            is_paper = mode in ("PAPER_AUTO", "PAPER_MANUAL")

            latest_price = entry_price
            latest_score = order.get("initial_ai_score")
            latest_verdict = None
            dilution_alert = False

            opp_price = None
            opp_analyzed_at = ""
            if opp:
                opp_price = (opp.get("quant_metrics") or {}).get("current_price")
                opp_analyzed_at = opp.get("analyzed_at") or ""
                latest_score = opp.get("asymmetry_score", latest_score)
                latest_verdict = opp.get("verdict_label")
                dilution_alert = bool((opp.get("sec_filings") or {}).get("shelf_dilution_risk"))

            live_mon_price = order.get("last_live_price_usd")
            live_mon_at = order.get("last_monitored_at") or ""
            if live_mon_price is not None and (live_mon_at >= opp_analyzed_at or opp_price is None):
                latest_price = float(live_mon_price)
            elif opp_price is not None:
                latest_price = float(opp_price)

            ref_price = (
                float(order["exit_price_usd"])
                if (status == "CHIUSO" and order.get("exit_price_usd") is not None)
                else latest_price
            )
            ratio = (ref_price / entry_price) if entry_price > 0 else 1.0
            pnl_pct = round((ratio - 1.0) * 100.0, 2) if entry_price > 0 else 0.0
            current_val_eur = round(amount_eur * ratio, 2)
            pnl_eur = round(current_val_eur - amount_eur, 2)

            initial_score = order.get("initial_ai_score")
            thesis_drift = "STABILE"
            if latest_score is not None and initial_score is not None and (initial_score - latest_score) >= 15:
                thesis_drift = "DEGRADO_TESI"
            elif dilution_alert or latest_verdict == "AVOID_DILUTION_TRAP":
                thesis_drift = "ATTENZIONE_DILUIZIONE"
            elif latest_score is not None and latest_score >= 75:
                thesis_drift = "TESI_CONFERMATA"

            order_month = (order.get("order_date") or "")[:7]
            if order_month == now_ym:
                monthly_count += 1
                monthly_eur += amount_eur

            if mode == "PAPER_AUTO":
                auto_orders_count += 1

            if status == "APERTO":
                open_count += 1
                total_invested_eur += amount_eur
                total_current_eur += current_val_eur
                unrealized_pnl_eur += pnl_eur
                if is_paper:
                    paper_open_count += 1
                    paper_invested_eur += amount_eur
                    paper_current_eur += current_val_eur
                    paper_unrealized_pnl_eur += pnl_eur
            else:
                closed_count += 1
                realized_pnl_eur += pnl_eur
                if pnl_pct > 0:
                    closed_wins += 1
                if is_paper:
                    paper_closed_count += 1
                    paper_realized_pnl_eur += pnl_eur
                    if pnl_pct > 0:
                        paper_wins += 1

            tp_pct = order.get("take_profit_pct")
            if tp_pct is None:
                tp_pct = cfg["take_profit_pct"]
            sl_pct = order.get("stop_loss_pct")
            if sl_pct is None:
                sl_pct = cfg["stop_loss_pct"]

            history = order.get("price_history") or [
                {
                    "ts": order.get("created_at") or order.get("order_date"),
                    "price_usd": round(entry_price, 4),
                    "pnl_pct": 0.0,
                    "ai_score": initial_score,
                }
            ]

            enriched.append(
                {
                    **order,
                    "mode": mode,
                    "auto_registered": bool(order.get("auto_registered", mode == "PAPER_AUTO")),
                    "take_profit_pct": tp_pct,
                    "stop_loss_pct": sl_pct,
                    "price_history": history,
                    "raw_latest_price_usd": round(ref_price, 4),
                    "latest_price_usd": round(ref_price, 2),
                    "pnl_pct": pnl_pct,
                    "pnl_eur": pnl_eur,
                    "current_value_eur": current_val_eur,
                    "latest_ai_score": latest_score,
                    "thesis_drift_status": thesis_drift,
                }
            )

        enriched.sort(key=lambda x: (x.get("order_date", ""), x.get("created_at", "")), reverse=True)
        total_pnl_eur = round(total_current_eur - total_invested_eur, 2)
        total_pnl_pct = (
            round((total_pnl_eur / total_invested_eur) * 100.0, 2) if total_invested_eur > 0 else 0.0
        )

        return {
            "orders": enriched,
            "summary": {
                "current_month": now_ym,
                "monthly_orders_used": monthly_count,
                "monthly_orders_limit": settings.MONTHLY_MICRO_ORDER_LIMIT,
                "monthly_slots_remaining": max(0, settings.MONTHLY_MICRO_ORDER_LIMIT - monthly_count),
                "monthly_allocated_eur": round(monthly_eur, 2),
                "total_invested_eur": round(total_invested_eur, 2),
                "total_current_value_eur": round(total_current_eur, 2),
                "total_pnl_eur": total_pnl_eur,
                "total_pnl_pct": total_pnl_pct,
                "unrealized_pnl_eur": round(unrealized_pnl_eur, 2),
                "realized_pnl_eur": round(realized_pnl_eur, 2),
                "open_count": open_count,
                "closed_count": closed_count,
                "auto_orders_count": auto_orders_count,
                "win_rate_pct": round((closed_wins / closed_count) * 100.0, 1) if closed_count > 0 else None,
                "paper_open_count": paper_open_count,
                "paper_closed_count": paper_closed_count,
                "paper_invested_eur": round(paper_invested_eur, 2),
                "paper_current_value_eur": round(paper_current_eur, 2),
                "paper_unrealized_pnl_eur": round(paper_unrealized_pnl_eur, 2),
                "paper_realized_pnl_eur": round(paper_realized_pnl_eur, 2),
                "paper_win_rate_pct": round((paper_wins / paper_closed_count) * 100.0, 1)
                if paper_closed_count > 0
                else None,
            },
        }

    def add_micro_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read_local()
            cfg = {**DEFAULT_AUTOPILOT_CONFIG, **(data.get("autopilot_config") or {})}
            order_date = payload.get("order_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            order_ym = order_date[:7]
            existing_orders = data.get("micro_orders", [])
            existing_month_count = sum(
                1 for o in existing_orders if (o.get("order_date") or "")[:7] == order_ym
            )
            if (
                not payload.get("override_monthly_limit", False)
                and existing_month_count >= settings.MONTHLY_MICRO_ORDER_LIMIT
            ):
                raise ValueError(
                    f"Limite disciplinato di {settings.MONTHLY_MICRO_ORDER_LIMIT} micro-ordini raggiunto per {order_ym}. "
                    "Abilita l'override esplicito solo se vuoi forzare un ordine extra."
                )

            sym = payload["ticker"].strip().upper()
            mode = payload.get("mode") or "PAPER_MANUAL"
            if payload.get("auto_registered") or mode == "PAPER_AUTO":
                open_same = sum(
                    1
                    for o in existing_orders
                    if (o.get("ticker") or "").upper() == sym and o.get("status", "APERTO") == "APERTO"
                )
                if open_same >= int(cfg.get("max_positions_per_ticker") or 1):
                    raise ValueError(f"Posizione già aperta su {sym} (limite duplicati Auto-Pilot).")

            opp = (data.get("opportunities") or {}).get(sym)
            entry_price = round(float(payload["entry_price_usd"]), 4)
            initial_score = payload.get("initial_ai_score") or (
                opp.get("asymmetry_score") if opp else None
            )
            now_iso = datetime.now(timezone.utc).isoformat()

            tp_pct = payload.get("take_profit_pct")
            sl_pct = payload.get("stop_loss_pct")

            order = {
                "id": str(uuid.uuid4())[:8],
                "ticker": sym,
                "order_date": order_date,
                "amount_eur": round(float(payload["amount_eur"]), 2),
                "entry_price_usd": entry_price,
                "exit_price_usd": None,
                "broker": payload.get("broker") or "Trading 212",
                "fractional": bool(payload.get("fractional", True)),
                "mode": mode,
                "auto_registered": bool(payload.get("auto_registered", mode == "PAPER_AUTO")),
                "take_profit_pct": float(tp_pct) if tp_pct is not None else float(cfg["take_profit_pct"]),
                "stop_loss_pct": float(sl_pct) if sl_pct is not None else float(cfg["stop_loss_pct"]),
                "last_live_price_usd": entry_price,
                "last_monitored_at": now_iso,
                "closed_at": None,
                "close_reason": None,
                "last_alert_reason": None,
                "last_alert_at": None,
                "price_history": payload.get("price_history")
                or [
                    {
                        "ts": now_iso,
                        "price_usd": entry_price,
                        "pnl_pct": 0.0,
                        "ai_score": initial_score,
                    }
                ],
                "initial_thesis": payload.get("initial_thesis", "").strip(),
                "invalidation_rule": payload.get("invalidation_rule", "").strip(),
                "initial_ai_score": initial_score,
                "status": payload.get("status") or "APERTO",
                "created_at": now_iso,
            }
            data.setdefault("micro_orders", []).append(order)
            self._write_local(data)

        if self._db is not None:
            try:
                self._db.collection("micro_orders").document(order["id"]).set(order)
            except Exception:
                pass
        return order

    def record_order_checkpoint(
        self,
        order_id: str,
        price_usd: float,
        ai_score: int | None,
        pnl_pct: float,
        monitored_at: str | None = None,
    ) -> dict[str, Any] | None:
        ts = monitored_at or datetime.now(timezone.utc).isoformat()
        updated_order: dict[str, Any] | None = None
        with self._lock:
            data = self._read_local()
            orders = data.get("micro_orders", [])
            for idx, o in enumerate(orders):
                if o.get("id") == order_id:
                    o["last_live_price_usd"] = round(float(price_usd), 4)
                    o["last_monitored_at"] = ts
                    hist = o.get("price_history")
                    if not hist:
                        hist = [
                            {
                                "ts": o.get("created_at") or o.get("order_date"),
                                "price_usd": round(float(o.get("entry_price_usd") or price_usd), 4),
                                "pnl_pct": 0.0,
                                "ai_score": o.get("initial_ai_score"),
                            }
                        ]
                    hist.append(
                        {
                            "ts": ts,
                            "price_usd": round(float(price_usd), 4),
                            "pnl_pct": round(float(pnl_pct), 2),
                            "ai_score": ai_score,
                        }
                    )
                    o["price_history"] = hist[-30:]
                    orders[idx] = o
                    self._write_local(data)
                    updated_order = dict(o)
                    break

        if updated_order is not None and self._db is not None:
            try:
                self._db.collection("micro_orders").document(order_id).set(updated_order)
            except Exception:
                pass
        return updated_order

    def update_micro_order(self, order_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        updated_order: dict[str, Any] | None = None
        with self._lock:
            data = self._read_local()
            orders = data.get("micro_orders", [])
            opps = data.get("opportunities", {})
            for idx, o in enumerate(orders):
                if o.get("id") == order_id:
                    for key in (
                        "status",
                        "amount_eur",
                        "entry_price_usd",
                        "exit_price_usd",
                        "broker",
                        "initial_thesis",
                        "invalidation_rule",
                        "mode",
                        "take_profit_pct",
                        "stop_loss_pct",
                        "last_live_price_usd",
                        "last_monitored_at",
                        "closed_at",
                        "close_reason",
                        "last_alert_reason",
                        "last_alert_at",
                    ):
                        if key in updates and updates[key] is not None:
                            o[key] = updates[key]

                    if updates.get("status") == "CHIUSO":
                        if not o.get("closed_at"):
                            o["closed_at"] = datetime.now(timezone.utc).isoformat()
                        if o.get("exit_price_usd") is None:
                            sym = (o.get("ticker") or "").upper()
                            opp_price = ((opps.get(sym) or {}).get("quant_metrics") or {}).get("current_price")
                            locked_price = (
                                o.get("last_live_price_usd")
                                if o.get("last_live_price_usd") is not None
                                else (opp_price if opp_price is not None else o.get("entry_price_usd"))
                            )
                            if locked_price is not None:
                                o["exit_price_usd"] = round(float(locked_price), 4)
                    elif updates.get("status") == "APERTO":
                        o["exit_price_usd"] = None
                        o["closed_at"] = None
                        o["close_reason"] = None

                    orders[idx] = o
                    self._write_local(data)
                    updated_order = dict(o)
                    break

        if updated_order is not None and self._db is not None:
            try:
                self._db.collection("micro_orders").document(order_id).set(updated_order)
            except Exception:
                pass
        return updated_order

    def delete_micro_order(self, order_id: str) -> bool:
        with self._lock:
            data = self._read_local()
            orders = data.get("micro_orders", [])
            new_orders = [o for o in orders if o.get("id") != order_id]
            if len(new_orders) == len(orders):
                return False
            data["micro_orders"] = new_orders
            self._write_local(data)

        if self._db is not None:
            try:
                self._db.collection("micro_orders").document(order_id).delete()
            except Exception:
                pass
        return True

    # ------------------------------------------------------------------
    # Static Cloud Snapshot Exporter (GitHub Pages Read-Only Mode)
    # ------------------------------------------------------------------
    def export_frontend_snapshot(self, output_path: Path | None = None) -> Path:
        """Esporta uno snapshot JSON completo e atomico per il deploy statico su GitHub Pages."""
        target = output_path or settings.FRONTEND_SNAPSHOT_PATH
        target.parent.mkdir(parents=True, exist_ok=True)

        items = self.list_opportunities(min_score=0, limit=50)
        journal = self.list_micro_orders()
        cfg = self.get_autopilot_config()
        logs = self.list_autopilot_logs(limit=40)
        monitor_logs = [lg for lg in logs if lg.get("action") == "MONITOR_CHECK"]
        last_monitor_at = monitor_logs[0]["ts"] if monitor_logs else None

        snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "health": {
                "status": "ok",
                "storage_mode": self.backend_mode,
                "gemini_configured": bool(
                    settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_")
                ),
                "alert_threshold": settings.ALERT_SCORE_THRESHOLD,
                "monthly_micro_order_limit": settings.MONTHLY_MICRO_ORDER_LIMIT,
                "static_readonly": True,
            },
            "opportunities": {
                "count": len(items),
                "top_daily": [o for o in items if int(o.get("asymmetry_score", 0)) >= 55][:5],
                "items": items,
            },
            "journal": journal,
            "autopilot": {
                "config": cfg,
                "logs": logs,
                "last_monitor_at": last_monitor_at,
                "journal": journal,
            },
            "pipeline_runs": self.list_pipeline_runs()[:10],
        }

        with self._lock:
            tmp_path = target.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            os.replace(tmp_path, target)
        return target


storage = ScouterStorage()
