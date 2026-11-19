import React, { useEffect } from "react";
import {
  X,
  TrendingUp,
  AlertOctagon,
  ShieldCheck,
  Scale,
  FileText,
  ExternalLink,
  Briefcase,
  Newspaper,
  CheckCircle2,
  XCircle,
  PlusCircle,
} from "lucide-react";

function fmtUsd(val) {
  if (val === null || val === undefined) return "N/D";
  const abs = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function SubScoreBar({ label, value, max }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  return (
    <div>
      <div className="flex justify-between text-[11px] text-slate-300">
        <span>{label}</span>
        <span className="font-mono-num font-semibold">
          {value}/{max}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-400"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function getBrokerStatusBadge(status) {
  switch (status) {
    case "DISPONIBILE_0_COMM":
      return { cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30", label: "0% Comm." };
    case "DISPONIBILE_FRAZIONATO":
      return { cls: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30", label: "Disponibile" };
    case "VERIFICA_MICRO_CAP":
      return { cls: "bg-amber-500/15 text-amber-300 border-amber-500/30", label: "Verifica App" };
    default:
      return { cls: "bg-slate-800 text-slate-400 border-slate-700", label: "Solo Intere" };
  }
}

export default function TickerDetailModal({ opportunity, onClose, onLogOrder }) {
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  if (!opportunity) return null;

  const q = opportunity.quant_metrics || {};
  const sec = opportunity.sec_filings || {};
  const news = opportunity.news || {};
  const hiring = opportunity.hiring_signals || {};
  const brokers = opportunity.broker_availability || [];
  const bull = opportunity.debate?.bull || {};
  const bear = opportunity.debate?.bear || {};
  const auditor = opportunity.debate?.auditor || {};
  const subs = opportunity.sub_scores || {};
  const strategy = opportunity.micro_strategy || {};

  // Always preserve S-3 shelf alerts, periodic 10-Q/10-K, S-1 IPO, and 8-K filings without dropping critical docs
  const combinedSecDocs = [
    ...(sec.filings_s3_shelf || []).slice(0, 3),
    ...(sec.filings_8k || []).slice(0, 4),
    ...(sec.filings_periodic || []).slice(0, 2),
    ...(sec.filings_s1_ipo || []).slice(0, 1),
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/80 p-3 backdrop-blur-sm sm:p-6">
      <div className="relative my-4 w-full max-w-6xl rounded-2xl border border-slate-800 bg-[#0c111d] shadow-2xl">
        {/* Sticky Modal Header */}
        <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-t-2xl border-b border-slate-800 bg-[#0c111d]/95 px-5 py-4 backdrop-blur-md">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="font-mono-num text-2xl font-bold text-slate-50">
                {opportunity.ticker}
              </span>
              <span className="rounded-md border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                {opportunity.exchange}
              </span>
              <span className="rounded-full border border-emerald-500/40 bg-emerald-500/15 px-3 py-0.5 font-mono-num text-xs font-bold text-emerald-300">
                Score {opportunity.asymmetry_score}/100 · {opportunity.verdict_label}
              </span>
            </div>
            <p className="mt-0.5 text-sm text-slate-400">
              {opportunity.company_name} · {opportunity.industry}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onLogOrder(opportunity)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500"
            >
              <PlusCircle className="h-4 w-4" />
              Registra Micro-Ordine (€{strategy.recommended_bullet_eur ?? 35})
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Chiudi scheda"
              className="rounded-lg border border-slate-700 bg-slate-800/80 p-2 text-slate-300 transition hover:bg-slate-700 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="space-y-6 p-5 sm:p-6">
          {/* Quantitative Snapshot Bar */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {[
              { label: "Prezzo Attuale", value: `$${q.current_price ?? "N/D"}`, sub: `Picco $${q.post_ipo_high ?? "N/D"}` },
              {
                label: "Drawdown Post-IPO",
                value: q.post_ipo_drawdown_pct != null ? `${q.post_ipo_drawdown_pct}%` : "N/D",
                sub: q.ipo_date ? `IPO ${q.ipo_date}` : "Finestra 6-24m",
              },
              { label: "Market Cap / EV", value: fmtUsd(q.market_cap), sub: `EV/Sales ${q.ev_to_sales ?? "N/D"}x` },
              {
                label: "Cassa / Net Cash",
                value: fmtUsd(q.cash_and_equivalents),
                sub: `Net ${fmtUsd(q.net_cash)}`,
              },
              {
                label: "Cash Runway",
                value: q.is_cash_flow_positive ? "CF Positivo" : `${q.runway_months ?? "N/D"} mesi`,
                sub: q.is_cash_flow_positive ? "Autofinanziata" : `Burn ${fmtUsd(q.monthly_burn_usd)}/m`,
              },
              {
                label: "Crescita Ricavi YoY",
                value: q.revenue_growth_yoy_pct != null ? `${q.revenue_growth_yoy_pct > 0 ? "+" : ""}${q.revenue_growth_yoy_pct}%` : "N/D",
                sub: `Current Ratio ${q.current_ratio ?? "N/D"}x`,
              },
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <div className="text-[11px] text-slate-400">{stat.label}</div>
                <div className="mt-1 font-mono-num text-base font-bold text-slate-100">{stat.value}</div>
                <div className="mt-0.5 font-mono-num text-[10px] text-slate-500">{stat.sub}</div>
              </div>
            ))}
          </div>

          {/* Judge 5-Line Verdict & Sub-Scores */}
          <section className="grid grid-cols-1 gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                <Scale className="h-4 w-4 text-emerald-400" />
                Agente Giudice — Tesi Sintetica in 5 Righe
              </h3>
              <ol className="mt-3 space-y-2 text-xs leading-relaxed text-slate-200 sm:text-sm">
                {(opportunity.thesis_5_lines || []).map((line, i) => (
                  <li key={i} className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-3.5 py-2">
                    {line}
                  </li>
                ))}
              </ol>

              {/* Micro Strategy Box */}
              <div className="mt-3 grid grid-cols-1 gap-2 rounded-xl border border-emerald-500/20 bg-emerald-950/20 p-3 text-xs sm:grid-cols-3">
                <div>
                  <span className="text-slate-400">Fascia Ingresso:</span>
                  <div className="font-medium text-emerald-300">{strategy.entry_zone || "N/D"}</div>
                </div>
                <div>
                  <span className="text-slate-400">Trigger Invalidazione:</span>
                  <div className="font-medium text-rose-300">{strategy.invalidation_trigger || "N/D"}</div>
                </div>
                <div>
                  <span className="text-slate-400">Orizzonte &amp; Ticket:</span>
                  <div className="font-medium text-slate-200">
                    €{strategy.recommended_bullet_eur ?? 35} · {strategy.time_horizon || "12-24m"}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Scomposizione Score
                </span>
                <span className="font-mono-num text-lg font-bold text-emerald-300">
                  {opportunity.asymmetry_score}/100
                </span>
              </div>
              <SubScoreBar label="Catalizzatori & Crescita" value={subs.catalyst_strength ?? 0} max={25} />
              <SubScoreBar label="Sopravvivenza & Runway" value={subs.financial_survival_runway ?? 0} max={25} />
              <SubScoreBar label="Allineamento Insider" value={subs.insider_alignment ?? 0} max={20} />
              <SubScoreBar label="Asimmetria Valutazione" value={subs.valuation_asymmetry ?? 0} max={15} />
              <SubScoreBar label="Confidenza Audit" value={subs.audit_confidence ?? 0} max={15} />
              <div className="pt-1 text-[10px] text-slate-500">
                Motore AI: <span className="font-mono-num text-slate-300">{opportunity.debate?.ai_engine}</span>
              </div>
            </div>
          </section>

          {/* Side-by-Side Bull vs Bear Debate */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Agente Bull */}
            <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/15 p-5">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-bold text-emerald-300">
                  <TrendingUp className="h-4 w-4" />
                  Agente BULL (Catalyst Hunter)
                </h3>
                <span className="rounded-md bg-emerald-500/20 px-2 py-0.5 font-mono-num text-xs font-semibold text-emerald-300">
                  Convinzione {bull.bull_conviction ?? "N/D"}%
                </span>
              </div>
              <p className="mt-2 text-xs font-medium text-slate-200">{bull.headline}</p>

              <div className="mt-3 space-y-2.5">
                {(bull.core_catalysts || []).map((cat, idx) => (
                  <div key={idx} className="rounded-xl border border-emerald-500/20 bg-slate-950/60 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-emerald-200">{cat.title}</span>
                      <span className="shrink-0 rounded bg-emerald-500/15 px-1.5 py-0.5 font-mono-num text-[10px] text-emerald-300">
                        {cat.source_tag}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-300">{cat.detail}</p>
                  </div>
                ))}
              </div>

              <div className="mt-3 space-y-1.5 border-t border-emerald-500/20 pt-3 text-xs text-slate-300">
                <div>
                  <span className="font-semibold text-emerald-300">Lettura Form 4:</span>{" "}
                  {bull.insider_conviction_read}
                </div>
                <div>
                  <span className="font-semibold text-emerald-300">Segnali Careers:</span>{" "}
                  {bull.expansion_signal}
                </div>
              </div>
            </div>

            {/* Agente Bear */}
            <div className="rounded-2xl border border-rose-500/30 bg-rose-950/15 p-5">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-bold text-rose-300">
                  <AlertOctagon className="h-4 w-4" />
                  Agente BEAR (Avvocato del Diavolo)
                </h3>
                <span className="rounded-md bg-rose-500/20 px-2 py-0.5 font-mono-num text-xs font-semibold text-rose-300">
                  Diluizione: {bear.dilution_risk_level ?? "MODERATO"}
                </span>
              </div>
              <p className="mt-2 text-xs font-medium text-slate-200">{bear.headline}</p>

              <div className="mt-3 space-y-2.5">
                {(bear.red_flags || []).map((flag, idx) => (
                  <div key={idx} className="rounded-xl border border-rose-500/20 bg-slate-950/60 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-rose-200">{flag.title}</span>
                      <div className="flex items-center gap-1.5">
                        <span className="rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300">
                          {flag.severity}
                        </span>
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono-num text-[10px] text-slate-300">
                          {flag.source_tag}
                        </span>
                      </div>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-300">{flag.detail}</p>
                  </div>
                ))}
              </div>

              <div className="mt-3 border-t border-rose-500/20 pt-3 text-xs text-slate-300">
                <span className="font-semibold text-rose-300">Audit Cassa &amp; Burn:</span>{" "}
                {bear.burn_and_balance_sheet_audit}
              </div>
            </div>
          </section>

          {/* Agente Auditor / Contro-Verifica */}
          <section className="rounded-2xl border border-cyan-500/30 bg-cyan-950/15 p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-sm font-bold text-cyan-300">
                <ShieldCheck className="h-4 w-4" />
                Agente AUDITOR — Contro-Verifica Anti-Allucinazione
              </h3>
              <span className="rounded-md border border-cyan-500/30 bg-cyan-500/15 px-2.5 py-0.5 font-mono-num text-xs font-semibold text-cyan-200">
                Affidabilità {auditor.overall_reliability ?? "N/D"} (
                {auditor.verification_score !== undefined ? `${auditor.verification_score}%` : "N/D"})
              </span>
            </div>

            <p className="mt-2 rounded-lg border border-cyan-500/20 bg-slate-950/50 p-3 text-xs text-slate-200">
              <span className="font-semibold text-cyan-300">Sanity Check Contabile: </span>
              {auditor.accounting_sanity_check}
            </p>

            <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Fatti Verificati dai Dati Grezzi
                </h4>
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {(auditor.verified_facts || []).map((fact, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                      <span>{fact}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Contestazioni &amp; Correzioni
                </h4>
                {(auditor.challenged_claims || []).length === 0 ? (
                  <p className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-emerald-300">
                    Nessuna esagerazione o dato non verificato rilevato tra Bull e Bear.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {auditor.challenged_claims.map((c, i) => (
                      <div key={i} className="rounded-lg border border-amber-500/30 bg-amber-950/20 p-2.5 text-xs">
                        <div className="flex items-center justify-between font-semibold text-amber-300">
                          <span>Agente {c.agent}</span>
                          <span>{c.audit_verdict}</span>
                        </div>
                        <p className="mt-1 text-slate-300">{c.claim}</p>
                        <p className="mt-1 text-cyan-200">Correzione: {c.correction}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* SEC EDGAR Filings & Form 4 + Alt Data */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* SEC EDGAR Links */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <FileText className="h-4 w-4 text-cyan-400" />
                  Documenti Ufficiali SEC EDGAR {sec.cik ? `(CIK ${sec.cik})` : ""}
                </h3>
                {sec.edgar_company_url && (
                  <a
                    href={sec.edgar_company_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300"
                  >
                    Apri Archivio SEC <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>

              <div className="mt-3 space-y-2">
                {combinedSecDocs.map((f, i) => {
                  const isDilutive = ["S-3", "S-3/A", "S-3ASR", "F-3", "F-3ASR", "424B5", "424B3"].includes(f.form);
                  return (
                    <a
                      key={i}
                      href={f.url}
                      target="_blank"
                      rel="noreferrer"
                      className={`flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs transition ${
                        isDilutive
                          ? "border-rose-500/30 bg-rose-950/20 hover:border-rose-400/50"
                          : "border-slate-800 bg-slate-950/60 hover:border-cyan-500/40"
                      }`}
                    >
                      <div className="min-w-0">
                        <span
                          className={`mr-2 rounded px-1.5 py-0.5 font-mono-num font-semibold ${
                            isDilutive ? "bg-rose-500/20 text-rose-300" : "bg-slate-800 text-cyan-300"
                          }`}
                        >
                          {f.form}
                        </span>
                        <span className="mr-2 font-mono-num text-slate-400">{f.filing_date}</span>
                        <span className="truncate text-slate-200">{f.description}</span>
                      </div>
                      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                    </a>
                  );
                })}
              </div>

              {/* Form 4 Summary */}
              <div className="mt-4 border-t border-slate-800 pt-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-300">Form 4 Insider Transactions</span>
                  <span className="font-mono-num text-emerald-300">
                    Acquisti Codice P: {sec.open_market_buys_count ?? 0} ({fmtUsd(sec.open_market_buys_usd)})
                  </span>
                </div>
                {(sec.form4_transactions || []).length > 0 ? (
                  <div className="mt-2 max-h-40 overflow-y-auto space-y-1.5">
                    {sec.form4_transactions.slice(0, 6).map((tx, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded bg-slate-950/70 px-2.5 py-1.5 text-[11px]"
                      >
                        <div className="truncate">
                          <span
                            className={`mr-1.5 rounded px-1 py-0.5 font-mono-num font-bold ${
                              tx.code === "P"
                                ? "bg-emerald-500/20 text-emerald-300"
                                : tx.code === "S"
                                  ? "bg-rose-500/20 text-rose-300"
                                  : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {tx.code}
                          </span>
                          <span className="text-slate-200">{tx.insider_name}</span>
                          <span className="ml-1 text-slate-500">({tx.role})</span>
                        </div>
                        <a
                          href={tx.url}
                          target="_blank"
                          rel="noreferrer"
                          className="shrink-0 font-mono-num text-cyan-400 hover:underline"
                        >
                          {fmtUsd(tx.value_usd)} ↗
                        </a>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-1.5 text-xs text-slate-500">
                    Nessuna transazione Form 4 recente estratta nel periodo di lookback.
                  </p>
                )}
              </div>
            </div>

            {/* Alternative Data: Careers & News */}
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <div className="flex items-center justify-between">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Briefcase className="h-4 w-4 text-indigo-400" />
                    Segnali Careers &amp; Espansione Organico
                  </h3>
                  <span className="rounded bg-indigo-500/15 px-2 py-0.5 font-mono-num text-xs font-semibold text-indigo-300">
                    {hiring.hiring_trend ?? "UNKNOWN"}
                  </span>
                </div>
                <p className="mt-2 text-xs text-slate-300">{hiring.evidence_note}</p>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-400">
                  <span>
                    Posizioni aperte:{" "}
                    <strong className="font-mono-num text-slate-200">{hiring.open_roles_count ?? "N/D"}</strong>
                  </span>
                  <span>
                    Focus: <strong className="text-slate-200">{hiring.department_focus ?? "N/D"}</strong>
                  </span>
                  {hiring.careers_url && (
                    <a
                      href={hiring.careers_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-cyan-400 hover:underline"
                    >
                      Apri Pagina Careers ↗
                    </a>
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <Newspaper className="h-4 w-4 text-amber-400" />
                  Ultime News &amp; Catalizzatori RSS
                </h3>
                <div className="mt-3 space-y-2">
                  {(news.articles || []).length === 0 ? (
                    <p className="text-xs text-slate-500">Nessun articolo recente recuperato.</p>
                  ) : (
                    news.articles.slice(0, 4).map((art, i) => (
                      <a
                        key={i}
                        href={art.url}
                        target="_blank"
                        rel="noreferrer"
                        className="block rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-xs transition hover:border-slate-700"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-slate-200 line-clamp-1">{art.title}</span>
                          <span
                            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                              art.sentiment_hint === "CATALYST"
                                ? "bg-emerald-500/20 text-emerald-300"
                                : art.sentiment_hint === "RISK"
                                  ? "bg-rose-500/20 text-rose-300"
                                  : art.sentiment_hint === "MIXED"
                                    ? "bg-amber-500/20 text-amber-300"
                                    : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {art.sentiment_hint}
                          </span>
                        </div>
                        <div className="mt-1 text-[10px] text-slate-500">
                          {art.source} · {art.published}
                        </div>
                      </a>
                    ))
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* Fractional Shares & Zero-Commission Broker Availability Check */}
          <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <h3 className="text-sm font-semibold text-slate-100">
              Check Rapido Azioni Frazionate &amp; Commissioni Zero (Micro-Ordini €25–€50)
            </h3>
            <p className="mt-0.5 text-xs text-slate-400">
              Verifica compatibilità stimata per {opportunity.ticker} su piattaforme retail europee / italiane
            </p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-2 pr-3 font-medium">Piattaforma</th>
                    <th className="py-2 px-3 font-medium">Stato</th>
                    <th className="py-2 px-3 font-medium">Frazionate</th>
                    <th className="py-2 px-3 font-medium">Comm. Zero</th>
                    <th className="py-2 px-3 font-medium">Minimo</th>
                    <th className="py-2 px-3 font-medium">FX / Regime</th>
                    <th className="py-2 pl-3 font-medium">Note Micro-Cap</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {brokers.map((b) => {
                    const st = getBrokerStatusBadge(b.status);
                    const minAmt = b.min_order_amount ?? b.min_order_eur ?? 1;
                    const sym = b.min_order_currency === "USD" ? "$" : "€";
                    return (
                      <tr key={b.broker} className="hover:bg-slate-800/30">
                        <td className="py-2.5 pr-3 font-semibold text-slate-100">{b.broker}</td>
                        <td className="py-2.5 px-3">
                          <span className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${st.cls}`}>
                            {st.label}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          {b.fractional_supported ? (
                            <span className="inline-flex items-center gap-1 text-emerald-300">
                              <CheckCircle2 className="h-3.5 w-3.5" /> Sì
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-rose-300">
                              <XCircle className="h-3.5 w-3.5" /> No
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3">
                          {b.zero_commission ? (
                            <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-300">€0</span>
                          ) : (
                            <span className="text-slate-400">Commissione fissa</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono-num text-slate-200">
                          {sym}
                          {minAmt}
                        </td>
                        <td className="py-2.5 px-3 text-slate-400">
                          {b.fx_fee} · {b.italian_tax_regime}
                        </td>
                        <td className="py-2.5 pl-3 text-slate-300">{b.notes}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
