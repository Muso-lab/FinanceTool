"""Alternative data engine: RSS News, Careers/Hiring Signals, and Broker Fractional Check."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

import feedparser
import requests
import yfinance as yf
from bs4 import BeautifulSoup

# Regex con confini di parola (\b) per evitare falsi positivi come "cut" dentro "executive" o "cutting-edge"
_CATALYST_RE = re.compile(
    r"\b(patent|patents|contract|contracts|award|awarded|partnership|fda|breakthrough|"
    r"launch|milestone|expansion|defense|nasa|commercial|backlog|deal|agreement|order|approval|clearance|wins|secures)\b",
    re.IGNORECASE,
)

_RISK_RE = re.compile(
    r"\b(offering|dilution|dilutive|shelf|warrant|warrants|lawsuit|investigation|layoff|layoffs|"
    r"job cuts|workforce reduction|downgrade|delay|shortfall|going concern|bankruptcy|restatement|delisting)\b",
    re.IGNORECASE,
)

_STOPWORDS_COMPANY = re.compile(
    r"^(the|a|an)\s+",
    re.IGNORECASE,
)


def _classify_headline(title: str) -> str:
    has_cat = bool(_CATALYST_RE.search(title))
    has_risk = bool(_RISK_RE.search(title))
    if has_cat and not has_risk:
        return "CATALYST"
    if has_risk and not has_cat:
        return "RISK"
    if has_cat and has_risk:
        return "MIXED"
    return "NEUTRAL"


def fetch_ticker_news(ticker: str, company_name: str = "", limit: int = 6) -> dict[str, Any]:
    """Aggregate recent news from Google News RSS and yfinance fallback."""
    symbol = ticker.strip().upper()
    cleaned_name = _STOPWORDS_COMPANY.sub("", company_name or "").strip()
    name_token = cleaned_name.split()[0] if cleaned_name else ""
    query = quote_plus(f"{symbol} stock {name_token}".strip())
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    articles: list[dict[str, Any]] = []
    try:
        resp = requests.get(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; IPOMicroCapScouter/1.0)"},
            timeout=8,
        )
        if resp.ok:
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:limit]:
                title = entry.get("title", "").strip()
                source_obj = entry.get("source")
                source_title = source_obj.get("title") if isinstance(source_obj, dict) else "Google News"
                articles.append(
                    {
                        "title": title,
                        "url": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "source": source_title or "News RSS",
                        "sentiment_hint": _classify_headline(title),
                    }
                )
    except Exception:
        pass

    if not articles:
        try:
            yf_news = yf.Ticker(symbol).news or []
            for item in yf_news[:limit]:
                content = item.get("content", item)
                title = (content.get("title") or item.get("title") or "").strip()
                link = (
                    (content.get("canonicalUrl") or {}).get("url")
                    or item.get("link")
                    or ""
                )
                if title:
                    articles.append(
                        {
                            "title": title,
                            "url": link,
                            "published": content.get("pubDate") or "",
                            "source": (content.get("provider") or {}).get("displayName") or "Yahoo Finance",
                            "sentiment_hint": _classify_headline(title),
                        }
                    )
        except Exception:
            pass

    catalyst_count = sum(1 for a in articles if a["sentiment_hint"] == "CATALYST")
    risk_count = sum(1 for a in articles if a["sentiment_hint"] == "RISK")

    return {
        "articles": articles,
        "catalyst_headlines_count": catalyst_count,
        "risk_headlines_count": risk_count,
    }


def _slug_candidates(company_name: str, website: str, ticker: str) -> list[str]:
    slugs: list[str] = []
    if website:
        host = re.sub(r"^https?://(www\.)?", "", website.lower()).split("/")[0]
        parts = [p for p in host.split(".") if p and p not in ("ir", "investors", "investor", "com", "io", "ai", "co", "net", "org")]
        if parts:
            slugs.append(parts[0])
    if company_name:
        cleaned = re.sub(
            r"\b(inc|corp|corporation|ltd|llc|holdings|group|technologies|tech|co)\b",
            "",
            company_name.lower(),
        )
        words = re.findall(r"[a-z0-9]+", cleaned)
        if words:
            slugs.append("-".join(words))
            slugs.append("".join(words))
            slugs.append(words[0])
    slugs.append(ticker.lower())
    seen: set[str] = set()
    return [s for s in slugs if len(s) >= 2 and not (s in seen or seen.add(s))]


def analyze_hiring_signals(
    ticker: str,
    company_name: str = "",
    website: str = "",
    news_articles: list[dict[str, Any]] | None = None,
    employees_count: int | None = None,
) -> dict[str, Any]:
    """Probe public ATS boards (Greenhouse/Lever/Ashby) and career pages for hiring spikes vs layoffs."""
    slugs = _slug_candidates(company_name, website, ticker)
    open_roles_count: int | None = None
    ats_source = ""
    careers_url = f"{website.rstrip('/')}/careers" if website else ""
    sample_titles: list[str] = []

    for slug in slugs[:3]:
        # 1) Greenhouse public API
        try:
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                timeout=3.5,
            )
            if r.ok:
                jobs = r.json().get("jobs", [])
                if isinstance(jobs, list) and len(jobs) > 0:
                    open_roles_count = len(jobs)
                    ats_source = "Greenhouse"
                    careers_url = f"https://boards.greenhouse.io/{slug}"
                    sample_titles = [j.get("title", "") for j in jobs[:10] if j.get("title")]
                    break
        except Exception:
            pass

        # 2) Lever public API
        try:
            r = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                timeout=3.5,
            )
            if r.ok:
                jobs = r.json()
                if isinstance(jobs, list) and len(jobs) > 0:
                    open_roles_count = len(jobs)
                    ats_source = "Lever"
                    careers_url = f"https://jobs.lever.co/{slug}"
                    sample_titles = [j.get("text", "") for j in jobs[:10] if j.get("text")]
                    break
        except Exception:
            pass

        # 3) Ashby public API
        try:
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                timeout=3.5,
            )
            if r.ok:
                jobs = r.json().get("jobs", [])
                if isinstance(jobs, list) and len(jobs) > 0:
                    open_roles_count = len(jobs)
                    ats_source = "Ashby"
                    careers_url = f"https://jobs.ashbyhq.com/{slug}"
                    sample_titles = [j.get("title", "") for j in jobs[:10] if j.get("title")]
                    break
        except Exception:
            pass

    # Fallback lightweight scrape of /careers looking strictly for actual job URLs or embedded ATS links
    if open_roles_count is None and website:
        for path in ("/careers", "/jobs"):
            target = f"{website.rstrip('/')}{path}"
            try:
                r = requests.get(
                    target,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; IPOMicroCapScouter/1.0)"},
                    timeout=4,
                )
                if r.ok and len(r.text) > 500:
                    soup = BeautifulSoup(r.text, "html.parser")
                    job_links: list[str] = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"].lower()
                        txt = a.get_text(" ", strip=True)
                        is_job_href = any(
                            p in href
                            for p in ("/job/", "/jobs/", "/position", "/opening", "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com")
                        )
                        is_role_title = any(
                            kw in txt.lower()
                            for kw in ("engineer", "scientist", "manager", "director", "sales", "analyst", "developer", "architect")
                        )
                        if is_job_href and is_role_title and len(txt) < 90:
                            job_links.append(txt)
                    if job_links:
                        open_roles_count = len(set(job_links))
                        ats_source = "Company Careers Page"
                        careers_url = target
                        sample_titles = list(dict.fromkeys(job_links))[:8]
                        break
            except Exception:
                continue

    layoff_news = False
    expansion_news = False
    for art in news_articles or []:
        t = (art.get("title") or "").lower()
        if re.search(r"\b(layoff|layoffs|workforce reduction|job cut|job cuts|restructuring)\b", t):
            layoff_news = True
        if re.search(r"\b(expansion|new facility|hiring|factory|contract)\b", t):
            expansion_news = True

    dept_focus = "Bilanciato"
    joined_titles = " ".join(sample_titles).lower()
    if any(k in joined_titles for k in ("engineer", "scientist", "r&d", "software", "hardware", "ai")):
        dept_focus = "R&D / Engineering"
    elif any(k in joined_titles for k in ("sales", "account", "revenue", "business development")):
        dept_focus = "Espansione Commerciale"

    # Normalize spike threshold if fullTimeEmployees is known (e.g. >= 20 roles or >= 4% of headcount)
    spike_threshold = 20
    if employees_count and employees_count > 0:
        spike_threshold = max(12, min(40, round(employees_count * 0.04)))

    if layoff_news and not (open_roles_count and open_roles_count >= spike_threshold):
        hiring_trend = "FREEZE_OR_CUTS"
        evidence_note = "Segnalati tagli organico / ristrutturazione nelle news recenti."
    elif open_roles_count is not None and open_roles_count >= spike_threshold:
        hiring_trend = "HIRING_SPIKE"
        evidence_note = (
            f"Rilevate {open_roles_count} posizioni aperte via {ats_source} (focus {dept_focus})"
            + (" nonostante news di ristrutturazione." if layoff_news else ".")
        )
    elif open_roles_count is not None and open_roles_count >= 1:
        hiring_trend = "STABLE"
        evidence_note = f"{open_roles_count} ruoli aperti individuati su {ats_source} (assunzioni selettive)."
    elif expansion_news:
        hiring_trend = "STABLE"
        evidence_note = "Nessun board ATS pubblico diretto; news indicano espansione operativa."
    else:
        hiring_trend = "UNKNOWN"
        evidence_note = "Board careers proprietario o dietro JS; verifica manuale consigliata."

    return {
        "open_roles_count": open_roles_count,
        "hiring_trend": hiring_trend,
        "department_focus": dept_focus,
        "ats_source": ats_source or "N/D",
        "careers_url": careers_url,
        "sample_roles": sample_titles[:5],
        "evidence_note": evidence_note,
    }


def check_broker_fractional_availability(
    ticker: str,
    exchange: str = "NASDAQ",
    current_price: float | None = None,
    market_cap: float | None = None,
) -> list[dict[str, Any]]:
    """Evaluate zero-commission & fractional share support on retail platforms used in Europe/Italy."""
    ex = (exchange or "NASDAQ").upper()
    is_major_us = any(k in ex for k in ("NASDAQ", "NMS", "NCM", "NGM", "NYSE", "NYQ", "ASE", "PCX", "BATS", "BTS", "CBOE"))
    is_tiny_micro = market_cap is not None and market_cap < 200_000_000
    price_usd = current_price or 0.0
    approx_price_eur = round(price_usd * 0.92, 2) if price_usd > 0 else 25.0
    fits_whole_micro = 0 < approx_price_eur <= 35.0

    t212_status = "DISPONIBILE_0_COMM" if is_major_us and not is_tiny_micro else "VERIFICA_MICRO_CAP"
    ibkr_status = "DISPONIBILE_FRAZIONATO" if is_major_us else "VERIFICA_MICRO_CAP"
    tr_status = "DISPONIBILE_FRAZIONATO" if is_major_us and (market_cap is None or market_cap >= 400_000_000) else "VERIFICA_MICRO_CAP"
    rev_status = "DISPONIBILE_0_COMM" if is_major_us and (market_cap is None or market_cap >= 400_000_000) else "VERIFICA_MICRO_CAP"

    return [
        {
            "broker": "Trading 212",
            "fractional_supported": is_major_us,
            "zero_commission": True,
            "min_order_amount": 1.0,
            "min_order_currency": "EUR",
            "fx_fee": "0.15%",
            "italian_tax_regime": "Dichiarativo",
            "status": t212_status,
            "notes": (
                f"{ticker} negoziabile frazionato da €1 su {ex}; commissione 0% (solo 0.15% FX)."
                if is_major_us and not is_tiny_micro
                else f"Micro-cap/listino {ex}: verifica disponibilità frazionata in-app su Trading 212."
            ),
        },
        {
            "broker": "Interactive Brokers (IBKR)",
            "fractional_supported": is_major_us,
            "zero_commission": False,
            "min_order_amount": 1.0,
            "min_order_currency": "USD",
            "fx_fee": "~0.002% (min $2) o auto-FX",
            "italian_tax_regime": "Dichiarativo",
            "status": ibkr_status,
            "notes": (
                "Copertura migliore sulle small/micro-cap US; frazionate da $1, commissioni ~$0.35 (Tiered)."
                if is_major_us
                else f"Listino {ex}: verifica accesso diretto e supporto frazionate su IBKR."
            ),
        },
        {
            "broker": "Trade Republic",
            "fractional_supported": is_major_us,
            "zero_commission": False,
            "min_order_amount": 1.0,
            "min_order_currency": "EUR",
            "fx_fee": "Spread L&S Exchange",
            "italian_tax_regime": "Amministrato / Dichiarativo (verifica IBAN IT)",
            "status": tr_status,
            "notes": "€1 fisso per ordine singolo (€0 in Piano Accumulo). Diverse micro-cap <$400M mancano su L&S.",
        },
        {
            "broker": "Scalable Capital",
            "fractional_supported": is_major_us,
            "zero_commission": False,
            "min_order_amount": 1.0,
            "min_order_currency": "EUR",
            "fx_fee": "Spread Gettex/Xetra",
            "italian_tax_regime": "Dichiarativo",
            "status": tr_status,
            "notes": "€0.99 per ordine (€0 con Prime+ sopra €250); verificare presenza su Gettex per micro-cap US.",
        },
        {
            "broker": "Revolut",
            "fractional_supported": is_major_us,
            "zero_commission": True,
            "min_order_amount": 1.0,
            "min_order_currency": "USD",
            "fx_fee": "0% entro soglia piano (poi 1%)",
            "italian_tax_regime": "Dichiarativo",
            "status": rev_status,
            "notes": "Ordini gratis mensili in base al piano; selezione micro-cap più ristretta.",
        },
        {
            "broker": "Directa SIM",
            "fractional_supported": False,
            "zero_commission": False,
            "min_order_amount": round(price_usd, 2) if price_usd > 0 else 25.0,
            "min_order_currency": "USD",
            "fx_fee": "Inclusa",
            "italian_tax_regime": "Regime Amministrato IT",
            "status": "SOLO_AZIONI_INTERE",
            "notes": (
                f"Niente frazionate. Prezzo ${price_usd:.2f} (~€{approx_price_eur:.2f}) compatibile con micro-ordine intero, ma commissione $9 US incide su ticket piccoli."
                if fits_whole_micro
                else f"Niente frazionate e 1 azione (${price_usd:.2f}, ~€{approx_price_eur:.2f}) supera il micro-ticket da €35."
            ),
        },
    ]
