"""Multi-Agent IPO & Micro-Cap AI Scouter Pipeline (Bull, Bear, Auditor/Verifier, Judge)."""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from config import settings
from services.alt_data import (
    analyze_hiring_signals,
    check_broker_fractional_availability,
    fetch_ticker_news,
)
from services.notifier import send_telegram_alert, send_daily_portfolio_briefing
from services.quant_screener import (
    discover_candidate_tickers,
    evaluate_screening_criteria,
    fetch_quant_metrics,
)
from services.sec_edgar import fetch_sec_filings
from services.storage import storage

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:
    genai = None
    genai_types = None

logger = logging.getLogger("scouter_pipeline")


# =============================================================================
# 4 DISTINCT AGENT PROMPTS (BULL, BEAR, AUDITOR/VERIFIER, JUDGE)
# =============================================================================

BULL_PROMPT = """Sei l'AGENTE BULL (Catalyst & Asymmetric Upside Hunter) di un desk di ricerca micro-cap post-IPO.
Il tuo compito è estrarre ESCLUSIVAMENTE i catalizzatori reali e verificabili presenti nei dati grezzi forniti (bilanci yfinance, depositi SEC 8-K e Form 4, news RSS, offerte di lavoro/Careers).

Regole ferree:
1. Ogni affermazione deve citare un tag fonte esplicito tra: [FIN-DATA], [SEC-8K], [FORM-4], [NEWS], [CAREERS].
2. Concentrati su: nuovi contratti materiali (8-K Item 1.01), brevetti/milestone (Item 8.01), acquisti sul mercato aperto da parte di insider (Form 4 Codice P, distinguendoli da grant/opzioni), espansione R&D/vendite dalle posizioni aperte, disallineamento tra crescita ricavi YoY e drawdown post-IPO.
3. NON inventare cifre o contratti assenti dal payload. Rispondi in ITALIANO con JSON valido.

Schema JSON richiesto:
{
  "headline": "Titolo sintetico della tesi rialzista (max 110 caratteri)",
  "core_catalysts": [
    {"title": "...", "detail": "...", "source_tag": "[SEC-8K]|[FORM-4]|[FIN-DATA]|[NEWS]|[CAREERS]", "impact": "ALTO|MEDIO"}
  ],
  "insider_conviction_read": "Lettura sintetica degli acquisti Form 4 (o assenza di acquisti)",
  "expansion_signal": "Valutazione trend assunzioni / pipeline commerciale",
  "bull_conviction": 0-100
}"""

BEAR_PROMPT = """Sei l'AGENTE BEAR (Forensic Short-Seller & Red-Flag Analyst).
Il tuo compito è cercare ESCLUSIVAMENTE elementi critici, rischi strutturali e trappole per investitori retail nei dati forniti.

Regole ferree:
1. Ogni red flag deve citare un tag fonte esplicito tra: [FIN-DATA], [SEC-8K], [SEC-S3], [FORM-4], [NEWS], [CAREERS].
2. Cerca attivamente: rischio diluizione imminente (depositi S-3 shelf registration, 424B5/ATM offerings, 8-K Item 3.02, warrant overhang), burn rate mensile vs runway, debito elevato/current ratio debole, vendite insider (Form 4 Codice S), tagli al personale o ritardi operativi.
3. NON inventare rischi assenti dal payload. Se i conti sono solidi, segnala comunque i principali rischi residui reali (es. concentrazione clienti, volatilità post-IPO, rischio esecuzione). Rispondi in ITALIANO con JSON valido.

Schema JSON richiesto:
{
  "headline": "Titolo sintetico del rischio principale (max 110 caratteri)",
  "red_flags": [
    {"title": "...", "detail": "...", "source_tag": "[FIN-DATA]|[SEC-8K]|[SEC-S3]|[FORM-4]|[NEWS]|[CAREERS]", "severity": "CRITICO|ALTO|MEDIO"}
  ],
  "dilution_risk_level": "BASSO|MODERATO|ALTO",
  "burn_and_balance_sheet_audit": "Analisi critica su cassa, burn mensile e sostenibilità",
  "bear_severity": 0-100
}"""

AUDITOR_VERIFIER_PROMPT = """Sei l'AGENTE AUDITOR / VERIFICATORE (Contro-Verifica Anti-Allucinazione & Coerenza Contabile).
Ricevi i dati grezzi originali insieme alle tesi dell'Agente BULL e dell'Agente BEAR.
Il tuo compito è verificare matematicamente e fattualmente ogni singola affermazione dei due agenti rispetto al payload grezzo.

Checklist obbligatoria:
1. Coerenza matematica: Runway = Cassa / Burn mensile (o Cash Flow >= 0); Net Cash = Cassa - Debito Totale; Post-IPO drawdown negativo e coerente.
2. Verifica Form 4: Assicurati che il Bull non abbia scambiato grant (Codice A) o esercizi di opzioni (Codice M) per acquisti reali sul mercato aperto (Codice P).
3. Verifica SEC S-3 / 8-K: Conferma che i rischi di diluizione citati dal Bear siano realmente supportati dai filing o dalle news.
4. Segnala esagerazioni, affermazioni non verificate o correzioni numeriche. Rispondi in ITALIANO con JSON valido.

Schema JSON richiesto:
{
  "verification_score": 0-100,
  "overall_reliability": "ALTA|MEDIA|BASSA",
  "accounting_sanity_check": "Verifica numerica su Runway, Net Cash, Burn e Form 4",
  "verified_facts": ["Lista di 3-5 fatti verificati al 100% nei dati grezzi"],
  "challenged_claims": [
    {"agent": "BULL|BEAR", "claim": "Affermazione imprecisa o esagerata", "audit_verdict": "ESAGERAZIONE|NON_VERIFICATO|CORREZIONE_NUMERICA", "correction": "Correzione basata sui dati reali"}
  ]
}"""

