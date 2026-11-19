"""Auto-Pilot Paper Trading Engine: Guardrail Auto-Registration, Virtual Budget & Multi-Tier Exit Monitor."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

import yfinance as yf

from services.notifier import send_autopilot_event_alert
from services.storage import ScouterStorage, storage as default_storage

logger = logging.getLogger("scouter_autopilot")


def fetch_fast_live_price(ticker: str) -> float | None:
    """Fetch latest quote quickly using yfinance fast_info with isolated 5d history fallback."""
    sym = ticker.strip().upper()
    tk = yf.Ticker(sym)
    try:
        fi = getattr(tk, "fast_info", None)
        if fi is not None:
            for key in ("lastPrice", "last_price", "regularMarketPrice", "previousClose"):
                val = fi.get(key) if isinstance(fi, dict) else getattr(fi, key, None)
                if val is not None:
                    num = float(val)
                    if num > 0:
                        return round(num, 4)
    except Exception as exc:
        logger.debug("fast_info failed for %s (%s), trying 5d history", sym, exc)

    try:
        hist = tk.history(period="5d", auto_adjust=True)
        if hist is not None and not hist.empty:
            val = float(hist["Close"].iloc[-1])
            if val > 0:
                return round(val, 4)
    except Exception as exc:
        logger.warning("Fast live price 5d fallback failed for %s: %s", sym, exc)
    return None


def _calculate_dynamic_ticket(
    opp: dict[str, Any],
    cfg: dict[str, Any],
    virtual_cash: float,
) -> float:
    """Calcola il ticket dinamico in base all'Asymmetry Score di Gemini (Dynamic Position Sizing)."""
    base = float(cfg.get("default_ticket_eur") or 35.0)
    if not cfg.get("enable_dynamic_sizing", False):
        return base

    score = int(opp.get("asymmetry_score") or 0)
    if score >= 90:
        multiplier = float(cfg.get("dynamic_size_score_90_multiplier") or 2.0)
        target = round(base * multiplier, 2)
    elif score >= 80:
        multiplier = float(cfg.get("dynamic_size_score_80_multiplier") or 1.43)
        target = round(base * multiplier, 2)
    else:
        target = base

    # Se la cassa è inferiore al target aumentato ma sufficiente per il ticket base, usa il cash disponibile
    if target > base and virtual_cash < target and virtual_cash >= base:
        return round(virtual_cash, 2)
    return round(target, 2)


def _evaluate_candidate_guardrails(
    opp: dict[str, Any],
    cfg: dict[str, Any],
    open_counts_by_ticker: dict[str, int],
    remaining_slots: int,
    virtual_cash_available: float,
    ticket_eur: float,
    open_counts_by_sector: dict[str, int] | None = None,
) -> tuple[bool, list[str]]:
    """Verify whether an analyzed opportunity satisfies every Auto-Pilot & virtual-budget guardrail."""
    reasons: list[str] = []
    sym = (opp.get("ticker") or "").upper()
    score = int(opp.get("asymmetry_score") or 0)
    auditor = (opp.get("debate") or {}).get("auditor") or {}
    bear = (opp.get("debate") or {}).get("bear") or {}
    quant = opp.get("quant_metrics") or {}
    sec = opp.get("sec_filings") or {}
    sector = (opp.get("sector") or quant.get("sector") or "").strip()

    audit_score = int(auditor.get("verification_score") or 0)
    is_cf_pos = bool(quant.get("is_cash_flow_positive"))
    runway = quant.get("runway_months")
    price = quant.get("current_price")
    monthly_limit = int(cfg.get("monthly_order_limit") or 10)

    if score < int(cfg["min_asymmetry_score"]):
        reasons.append(f"Score AI {score} < soglia {cfg['min_asymmetry_score']}")

    if audit_score < int(cfg["min_audit_score"]):
        reasons.append(f"Audit Contro-Verifica {audit_score}% < {cfg['min_audit_score']}%")

    if not is_cf_pos and (runway is None or float(runway) < float(cfg["min_runway_months"])):
        reasons.append(f"Runway {runway if runway is not None else 'N/D'}m < {cfg['min_runway_months']}m")

    if cfg.get("block_high_dilution_risk") and (
        bear.get("dilution_risk_level") == "ALTO" or sec.get("shelf_dilution_risk")
    ):
        reasons.append("Blocco attivo: rischio diluizione ALTO / S-3 shelf")

    if not price or float(price) <= 0:
        reasons.append("Prezzo corrente non valido")

    max_pos = int(cfg.get("max_positions_per_ticker") or 1)
    if open_counts_by_ticker.get(sym, 0) >= max_pos:
        reasons.append("Posizione già aperta su questo ticker")

    # Guardrail di concentrazione settoriale (Sector Concentration Cap)
    max_sec = int(cfg.get("max_positions_per_sector") or 2)
    if open_counts_by_sector and sector and sector.lower() not in ("", "unknown", "n/d"):
        if open_counts_by_sector.get(sector, 0) >= max_sec:
            reasons.append(f"Tetto settoriale: già {open_counts_by_sector[sector]}/{max_sec} posizioni nel settore '{sector}'")

    if cfg.get("respect_monthly_5_limit", True) and remaining_slots <= 0:
        reasons.append(f"Limite mensile {monthly_limit}/{monthly_limit} raggiunto")

    if virtual_cash_available < ticket_eur:
        reasons.append(f"Cassa virtuale insufficiente (€{virtual_cash_available:.2f} < €{ticket_eur:.2f})")

    return len(reasons) == 0, reasons


