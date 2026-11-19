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
