"""Unit and integration tests for IPO & Micro-Cap AI Scouter."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import api  # noqa: E402
import scouter_pipeline  # noqa: E402
from services import autopilot  # noqa: E402
from services.alt_data import _classify_headline, check_broker_fractional_availability  # noqa: E402
from services.quant_screener import evaluate_screening_criteria  # noqa: E402
from services.storage import ScouterStorage  # noqa: E402


def _sample_quant_pass() -> dict:
    return {
        "ticker": "TEST",
        "company_name": "Test Space Corp",
        "sector": "Industrials",
        "industry": "Aerospace & Defense",
        "exchange": "NYSE",
        "currency": "USD",
        "website": "https://example.com",
        "business_summary": "Space infrastructure provider.",
        "current_price": 8.50,
        "ipo_date": "2024-06-15",
        "months_since_ipo": 14.0,
        "post_ipo_high": 18.00,
        "post_ipo_drawdown_pct": -52.78,
        "post_ipo_change_pct": -15.0,
        "market_cap": 420_000_000,
        "enterprise_value": 360_000_000,
        "cash_and_equivalents": 85_000_000,
        "total_debt": 25_000_000,
        "net_cash": 60_000_000,
        "revenue_ttm": 190_000_000,
        "revenue_growth_yoy_pct": 34.5,
        "gross_margin_pct": 31.2,
        "ev_to_sales": 1.89,
        "operating_cash_flow_ttm": -24_000_000,
        "free_cash_flow_ttm": -28_000_000,
        "monthly_burn_usd": 2_000_000,
        "is_cash_flow_positive": False,
        "runway_months": 42.5,
        "current_ratio": 2.1,
        "debt_to_equity": 38.0,
        "toxic_debt_flag": False,
        "toxic_debt_reasons": [],
        "is_micro_or_small_cap": True,
        "data_available": True,
    }


def test_quant_screener_passes_healthy_post_ipo() -> None:
    metrics = _sample_quant_pass()
    res = evaluate_screening_criteria(metrics)
    assert res["passed"] is True
    assert res["strict_ipo_window"] is True
    assert res["filter_breakdown"]["runway_ok"] is True
    assert res["filter_breakdown"]["revenue_growth_ok"] is True
    assert "Net Cash Positiva" in res["quant_tags"]


def test_quant_screener_rejects_positive_drawdown_and_short_runway() -> None:
    metrics = _sample_quant_pass()
    metrics["post_ipo_drawdown_pct"] = 20.0
    res_pos = evaluate_screening_criteria(metrics)
    assert res_pos["passed"] is False
    assert res_pos["filter_breakdown"]["drawdown_ok"] is False

    metrics2 = _sample_quant_pass()
    metrics2["runway_months"] = 6.5
    metrics2["toxic_debt_flag"] = True
    metrics2["current_ratio"] = 0.72
    res = evaluate_screening_criteria(metrics2)
    assert res["passed"] is False
    assert res["filter_breakdown"]["runway_ok"] is False
    assert res["filter_breakdown"]["liquidity_no_toxic_debt"] is False


def test_multi_agent_debate_and_auditor_cross_verification() -> None:
    quant = _sample_quant_pass()
    screening = evaluate_screening_criteria(quant)
    sec = {
        "cik": "0001819810",
        "filings_8k": [
            {
                "form": "8-K",
                "filing_date": "2026-10-15",
                "items": ["1.01", "8.01"],
                "item_descriptions": ["Item 1.01: Accordo / Contratto Materiale"],
                "description": "Item 1.01: Accordo / Contratto Materiale",
                "url": "https://www.sec.gov/Archives/edgar/data/1819810/test/test.htm",
            }
        ],
        "filings_s3_shelf": [],
        "shelf_dilution_risk": False,
        "open_market_buys_count": 2,
        "open_market_buys_usd": 245000.0,
        "open_market_sales_count": 0,
        "open_market_sales_usd": 0.0,
        "cluster_insider_buying": True,
        "form4_transactions": [
            {
                "filing_date": "2026-10-20",
                "transaction_date": "2026-10-18",
                "insider_name": "Jane Doe",
                "role": "CEO",
                "code": "P",
                "acquired_or_disposed": "A",
                "shares": 20000,
                "price_usd": 8.0,
                "value_usd": 160000.0,
                "url": "https://www.sec.gov/Archives/edgar/data/1819810/test/form4.xml",
            }
        ],
    }
    news = {
        "articles": [
            {
                "title": "Test Space Corp wins multi-year patent & defense contract",
                "url": "https://example.com/news",
                "published": "2026-10-22",
                "source": "MarketWire",
                "sentiment_hint": "CATALYST",
            }
        ],
        "catalyst_headlines_count": 1,
        "risk_headlines_count": 0,
    }
    hiring = {
        "open_roles_count": 26,
        "hiring_trend": "HIRING_SPIKE",
        "department_focus": "R&D / Engineering",
        "ats_source": "Greenhouse",
        "careers_url": "https://boards.greenhouse.io/test",
        "sample_roles": ["RF Systems Engineer", "Flight Software Engineer"],
        "evidence_note": "Rilevate 26 posizioni aperte via Greenhouse.",
    }

    payload = scouter_pipeline._build_ground_truth_payload(quant, screening, sec, news, hiring)
    bull = scouter_pipeline._fallback_bull(payload)
    bear = scouter_pipeline._fallback_bear(payload)
    auditor = scouter_pipeline._fallback_auditor(payload, bull, bear)
    judge = scouter_pipeline._enforce_judge_invariants(
        scouter_pipeline._fallback_judge(payload, bull, bear, auditor),
        payload,
        bull,
        bear,
        auditor,
    )

    assert len(judge["thesis_5_lines"]) == 5
    assert judge["asymmetry_score"] == sum(judge["sub_scores"].values())
    assert judge["asymmetry_score"] >= 75
    assert judge["verdict_label"] == "STRONG_ASYMMETRIC_BUY"
    assert auditor["verification_score"] >= 80
    assert "Insider Buying" in judge["signal_tags"]


def test_judge_invariants_sanitize_malformed_llm_output() -> None:
    quant = _sample_quant_pass()
    screening = evaluate_screening_criteria(quant)
    sec = {"cik": "0001819810", "filings_8k": [], "filings_s3_shelf": [], "shelf_dilution_risk": False}
    payload = scouter_pipeline._build_ground_truth_payload(
        quant, screening, sec, {"articles": []}, {}
    )
    malformed_judge = {
        "sub_scores": {
            "catalyst_strength": None,
            "financial_survival_runway": "18/25",
            "insider_alignment": "bad",
            "valuation_asymmetry": 0,
            "audit_confidence": 12,
        },
        "thesis_5_lines": "Riga uno test\nRiga due test",
        "micro_strategy": None,
    }
    res = scouter_pipeline._enforce_judge_invariants(
        malformed_judge, payload, {}, {}, {"verification_score": 85}
    )
    assert len(res["thesis_5_lines"]) == 5
    assert res["thesis_5_lines"][0] == "Riga uno test"
    assert res["asymmetry_score"] == sum(res["sub_scores"].values())
    assert isinstance(res["micro_strategy"], dict)


def test_auditor_challenges_unverified_insider_claim() -> None:
    quant = _sample_quant_pass()
    screening = evaluate_screening_criteria(quant)
    sec = {
        "cik": "0001819810",
        "filings_8k": [],
        "filings_s3_shelf": [],
        "shelf_dilution_risk": False,
        "open_market_buys_count": 0,
        "open_market_buys_usd": 0.0,
        "open_market_sales_count": 0,
        "open_market_sales_usd": 0.0,
        "cluster_insider_buying": False,
        "form4_transactions": [],
    }
    payload = scouter_pipeline._build_ground_truth_payload(
        quant, screening, sec, {"articles": [], "catalyst_headlines_count": 0, "risk_headlines_count": 0}, {}
    )
    fake_bull = {
        "core_catalysts": [
            {"title": "Massiccio Insider Buying", "detail": "Acquisti dei manager.", "source_tag": "[FORM-4]"}
        ]
    }
    fake_bear = {"dilution_risk_level": "ALTO"}
    auditor = scouter_pipeline._fallback_auditor(payload, fake_bull, fake_bear)
    agents_challenged = {c["agent"] for c in auditor["challenged_claims"]}
    assert "BULL" in agents_challenged
    assert "BEAR" in agents_challenged


def test_news_headline_classifier_uses_word_boundaries() -> None:
    assert _classify_headline("Company signs cutting-edge European space deal with executive team") == "CATALYST"
    assert _classify_headline("Firm announces 50M shelf offering and layoffs") == "RISK"


def test_broker_fractional_check_returns_italian_platforms() -> None:
    brokers = check_broker_fractional_availability("RDW", "NYSE", current_price=11.2, market_cap=750_000_000)
    names = {b["broker"] for b in brokers}
    assert "Trading 212" in names
    assert "Interactive Brokers (IBKR)" in names
    assert "Trade Republic" in names
    assert "Directa SIM" in names
    t212 = next(b for b in brokers if b["broker"] == "Trading 212")
    assert t212["fractional_supported"] is True
    assert t212["zero_commission"] is True


def test_journal_crud_and_monthly_limit_enforcement(tmp_path: Path, monkeypatch) -> None:
    temp_store = ScouterStorage(store_path=tmp_path / "test_store.json")
    temp_store.upsert_opportunity(
        {
            "ticker": "RDW",
            "asymmetry_score": 82,
            "verdict_label": "STRONG_ASYMMETRIC_BUY",
            "quant_metrics": {"current_price": 12.0},
            "sec_filings": {"shelf_dilution_risk": False},
        }
    )
    monkeypatch.setattr(api, "storage", temp_store)

    client = TestClient(api.app)
    created_ids = []
    for i in range(5):
        resp = client.post(
            "/api/journal",
            json={
                "ticker": "RDW",
                "order_date": "2026-11-19",
                "amount_eur": 35.0,
                "entry_price_usd": 10.0,
                "broker": "Trading 212",
                "fractional": True,
                "initial_thesis": f"Contratti difesa 8-K #{i}",
                "invalidation_rule": "Runway sotto 12 mesi",
                "initial_ai_score": 80,
            },
        )
        assert resp.status_code == 201
        created_ids.append(resp.json()["order"]["id"])

    # 6th order in same month must be rejected without override
    blocked = client.post(
        "/api/journal",
        json={
            "ticker": "RDW",
            "order_date": "2026-11-19",
            "amount_eur": 35.0,
            "entry_price_usd": 10.0,
            "broker": "Trading 212",
            "fractional": True,
            "initial_thesis": "Ordine extra non forzato",
        },
    )
    assert blocked.status_code == 400

    # Delete one and verify slots free up
    del_resp = client.delete(f"/api/journal/{created_ids[0]}")
    assert del_resp.status_code == 200
    assert del_resp.json()["journal"]["summary"]["monthly_orders_used"] == 4


def _seed_autopilot_opportunities(store: ScouterStorage) -> None:
    store.upsert_opportunity(
        {
            "ticker": "ALPHA",
            "asymmetry_score": 82,
            "verdict_label": "STRONG_ASYMMETRIC_BUY",
            "thesis_5_lines": ["1. Contratto 8-K.", "2. Cassa 30m.", "3. Insider buy.", "4. Ok.", "5. Ticket 35."],
            "quant_metrics": {"current_price": 10.0, "runway_months": 30.0, "is_cash_flow_positive": False},
            "sec_filings": {"shelf_dilution_risk": False},
            "debate": {"auditor": {"verification_score": 92}, "bear": {"dilution_risk_level": "BASSO"}},
            "micro_strategy": {"invalidation_trigger": "Runway < 12m"},
        }
    )
    store.upsert_opportunity(
        {
            "ticker": "LOWAUD",
            "asymmetry_score": 78,
            "verdict_label": "STRONG_ASYMMETRIC_BUY",
            "thesis_5_lines": ["1. Tesi.", "2. Cassa.", "3. Insider.", "4. Audit basso.", "5. Plan."],
            "quant_metrics": {"current_price": 8.0, "runway_months": 20.0, "is_cash_flow_positive": False},
            "sec_filings": {"shelf_dilution_risk": False},
            "debate": {"auditor": {"verification_score": 60}, "bear": {"dilution_risk_level": "MODERATO"}},
        }
    )
    store.upsert_opportunity(
        {
            "ticker": "WEAK",
            "asymmetry_score": 62,
            "verdict_label": "WATCHLIST_ACCUMULATE",
            "thesis_5_lines": ["1. Tesi.", "2. Cassa.", "3. Insider.", "4. Ok.", "5. Plan."],
            "quant_metrics": {"current_price": 5.0, "runway_months": 24.0, "is_cash_flow_positive": False},
            "sec_filings": {"shelf_dilution_risk": False},
            "debate": {"auditor": {"verification_score": 90}, "bear": {"dilution_risk_level": "BASSO"}},
        }
    )


def test_autopilot_auto_register_guardrails_and_dry_run(tmp_path: Path) -> None:
    store = ScouterStorage(store_path=tmp_path / "ap_store.json")
    _seed_autopilot_opportunities(store)

    # Dry-run must preview ALPHA and reject LOWAUD (audit < 80) and WEAK (score < 75) without persisting
    preview = autopilot.evaluate_and_auto_register(dry_run=True, store=store)
    assert len(preview["registered"]) == 1
    assert preview["registered"][0]["ticker"] == "ALPHA"
    assert len(preview["skipped"]) == 2
    assert len(store.list_micro_orders()["orders"]) == 0

    # Real auto-register creates PAPER_AUTO order and blocks duplicate on 2nd run
    exec_res = autopilot.evaluate_and_auto_register(dry_run=False, store=store)
    assert len(exec_res["registered"]) == 1
    assert exec_res["registered"][0]["mode"] == "PAPER_AUTO"
    assert exec_res["journal"]["summary"]["monthly_orders_used"] == 1

    second_run = autopilot.evaluate_and_auto_register(dry_run=False, store=store)
    assert len(second_run["registered"]) == 0
    alpha_skip = next(s for s in second_run["skipped"] if s["ticker"] == "ALPHA")
    assert any("già aperta" in r for r in alpha_skip["reasons"])


def test_autopilot_monitor_tp_sl_thesis_and_real_order_protection(tmp_path: Path) -> None:
    store = ScouterStorage(store_path=tmp_path / "mon_store.json")
    _seed_autopilot_opportunities(store)

    # 1) PAPER_AUTO hitting Take Profit (+70% >= +60%)
    tp_order = store.add_micro_order(
        {
            "ticker": "TP_TICK",
            "amount_eur": 35.0,
            "entry_price_usd": 10.0,
            "mode": "PAPER_AUTO",
            "take_profit_pct": 60.0,
            "stop_loss_pct": -35.0,
            "initial_thesis": "Test TP",
            "initial_ai_score": 80,
        }
    )
    # 2) PAPER_MANUAL hitting Stop Loss (-40% <= -35%)
    sl_order = store.add_micro_order(
        {
            "ticker": "SL_TICK",
            "amount_eur": 35.0,
            "entry_price_usd": 10.0,
            "mode": "PAPER_MANUAL",
            "take_profit_pct": 60.0,
            "stop_loss_pct": -35.0,
            "initial_thesis": "Test SL",
            "initial_ai_score": 80,
        }
    )
    # 3) PAPER_AUTO hitting Thesis Stop (score dropped from 82 to 50)
    store.upsert_opportunity(
        {
            "ticker": "THESIS_TICK",
            "asymmetry_score": 50,
            "verdict_label": "AVOID_DILUTION_TRAP",
            "quant_metrics": {"current_price": 9.8},
            "sec_filings": {"shelf_dilution_risk": True},
        }
    )
    th_order = store.add_micro_order(
        {
            "ticker": "THESIS_TICK",
            "amount_eur": 35.0,
            "entry_price_usd": 10.0,
            "mode": "PAPER_AUTO",
            "initial_thesis": "Test Thesis Drop",
            "initial_ai_score": 82,
        }
    )
    # 4) REAL order hitting TP -> MUST NOT auto-close; MUST only emit alert
    real_order = store.add_micro_order(
        {
            "ticker": "REAL_TICK",
            "amount_eur": 35.0,
            "entry_price_usd": 10.0,
            "mode": "REAL",
            "initial_thesis": "Real order protection test",
            "initial_ai_score": 80,
        }
    )

    mock_prices = {
        "TP_TICK": 17.0,     # +70%
        "SL_TICK": 6.0,      # -40%
        "THESIS_TICK": 9.8,  # -2%, but score 50 < 55
        "REAL_TICK": 18.0,   # +80%, must NOT close
    }

    mon_res = autopilot.run_portfolio_monitor(
        refresh_live_prices=True,
        rescan_ai=False,
        store=store,
        price_fetcher=lambda sym: mock_prices.get(sym),
    )

    assert mon_res["checked_count"] == 4
    closed_ids = {c["order_id"] for c in mon_res["auto_closed"]}
    alert_ids = {a["order_id"] for a in mon_res["alerts"]}

    assert tp_order["id"] in closed_ids
    assert sl_order["id"] in closed_ids
    assert th_order["id"] in closed_ids
    assert real_order["id"] not in closed_ids
    assert real_order["id"] in alert_ids

    orders_by_id = {o["id"]: o for o in mon_res["journal"]["orders"]}
    assert orders_by_id[tp_order["id"]]["status"] == "CHIUSO"
    assert "TAKE_PROFIT" in orders_by_id[tp_order["id"]]["close_reason"]
    assert orders_by_id[real_order["id"]]["status"] == "APERTO"
    assert len(orders_by_id[real_order["id"]]["price_history"]) >= 2


def test_autopilot_api_endpoints(tmp_path: Path, monkeypatch) -> None:
    temp_store = ScouterStorage(store_path=tmp_path / "api_ap_store.json")
    _seed_autopilot_opportunities(temp_store)
    monkeypatch.setattr(api, "storage", temp_store)
    monkeypatch.setattr(autopilot, "default_storage", temp_store)

    client = TestClient(api.app)

    st_resp = client.get("/api/autopilot/status")
    assert st_resp.status_code == 200
    assert st_resp.json()["config"]["min_asymmetry_score"] == 75

    put_resp = client.put("/api/autopilot/config", json={"take_profit_pct": 75.0, "min_asymmetry_score": 78})
    assert put_resp.status_code == 200
    assert put_resp.json()["config"]["take_profit_pct"] == 75.0

    dry_resp = client.post("/api/autopilot/auto-register", json={"dry_run": True})
    assert dry_resp.status_code == 200
    assert len(dry_resp.json()["registered"]) == 1

    reg_resp = client.post("/api/autopilot/auto-register", json={"dry_run": False})
    assert reg_resp.status_code == 200
    assert len(reg_resp.json()["registered"]) == 1

    mon_resp = client.post("/api/autopilot/monitor", json={"refresh_live_prices": False, "rescan_ai": False})
    assert mon_resp.status_code == 200
    assert mon_resp.json()["checked_count"] == 1


def test_audit_fixes_close_price_lock_real_alert_dedup_and_config_validation(tmp_path: Path, monkeypatch) -> None:
    temp_store = ScouterStorage(store_path=tmp_path / "audit_ap_store.json")
    temp_store.upsert_opportunity(
        {
            "ticker": "LOCKTEST",
            "asymmetry_score": 80,
            "quant_metrics": {"current_price": 15.0},
            "sec_filings": {"shelf_dilution_risk": False},
        }
    )
    monkeypatch.setattr(api, "storage", temp_store)
    monkeypatch.setattr(autopilot, "default_storage", temp_store)

    client = TestClient(api.app)

    # 1. Cross-field validation: thesis_degrade_min_score >= min_asymmetry_score -> 400
    bad_cfg = client.put("/api/autopilot/config", json={"min_asymmetry_score": 60, "thesis_degrade_min_score": 65})
    assert bad_cfg.status_code == 400

    # 2. Manual close locks exit_price_usd; re-scanning opportunity price does NOT mutate realized PnL
    ord_resp = client.post(
        "/api/journal",
        json={
            "ticker": "LOCKTEST",
            "amount_eur": 40.0,
            "entry_price_usd": 10.0,
            "mode": "PAPER_MANUAL",
            "initial_thesis": "Test exit price locking",
        },
    )
    assert ord_resp.status_code == 201
    oid = ord_resp.json()["order"]["id"]

    temp_store.record_order_checkpoint(oid, 15.0, 80, 50.0)
    closed = client.patch(f"/api/journal/{oid}", json={"status": "CHIUSO"})
    assert closed.status_code == 200
    assert closed.json()["order"]["exit_price_usd"] == 15.0

    # Mutate opportunity price afterwards -> realized PnL must stay +50% (€20.0)
    temp_store.upsert_opportunity({"ticker": "LOCKTEST", "asymmetry_score": 80, "quant_metrics": {"current_price": 5.0}})
    j_after = client.get("/api/journal").json()
    assert j_after["summary"]["paper_realized_pnl_eur"] == 20.0

    # Reopening clears exit_price_usd
    reopened = client.patch(f"/api/journal/{oid}", json={"status": "APERTO"})
    assert reopened.status_code == 200
    assert reopened.json()["order"]["exit_price_usd"] is None

    # 3. REAL alert deduplication + no checkpoint pollution when refresh_live_prices=False
    real_o = temp_store.add_micro_order(
        {
            "ticker": "REALDUP",
            "amount_eur": 35.0,
            "entry_price_usd": 10.0,
            "mode": "REAL",
            "initial_thesis": "Real alert cooldown check",
            "initial_ai_score": 80,
        }
    )
    autopilot.run_portfolio_monitor(
        refresh_live_prices=True,
        rescan_ai=False,
        store=temp_store,
        price_fetcher=lambda s: 18.0 if s == "REALDUP" else 15.0,
    )
    autopilot.run_portfolio_monitor(
        refresh_live_prices=True,
        rescan_ai=False,
        store=temp_store,
        price_fetcher=lambda s: 18.0 if s == "REALDUP" else 15.0,
    )
    alert_logs = [lg for lg in temp_store.list_autopilot_logs() if lg["action"] == "ALERT" and lg["ticker"] == "REALDUP"]
    assert len(alert_logs) == 1

    # refresh_live_prices=False does not inflate price_history
    before_len = len(next(o for o in temp_store.list_micro_orders()["orders"] if o["id"] == real_o["id"])["price_history"])
    autopilot.run_portfolio_monitor(refresh_live_prices=False, rescan_ai=False, store=temp_store)
    after_len = len(next(o for o in temp_store.list_micro_orders()["orders"] if o["id"] == real_o["id"])["price_history"])
    assert after_len == before_len


def test_snapshot_export_and_monitor_only(tmp_path: Path, monkeypatch) -> None:
    import json

    temp_store = ScouterStorage(store_path=tmp_path / "snap_store.json")
    temp_store.upsert_opportunity(
        {
            "ticker": "SNAPT",
            "asymmetry_score": 81,
            "verdict_label": "STRONG_ASYMMETRIC_BUY",
            "quant_metrics": {"current_price": 12.5, "runway_months": 30.0},
            "debate": {"auditor": {"verification_score": 90}},
        }
    )
    temp_store.add_micro_order(
        {
            "ticker": "SNAPT",
            "amount_eur": 35.0,
            "entry_price_usd": 10.0,
            "mode": "PAPER_AUTO",
            "initial_thesis": "Snapshot test",
        }
    )
    snap_out = tmp_path / "scouter_snapshot.json"
    monkeypatch.setattr(scouter_pipeline, "storage", temp_store)
    monkeypatch.setattr(autopilot, "default_storage", temp_store)
    monkeypatch.setattr(autopilot, "fetch_fast_live_price", lambda _s: 12.5)
    monkeypatch.setattr(temp_store, "export_frontend_snapshot", lambda output_path=None: ScouterStorage.export_frontend_snapshot(temp_store, snap_out))

    res = scouter_pipeline.run_monitor_only(export_snapshot=True)
    assert res["mode"] == "monitor_only"
    assert res["checked_count"] == 1
    assert snap_out.exists()

    snap = json.loads(snap_out.read_text(encoding="utf-8"))
    assert snap["health"]["static_readonly"] is True
    assert snap["opportunities"]["count"] == 1
    assert snap["journal"]["summary"]["monthly_orders_used"] == 1
    assert len(snap["autopilot"]["logs"]) >= 1