def evaluate_and_auto_register(
    dry_run: bool = False,
    force: bool = False,
    store: ScouterStorage | None = None,
) -> dict[str, Any]:
    """Screen opportunities against guardrails & virtual budget, opening qualifying PAPER_AUTO micro-orders."""
    st = store or default_storage
    cfg = st.get_autopilot_config()
    journal = st.list_micro_orders()
    summary = journal["summary"]
    remaining_slots = int(summary["monthly_slots_remaining"])
    virtual_cash = float(summary.get("paper_cash_available_eur", cfg.get("virtual_budget_eur", 1000.0)))
    ticket_eur = float(cfg.get("default_ticket_eur") or 35.0)

    if not cfg.get("enabled", True) and not dry_run and not force:
        return {
            "dry_run": False,
            "enabled": False,
            "registered": [],
            "skipped": [],
            "remaining_slots": remaining_slots,
            "virtual_cash_available_eur": round(virtual_cash, 2),
            "config_used": cfg,
            "message": "Auto-Pilot disabilitato nelle regole.",
            "journal": journal,
            "logs": st.list_autopilot_logs(),
        }

    opps = st.list_opportunities(min_score=0, limit=50)

    open_counts_by_ticker: dict[str, int] = {}
    open_counts_by_sector: dict[str, int] = {}
    for ord_item in journal["orders"]:
        if ord_item.get("status", "APERTO") == "APERTO":
            t = (ord_item.get("ticker") or "").upper()
            open_counts_by_ticker[t] = open_counts_by_ticker.get(t, 0) + 1
            t_opp = st.get_opportunity(t)
            sec = ((t_opp.get("sector") if t_opp else None) or "").strip()
            if sec:
                open_counts_by_sector[sec] = open_counts_by_sector.get(sec, 0) + 1

    registered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for opp in opps:
        sym = (opp.get("ticker") or "").upper()
        # Calcolo ticket dinamico in base all'Asymmetry Score
        dynamic_ticket = _calculate_dynamic_ticket(opp, cfg, virtual_cash)
        passed, reasons = _evaluate_candidate_guardrails(
            opp,
            cfg,
            open_counts_by_ticker,
            remaining_slots,
            virtual_cash,
            dynamic_ticket,
            open_counts_by_sector=open_counts_by_sector,
        )
        if not passed:
            skipped.append(
                {
                    "ticker": sym,
                    "asymmetry_score": opp.get("asymmetry_score"),
                    "audit_score": ((opp.get("debate") or {}).get("auditor") or {}).get("verification_score"),
                    "reasons": reasons,
                }
            )
            continue

        quant = opp.get("quant_metrics") or {}
        price = float(quant["current_price"])
        thesis_lines = opp.get("thesis_5_lines") or []
        initial_thesis = (
            " ".join(thesis_lines[:2])
            if thesis_lines
            else f"Auto-Pilot Asymmetry Score {opp.get('asymmetry_score')}/100"
        )
        invalidation_rule = (opp.get("micro_strategy") or {}).get("invalidation_trigger") or (
            f"TP1 +{cfg['tp1_pct']}% / TP2 +{cfg['take_profit_pct']}% / SL {cfg['stop_loss_pct']}%"
        )

        if dry_run:
            registered.append(
                {
                    "ticker": sym,
                    "asymmetry_score": opp.get("asymmetry_score"),
                    "entry_price_usd": price,
                    "amount_eur": dynamic_ticket,
                    "mode": "PAPER_AUTO",
                    "take_profit_pct": cfg["take_profit_pct"],
                    "stop_loss_pct": cfg["stop_loss_pct"],
                }
            )
        else:
            try:
                order = st.add_micro_order(
                    {
                        "ticker": sym,
                        "amount_eur": dynamic_ticket,
                        "entry_price_usd": price,
                        "broker": cfg.get("default_broker") or "Trading 212 (Paper)",
                        "fractional": True,
                        "mode": "PAPER_AUTO",
                        "auto_registered": True,
                        "take_profit_pct": cfg["take_profit_pct"],
                        "stop_loss_pct": cfg["stop_loss_pct"],
                        "initial_thesis": initial_thesis,
                        "invalidation_rule": invalidation_rule,
                        "initial_ai_score": opp.get("asymmetry_score"),
                        "override_monthly_limit": not cfg.get("respect_monthly_5_limit", True),
                    }
                )
            except ValueError as exc:
                skipped.append(
                    {
                        "ticker": sym,
                        "asymmetry_score": opp.get("asymmetry_score"),
                        "audit_score": ((opp.get("debate") or {}).get("auditor") or {}).get("verification_score"),
                        "reasons": [str(exc)],
                    }
                )
                continue

            registered.append(order)
            msg = (
                f"Auto-registrato micro-ordine PAPER_AUTO €{dynamic_ticket:.2f} su {sym} @ ${price:.2f} "
                f"(Score {opp.get('asymmetry_score')}/100, TP1 +{cfg['tp1_pct']}%, TP2 +{cfg['take_profit_pct']}%)."
            )
            st.append_autopilot_log(
                "AUTO_REGISTER",
                sym,
                msg,
                {"order_id": order["id"], "score": opp.get("asymmetry_score"), "price_usd": price},
            )
            if cfg.get("notify_telegram"):
                send_autopilot_event_alert("AUTO_REGISTER", sym, msg)

        open_counts_by_ticker[sym] = open_counts_by_ticker.get(sym, 0) + 1
        cand_sec = ((opp.get("sector") or quant.get("sector") or "")).strip()
        if cand_sec:
            open_counts_by_sector[cand_sec] = open_counts_by_sector.get(cand_sec, 0) + 1
        virtual_cash = round(virtual_cash - dynamic_ticket, 2)
        if cfg.get("respect_monthly_5_limit", True):
            remaining_slots = max(0, remaining_slots - 1)

    if not dry_run and skipped and not registered:
        st.append_autopilot_log(
            "SKIPPED_GUARDRAIL",
            "ALL",
            f"Nessun nuovo ordine auto-registrato: {len(skipped)} candidati filtrati dai guardrail.",
            {"skipped_tickers": [s["ticker"] for s in skipped[:6]]},
        )

    return {
        "dry_run": dry_run,
        "enabled": cfg.get("enabled", True),
        "registered": registered,
        "skipped": skipped,
        "remaining_slots": remaining_slots,
        "virtual_cash_available_eur": round(virtual_cash, 2),
        "config_used": cfg,
        "journal": st.list_micro_orders(),
        "logs": st.list_autopilot_logs(),
    }


