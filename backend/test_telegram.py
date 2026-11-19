"""Invia un messaggio di prova su Telegram per verificare TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.

Uso locale:  python test_telegram.py
Su GitHub:   Actions -> "Test Telegram Notification" -> Run workflow
"""

from __future__ import annotations

import sys

import requests

from config import settings


def main() -> int:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        print("ERRORE: TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID non impostati.")
        return 1

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "✅ IPO & Micro-Cap AI Scouter: notifiche Telegram attive!\n"
            "Riceverai qui alert su nuovi segnali (score ≥ soglia), ordini paper aperti, "
            "TP1 parziali, chiusure TP/SL/Trailing.",
        },
        timeout=15,
    )
    if resp.ok:
        print("OK: messaggio inviato su Telegram.")
        return 0
    print(f"ERRORE Telegram HTTP {resp.status_code}: {resp.text}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
