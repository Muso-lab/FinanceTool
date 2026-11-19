"""Configurazione centrale per IPO & Micro-Cap AI Scouter.

Raccoglie le variabili d'ambiente (con fallback sicuri per evitare stringhe vuote
in GitHub Actions), i percorsi di persistenza e i parametri quantitativi di screening.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORE_PATH = DATA_DIR / "scouter_store.json"
# Snapshot statico letto dal frontend su GitHub Pages quando il backend FastAPI non è attivo
FRONTEND_SNAPSHOT_PATH = BASE_DIR.parent / "frontend" / "public" / "scouter_snapshot.json"

load_dotenv(BASE_DIR / ".env")


def _env_str(key: str, default: str) -> str:
    """Restituisce la variabile d'ambiente pulita o il default se vuota/assente."""
    val = os.getenv(key)
    return val.strip() if (val is not None and val.strip()) else default


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    try:
        return int(val.strip()) if (val is not None and val.strip()) else default
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    try:
        return float(val.strip()) if (val is not None and val.strip()) else default
    except ValueError:
        return default


class Settings:
    """Parametri runtime caricati da .env o environment variables CI."""

    # Motore AI Gemini (opzionale: se assente attiva il motore forense deterministico locale)
    GEMINI_API_KEY: str = _env_str("GEMINI_API_KEY", "")
    GEMINI_MODEL_FAST: str = _env_str("GEMINI_MODEL_FAST", "gemini-3.8-flash")
    GEMINI_MODEL_REASONING: str = _env_str("GEMINI_MODEL_REASONING", "gemini-3.8-flash")

    # Provider dati mercato e SEC EDGAR (User-Agent obbligatorio per evitare HTTP 403 da sec.gov)
    FINNHUB_API_KEY: str = _env_str("FINNHUB_API_KEY", "")
    ALPHA_VANTAGE_API_KEY: str = _env_str("ALPHA_VANTAGE_API_KEY", "")
    SEC_USER_AGENT: str = _env_str(
        "SEC_USER_AGENT",
        "IPOMicroCapScouter/1.0 (personal-research@example.com)",
    )

    # Persistenza duale (Firebase Firestore opzionale + JSON locale versionabile)
    FIREBASE_SERVICE_ACCOUNT_PATH: str = _env_str("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    FIREBASE_PROJECT_ID: str = _env_str("FIREBASE_PROJECT_ID", "")
    STORE_PATH: Path = STORE_PATH
    FRONTEND_SNAPSHOT_PATH: Path = FRONTEND_SNAPSHOT_PATH

    # Notifiche Telegram Bot per alert asimmetrici ed eventi Auto-Pilot
    TELEGRAM_BOT_TOKEN: str = _env_str("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = _env_str("TELEGRAM_CHAT_ID", "")
    ALERT_SCORE_THRESHOLD: int = _env_int("ALERT_SCORE_THRESHOLD", 75)

    # Soglie quantitative di screening post-IPO
    IPO_MIN_MONTHS: int = _env_int("IPO_MIN_MONTHS", 6)
    IPO_MAX_MONTHS: int = _env_int("IPO_MAX_MONTHS", 24)
    MIN_POST_IPO_DRAWDOWN_PCT: float = _env_float("MIN_POST_IPO_DRAWDOWN_PCT", 15.0)
    MAX_POST_IPO_DRAWDOWN_PCT: float = _env_float("MAX_POST_IPO_DRAWDOWN_PCT", 88.0)
    MIN_RUNWAY_MONTHS: float = _env_float("MIN_RUNWAY_MONTHS", 12.0)
    MIN_REV_GROWTH_YOY: float = _env_float("MIN_REV_GROWTH_YOY", 0.0)
    MAX_MARKET_CAP_USD: float = _env_float("MAX_MARKET_CAP_USD", 5_000_000_000.0)

    # Disciplina portafoglio micro-ordini (max 10 operazioni mensili da poche decine di euro)
    MONTHLY_MICRO_ORDER_LIMIT: int = _env_int("MONTHLY_MICRO_ORDER_LIMIT", 10)
    DEFAULT_MICRO_ORDER_EUR: float = _env_float("DEFAULT_MICRO_ORDER_EUR", 35.0)

    # Universo curato di default affiancato dal calendario IPO Finnhub
    DEFAULT_UNIVERSE: list[str] = [
        "RDW",
        "PL",
        "BKSY",
        "OUST",
        "TEM",
        "ALAB",
        "ASTS",
        "ENVX",
        "HNST",
        "NRDY",
        "COOK",
        "SOUN",
        "SERV",
        "RKLB",
    ]


settings = Settings()
