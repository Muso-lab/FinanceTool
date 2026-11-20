"""SEC EDGAR API client for 8-K catalysts, Form 4 insider buying, and S-3/424B5 dilution alerts."""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from config import DATA_DIR, settings

TICKER_CACHE_PATH = DATA_DIR / "sec_tickers_cache.json"

_ITEM_LABELS: dict[str, str] = {
    "1.01": "Accordo / Contratto Materiale",
    "1.02": "Terminazione Accordo",
    "1.03": "Procedura Fallimento / Bancarotta",
    "2.02": "Risultati Finanziari",
    "2.03": "Nuovo Debito / Obbligazione Diretta",
    "3.01": "Avviso Delisting / Non Conformità",
    "3.02": "Emissione Azioni Non Registrate (Diluizione)",
    "4.02": "Restatement Bilanci (Red Flag)",
    "5.02": "Cambio Dirigenti / CdA",
    "5.03": "Modifica Statuto / Reverse Split",
    "5.07": "Voto Azionisti",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Altri Eventi / Brevetti / Milestone",
    "9.01": "Bilanci ed Exhibit",
}


def _sec_headers() -> dict[str, str]:
    return {
        "User-Agent": settings.SEC_USER_AGENT or "IPOMicroCapScouter/1.0 (personal-research@example.com)",
        "Accept-Encoding": "gzip, deflate",
    }


