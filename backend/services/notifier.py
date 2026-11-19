"""Telegram Bot notification service for high-conviction asymmetric alerts & Auto-Pilot events."""

from __future__ import annotations

import html
from typing import Any
import requests

from config import settings


def _post_telegram_html(message: str) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return resp.ok
    except Exception:
        return False


def send_telegram_alert(record: dict[str, Any]) -> bool:
    """Send an HTML-escaped Telegram alert when a ticker exceeds ALERT_SCORE_THRESHOLD."""
    ticker = html.escape(str(record.get("ticker", "N/D")))
    company = html.escape(str(record.get("company_name", "")))
    score = int(record.get("asymmetry_score", 0))
    verdict = html.escape(str(record.get("verdict_label", "")))
    quant = record.get("quant_metrics") or {}
    tags = html.escape(", ".join(record.get("signal_tags") or []))
    thesis = "\n".join(html.escape(str(line)) for line in (record.get("thesis_5_lines") or []))

    runway_str = (
        "CF+"
        if quant.get("is_cash_flow_positive")
        else f"{quant.get('runway_months', 'N/D')}m"
    )
    dd_str = html.escape(str(quant.get("post_ipo_drawdown_pct", "N/D")))

    message = (
        f"🚨 <b>IPO &amp; Micro-Cap AI Scouter Alert</b>\n"
        f"<b>{ticker}</b> ({company})\n"
        f"🎯 <b>Asymmetry Score:</b> {score}/100 (<code>{verdict}</code>)\n"
        f"📉 <b>Post-IPO Drawdown:</b> {dd_str}% | ⏳ <b>Runway:</b> {runway_str}\n"
        f"🏷️ <b>Segnali:</b> {tags}\n\n"
        f"<b>Tesi in 5 righe:</b>\n{thesis}"
    )
    return _post_telegram_html(message)


def send_autopilot_event_alert(event_type: str, ticker: str, summary: str) -> bool:
    """Send an HTML-escaped Telegram notification for Auto-Pilot paper trades & real alerts."""
    safe_event = html.escape(str(event_type))
    safe_ticker = html.escape(str(ticker))
    safe_summary = html.escape(str(summary))
    icon = "🤖" if "AUTO_REGISTER" in event_type else ("🏁" if "AUTO_CLOSE" in event_type else "⚠️")
    message = (
        f"{icon} <b>Auto-Pilot Scouter [{safe_event}]</b>\n"
        f"<b>Ticker:</b> {safe_ticker}\n"
        f"{safe_summary}"
    )
    return _post_telegram_html(message)


def send_daily_portfolio_briefing(
    journal: dict[str, Any],
    top_candidates: list[dict[str, Any]] | None = None,
) -> bool:
    """Invia un aggiornamento riepilogativo giornaliero su Telegram con il valore del portafoglio e le posizioni."""
    from datetime import datetime, timezone

    summary = journal.get("summary") or {}
    orders = journal.get("orders") or []
    open_orders = [o for o in orders if o.get("status", "APERTO") == "APERTO"]

    equity = float(summary.get("paper_total_equity_eur") or summary.get("virtual_budget_eur") or 1000.0)
    budget = float(summary.get("virtual_budget_eur") or 1000.0)
    cash = float(summary.get("paper_cash_available_eur") or budget)
    invested = float(summary.get("paper_invested_eur") or 0.0)
    tot_pnl_eur = float(summary.get("total_pnl_eur") or 0.0)
    tot_pnl_pct = float(summary.get("total_pnl_pct") or 0.0)

    pnl_sign = "+" if tot_pnl_eur >= 0 else ""
    pnl_icon = "🟢" if tot_pnl_eur >= 0 else "🔴"
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    lines = [
        f"📊 <b>Briefing Giornaliero Portafoglio ({date_str})</b>",
        f"💼 <b>Equity Totale:</b> €{equity:.2f} ({pnl_sign}{tot_pnl_pct:.2f}% | {pnl_icon} {pnl_sign}€{tot_pnl_eur:.2f})",
        f"💵 <b>Cassa:</b> €{cash:.2f} | <b>Investito:</b> €{invested:.2f}",
        f"🛡️ <b>Slot Mese:</b> {summary.get('monthly_orders_used', 0)}/{summary.get('monthly_orders_limit', 10)} usati",
        "",
        f"<b>Posizioni Attive ({len(open_orders)}):</b>",
    ]

    if not open_orders:
        lines.append("<i>Nessuna posizione aperta al momento (100% liquidità).</i>")
    else:
        for ord_item in open_orders:
            sym = html.escape(str(ord_item.get("ticker", "N/D")))
            pnl_pos = float(ord_item.get("pnl_pct") or 0.0)
            sign_pos = "+" if pnl_pos >= 0 else ""
            pos_icon = "🟢" if pnl_pos >= 0 else "🔴"
            entry = float(ord_item.get("entry_price_usd") or 0.0)
            latest = float(ord_item.get("latest_price_usd") or ord_item.get("last_live_price_usd") or entry)
            val_eur = float(ord_item.get("current_value_eur") or ord_item.get("amount_eur") or 0.0)
            tp1_status = " <i>[Free-Ride attivo]</i>" if ord_item.get("tp1_executed") else ""
            lines.append(
                f"• <b>{sym}</b>: ${latest:.2f} (ingr. ${entry:.2f}) | {pos_icon} <b>{sign_pos}{pnl_pos:.1f}%</b> (€{val_eur:.2f}){tp1_status}"
            )

    if top_candidates:
        lines.append("")
        lines.append("<b>Top Segnali Filtrati Oggi:</b>")
        for cand in top_candidates[:3]:
            c_sym = html.escape(str(cand.get("ticker", "")))
            c_score = cand.get("asymmetry_score") or cand.get("score") or 0
            c_verd = html.escape(str(cand.get("verdict") or cand.get("verdict_label") or ""))
            lines.append(f"• <b>{c_sym}</b>: Score {c_score}/100 (<code>{c_verd}</code>)")

    lines.append("")
    lines.append("🔗 <a href=\"https://muso-lab.github.io/FinanceTool/\">Apri Dashboard Web</a>")

    return _post_telegram_html("\n".join(lines))
