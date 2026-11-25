"""Quantitative universe discovery and fundamental screening engine."""

from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
import yfinance as yf

from config import settings
from services.sec_edgar import _is_valid_common_ticker, discover_recent_sec_filing_tickers

_US_EXCHANGES = ("NASDAQ", "NYSE", "AMEX", "BATS", "CBOE")


def _is_configured(value: str) -> bool:
    return bool(value) and not value.startswith("your_")


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        num = float(val)
        if math.isnan(num) or math.isinf(num):
            return None
        return num
    except (TypeError, ValueError):
        return None


def _is_in_cooldown(
    ticker: str,
    recently_analyzed: dict[str, str],
    open_portfolio_tickers: set[str],
    cutoff_dt: datetime,
) -> bool:
    """Return True if ticker is already held in open portfolio or analyzed within cooldown window."""
    sym = ticker.strip().upper()
    if sym in open_portfolio_tickers:
        return True
    ts_str = recently_analyzed.get(sym)
    if not ts_str:
        return False
    try:
        analyzed_dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if analyzed_dt.tzinfo is None:
            analyzed_dt = analyzed_dt.replace(tzinfo=timezone.utc)
        return analyzed_dt >= cutoff_dt
    except Exception:
        return False


def _deterministic_rotate(items: list[dict[str, Any]], seed_key: str) -> list[dict[str, Any]]:
    """Deterministically shuffle/rotate a candidate list based on UTC date so every day explores new slices."""
    if len(items) <= 1:
        return list(items)
    copied = list(items)
    digest = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:12], 16)
    rng = random.Random(digest)
    rng.shuffle(copied)
    return copied