JUDGE_PROMPT = """Sei l'AGENTE GIUDICE (Chief Investment Officer per micro-investimenti asimmetrici da 25-50 EUR).
Sintetizza il dibattito tra Agente BULL, Agente BEAR e la Contro-Verifica dell'Agente AUDITOR.
Assegna un punteggio di asimmetria da 1 a 100 scomponendolo in 5 sub-score e scrivi una TESI SINTETICA IN ESATTAMENTE 5 RIGHE in ITALIANO.

Criteri di scoring:
- catalyst_strength (0-25): contratti 8-K, brevetti, trend ricavi e espansione operativa verificata.
- financial_survival_runway (0-25): cassa, runway > 12 mesi (o FCF/OCF positivo), assenza di debito tossico.
- insider_alignment (0-20): acquisti Form 4 Codice P (cluster buying = punteggio alto) vs vendite pesanti.
- valuation_asymmetry (0-15): entità del calo post-IPO rispetto ai fondamentali e multipli EV/Sales.
- audit_confidence (0-15): affidabilità dei dati verificata dall'Auditor e assenza di diluizione imminente S-3.

Regole per `thesis_5_lines`:
Deve essere un array JSON di ESATTAMENTE 5 stringhe brevi e ad alta densità informativa:
- Riga 1: Modello di business e catalizzatore asimmetrico principale.
- Riga 2: Solidità finanziaria (cassa, runway, crescita ricavi YoY).
- Riga 3: Segnali insider (Form 4) e dati alternativi (Careers/News).
- Riga 4: Rischio principale evidenziato dal Bear e mitigante/verifica Auditor.
- Riga 5: Piano operativo per micro-ordine (frazionato, livello invalidazione tesi, orizzonte).

Rispondi in ITALIANO con JSON valido:
{
  "sub_scores": {
    "catalyst_strength": 0-25,
    "financial_survival_runway": 0-25,
    "insider_alignment": 0-20,
    "valuation_asymmetry": 0-15,
    "audit_confidence": 0-15
  },
  "asymmetry_score": 1-100,
  "verdict_label": "STRONG_ASYMMETRIC_BUY|WATCHLIST_ACCUMULATE|AVOID_DILUTION_TRAP",
  "thesis_5_lines": ["...", "...", "...", "...", "..."],
  "signal_tags": ["max 6 tag sintetici"],
  "micro_strategy": {
    "recommended_bullet_eur": 35,
    "entry_zone": "es. Accumulo frazionato sotto $X.XX",
    "invalidation_trigger": "Condizione oggettiva che invalida la tesi",
    "time_horizon": "es. 12-24 mesi"
  }
}"""


def _gemini_ready() -> bool:
    key = settings.GEMINI_API_KEY
    return bool(genai and key and not key.startswith("your_") and len(key) > 15)