def _load_ticker_cik_map() -> dict[str, str]:
    """Load SEC ticker -> 10-digit zero-padded CIK mapping with local cache."""
    if TICKER_CACHE_PATH.exists():
        try:
            age = time.time() - TICKER_CACHE_PATH.stat().st_mtime
            if age < 7 * 86400:
                return json.loads(TICKER_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    mapping: dict[str, str] = {}
    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_sec_headers(),
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            for row in data.values():
                t = (row.get("ticker") or "").strip().upper()
                cik_int = row.get("cik_str")
                if t and cik_int is not None:
                    mapping[t] = str(cik_int).zfill(10)
            if mapping:
                TICKER_CACHE_PATH.write_text(json.dumps(mapping), encoding="utf-8")
                return mapping
    except Exception:
        pass

    if TICKER_CACHE_PATH.exists():
        try:
            return json.loads(TICKER_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return mapping


def resolve_cik(ticker: str) -> str | None:
    """Resolve stock ticker to 10-digit zero-padded SEC CIK."""
    mapping = _load_ticker_cik_map()
    return mapping.get(ticker.strip().upper())


def _build_edgar_url(cik_int: int, accession: str, primary_doc: str) -> str:
    acc_nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{primary_doc}"


def _parse_form4_xml(cik_int: int, accession: str, primary_doc: str, filing_date: str) -> list[dict[str, Any]]:
    """Scarica e analizza il Form 4 XML grezzo per isolare gli acquisti reali open-market (Codice P).

    Nota tecnica SEC EDGAR: `primaryDocument` contiene spesso un prefisso XSLT (es. `xslF345X05/`),
    quindi estraiamo il nome file finale per leggere l'XML puro mantenendo `human_url` per l'utente.
    """
    raw_doc = primary_doc.split("/")[-1]
    xml_url = _build_edgar_url(cik_int, accession, raw_doc)
    human_url = _build_edgar_url(cik_int, accession, primary_doc)

    transactions: list[dict[str, Any]] = []
    try:
        time.sleep(0.14)
        resp = requests.get(xml_url, headers=_sec_headers(), timeout=12)
        if not resp.ok or "<ownershipDocument" not in resp.text:
            return transactions
        root = ET.fromstring(resp.text)

        owner_name = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "Insider").strip()
        is_officer = (root.findtext(".//reportingOwner/reportingOwnerRelationship/isOfficer") or "0").strip() in ("1", "true", "True")
        is_director = (root.findtext(".//reportingOwner/reportingOwnerRelationship/isDirector") or "0").strip() in ("1", "true", "True")
        officer_title = (root.findtext(".//reportingOwner/reportingOwnerRelationship/officerTitle") or "").strip()
        role = officer_title or ("Officer" if is_officer else ("Director" if is_director else "10% Owner"))

        for tx in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
            code = (tx.findtext(".//transactionCoding/transactionCode") or "").strip().upper()
            tx_date = (tx.findtext(".//transactionDate/value") or filing_date).strip()
            shares_txt = tx.findtext(".//transactionAmounts/transactionShares/value")
            price_txt = tx.findtext(".//transactionAmounts/transactionPricePerShare/value")
            acq_disp = (tx.findtext(".//transactionAmounts/transactionAcquiredDisposedCode/value") or "").strip().upper()

            try:
                shares = float(shares_txt) if shares_txt else 0.0
            except ValueError:
                shares = 0.0
            try:
                price = float(price_txt) if price_txt else 0.0
            except ValueError:
                price = 0.0

            value_usd = round(shares * price, 2)
            transactions.append(
                {
                    "filing_date": filing_date,
                    "transaction_date": tx_date,
                    "insider_name": owner_name,
                    "role": role,
                    "code": code,
                    "acquired_or_disposed": acq_disp,
                    "shares": shares,
                    "price_usd": price,
                    "value_usd": value_usd,
                    "url": human_url,
                }
            )
    except Exception:
        return transactions
    return transactions


def fetch_sec_filings(ticker: str, lookback_days: int = 365) -> dict[str, Any]:
    """Fetch 8-K, Form 4, S-1/424B4, S-3/424B5, and 10-Q/10-K data from SEC EDGAR."""
    symbol = ticker.strip().upper()
    cik_padded = resolve_cik(symbol)
    if not cik_padded:
        return {
            "ticker": symbol,
            "cik": None,
            "edgar_company_url": "https://www.sec.gov/edgar/searchedgar/companysearch",
            "filings_8k": [],
            "filings_periodic": [],
            "filings_s1_ipo": [],
            "filings_s3_shelf": [],
            "shelf_dilution_risk": False,
            "form4_transactions": [],
            "open_market_buys_count": 0,
            "open_market_buys_usd": 0.0,
            "open_market_sales_count": 0,
            "open_market_sales_usd": 0.0,
            "cluster_insider_buying": False,
            "sec_tags": [],
            "status": "cik_not_found",
        }

    cik_int = int(cik_padded)
    edgar_company_url = f"https://www.sec.gov/edgar/browse/?CIK={cik_padded}"

    try:
        time.sleep(0.14)
        resp = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik_padded}.json",
            headers=_sec_headers(),
            timeout=15,
        )
        if not resp.ok:
            raise RuntimeError(f"SEC HTTP {resp.status_code}")
        sub = resp.json()
    except Exception as exc:
        return {
            "ticker": symbol,
            "cik": cik_padded,
            "edgar_company_url": edgar_company_url,
            "filings_8k": [],
            "filings_periodic": [],
            "filings_s1_ipo": [],
            "filings_s3_shelf": [],
            "shelf_dilution_risk": False,
            "form4_transactions": [],
            "open_market_buys_count": 0,
            "open_market_buys_usd": 0.0,
            "open_market_sales_count": 0,
            "open_market_sales_usd": 0.0,
            "cluster_insider_buying": False,
            "sec_tags": [],
            "status": f"sec_fetch_error: {exc}",
        }

    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    items_list = recent.get("items", [])
    descs = recent.get("primaryDocDescription", [])

    # I moduli S-3 Shelf restano attivi fino a 3 anni dalla registrazione SEC (lookback esteso a 1095 giorni)
    now_utc = datetime.now(timezone.utc)
    cutoff_recent = (now_utc - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    cutoff_shelf = (now_utc - timedelta(days=3 * 365)).strftime("%Y-%m-%d")

    filings_8k: list[dict[str, Any]] = []
    filings_periodic: list[dict[str, Any]] = []
    filings_s1_ipo: list[dict[str, Any]] = []
    filings_s3_shelf: list[dict[str, Any]] = []
    form4_candidates: list[tuple[str, str, str]] = []

    for i, form in enumerate(forms):
        f_date = dates[i] if i < len(dates) else ""
        acc = accessions[i] if i < len(accessions) else ""
        doc = primary_docs[i] if i < len(primary_docs) else ""
        raw_items = items_list[i] if i < len(items_list) else []
        desc = (descs[i] if i < len(descs) else "") or ""

        if not acc or not doc:
            continue

        url = _build_edgar_url(cik_int, acc, doc)
        form_upper = str(form).upper().strip()

        if form_upper in ("8-K", "8-K/A") and f_date >= cutoff_recent and len(filings_8k) < 6:
            if isinstance(raw_items, str):
                parsed_items = [x.strip() for x in raw_items.split(",") if x.strip()]
            else:
                parsed_items = [str(x).strip() for x in raw_items]
            item_descriptions = [
                f"Item {it}: {_ITEM_LABELS.get(it, 'Disclosure')}" for it in parsed_items
            ]
            # SEC primaryDocDescription is often literally "8-K"; prefer readable item_descriptions
            desc_clean = desc.strip() if desc.strip().upper() not in ("8-K", "8-K/A", "CURRENT REPORT", "") else ""
            readable_desc = ", ".join(item_descriptions) or desc_clean or "Current Report 8-K"
            filings_8k.append(
                {
                    "form": form_upper,
                    "filing_date": f_date,
                    "items": parsed_items,
                    "item_descriptions": item_descriptions,
                    "description": readable_desc,
                    "url": url,
                }
            )
        elif form_upper in ("10-Q", "10-K", "20-F") and len(filings_periodic) < 4:
            filings_periodic.append(
                {
                    "form": form_upper,
                    "filing_date": f_date,
                    "description": desc or f"Periodic Report {form_upper}",
                    "url": url,
                }
            )
        elif form_upper in ("S-1", "S-1/A", "424B4", "F-1") and len(filings_s1_ipo) < 3:
            filings_s1_ipo.append(
                {
                    "form": form_upper,
                    "filing_date": f_date,
                    "description": desc or f"IPO Registration {form_upper}",
                    "url": url,
                }
            )
        elif (
            form_upper in ("S-3", "S-3/A", "S-3ASR", "F-3", "F-3ASR", "424B5", "424B3")
            and f_date >= cutoff_shelf
            and len(filings_s3_shelf) < 5
        ):
            filings_s3_shelf.append(
                {
                    "form": form_upper,
                    "filing_date": f_date,
                    "description": f"Shelf / ATM Takedown {form_upper} (Rischio Diluizione)",
                    "url": url,
                }
            )
        elif form_upper in ("4", "4/A") and f_date >= cutoff_recent and len(form4_candidates) < 10:
            form4_candidates.append((acc, doc, f_date))

    # Parse up to 10 recent Form 4 XMLs so routine RSU grants don't crowd out open-market buys
    form4_transactions: list[dict[str, Any]] = []
    for acc, doc, f_date in form4_candidates[:10]:
        form4_transactions.extend(_parse_form4_xml(cik_int, acc, doc, f_date))

    buys = [t for t in form4_transactions if t["code"] == "P" and t["value_usd"] > 0]
    sales = [t for t in form4_transactions if t["code"] == "S" and t["value_usd"] > 0]
    distinct_buyers = {t["insider_name"] for t in buys}

    open_market_buys_usd = round(sum(t["value_usd"] for t in buys), 2)
    open_market_sales_usd = round(sum(t["value_usd"] for t in sales), 2)
    cluster_insider_buying = len(distinct_buyers) >= 2
    has_302_dilution = any("3.02" in f["items"] for f in filings_8k)
    shelf_dilution_risk = bool(filings_s3_shelf or has_302_dilution)

    sec_tags: list[str] = []
    if len(buys) > 0:
        sec_tags.append("Insider Buying (Form 4)")
    if cluster_insider_buying:
        sec_tags.append("Cluster Insider Buying")
    if any(any(it in ("1.01", "8.01") for it in f["items"]) for f in filings_8k):
        sec_tags.append("8-K Contratto / Catalyst")
    if any(any(it in ("3.01", "4.02", "1.03", "5.03") for it in f["items"]) for f in filings_8k):
        sec_tags.append("8-K Red Flag (Delisting/Restatement)")
    if shelf_dilution_risk:
        sec_tags.append("Rischio Diluizione (S-3/424B5)")

    return {
        "ticker": symbol,
        "cik": cik_padded,
        "entity_name": sub.get("name") or symbol,
        "sic_description": sub.get("sicDescription") or "",
        "edgar_company_url": edgar_company_url,
        "filings_8k": filings_8k,
        "filings_periodic": filings_periodic,
        "filings_s1_ipo": filings_s1_ipo,
        "filings_s3_shelf": filings_s3_shelf,
        "shelf_dilution_risk": shelf_dilution_risk,
        "form4_transactions": form4_transactions[:15],
        "open_market_buys_count": len(buys),
        "open_market_buys_usd": open_market_buys_usd,
        "open_market_sales_count": len(sales),
        "open_market_sales_usd": open_market_sales_usd,
        "cluster_insider_buying": cluster_insider_buying,
        "sec_tags": sec_tags,
        "status": "ok",
    }


def _is_valid_common_ticker(symbol: str) -> bool:
    """Filter out warrants, units, rights, and non-alpha OTC/preferred suffixes."""
    sym = symbol.strip().upper()
    if not sym or not sym.isalpha() or len(sym) > 5:
        return False
    # 5-letter NASDAQ tickers ending in W (warrant), U (unit), R (right) are typically SPAC derivatives
    if len(sym) == 5 and sym[-1] in ("W", "U", "R"):
        return False
    return True


def _parse_sec_atom_ciks(atom_xml: str, form_type: str) -> list[str]:
    """Extract ordered, deduplicated 10-digit issuer/filer CIKs from a SEC EDGAR Atom feed."""
    titles = re.findall(r"<title>(.*?)</title>", atom_xml, flags=re.IGNORECASE | re.DOTALL)
    # Form 4 feeds list both (Reporting) individuals and (Issuer) companies — keep only (Issuer)
    want_tag = "(issuer)" if form_type.strip() == "4" else "(filer)"
    ciks: list[str] = []
    seen: set[str] = set()
    for raw_title in titles:
        t_lower = raw_title.lower()
        if want_tag not in t_lower:
            continue
        match = re.search(r"\((\d{10})\)", raw_title)
        if match:
            cik = match.group(1)
            if cik not in seen:
                seen.add(cik)
                ciks.append(cik)
    return ciks


def discover_recent_sec_filing_tickers(
    forms: tuple[str, ...] = ("4", "8-K"),
    max_per_form: int = 18,
) -> list[dict[str, Any]]:
    """Event-driven SEC EDGAR live radar: discovers US listed tickers with fresh Form 4 or 8-K filings."""
    ticker_to_cik = _load_ticker_cik_map()
    if not ticker_to_cik:
        return []

    # Invert mapping (keep shortest / cleanest primary ticker per CIK)
    cik_to_ticker: dict[str, str] = {}
    for sym, cik in ticker_to_cik.items():
        if not _is_valid_common_ticker(sym):
            continue
        prev = cik_to_ticker.get(cik)
        if prev is None or len(sym) < len(prev):
            cik_to_ticker[cik] = sym

    discovered: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()

    for form_type in forms:
        owner_param = "only" if form_type.strip() == "4" else "include"
        url = (
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
            f"&type={form_type}&owner={owner_param}&count=80&output=atom"
        )
        try:
            resp = requests.get(url, headers=_sec_headers(), timeout=12)
            if not resp.ok:
                continue
            ciks = _parse_sec_atom_ciks(resp.text, form_type)
            added_for_form = 0
            source_label = f"sec_live_form_{form_type.lower().replace('-', '')}"
            for cik in ciks:
                sym = cik_to_ticker.get(cik)
                if not sym or sym in seen_tickers:
                    continue
                seen_tickers.add(sym)
                discovered.append(
                    {
                        "ticker": sym,
                        "source": source_label,
                        "ipo_date_hint": None,
                    }
                )
                added_for_form += 1
                if added_for_form >= max_per_form:
                    break
            time.sleep(0.15)
        except Exception:
            continue

    return discovered