def _should_send_real_alert(ord_item: dict[str, Any], alert_key: str, now_dt: datetime) -> bool:
    """Deduplicate REAL alerts using canonical trigger key across a 12-hour cooldown."""
    if ord_item.get("last_alert_reason") != alert_key:
        return True
    last_at = ord_item.get("last_alert_at")
    if not last_at:
        return True
    try:
        prev_dt = datetime.fromisoformat(last_at)
        return (now_dt - prev_dt).total_seconds() >= 12 * 3600
    except Exception:
        return True


def run_portfolio_monitor(
    refresh_live_prices: bool = True,
    rescan_ai: bool = False,
    store: ScouterStorage | None = None,
    price_fetcher: Callable[[str], float | None] | None = None,
) -> dict[str, Any]:
    """Monitor open positions: refresh quotes, track peaks, and execute TP1 Free-Ride / TP2 / Trailing / SL / Thesis exits."""
    st = store or default_storage
    fetcher = price_fetcher or fetch_fast_live_price
    cfg = st.get_autopilot_config()
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    journal_before = st.list_micro_orders()
    open_orders = [o for o in journal_before["orders"] if o.get("status", "APERTO") == "APERTO"]

    unique_tickers = list(dict.fromkeys((o.get("ticker") or "").upper() for o in open_orders if o.get("ticker")))
    live_quotes: dict[str, float] = {}
    rescanned_opps: dict[str, dict[str, Any]] = {}

    if rescan_ai:
        from scouter_pipeline import analyze_single_ticker

        for sym in unique_tickers:
            try:
                rec = analyze_single_ticker(sym, save_to_store=True, notify=False)
                rescanned_opps[sym] = rec
                p = (rec.get("quant_metrics") or {}).get("current_price")
                if p is not None and float(p) > 0:
                    live_quotes[sym] = float(p)
            except Exception as exc:
                logger.warning("Monitor AI rescan failed for %s: %s", sym, exc)

    if refresh_live_prices:
        for sym in unique_tickers:
            if sym not in live_quotes:
                q_price = fetcher(sym)
                if q_price is not None and q_price > 0:
                    live_quotes[sym] = q_price

    price_updates: list[dict[str, Any]] = []
    partial_exits: list[dict[str, Any]] = []
    auto_closed: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []

    for ord_item in open_orders:
        sym = (ord_item.get("ticker") or "").upper()
        entry_price = float(ord_item.get("entry_price_usd") or 0.0)
        opp = rescanned_opps.get(sym) or st.get_opportunity(sym)

        fresh_price = live_quotes.get(sym)
        if fresh_price is not None:
            eval_price = float(fresh_price)
        else:
            eval_price = float(
                ord_item.get("raw_latest_price_usd")
                or ord_item.get("last_live_price_usd")
                or entry_price
            )

        latest_score = ord_item.get("latest_ai_score")
        if opp:
            latest_score = opp.get("asymmetry_score", latest_score)

        pnl_pct = round(((eval_price - entry_price) / entry_price) * 100.0, 2) if entry_price > 0 else 0.0
        peak_price = max(float(ord_item.get("peak_price_usd") or entry_price), eval_price)
        peak_gain_pct = round(((peak_price - entry_price) / entry_price) * 100.0, 2) if entry_price > 0 else 0.0
        pullback_from_peak_pct = (
            round(((peak_price - eval_price) / peak_price) * 100.0, 2) if peak_price > 0 else 0.0
        )

        if fresh_price is not None:
            st.record_order_checkpoint(
                order_id=ord_item["id"],
                price_usd=eval_price,
                ai_score=latest_score,
                pnl_pct=pnl_pct,
                monitored_at=now_iso,
            )

        price_updates.append(
            {
                "order_id": ord_item["id"],
                "ticker": sym,
                "price_usd": eval_price,
                "pnl_pct": pnl_pct,
                "ai_score": latest_score,
                "live_quote_fetched": fresh_price is not None,
            }
        )

        mode = ord_item.get("mode") or ("PAPER_AUTO" if ord_item.get("auto_registered") else "PAPER_MANUAL")
        is_paper = mode in ("PAPER_AUTO", "PAPER_MANUAL")

        tp_target = float(
            ord_item.get("take_profit_pct")
            if ord_item.get("take_profit_pct") is not None
            else cfg["take_profit_pct"]
        )
        sl_target = float(
            ord_item.get("stop_loss_pct")
            if ord_item.get("stop_loss_pct") is not None
            else cfg["stop_loss_pct"]
        )
        initial_score = ord_item.get("initial_ai_score")

        # Scala obiettivi di uscita:
        # 1) Hard Stop-Loss (o Break-Even Stop a 0% dopo TP1)
        # 2) TP2 Finale (chiusura totale al raggiungimento del target massimo)
        # 3) TP1 Parziale "Free Ride" (incassa metà posizione a +35% e sposta SL a 0%)
        # 4) Trailing Stop protettivo (protegge guadagni dopo un picco >= +25%)
        # 5) Thesis Stop AI (degrado fondamentale o diluizione)
        close_reason: str | None = None
        close_key: str | None = None
        if cfg.get("auto_close_on_tp_sl", True) or not is_paper:
            if pnl_pct <= sl_target:
                label = "BREAK_EVEN_STOP" if (ord_item.get("tp1_executed") and sl_target == 0.0) else "STOP_LOSS"
                close_key = label
                close_reason = f"{label} ({pnl_pct:.1f}% <= {sl_target:.1f}%)"
            elif pnl_pct >= tp_target:
                close_key = "TAKE_PROFIT_FINAL"
                close_reason = f"TAKE_PROFIT_FINAL (+{pnl_pct:.1f}% >= +{tp_target:.1f}%)"

        # TP1 Parziale (solo se non ha già attivato TP2 / SL)
        if (
            close_reason is None
            and cfg.get("enable_partial_tp1", True)
            and not ord_item.get("tp1_executed", False)
            and pnl_pct >= float(cfg.get("tp1_pct") or 35.0)
        ):
            tp1_pct = float(cfg.get("tp1_pct") or 35.0)
            sell_ratio = max(10.0, min(90.0, float(cfg.get("tp1_sell_ratio_pct") or 50.0))) / 100.0
            tp1_label = f"TP1_PARZIALE (+{pnl_pct:.1f}% >= +{tp1_pct:.1f}%)"
            if is_paper:
                active_amt = float(ord_item.get("amount_eur") or 0.0)
                sold_basis = round(active_amt * sell_ratio, 2)
                remaining_amt = round(active_amt - sold_basis, 2)
                ratio = (eval_price / entry_price) if entry_price > 0 else 1.0
                sold_proceeds = round(sold_basis * ratio, 2)
                tp1_profit = round(sold_proceeds - sold_basis, 2)
                new_partial_realized = round(float(ord_item.get("partial_realized_pnl_eur") or 0.0) + tp1_profit, 2)
                note = (
                    f"TP1 +{pnl_pct:.1f}% @ ${eval_price:.2f}: venduto {int(sell_ratio * 100)}% "
                    f"(+€{tp1_profit:.2f} incassati), SL spostato a 0% Break-Even."
                )
                st.update_micro_order(
                    ord_item["id"],
                    {
                        "amount_eur": remaining_amt,
                        "partial_realized_pnl_eur": new_partial_realized,
                        "tp1_executed": True,
                        "tp1_note": note,
                        "stop_loss_pct": 0.0,
                        "peak_price_usd": peak_price,
                    },
                )
                st.append_autopilot_log(
                    "PARTIAL_TP1",
                    sym,
                    note,
                    {"order_id": ord_item["id"], "profit_eur": tp1_profit, "remaining_eur": remaining_amt},
                )
                if cfg.get("notify_telegram"):
                    send_autopilot_event_alert("PARTIAL_TP1", sym, note)
                partial_exits.append({"order_id": ord_item["id"], "ticker": sym, "profit_eur": tp1_profit})
                # La restante quota paper prosegue in Free-Ride fino al prossimo ciclo
                continue
            else:
                # Per gli ordini REAL emette alert TP1 con cooldown canonico ma prosegue
                # la valutazione di Trailing Stop e Thesis Stop (niente `continue`!).
                if _should_send_real_alert(ord_item, "TP1_PARZIALE", now_dt):
                    st.update_micro_order(
                        ord_item["id"],
                        {"last_alert_reason": "TP1_PARZIALE", "last_alert_at": now_iso},
                    )
                    ord_item["last_alert_reason"] = "TP1_PARZIALE"
                    ord_item["last_alert_at"] = now_iso
                    msg = f"Posizione REALE {sym} ha raggiunto {tp1_label} (@ ${eval_price:.2f}). Valuta presa di profitto parziale."
                    st.append_autopilot_log("ALERT", sym, msg, {"order_id": ord_item["id"], "reason": tp1_label})
                    if cfg.get("notify_telegram"):
                        send_autopilot_event_alert("ALERT", sym, msg)
                alerts.append({"order_id": ord_item["id"], "ticker": sym, "reason": tp1_label, "pnl_pct": pnl_pct})

        # Trailing Stop protettivo
        if (
            close_reason is None
            and cfg.get("enable_trailing_stop", True)
            and peak_gain_pct >= float(cfg.get("trailing_activation_pct") or 25.0)
            and pullback_from_peak_pct >= float(cfg.get("trailing_stop_pct") or 15.0)
        ):
            close_key = "TRAILING_STOP"
            close_reason = (
                f"TRAILING_STOP (-{pullback_from_peak_pct:.1f}% dal picco ${peak_price:.2f}, P&L {pnl_pct:+.1f}%)"
            )

        # Thesis Stop (degrado AI Score)
        if close_reason is None and cfg.get("auto_close_on_thesis_degrade", True) and latest_score is not None:
            min_s = int(cfg.get("thesis_degrade_min_score") or 55)
            drop_pts = int(cfg.get("thesis_degrade_drop_pts") or 18)
            score_dropped = initial_score is not None and (int(initial_score) - int(latest_score)) >= drop_pts
            entered_above_min = initial_score is None or int(initial_score) >= min_s
            if entered_above_min and int(latest_score) < min_s:
                close_key = "THESIS_STOP"
                close_reason = f"THESIS_STOP (AI Score {latest_score} < {min_s})"
            elif score_dropped:
                close_key = "THESIS_STOP"
                close_reason = f"THESIS_STOP (Calo Score {initial_score} -> {latest_score})"

        # Time Stop (uscita disciplinata se il titolo rimane piatto dopo N giorni)
        if close_reason is None and cfg.get("enable_time_stop", True) and is_paper:
            created_str = ord_item.get("created_at") or ord_item.get("order_date")
            if created_str:
                try:
                    c_dt = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
                    age_days = (now_dt - c_dt).days
                    max_days = int(cfg.get("time_stop_days") or 60)
                    max_band = float(cfg.get("time_stop_max_pnl_pct") or 10.0)
                    if age_days >= max_days and abs(pnl_pct) <= max_band:
                        close_key = "TIME_STOP_EXPIRED"
                        close_reason = f"TIME_STOP ({age_days}gg >= {max_days}gg piatto, capitale riallocato)"
                except Exception:
                    pass

        # Regola di sicurezza: le posizioni simulate si chiudono automaticamente;
        # le posizioni REAL non vengono mai toccate automaticamente (solo alert deduplicato 12h).
        if close_reason:
            if is_paper:
                st.update_micro_order(
                    ord_item["id"],
                    {
                        "status": "CHIUSO",
                        "exit_price_usd": round(eval_price, 4),
                        "closed_at": now_iso,
                        "close_reason": close_reason,
                        "peak_price_usd": peak_price,
                    },
                )
                msg = f"Chiusa posizione simulata {sym} ({mode}) @ ${eval_price:.2f} | P&L {pnl_pct:+.2f}% | {close_reason}"
                st.append_autopilot_log(
                    "AUTO_CLOSE",
                    sym,
                    msg,
                    {"order_id": ord_item["id"], "reason": close_reason, "pnl_pct": pnl_pct},
                )
                if cfg.get("notify_telegram"):
                    send_autopilot_event_alert("AUTO_CLOSE", sym, msg)
                auto_closed.append({"order_id": ord_item["id"], "ticker": sym, "reason": close_reason, "pnl_pct": pnl_pct})
            else:
                alert_key = close_key or close_reason
                if _should_send_real_alert(ord_item, alert_key, now_dt):
                    st.update_micro_order(
                        ord_item["id"],
                        {"last_alert_reason": alert_key, "last_alert_at": now_iso},
                    )
                    msg = f"Posizione REALE {sym} ha attivato {close_reason} (@ ${eval_price:.2f}, {pnl_pct:+.2f}%). Nessuna chiusura automatica."
                    st.append_autopilot_log(
                        "ALERT",
                        sym,
                        msg,
                        {"order_id": ord_item["id"], "reason": close_reason, "pnl_pct": pnl_pct},
                    )
                    if cfg.get("notify_telegram"):
                        send_autopilot_event_alert("ALERT", sym, msg)
                alerts.append({"order_id": ord_item["id"], "ticker": sym, "reason": close_reason, "pnl_pct": pnl_pct})

    st.append_autopilot_log(
        "MONITOR_CHECK",
        ",".join(unique_tickers) if unique_tickers else "NONE",
        f"Monitorate {len(open_orders)} posizioni aperte ({len(live_quotes)} quote aggiornate, {len(partial_exits)} TP1 parziali, {len(auto_closed)} chiusure).",
        {"checked_count": len(open_orders), "rescan_ai": rescan_ai},
    )

    return {
        "monitored_at": now_iso,
        "checked_count": len(open_orders),
        "price_updates": price_updates,
        "partial_exits": partial_exits,
        "auto_closed": auto_closed,
        "alerts": alerts,
        "journal": st.list_micro_orders(),
        "logs": st.list_autopilot_logs(),
    }