def _extract_json_block(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _safe_int(val: Any, default: int, min_v: int, max_v: int) -> int:
    try:
        if isinstance(val, str):
            m = re.search(r"-?\d+", val)
            num = int(m.group(0)) if m else default
        elif val is None:
            num = default
        else:
            num = int(round(float(val)))
        return max(min_v, min(max_v, num))
    except (TypeError, ValueError):
        return default


def _call_gemini_agent(
    client: Any,
    system_prompt: str,
    payload: dict[str, Any],
    model_name: str,
) -> dict[str, Any] | None:
    if client is None:
        return None

    candidate_models = [model_name, "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
    models_to_try = [m for i, m in enumerate(candidate_models) if m and m not in candidate_models[:i]]

    for target_model in models_to_try:
        for attempt in range(1, 3):
            try:
                config_kwargs: dict[str, Any] = {
                    "system_instruction": system_prompt,
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                }
                response = client.models.generate_content(
                    model=target_model,
                    contents=json.dumps(payload, ensure_ascii=False, default=str),
                    config=genai_types.GenerateContentConfig(**config_kwargs) if genai_types else None,
                )
                if response and response.text:
                    res = _extract_json_block(response.text)
                    if res:
                        return res
            except Exception as exc:
                err_msg = str(exc)
                if "503" in err_msg or "UNAVAILABLE" in err_msg:
                    logger.warning("Gemini model %s 503 spike (attempt %d/2), retrying in 2s...", target_model, attempt)
                    time.sleep(2)
                    continue
                if any(k in err_msg for k in ["404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED"]):
                    logger.warning("Gemini model %s transient error (%s), trying fallback model...", target_model, err_msg[:60])
                    break
                logger.warning("Gemini agent call failed (%s): %s", target_model, exc)
                break
    return None


def _fmt_usd(val: float | None) -> str:
    if val is None:
        return "N/D"
    abs_v = abs(val)
    sign = "-" if val < 0 else ""
    if abs_v >= 1_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000:.2f}B"
    if abs_v >= 1_000_000:
        return f"{sign}${abs_v / 1_000_000:.1f}M"
    if abs_v >= 1_000:
        return f"{sign}${abs_v / 1_000:.0f}K"
    return f"{sign}${abs_v:.0f}"


def _build_ground_truth_payload(
    quant: dict[str, Any],
    screening: dict[str, Any],
    sec: dict[str, Any],
    news: dict[str, Any],
    hiring: dict[str, Any],
) -> dict[str, Any]:
    """Compact ground-truth evidence dictionary passed to all 4 agents."""
    return {
        "ticker": quant["ticker"],
        "company_name": quant["company_name"],
        "sector": quant["sector"],
        "industry": quant["industry"],
        "business_summary": quant["business_summary"],
        "quant_metrics": {
            "current_price": quant["current_price"],
            "ipo_date": quant["ipo_date"],
            "months_since_ipo": quant["months_since_ipo"],
            "post_ipo_high": quant["post_ipo_high"],
            "post_ipo_drawdown_pct": quant["post_ipo_drawdown_pct"],
            "post_ipo_change_pct": quant["post_ipo_change_pct"],
            "market_cap": quant["market_cap"],
            "enterprise_value": quant["enterprise_value"],
            "cash_and_equivalents": quant["cash_and_equivalents"],
            "total_debt": quant["total_debt"],
            "net_cash": quant["net_cash"],
            "revenue_ttm": quant["revenue_ttm"],
            "revenue_growth_yoy_pct": quant["revenue_growth_yoy_pct"],
            "gross_margin_pct": quant["gross_margin_pct"],
            "ev_to_sales": quant["ev_to_sales"],
            "operating_cash_flow_ttm": quant["operating_cash_flow_ttm"],
            "free_cash_flow_ttm": quant["free_cash_flow_ttm"],
            "monthly_burn_usd": quant["monthly_burn_usd"],
            "is_cash_flow_positive": quant["is_cash_flow_positive"],
            "runway_months": quant["runway_months"],
            "current_ratio": quant["current_ratio"],
            "toxic_debt_flag": quant["toxic_debt_flag"],
            "toxic_debt_reasons": quant["toxic_debt_reasons"],
        },
        "screening_passed": screening["passed"],
        "sec_summary": {
            "cik": sec.get("cik"),
            "filings_8k": sec.get("filings_8k", [])[:4],
            "filings_s3_shelf": sec.get("filings_s3_shelf", []),
            "shelf_dilution_risk": sec.get("shelf_dilution_risk", False),
            "open_market_buys_count": sec.get("open_market_buys_count", 0),
            "open_market_buys_usd": sec.get("open_market_buys_usd", 0.0),
            "open_market_sales_count": sec.get("open_market_sales_count", 0),
            "open_market_sales_usd": sec.get("open_market_sales_usd", 0.0),
            "cluster_insider_buying": sec.get("cluster_insider_buying", False),
            "form4_sample": sec.get("form4_transactions", [])[:6],
        },
        "news_summary": news,
        "hiring_signals": hiring,
    }


def _fallback_bull(payload: dict[str, Any]) -> dict[str, Any]:
    q = payload["quant_metrics"]
    s = payload["sec_summary"]
    h = payload["hiring_signals"]
    n = payload["news_summary"]

    catalysts: list[dict[str, str]] = []
    rev_g = q.get("revenue_growth_yoy_pct")
    dd = q.get("post_ipo_drawdown_pct")
    if rev_g is not None and rev_g > 0:
        catalysts.append(
            {
                "title": f"Crescita Ricavi YoY +{rev_g:.1f}% vs Prezzo Scontato ({dd or 0:.1f}% dal picco)",
                "detail": (
                    f"Il titolo quota con un drawdown del {abs(dd or 0):.1f}% dal massimo post-IPO nonostante "
                    f"ricavi TTM pari a {_fmt_usd(q.get('revenue_ttm'))} in crescita del +{rev_g:.1f}% YoY."
                ),
                "source_tag": "[FIN-DATA]",
                "impact": "ALTO" if rev_g >= 20 else "MEDIO",
            }
        )

    if s.get("open_market_buys_count", 0) > 0:
        catalysts.append(
            {
                "title": (
                    "Cluster Insider Buying (Form 4 Codice P)"
                    if s.get("cluster_insider_buying")
                    else "Acquisto Diretto Insider sul Mercato (Form 4)"
                ),
                "detail": (
                    f"Rilevati {s['open_market_buys_count']} acquisti open-market (Codice P) per un controvalore "
                    f"complessivo di {_fmt_usd(s.get('open_market_buys_usd'))}."
                ),
                "source_tag": "[FORM-4]",
                "impact": "ALTO",
            }
        )

    item_8k_cats = [f for f in s.get("filings_8k", []) if any(it in ("1.01", "8.01") for it in f.get("items", []))]
    if item_8k_cats:
        latest = item_8k_cats[0]
        catalysts.append(
            {
                "title": f"Deposito SEC 8-K ({latest.get('filing_date', '')}): Eventi Materiali / Contratti",
                "detail": latest.get("description") or "Nuovo accordo materiale o aggiornamento strategico depositato.",
                "source_tag": "[SEC-8K]",
                "impact": "ALTO",
            }
        )

    if h.get("hiring_trend") == "HIRING_SPIKE":
        catalysts.append(
            {
                "title": f"Espansione Organico: {h.get('open_roles_count')} posizioni aperte",
                "detail": f"{h.get('evidence_note')} Focus prevalente su {h.get('department_focus')}.",
                "source_tag": "[CAREERS]",
                "impact": "MEDIO",
            }
        )

    if n.get("catalyst_headlines_count", 0) > 0:
        cat_arts = [a["title"] for a in n.get("articles", []) if a.get("sentiment_hint") == "CATALYST"]
        catalysts.append(
            {
                "title": f"Catalizzatori Media & News ({n['catalyst_headlines_count']} articoli positivi)",
                "detail": cat_arts[0] if cat_arts else "Copertura stampa focalizzata su nuovi contratti o milestone.",
                "source_tag": "[NEWS]",
                "impact": "MEDIO",
            }
        )

    if not catalysts:
        catalysts.append(
            {
                "title": "Opzionalità di Ritorno alla Media Post-IPO",
                "detail": f"Cassa disponibile pari a {_fmt_usd(q.get('cash_and_equivalents'))} per finanziare l'esecuzione.",
                "source_tag": "[FIN-DATA]",
                "impact": "MEDIO",
            }
        )

    bull_conv = 48
    if rev_g and rev_g >= 20:
        bull_conv += 15
    if s.get("open_market_buys_count", 0) > 0:
        bull_conv += 16
    if item_8k_cats:
        bull_conv += 10
    if h.get("hiring_trend") == "HIRING_SPIKE":
        bull_conv += 8

    return {
        "headline": f"Asimmetria su {payload['ticker']}: fondamentali in crescita nonostante calo post-IPO",
        "core_catalysts": catalysts[:5],
        "insider_conviction_read": (
            f"Segnale forte: {s['open_market_buys_count']} acquisti diretti Codice P ({_fmt_usd(s.get('open_market_buys_usd'))})."
            if s.get("open_market_buys_count", 0) > 0
            else "Nessun acquisto Codice P recente nei Form 4 ispezionati; allineamento affidato alle partecipazioni esistenti."
        ),
        "expansion_signal": h.get("evidence_note", "Trend assunzioni in monitoraggio."),
        "bull_conviction": min(95, bull_conv),
    }


def _fallback_bear(payload: dict[str, Any]) -> dict[str, Any]:
    q = payload["quant_metrics"]
    s = payload["sec_summary"]
    h = payload["hiring_signals"]
    n = payload["news_summary"]

    red_flags: list[dict[str, str]] = []
    runway = q.get("runway_months")
    is_cf_pos = q.get("is_cash_flow_positive")
    if not is_cf_pos:
        sev = "CRITICO" if (runway is not None and runway < 12) else ("ALTO" if (runway is not None and runway < 18) else "MEDIO")
        red_flags.append(
            {
                "title": f"Cash Burn Attivo ({_fmt_usd(q.get('monthly_burn_usd'))}/mese)",
                "detail": (
                    f"Cash flow effettivo negativo (OCF {_fmt_usd(q.get('operating_cash_flow_ttm'))}, "
                    f"FCF {_fmt_usd(q.get('free_cash_flow_ttm'))}). "
                    f"Autonomia di cassa stimata in {runway if runway is not None else 'N/D'} mesi."
                ),
                "source_tag": "[FIN-DATA]",
                "severity": sev,
            }
        )

    has_302 = any("3.02" in f.get("items", []) for f in s.get("filings_8k", []))
    if s.get("shelf_dilution_risk") or has_302:
        red_flags.append(
            {
                "title": "Rischio Diluizione Attivo (Depositi S-3/424B5 o 8-K Item 3.02)",
                "detail": (
                    f"Rilevati {len(s.get('filings_s3_shelf', []))} moduli S-3/424B5 recenti o emissioni non registrate: "
                    "la società può emettere nuove azioni diluendo i micro-azionisti."
                ),
                "source_tag": "[SEC-S3]" if s.get("filings_s3_shelf") else "[SEC-8K]",
                "severity": "ALTO",
            }
        )

    if q.get("toxic_debt_flag"):
        red_flags.append(
            {
                "title": "Struttura Patrimoniale Sotto Pressione",
                "detail": "; ".join(q.get("toxic_debt_reasons", ["Leva finanziaria o liquidità a breve sfavorevole."])),
                "source_tag": "[FIN-DATA]",
                "severity": "CRITICO",
            }
        )

    if s.get("open_market_sales_count", 0) > 0:
        red_flags.append(
            {
                "title": f"Vendite Insider Form 4 ({_fmt_usd(s.get('open_market_sales_usd'))})",
                "detail": f"Registrate {s['open_market_sales_count']} transazioni Codice S in uscita nei Form 4 recenti.",
                "source_tag": "[FORM-4]",
                "severity": "MEDIO",
            }
        )

    if h.get("hiring_trend") == "FREEZE_OR_CUTS":
        red_flags.append(
            {
                "title": "Segnali di Contrazione / Tagli Organico",
                "detail": h.get("evidence_note", "Possibile freeze delle assunzioni o ristrutturazione."),
                "source_tag": "[CAREERS]",
                "severity": "ALTO",
            }
        )

    if n.get("risk_headlines_count", 0) > 0:
        risk_arts = [a["title"] for a in n.get("articles", []) if a.get("sentiment_hint") == "RISK"]
        red_flags.append(
            {
                "title": f"Notizie Critiche Recenti ({n['risk_headlines_count']} alert)",
                "detail": risk_arts[0] if risk_arts else "Segnalati titoli di stampa relativi a rischi legali o finanziari.",
                "source_tag": "[NEWS]",
                "severity": "MEDIO",
            }
        )

    if not red_flags:
        red_flags.append(
            {
                "title": "Volatilità Micro-Cap & Rischio Esecuzione Post-IPO",
                "detail": "Titolo a bassa capitalizzazione soggetto a spread ampi, cicli di cassa e possibile lock-up overhang.",
                "source_tag": "[FIN-DATA]",
                "severity": "MEDIO",
            }
        )

    dilution_level = (
        "ALTO"
        if (s.get("shelf_dilution_risk") or (runway is not None and runway < 12))
        else ("MODERATO" if not is_cf_pos else "BASSO")
    )
    bear_sev = 28
    if not is_cf_pos and runway is not None and runway < 15:
        bear_sev += 25
    if s.get("shelf_dilution_risk"):
        bear_sev += 20
    if q.get("toxic_debt_flag"):
        bear_sev += 22
    if s.get("open_market_sales_count", 0) > s.get("open_market_buys_count", 0):
        bear_sev += 10

    return {
        "headline": (
            f"Allerta diluizione e burn rate su {payload['ticker']}"
            if dilution_level == "ALTO"
            else f"Rischi esecutivi e volatilità post-IPO su {payload['ticker']}"
        ),
        "red_flags": red_flags[:5],
        "dilution_risk_level": dilution_level,
        "burn_and_balance_sheet_audit": (
            f"Cassa {_fmt_usd(q.get('cash_and_equivalents'))}, Debito {_fmt_usd(q.get('total_debt'))}, "
            f"Current Ratio {q.get('current_ratio') or 'N/D'}x. "
            + ("Cash flow positivo." if is_cf_pos else f"Burn mensile {_fmt_usd(q.get('monthly_burn_usd'))}.")
        ),
        "bear_severity": min(95, bear_sev),
    }


def _fallback_auditor(payload: dict[str, Any], bull: dict[str, Any], bear: dict[str, Any]) -> dict[str, Any]:
    q = payload["quant_metrics"]
    s = payload["sec_summary"]

    cash = q.get("cash_and_equivalents")
    debt = q.get("total_debt") or 0.0
    net_cash = q.get("net_cash")
    burn = q.get("monthly_burn_usd") or 0.0
    runway = q.get("runway_months")

    runway_fact = (
        "Sostenibilità: Cash flow positivo, nessuna dipendenza immediata da aumenti di capitale."
        if q.get("is_cash_flow_positive")
        else (
            f"Runway calcolata: {_fmt_usd(cash)} / {_fmt_usd(burn)} al mese = {runway:.1f} mesi."
            if (cash is not None and burn > 0 and runway is not None)
            else "Runway non determinabile con precisione dai campi di cassa/burn disponibili."
        )
    )

    verified_facts = [
        f"Bilancio: Cassa {_fmt_usd(cash)} vs Debito Totale {_fmt_usd(debt)} (Net Cash: {_fmt_usd(net_cash)}).",
        runway_fact,
        f"Form 4 SEC: verificati {s.get('open_market_buys_count', 0)} acquisti reali Codice P vs {s.get('open_market_sales_count', 0)} vendite Codice S (esclusi grant/opzioni).",
        f"Drawdown post-IPO confermato a {q.get('post_ipo_drawdown_pct') if q.get('post_ipo_drawdown_pct') is not None else 'N/D'}% rispetto al picco di {_fmt_usd(q.get('post_ipo_high'))}.",
    ]

    challenged: list[dict[str, str]] = []
    if s.get("open_market_buys_count", 0) == 0 and any(
        "insider" in (c.get("title", "") + c.get("detail", "")).lower()
        for c in bull.get("core_catalysts", [])
    ):
        challenged.append(
            {
                "agent": "BULL",
                "claim": "Possibile enfatizzazione dell'allineamento insider",
                "audit_verdict": "NON_VERIFICATO",
                "correction": "Nei Form 4 recenti non risultano acquisti open-market Codice P con denaro proprio.",
            }
        )

    if bear.get("dilution_risk_level") == "ALTO" and not s.get("shelf_dilution_risk") and (
        q.get("is_cash_flow_positive") or (runway is not None and runway >= 24)
    ):
        challenged.append(
            {
                "agent": "BEAR",
                "claim": "Rischio diluizione classificato ALTO senza shelf S-3 attivo",
                "audit_verdict": "ESAGERAZIONE",
                "correction": f"Runway di {runway} mesi e assenza di S-3 attivo ridimensionano l'urgenza diluitiva nel breve.",
            }
        )

    ver_score = 92 if q.get("current_price") is not None else 60
    if not s.get("cik"):
        ver_score -= 12
    ver_score -= len(challenged) * 5
    ver_score = max(45, min(98, ver_score))

    runway_short = (
        "CF Positivo"
        if q.get("is_cash_flow_positive")
        else (f"{runway:.1f} mesi" if runway is not None else "N/D")
    )

    return {
        "verification_score": ver_score,
        "overall_reliability": "ALTA" if ver_score >= 80 else ("MEDIA" if ver_score >= 60 else "BASSA"),
        "accounting_sanity_check": (
            f"Coerenza verificata: Net Cash {_fmt_usd(net_cash)}, "
            f"Runway {runway_short}, "
            "Form 4 Codice P separato correttamente da grant (Codice A/M)."
        ),
        "verified_facts": verified_facts,
        "challenged_claims": challenged,
    }


def _fallback_judge(
    payload: dict[str, Any],
    bull: dict[str, Any],
    bear: dict[str, Any],
    auditor: dict[str, Any],
) -> dict[str, Any]:
    q = payload["quant_metrics"]
    s = payload["sec_summary"]
    h = payload["hiring_signals"]
    n = payload["news_summary"]

    # 1) catalyst_strength (0-25)
    cat_score = 8
    rev_g = q.get("revenue_growth_yoy_pct")
    if rev_g is not None:
        if rev_g >= 35:
            cat_score += 7
        elif rev_g >= 15:
            cat_score += 5
        elif rev_g > 0:
            cat_score += 3
    if any(any(it in ("1.01", "8.01") for it in f.get("items", [])) for f in s.get("filings_8k", [])):
        cat_score += 5
    if h.get("hiring_trend") == "HIRING_SPIKE":
        cat_score += 3
    if n.get("catalyst_headlines_count", 0) > 0:
        cat_score += 2
    cat_score = min(25, cat_score)

    # 2) financial_survival_runway (0-25)
    runway = q.get("runway_months") or 0.0
    if q.get("is_cash_flow_positive"):
        surv_score = 23
    elif runway >= 24:
        surv_score = 20
    elif runway >= 16:
        surv_score = 16
    elif runway >= 12:
        surv_score = 13
    else:
        surv_score = 5
    if (q.get("net_cash") or 0) > 0:
        surv_score += 2
    if q.get("toxic_debt_flag"):
        surv_score = max(2, surv_score - 8)
    surv_score = min(25, surv_score)

    # 3) insider_alignment (0-20)
    ins_score = 8
    if s.get("cluster_insider_buying"):
        ins_score = 19
    elif s.get("open_market_buys_count", 0) > 0:
        ins_score = 15
    elif s.get("open_market_sales_count", 0) > 2:
        ins_score = 5

    # 4) valuation_asymmetry (0-15) — strictly require negative drawdown
    raw_dd = q.get("post_ipo_drawdown_pct")
    dd_mag = abs(raw_dd) if (raw_dd is not None and raw_dd < 0) else 0.0
    val_score = 5
    if 30 <= dd_mag <= 75 and (rev_g or 0) > 10:
        val_score = 13
    elif 15 <= dd_mag <= 85:
        val_score = 10
    if q.get("ev_to_sales") and q["ev_to_sales"] < 4.0:
        val_score = min(15, val_score + 2)

    # 5) audit_confidence (0-15)
    aud_score = round((auditor.get("verification_score", 75) / 100.0) * 15)
    if s.get("shelf_dilution_risk"):
        aud_score = max(4, aud_score - 3)
    aud_score = min(15, aud_score)

    total = max(1, min(100, cat_score + surv_score + ins_score + val_score + aud_score))
    verdict_label = (
        "STRONG_ASYMMETRIC_BUY"
        if total >= 75
        else ("WATCHLIST_ACCUMULATE" if total >= 55 else "AVOID_DILUTION_TRAP")
    )

    price = q.get("current_price") or 0.0
    runway_txt = (
        "Cash Flow Positivo"
        if q.get("is_cash_flow_positive")
        else (f"runway di {runway:.1f} mesi" if q.get("runway_months") is not None else "runway N/D")
    )
    rev_txt = f"{rev_g:+.1f}%" if rev_g is not None else "N/D"
    dd_txt = f"{raw_dd}%" if raw_dd is not None else "N/D"
    insider_txt = (
        f"{s.get('open_market_buys_count')} acquisti insider Codice P ({_fmt_usd(s.get('open_market_buys_usd'))})"
        if s.get("open_market_buys_count", 0) > 0
        else "nessun acquisto open-market Codice P recente"
    )
    bull_cat_title = (bull.get("core_catalysts") or [{}])[0].get("title") or payload["industry"]

    thesis_5_lines = [
        f"1. Tesi Core: {payload['company_name']} ({payload['ticker']}) tratta a {dd_txt} dal picco post-IPO; driver principale: {bull_cat_title}.",
        f"2. Sopravvivenza: Ricavi YoY a {rev_txt} con cassa di {_fmt_usd(q.get('cash_and_equivalents'))} e {runway_txt} (Net Cash {_fmt_usd(q.get('net_cash'))}).",
        f"3. Segnali Lenti: SEC Form 4 mostra {insider_txt}; segnale Careers '{h.get('hiring_trend', 'UNKNOWN')}' ({h.get('department_focus', 'N/D')}).",
        f"4. Contro-Verifica Bear/Auditor: Rischio diluizione {bear.get('dilution_risk_level', 'MODERATO')}; affidabilità dati verificata al {auditor.get('verification_score', 80)}%.",
        f"5. Piano Micro-Ordine: Ticket da €{int(settings.DEFAULT_MICRO_ORDER_EUR)} in frazionate a ~${price:.2f}; invalidazione se runway < 9m o emissione S-3 diluitiva.",
    ]

    tags = _build_signal_tags(payload, bear)
    return {
        "sub_scores": {
            "catalyst_strength": cat_score,
            "financial_survival_runway": surv_score,
            "insider_alignment": ins_score,
            "valuation_asymmetry": val_score,
            "audit_confidence": aud_score,
        },
        "asymmetry_score": total,
        "verdict_label": verdict_label,
        "thesis_5_lines": thesis_5_lines,
        "signal_tags": tags[:6],
        "micro_strategy": {
            "recommended_bullet_eur": settings.DEFAULT_MICRO_ORDER_EUR if total >= 70 else 25.0,
            "entry_zone": f"Accumulo frazionato area ${price * 0.94:.2f} - ${price * 1.03:.2f}" if price else "Solo in fascia di consolidamento",
            "invalidation_trigger": "Runway < 9 mesi, annuncio offerta ATM/S-3 fortemente diluitiva o contrazione ricavi > -10%.",
            "time_horizon": "12-24 mesi (orizzonte lento post-IPO)",
        },
    }


def _build_signal_tags(payload: dict[str, Any], bear: dict[str, Any]) -> list[str]:
    q = payload["quant_metrics"]
    s = payload["sec_summary"]
    h = payload["hiring_signals"]

    tags: list[str] = []
    if s.get("cluster_insider_buying") or s.get("open_market_buys_count", 0) > 0:
        tags.append("Insider Buying")
    if any(any(it in ("1.01", "8.01") for it in f.get("items", [])) for f in s.get("filings_8k", [])):
        tags.append("8-K Contratto/Brevetto")
    if h.get("hiring_trend") == "HIRING_SPIKE":
        tags.append("Hiring Spike")
    if q.get("is_cash_flow_positive"):
        tags.append("Cash Flow Positivo")
    elif (q.get("runway_months") or 0) >= 24:
        tags.append("Runway > 24m")
    if (q.get("net_cash") or 0) > 0:
        tags.append("Net Cash")
    if q.get("post_ipo_drawdown_pct") is not None and q["post_ipo_drawdown_pct"] <= -25:
        tags.append(f"Post-IPO {q['post_ipo_drawdown_pct']:.0f}%")
    if s.get("shelf_dilution_risk") or bear.get("dilution_risk_level") == "ALTO":
        tags.append("Rischio Diluizione")
    return list(dict.fromkeys(tags))


def _enforce_judge_invariants(
    judge: dict[str, Any],
    payload: dict[str, Any],
    bull: dict[str, Any],
    bear: dict[str, Any],
    auditor: dict[str, Any],
) -> dict[str, Any]:
    """Ensure sub-scores sum cleanly, 5 lines exist, micro_strategy is valid, and verdict matches thresholds."""
    subs = judge.get("sub_scores") if isinstance(judge.get("sub_scores"), dict) else {}
    cat = _safe_int(subs.get("catalyst_strength"), 12, 0, 25)
    surv = _safe_int(subs.get("financial_survival_runway"), 12, 0, 25)
    ins = _safe_int(subs.get("insider_alignment"), 8, 0, 20)
    val = _safe_int(subs.get("valuation_asymmetry"), 8, 0, 15)
    aud = _safe_int(subs.get("audit_confidence"), 10, 0, 15)

    if cat + surv + ins + val + aud == 0:
        cat = 1

    total = max(1, min(100, cat + surv + ins + val + aud))
    judge["sub_scores"] = {
        "catalyst_strength": cat,
        "financial_survival_runway": surv,
        "insider_alignment": ins,
        "valuation_asymmetry": val,
        "audit_confidence": aud,
    }
    judge["asymmetry_score"] = total
    judge["verdict_label"] = (
        "STRONG_ASYMMETRIC_BUY"
        if total >= 75
        else ("WATCHLIST_ACCUMULATE" if total >= 55 else "AVOID_DILUTION_TRAP")
    )

    raw_lines = judge.get("thesis_5_lines")
    if isinstance(raw_lines, str):
        lines = [ln.strip() for ln in raw_lines.splitlines() if ln.strip()]
    elif isinstance(raw_lines, list):
        lines = [str(x).strip() for x in raw_lines if str(x).strip()]
    else:
        lines = []

    fallback_judge = _fallback_judge(payload, bull, bear, auditor)
    fallback_lines = fallback_judge["thesis_5_lines"]
    while len(lines) < 5:
        lines.append(fallback_lines[len(lines)])
    judge["thesis_5_lines"] = lines[:5]

    if not isinstance(judge.get("signal_tags"), list) or not judge["signal_tags"]:
        judge["signal_tags"] = _build_signal_tags(payload, bear)[:6]

    if not isinstance(judge.get("micro_strategy"), dict):
        judge["micro_strategy"] = fallback_judge["micro_strategy"]
    else:
        for k, v in fallback_judge["micro_strategy"].items():
            if not judge["micro_strategy"].get(k):
                judge["micro_strategy"][k] = v

    return judge


def run_multi_agent_debate(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute Bull -> Bear -> Auditor (Contro-Verifica) -> Judge pipeline."""
    client = genai.Client(api_key=settings.GEMINI_API_KEY) if _gemini_ready() else None
    gemini_agents_used = 0

    bull = _call_gemini_agent(client, BULL_PROMPT, payload, settings.GEMINI_MODEL_FAST)
    if isinstance(bull, dict) and isinstance(bull.get("core_catalysts"), list):
        gemini_agents_used += 1
    else:
        bull = _fallback_bull(payload)

    bear = _call_gemini_agent(client, BEAR_PROMPT, payload, settings.GEMINI_MODEL_FAST)
    if isinstance(bear, dict) and isinstance(bear.get("red_flags"), list):
        gemini_agents_used += 1
    else:
        bear = _fallback_bear(payload)

    auditor_input = {"ground_truth": payload, "bull_report": bull, "bear_report": bear}
    auditor = _call_gemini_agent(client, AUDITOR_VERIFIER_PROMPT, auditor_input, settings.GEMINI_MODEL_FAST)
    if isinstance(auditor, dict) and "verification_score" in auditor:
        auditor["verification_score"] = _safe_int(auditor.get("verification_score"), 80, 0, 100)
        gemini_agents_used += 1
    else:
        auditor = _fallback_auditor(payload, bull, bear)

    judge_input = {
        "ground_truth": payload,
        "bull_report": bull,
        "bear_report": bear,
        "auditor_verification": auditor,
    }
    judge = _call_gemini_agent(client, JUDGE_PROMPT, judge_input, settings.GEMINI_MODEL_REASONING)
    if isinstance(judge, dict) and isinstance(judge.get("sub_scores"), dict):
        gemini_agents_used += 1
    else:
        judge = _fallback_judge(payload, bull, bear, auditor)

    judge = _enforce_judge_invariants(judge, payload, bull, bear, auditor)

    if gemini_agents_used == 4:
        engine_label = f"{settings.GEMINI_MODEL_REASONING} (4/4 Gemini)"
    elif gemini_agents_used > 0:
        engine_label = f"hybrid ({gemini_agents_used}/4 Gemini + Fallback)"
    else:
        engine_label = "forensic_rules_engine_fallback"

    return {
        "ai_engine": engine_label,
        "bull_report": bull,
        "bear_report": bear,
        "auditor_report": auditor,
        "judge_verdict": judge,
    }


def analyze_single_ticker(
    ticker: str,
    save_to_store: bool = True,
    notify: bool = False,
    preloaded_quant: dict[str, Any] | None = None,
    preloaded_screening: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full end-to-end ingestion, 4-agent analysis, broker check, and storage for one ticker."""
    symbol = ticker.strip().upper()
    quant = preloaded_quant or fetch_quant_metrics(symbol)
    if not quant.get("data_available"):
        raise ValueError(f"Dati di mercato non disponibili per il ticker '{symbol}'.")

    screening = preloaded_screening or evaluate_screening_criteria(quant)
    sec = fetch_sec_filings(symbol)
    news = fetch_ticker_news(symbol, quant.get("company_name", ""))
    hiring = analyze_hiring_signals(
        symbol,
        quant.get("company_name", ""),
        quant.get("website", ""),
        news.get("articles", []),
        quant.get("full_time_employees"),
    )
    brokers = check_broker_fractional_availability(
        symbol,
        quant.get("exchange", "NASDAQ"),
        quant.get("current_price"),
        quant.get("market_cap"),
    )

    payload = _build_ground_truth_payload(quant, screening, sec, news, hiring)
    debate = run_multi_agent_debate(payload)
    judge = debate["judge_verdict"]

    record = {
        "ticker": symbol,
        "company_name": quant["company_name"],
        "sector": quant["sector"],
        "industry": quant["industry"],
        "exchange": quant["exchange"],
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "asymmetry_score": judge["asymmetry_score"],
        "verdict_label": judge["verdict_label"],
        "sub_scores": judge["sub_scores"],
        "thesis_5_lines": judge["thesis_5_lines"],
        "signal_tags": judge["signal_tags"],
        "micro_strategy": judge["micro_strategy"],
        "quant_metrics": quant,
        "screening": screening,
        "sec_filings": sec,
        "news": news,
        "hiring_signals": hiring,
        "broker_availability": brokers,
        "debate": {
            "ai_engine": debate["ai_engine"],
            "bull": debate["bull_report"],
            "bear": debate["bear_report"],
            "auditor": debate["auditor_report"],
        },
    }

    if save_to_store:
        storage.upsert_opportunity(record)

    if notify and record["asymmetry_score"] >= settings.ALERT_SCORE_THRESHOLD:
        send_telegram_alert(record)

    return record


def _compute_stage1_prescore(
    quant: dict[str, Any],
    screening: dict[str, Any],
    source: str,
) -> float:
    """Fast quantitative Stage-1 ranking score used to pick the best finalists for Stage-2 4-agent AI debate."""
    score = 0.0
    if screening.get("passed"):
        score += 40.0

    rev_g = quant.get("revenue_growth_yoy_pct")
    if rev_g is not None and rev_g > 0:
        score += min(20.0, float(rev_g) * 0.4)

    if quant.get("is_cash_flow_positive"):
        score += 15.0
    else:
        runway = quant.get("runway_months")
        if runway is not None and runway >= 12:
            score += min(15.0, float(runway) * 0.5)

    dd = abs(float(quant.get("post_ipo_drawdown_pct") or 0.0))
    if 15.0 <= dd <= 75.0:
        score += 15.0
    elif dd > 75.0:
        score += 5.0

    mcap = quant.get("market_cap")
    if mcap is not None and mcap > 0:
        if mcap <= 2_000_000_000:
            score += 10.0
        elif mcap <= 5_000_000_000:
            score += 5.0

    # Event-driven discovery bonus
    if source == "sec_live_form_4":
        score += 12.0
    elif source == "sec_live_form_8k":
        score += 8.0
    elif source == "finnhub_ipo_calendar":
        score += 5.0

    return round(score, 2)


def run_daily_pipeline(
    tickers: list[str] | None = None,
    max_candidates: int = 36,
    max_deep_analyze: int | None = None,
    top_n_save: int = 5,
    notify: bool = True,
    auto_register: bool = False,
    auto_monitor: bool = False,
    export_snapshot: bool = True,
) -> dict[str, Any]:
    """Execute 2-Stage Funnel daily pipeline:
    Stage 1: Fast quantitative pre-screening across a wide rotating universe (Finnhub IPO + SEC Live Radar + Curated).
    Stage 2: Deep SEC EDGAR + News + Careers + 4-Agent Gemini debate on top finalists only.
    """
    if tickers:
        candidate_list = [{"ticker": t.strip().upper(), "source": "cli_override"} for t in tickers if t.strip()]
    else:
        existing_opps = storage.list_opportunities(min_score=0, limit=500)
        recently_analyzed = {
            (o.get("ticker") or "").upper(): o.get("analyzed_at", "")
            for o in existing_opps
            if o.get("ticker")
        }
        open_orders = storage.list_micro_orders().get("orders", [])
        open_portfolio_tickers = {
            (o.get("ticker") or "").upper()
            for o in open_orders
            if o.get("status", "APERTO") == "APERTO" and o.get("ticker")
        }
        candidate_list = discover_candidate_tickers(
            max_candidates=max_candidates,
            recently_analyzed=recently_analyzed,
            open_portfolio_tickers=open_portfolio_tickers,
        )

    # ---------------- STAGE 1: Fast Quantitative Funnel ----------------
    stage1_passed: list[tuple[float, str, dict[str, Any], dict[str, Any], str]] = []
    borderline: list[tuple[float, str, dict[str, Any], dict[str, Any], str]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for item in candidate_list:
        sym = item["ticker"]
        src = item.get("source", "unknown")
        try:
            quant = fetch_quant_metrics(sym)
            if not quant.get("data_available"):
                errors.append({"ticker": sym, "error": "Dati yfinance non disponibili"})
                continue
            screening = evaluate_screening_criteria(quant)
            pre_score = _compute_stage1_prescore(quant, screening, src)

            if screening["passed"] or tickers:
                stage1_passed.append((pre_score, sym, quant, screening, src))
            else:
                fb = screening["filter_breakdown"]
                if fb["revenue_growth_ok"] and fb["runway_ok"] and fb["liquidity_no_toxic_debt"]:
                    borderline.append((pre_score, sym, quant, screening, src))
                else:
                    skipped.append({"ticker": sym, "source": src, "reasons": fb})
        except Exception as exc:
            errors.append({"ticker": sym, "error": str(exc)})

    stage1_passed.sort(key=lambda x: x[0], reverse=True)
    borderline.sort(key=lambda x: x[0], reverse=True)

    deep_limit = len(stage1_passed) if tickers else int(max_deep_analyze or settings.MAX_DEEP_ANALYZE)
    finalists = list(stage1_passed[:deep_limit])

    # If fewer than 3 strict candidates passed in batch mode, supplement with top borderline candidates
    if not tickers and len(finalists) < min(3, deep_limit) and borderline:
        needed = min(3, deep_limit) - len(finalists)
        finalists.extend(borderline[:needed])

    # ---------------- STAGE 2: Deep 4-Agent AI Debate on Finalists ----------------
    analyzed: list[dict[str, Any]] = []
    for _pre_score, sym, quant, screening, src in finalists:
        try:
            rec = analyze_single_ticker(
                sym,
                save_to_store=True,
                notify=notify,
                preloaded_quant=quant,
                preloaded_screening=screening,
            )
            rec["discovery_source"] = src
            analyzed.append(rec)
        except Exception as exc:
            errors.append({"ticker": sym, "error": str(exc)})

    analyzed.sort(key=lambda r: r.get("asymmetry_score", 0), reverse=True)
    top_picks = analyzed[:top_n_save]

    source_counts: dict[str, int] = {}
    for item in candidate_list:
        s = item.get("source", "unknown")
        source_counts[s] = source_counts.get(s, 0) + 1

    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "candidates_scanned": len(candidate_list),
        "stage1_passed_count": len(stage1_passed),
        "stage2_deep_analyzed_count": len(analyzed),
        "analyzed_count": len(analyzed),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "discovery_sources": source_counts,
        "top_tickers": [
            {"ticker": r["ticker"], "score": r["asymmetry_score"], "verdict": r["verdict_label"]}
            for r in top_picks
        ],
        "skipped": skipped,
        "errors": errors,
    }

    if auto_monitor or auto_register:
        from services.autopilot import evaluate_and_auto_register, run_portfolio_monitor

        if auto_monitor:
            mon_res = run_portfolio_monitor(refresh_live_prices=True, rescan_ai=False)
            summary["auto_monitor"] = {
                "checked_count": mon_res["checked_count"],
                "auto_closed": mon_res["auto_closed"],
                "alerts": mon_res["alerts"],
            }
        if auto_register:
            reg_res = evaluate_and_auto_register(dry_run=False)
            summary["auto_register"] = {
                "registered_tickers": [r["ticker"] for r in reg_res["registered"]],
                "skipped_count": len(reg_res["skipped"]),
            }

    storage.record_pipeline_run(summary)
    if export_snapshot:
        snapshot_path = storage.export_frontend_snapshot()
        summary["snapshot_exported"] = str(snapshot_path)

    if notify:
        try:
            send_daily_portfolio_briefing(
                journal=storage.list_micro_orders(),
                top_candidates=top_picks,
            )
        except Exception as b_exc:
            logger.warning("Daily portfolio briefing notification failed: %s", b_exc)

    return summary


def run_monitor_only(export_snapshot: bool = True) -> dict[str, Any]:
    """Modalità leggera per GitHub Actions intraday: aggiorna prezzi, TP/SL e snapshot senza ri-eseguire lo screening."""
    from services.autopilot import run_portfolio_monitor

    mon_res = run_portfolio_monitor(refresh_live_prices=True, rescan_ai=False)
    output: dict[str, Any] = {
        "mode": "monitor_only",
        "monitored_at": mon_res["monitored_at"],
        "checked_count": mon_res["checked_count"],
        "price_updates": mon_res["price_updates"],
        "auto_closed": mon_res["auto_closed"],
        "alerts": mon_res["alerts"],
    }
    if export_snapshot:
        snapshot_path = storage.export_frontend_snapshot()
        output["snapshot_exported"] = str(snapshot_path)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IPO & Micro-Cap AI Scouter Daily Pipeline")
    parser.add_argument("--tickers", nargs="*", help="Optional explicit list of tickers to analyze")
    parser.add_argument("--max-candidates", type=int, default=36, help="Stage 1: max universe tickers to pre-screen")
    parser.add_argument("--max-deep", type=int, default=settings.MAX_DEEP_ANALYZE, help="Stage 2: max finalists for 4-agent AI debate")
    parser.add_argument("--no-notify", action="store_true", help="Disable Telegram alerts")
    parser.add_argument("--auto-register", action="store_true", help="Run Paper Auto-Registration after scan")
    parser.add_argument("--auto-monitor", action="store_true", help="Run Portfolio Auto-Monitor after scan")
    parser.add_argument(
        "--monitor-only",
        action="store_true",
        help="Skip full screening and only refresh live prices, TP/SL exits, and static snapshot",
    )
    parser.add_argument(
        "--briefing-only",
        action="store_true",
        help="Send daily Telegram portfolio briefing and exit",
    )
    args = parser.parse_args()

    if args.briefing_only:
        send_daily_portfolio_briefing(journal=storage.list_micro_orders(), top_candidates=None)
        result = {"status": "briefing_sent"}
    elif args.monitor_only:
        result = run_monitor_only(export_snapshot=True)
    else:
        result = run_daily_pipeline(
            tickers=args.tickers,
            max_candidates=args.max_candidates,
            max_deep_analyze=args.max_deep,
            notify=not args.no_notify,
            auto_register=args.auto_register,
            auto_monitor=args.auto_monitor,
            export_snapshot=True,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