def discover_candidate_tickers(
    max_candidates: int = 36,
    recently_analyzed: dict[str, str] | None = None,
    open_portfolio_tickers: set[str] | None = None,
    cooldown_days: int | None = None,
    include_sec_radar: bool = True,
    rotation_seed: str | None = None,
) -> list[dict[str, Any]]:
    """Multi-source rotating universe discovery with cooldown anti-repetition:
    1. Full Finnhub US IPO calendar (6-24 months, excluding warrants/units)
    2. Live SEC EDGAR Form 4 & 8-K event-driven radar
    3. Multi-sector curated post-IPO / micro-cap universe
    Deprioritizes tickers analyzed within `cooldown_days` or already open in portfolio.
    """
    now = datetime.now(timezone.utc)
    cd_days = settings.DISCOVERY_COOLDOWN_DAYS if cooldown_days is None else max(0, int(cooldown_days))
    cutoff_dt = now - timedelta(days=cd_days)
    recent_map = {k.strip().upper(): v for k, v in (recently_analyzed or {}).items() if k}
    open_set = {t.strip().upper() for t in (open_portfolio_tickers or set()) if t}
    day_seed = rotation_seed or now.strftime("%Y-%m-%d")

    # Pool 1: Full Finnhub US IPO Calendar (6-24m)
    finnhub_pool: list[dict[str, Any]] = []
    if _is_configured(settings.FINNHUB_API_KEY):
        try:
            start = (now - timedelta(days=settings.IPO_MAX_MONTHS * 30)).strftime("%Y-%m-%d")
            end = (now - timedelta(days=settings.IPO_MIN_MONTHS * 30)).strftime("%Y-%m-%d")
            resp = requests.get(
                "https://finnhub.io/api/v1/ipo",
                params={"from": start, "to": end, "token": settings.FINNHUB_API_KEY},
                timeout=12,
            )
            if resp.ok:
                seen_fh: set[str] = set()
                for item in resp.json().get("ipoCalendar", []):
                    symbol = (item.get("symbol") or "").strip().upper()
                    exchange = (item.get("exchange") or "").upper()
                    status = (item.get("status") or "").lower()
                    valid_exchange = (not exchange) or any(ex in exchange for ex in _US_EXCHANGES)
                    if (
                        _is_valid_common_ticker(symbol)
                        and status in ("priced", "")
                        and valid_exchange
                        and symbol not in seen_fh
                    ):
                        seen_fh.add(symbol)
                        finnhub_pool.append(
                            {
                                "ticker": symbol,
                                "source": "finnhub_ipo_calendar",
                                "ipo_date_hint": item.get("date"),
                            }
                        )
        except Exception:
            pass

    # Pool 2: Live SEC EDGAR Radar (Form 4 Insider + 8-K Catalysts)
    sec_pool: list[dict[str, Any]] = []
    if include_sec_radar:
        try:
            sec_pool = discover_recent_sec_filing_tickers(forms=("4", "8-K"), max_per_form=18)
        except Exception:
            sec_pool = []

    # Pool 3: Multi-sector curated post-IPO / micro-cap universe
    curated_pool: list[dict[str, Any]] = [
        {
            "ticker": t.strip().upper(),
            "source": "curated_post_ipo_microcap",
            "ipo_date_hint": None,
        }
        for t in settings.DEFAULT_UNIVERSE
        if t.strip()
    ]

    # Deterministic daily rotation so we explore fresh slices instead of repeating index 0..5
    finnhub_rot = _deterministic_rotate(finnhub_pool, f"fh:{day_seed}")
    curated_rot = _deterministic_rotate(curated_pool, f"cur:{day_seed}")
    # SEC live pool is already ordered by most recent filing first

    def _split_fresh(pool: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        fresh, cooling = [], []
        for item in pool:
            if _is_in_cooldown(item["ticker"], recent_map, open_set, cutoff_dt):
                cooling.append(item)
            else:
                fresh.append(item)
        return fresh, cooling

    fh_fresh, fh_cool = _split_fresh(finnhub_rot)
    sec_fresh, sec_cool = _split_fresh(sec_pool)
    cur_fresh, cur_cool = _split_fresh(curated_rot)

    # Round-robin interleave fresh candidates across all 3 sources
    selected: list[dict[str, Any]] = []
    seen_all: set[str] = set()

    def _interleave(queues: list[list[dict[str, Any]]]) -> None:
        idxs = [0] * len(queues)
        while len(selected) < max_candidates:
            progressed = False
            for q_i, q in enumerate(queues):
                while idxs[q_i] < len(q):
                    cand = q[idxs[q_i]]
                    idxs[q_i] += 1
                    sym = cand["ticker"]
                    if sym not in seen_all:
                        seen_all.add(sym)
                        selected.append(cand)
                        progressed = True
                        break
                if len(selected) >= max_candidates:
                    break
            if not progressed:
                break

    # Priority 1: Fresh/unseen candidates across Finnhub IPOs, SEC Live Radar, and Curated Universe
    _interleave([fh_fresh, sec_fresh, cur_fresh])

    # Priority 2 (fallback only if fewer than max_candidates fresh tickers exist): oldest-analyzed cooldown tickers
    if len(selected) < max_candidates:
        all_cooling = fh_cool + sec_cool + cur_cool
        all_cooling.sort(key=lambda c: recent_map.get(c["ticker"], ""))
        for cand in all_cooling:
            sym = cand["ticker"]
            if sym not in seen_all:
                seen_all.add(sym)
                selected.append(cand)
            if len(selected) >= max_candidates:
                break

    return selected[:max_candidates]


def _extract_statement_value(df: Any, row_candidates: list[str]) -> tuple[float | None, float | None]:
    """Return (most_recent, previous_year) values sorted descending by reporting date."""
    if df is None or getattr(df, "empty", True):
        return None, None
    try:
        df_sorted = df.reindex(sorted(df.columns, reverse=True), axis=1)
    except Exception:
        df_sorted = df

    for label in row_candidates:
        if label in df_sorted.index:
            series = df_sorted.loc[label].dropna()
            if len(series) >= 2:
                return _safe_float(series.iloc[0]), _safe_float(series.iloc[1])
            if len(series) == 1:
                return _safe_float(series.iloc[0]), None
    return None, None


def fetch_quant_metrics(ticker: str) -> dict[str, Any]:
    """Fetch full post-IPO price history, drawdown, cash runway, growth, and debt metrics via yfinance."""
    symbol = ticker.strip().upper()
    tk = yf.Ticker(symbol)

    info: dict[str, Any] = {}
    try:
        info = tk.info or {}
    except Exception:
        info = {}

    hist = None
    try:
        hist = tk.history(period="max", auto_adjust=True)
        if hist is None or hist.empty:
            hist = tk.history(period="2y", auto_adjust=True)
    except Exception:
        hist = None

    current_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    if current_price is None and hist is not None and not hist.empty:
        current_price = _safe_float(hist["Close"].iloc[-1])

    # Determine true IPO / first-trade date
    ipo_date_str: str | None = None
    months_since_ipo: float | None = None
    first_trade_sec = info.get("firstTradeDateEpochUtc")
    first_trade_ms = info.get("firstTradeDateMilliseconds")
    ts: float | None = None
    if first_trade_sec is not None:
        ts = _safe_float(first_trade_sec)
        if ts is not None and abs(ts) > 1e10:
            ts /= 1000.0
    elif first_trade_ms is not None:
        ts = _safe_float(first_trade_ms)
        if ts is not None:
            # firstTradeDateMilliseconds is always in ms (pre-2001 dates are < 1e12 ms!)
            ts /= 1000.0

    if ts is not None:
        try:
            ipo_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            ipo_date_str = ipo_dt.strftime("%Y-%m-%d")
            months_since_ipo = round((datetime.now(timezone.utc) - ipo_dt).days / 30.44, 1)
        except (OverflowError, OSError, ValueError):
            ipo_date_str = None
            months_since_ipo = None

    if ipo_date_str is None and hist is not None and not hist.empty:
        first_idx = hist.index[0].to_pydatetime()
        if first_idx.tzinfo is None:
            first_idx = first_idx.replace(tzinfo=timezone.utc)
        ipo_date_str = first_idx.strftime("%Y-%m-%d")
        months_since_ipo = round((datetime.now(timezone.utc) - first_idx).days / 30.44, 1)

    post_ipo_high = None
    post_ipo_drawdown_pct = None
    post_ipo_change_pct = None
    if hist is not None and not hist.empty and current_price is not None:
        hist_high = _safe_float(hist["High"].max())
        post_ipo_high = max(hist_high, current_price) if hist_high is not None else current_price
        first_close = _safe_float(hist["Close"].iloc[0])
        if post_ipo_high and post_ipo_high > 0:
            raw_dd = ((current_price - post_ipo_high) / post_ipo_high) * 100.0
            post_ipo_drawdown_pct = round(min(0.0, raw_dd), 2)
        if first_close and first_close > 0:
            post_ipo_change_pct = round(((current_price - first_close) / first_close) * 100.0, 2)

    market_cap = _safe_float(info.get("marketCap"))
    enterprise_value = _safe_float(info.get("enterpriseValue"))

    try:
        bs = tk.balance_sheet
    except Exception:
        bs = None
    try:
        inc = tk.income_stmt
    except Exception:
        inc = None
    try:
        cf = tk.cashflow
    except Exception:
        cf = None

    cash = _safe_float(info.get("totalCash"))
    if cash is None:
        cash, _ = _extract_statement_value(
            bs,
            [
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Cash Equivalents",
                "Cash Financial",
            ],
        )

    total_debt = _safe_float(info.get("totalDebt"))
    if total_debt is None:
        total_debt, _ = _extract_statement_value(
            bs,
            ["Total Debt", "Long Term Debt And Capital Lease Obligation"],
        )
    total_debt = total_debt or 0.0

    net_cash = round(cash - total_debt, 2) if cash is not None else None

    # Revenue & YoY Growth (preserve 0.0 for pre-revenue firms)
    rev_growth_info = _safe_float(info.get("revenueGrowth"))
    rev_recent, rev_prev = _extract_statement_value(inc, ["Total Revenue", "Operating Revenue"])
    info_rev = _safe_float(info.get("totalRevenue"))
    revenue_ttm = info_rev if info_rev is not None else rev_recent

    revenue_growth_yoy_pct: float | None = None
    if rev_growth_info is not None:
        revenue_growth_yoy_pct = round(rev_growth_info * 100.0, 2)
    elif rev_recent is not None and rev_prev is not None and abs(rev_prev) > 0:
        revenue_growth_yoy_pct = round(((rev_recent - rev_prev) / abs(rev_prev)) * 100.0, 2)

    # Flussi di cassa: usiamo il Free Cash Flow quando è negativo (aziende CapEx-intensive)
    # per evitare di stimare una runway infinita quando OCF >= 0 ma gli investimenti bruciano cassa.
    ocf_ttm = _safe_float(info.get("operatingCashflow"))
    if ocf_ttm is None:
        ocf_ttm, _ = _extract_statement_value(
            cf,
            ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
        )

    fcf_ttm = _safe_float(info.get("freeCashflow"))
    if fcf_ttm is None:
        fcf_ttm, _ = _extract_statement_value(cf, ["Free Cash Flow"])

    effective_cf = (
        fcf_ttm
        if (fcf_ttm is not None and fcf_ttm < 0)
        else (ocf_ttm if ocf_ttm is not None else fcf_ttm)
    )

    is_cash_flow_positive = False
    monthly_burn_usd = 0.0
    runway_months: float | None = None

    if effective_cf is not None:
        if effective_cf >= 0:
            is_cash_flow_positive = True
            runway_months = 99.0
        else:
            monthly_burn_usd = round(abs(effective_cf) / 12.0, 2)
            if cash is not None and monthly_burn_usd > 0:
                runway_months = round(min(cash / monthly_burn_usd, 99.0), 1)

    current_ratio = _safe_float(info.get("currentRatio"))
    if current_ratio is None:
        curr_assets, _ = _extract_statement_value(bs, ["Current Assets"])
        curr_liab, _ = _extract_statement_value(bs, ["Current Liabilities"])
        if curr_assets is not None and curr_liab and curr_liab > 0:
            current_ratio = round(curr_assets / curr_liab, 2)

    debt_to_equity = _safe_float(info.get("debtToEquity"))
    equity, _ = _extract_statement_value(bs, ["Stockholders Equity", "Total Equity Gross Minority Interest"])
    if debt_to_equity is None and equity is not None:
        if equity <= 0 and total_debt > 0:
            debt_to_equity = 999.0
        elif equity > 0:
            debt_to_equity = round((total_debt / equity) * 100.0, 2)

    # Rilevamento debito tossico: evita falsi positivi su software/SaaS a debito zero con ricavi differiti
    toxic_debt_flag = False
    toxic_debt_reasons: list[str] = []
    if current_ratio is not None and current_ratio < 1.0 and total_debt > 0 and not is_cash_flow_positive:
        toxic_debt_flag = True
        toxic_debt_reasons.append(f"Current ratio critico ({current_ratio:.2f}x < 1.0x) con debito attivo")
    if cash is not None and total_debt > max(cash * 2.5, 10_000_000) and not is_cash_flow_positive:
        toxic_debt_flag = True
        toxic_debt_reasons.append("Debito > 2.5x della cassa con cash burn attivo")
    if debt_to_equity is not None and debt_to_equity > 250.0 and not is_cash_flow_positive:
        toxic_debt_flag = True
        toxic_debt_reasons.append(f"Leva elevata o patrimonio netto negativo (D/E {debt_to_equity:.1f}%)")

    gross_margin_pct = _safe_float(info.get("grossMargins"))
    if gross_margin_pct is not None:
        gross_margin_pct = round(gross_margin_pct * 100.0, 2)

    ev_to_sales = None
    if enterprise_value is not None and revenue_ttm and revenue_ttm > 0:
        ev_to_sales = round(enterprise_value / revenue_ttm, 2)

    return {
        "ticker": symbol,
        "company_name": info.get("longName") or info.get("shortName") or symbol,
        "sector": info.get("sector") or "Technology / Emerging",
        "industry": info.get("industry") or "Specialized Tech",
        "exchange": info.get("exchange") or "NASDAQ",
        "currency": info.get("currency") or "USD",
        "website": info.get("website") or "",
        "business_summary": (info.get("longBusinessSummary") or "")[:700],
        "current_price": round(current_price, 2) if current_price is not None else None,
        "ipo_date": ipo_date_str,
        "months_since_ipo": months_since_ipo,
        "post_ipo_high": round(post_ipo_high, 2) if post_ipo_high is not None else None,
        "post_ipo_drawdown_pct": post_ipo_drawdown_pct,
        "post_ipo_change_pct": post_ipo_change_pct,
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "cash_and_equivalents": cash,
        "total_debt": total_debt,
        "net_cash": net_cash,
        "revenue_ttm": revenue_ttm,
        "revenue_growth_yoy_pct": revenue_growth_yoy_pct,
        "gross_margin_pct": gross_margin_pct,
        "ev_to_sales": ev_to_sales,
        "operating_cash_flow_ttm": ocf_ttm,
        "free_cash_flow_ttm": fcf_ttm,
        "monthly_burn_usd": monthly_burn_usd,
        "is_cash_flow_positive": is_cash_flow_positive,
        "runway_months": runway_months,
        "current_ratio": round(current_ratio, 2) if current_ratio is not None else None,
        "debt_to_equity": round(debt_to_equity, 2) if debt_to_equity is not None else None,
        "toxic_debt_flag": toxic_debt_flag,
        "toxic_debt_reasons": toxic_debt_reasons,
        "full_time_employees": info.get("fullTimeEmployees"),
        "is_micro_or_small_cap": (
            market_cap is None or market_cap <= settings.MAX_MARKET_CAP_USD
        ),
        "data_available": current_price is not None,
    }


def evaluate_screening_criteria(metrics: dict[str, Any]) -> dict[str, Any]:
    """Evaluate quantitative survival & post-IPO asymmetry filters (enforcing negative drawdown)."""
    drawdown = metrics.get("post_ipo_drawdown_pct")
    rev_growth = metrics.get("revenue_growth_yoy_pct")
    runway = metrics.get("runway_months")
    is_cf_pos = bool(metrics.get("is_cash_flow_positive"))
    months_ipo = metrics.get("months_since_ipo")
    current_ratio = metrics.get("current_ratio")
    toxic_debt = bool(metrics.get("toxic_debt_flag"))
    is_small_micro = bool(metrics.get("is_micro_or_small_cap", True))

    drawdown_ok = (
        drawdown is not None
        and drawdown < 0
        and -settings.MAX_POST_IPO_DRAWDOWN_PCT <= drawdown <= -settings.MIN_POST_IPO_DRAWDOWN_PCT
    )
    revenue_growth_ok = rev_growth is not None and rev_growth > settings.MIN_REV_GROWTH_YOY
    runway_ok = is_cf_pos or (runway is not None and runway >= settings.MIN_RUNWAY_MONTHS)
    liquidity_ok = (not toxic_debt) and (current_ratio is None or current_ratio >= 1.0)
    strict_ipo_window = (
        months_ipo is not None
        and settings.IPO_MIN_MONTHS <= months_ipo <= settings.IPO_MAX_MONTHS
    )

    passed = bool(
        metrics.get("data_available")
        and drawdown_ok
        and revenue_growth_ok
        and runway_ok
        and liquidity_ok
        and is_small_micro
    )

    tags: list[str] = []
    if drawdown is not None and drawdown <= -20.0:
        tags.append(f"Post-IPO {drawdown:.0f}%")
    if rev_growth is not None and rev_growth >= 20.0:
        tags.append(f"Ricavi +{rev_growth:.0f}% YoY")
    elif revenue_growth_ok:
        tags.append("Ricavi YoY Positivi")
    if is_cf_pos:
        tags.append("Cash Flow Positivo")
    elif runway is not None and runway >= 24.0:
        tags.append(f"Runway {runway:.0f}m")
    elif runway is not None and runway >= 12.0:
        tags.append(f"Runway > 12m ({runway:.0f}m)")
    if metrics.get("net_cash") is not None and metrics["net_cash"] > 0:
        tags.append("Net Cash Positiva")
    if metrics.get("market_cap") and metrics["market_cap"] < 500_000_000:
        tags.append("Pure Micro-Cap")
    if toxic_debt:
        tags.append("Alert Debito Tossico")

    return {
        "passed": passed,
        "strict_ipo_window": strict_ipo_window,
        "filter_breakdown": {
            "drawdown_ok": drawdown_ok,
            "revenue_growth_ok": revenue_growth_ok,
            "runway_ok": runway_ok,
            "liquidity_no_toxic_debt": liquidity_ok,
            "small_or_micro_cap": is_small_micro,
            "strict_ipo_6_24m": strict_ipo_window,
        },
        "quant_tags": tags,
    }
