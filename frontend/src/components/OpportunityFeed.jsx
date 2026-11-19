import React, { useMemo, useState } from "react";
import HowItWorksBanner from "./HowItWorksBanner";
import {
  TrendingDown,
  ShieldCheck,
  AlertTriangle,
  ArrowUpRight,
  Filter,
  Flame,
  PlusCircle,
  Clock,
  DollarSign,
  Briefcase,
  ChevronRight,
  TrendingUp,
} from "lucide-react";

function formatCompactUsd(val) {
  if (val === null || val === undefined) return "N/D";
  const abs = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function getScoreColors(score) {
  if (score >= 75) {
    return {
      ring: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
      badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
      label: "Alta Asimmetria",
    };
  }
  if (score >= 55) {
    return {
      ring: "border-amber-500/40 bg-amber-500/15 text-amber-300",
      badge: "bg-amber-500/15 text-amber-300 border-amber-500/30",
      label: "Watchlist",
    };
  }
  return {
    ring: "border-rose-500/40 bg-rose-500/15 text-rose-300",
    badge: "bg-rose-500/15 text-rose-300 border-rose-500/30",
    label: "Rischio / Evita",
  };
}

function getTagStyle(tag) {
  const lower = tag.toLowerCase();
  if (lower.includes("diluizione") || lower.includes("debito")) {
    return "border-rose-500/30 bg-rose-500/10 text-rose-300";
  }
  if (lower.includes("insider")) {
    return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
  }
  if (lower.includes("8-k") || lower.includes("brevetto") || lower.includes("contratto")) {
    return "border-cyan-500/30 bg-cyan-500/10 text-cyan-300";
  }
  if (lower.includes("hiring")) {
    return "border-indigo-500/30 bg-indigo-500/10 text-indigo-300";
  }
  return "border-slate-700 bg-slate-800/80 text-slate-300";
}

export default function OpportunityFeed({
  opportunities,
  journalSummary,
  orders = [],
  onSelectTicker,
  onQuickLogOrder,
  onGoToJournal,
  onGoToAutoPilot,
}) {
  const [minScoreFilter, setMinScoreFilter] = useState(0);
  const [tagFilter, setTagFilter] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const openOrders = useMemo(
    () => orders.filter((o) => (o.status || "APERTO") === "APERTO"),
    [orders]
  );

  const availableTags = useMemo(() => {
    const set = new Set();
    opportunities.forEach((o) => (o.signal_tags || []).forEach((t) => set.add(t)));
    return ["ALL", ...Array.from(set)];
  }, [opportunities]);

  const filtered = useMemo(() => {
    return opportunities.filter((item) => {
      if ((item.asymmetry_score || 0) < minScoreFilter) return false;
      if (tagFilter !== "ALL" && !(item.signal_tags || []).includes(tagFilter)) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const hit =
          item.ticker?.toLowerCase().includes(q) ||
          item.company_name?.toLowerCase().includes(q) ||
          item.sector?.toLowerCase().includes(q) ||
          item.industry?.toLowerCase().includes(q);
        if (!hit) return false;
      }
      return true;
    });
  }, [opportunities, minScoreFilter, tagFilter, searchQuery]);

  const topDaily = useMemo(
    () => opportunities.filter((o) => (o.asymmetry_score || 0) >= 55).slice(0, 5),
    [opportunities]
  );
  const highConvictionCount = opportunities.filter((o) => o.asymmetry_score >= 75).length;
  const avgScore = opportunities.length
    ? Math.round(opportunities.reduce((acc, o) => acc + (o.asymmetry_score || 0), 0) / opportunities.length)
    : 0;

  return (
    <div className="space-y-6">
      {/* Guida Metodologia & Come Funziona */}
      <HowItWorksBanner />

      {/* KPI Summary Strip */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Top Picks Giornalieri</span>
            <Flame className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-mono-num text-2xl font-bold text-slate-50">
              {topDaily.length}
            </span>
            <span className="text-xs text-emerald-400">
              ({highConvictionCount} sopra soglia 75)
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Media Asymmetry Score</span>
            <ShieldCheck className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-mono-num text-2xl font-bold text-slate-50">{avgScore}</span>
            <span className="text-xs text-slate-400">/ 100 (Contro-Verificato)</span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Cartucce Mensili Disponibili</span>
            <DollarSign className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-mono-num text-2xl font-bold text-slate-50">
              {journalSummary?.monthly_slots_remaining ?? 10}
            </span>
            <span className="text-xs text-slate-400">
              su {journalSummary?.monthly_orders_limit ?? 10} ordini/mese
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Approccio Strategico</span>
            <Clock className="h-4 w-4 text-indigo-400" />
          </div>
          <div className="mt-2 text-xs leading-relaxed text-slate-300">
            Micro-ticket <span className="font-mono-num font-semibold text-emerald-300">€25–€50</span> frazionati · Orizzonte lento 12–24m
          </div>
        </div>
      </section>

      {/* Portafoglio Attivo (Paper Trading Auto-Pilot) */}
      {openOrders.length > 0 && (
        <section className="rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-slate-900/95 via-slate-900/70 to-slate-950 p-4 sm:p-5 shadow-lg shadow-emerald-950/15">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-slate-800/80 pb-3.5">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/40 bg-emerald-500/10 text-emerald-400">
                <Briefcase className="h-4 w-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-slate-100">Il Tuo Portafoglio Attivo</h3>
                  <span className="rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                    {openOrders.length} {openOrders.length === 1 ? "posizione aperta" : "posizioni aperte"}
                  </span>
                  <span className="rounded-full border border-cyan-500/40 bg-cyan-500/15 px-2 py-0.5 text-[10px] font-semibold text-cyan-300">
                    Paper Auto-Pilot
                  </span>
                </div>
                <p className="text-xs text-slate-400">Monitoraggio prezzi in tempo reale con exit strategy asimmetrica</p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 sm:gap-4 text-xs">
              <div>
                <span className="text-slate-400">Equity: </span>
                <span className="font-mono-num font-bold text-slate-100">€{(journalSummary?.paper_total_equity_eur ?? 1000).toFixed(2)}</span>
              </div>
              <div>
                <span className="text-slate-400">P&L Totale: </span>
                <span className={`font-mono-num font-bold ${(journalSummary?.total_pnl_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {(journalSummary?.total_pnl_pct ?? 0) >= 0 ? "+" : ""}{(journalSummary?.total_pnl_pct ?? 0).toFixed(2)}% (€{((journalSummary?.total_pnl_eur ?? 0) >= 0 ? "+" : "")}{(journalSummary?.total_pnl_eur ?? 0).toFixed(2)})
                </span>
              </div>
              {onGoToJournal && (
                <button
                  type="button"
                  onClick={onGoToJournal}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-200 hover:border-slate-600 hover:text-white transition"
                >
                  Dettagli Diario <ChevronRight className="h-3.5 w-3.5 text-cyan-400" />
                </button>
              )}
            </div>
          </div>

          {/* Griglia delle posizioni aperte */}
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {openOrders.map((ord) => {
              const pnl = ord.pnl_pct ?? 0;
              const isProfit = pnl >= 0;
              const entry = ord.entry_price_usd ? `$${ord.entry_price_usd.toFixed(2)}` : "N/D";
              const current = ord.latest_price_usd ? `$${ord.latest_price_usd.toFixed(2)}` : entry;
              const tp1Target = ord.take_profit_pct ? ord.take_profit_pct : 25;
              const progressTp1 = Math.max(0, Math.min(100, Math.round((pnl / tp1Target) * 100)));

              return (
                <div
                  key={ord.id}
                  className="rounded-xl border border-slate-800/90 bg-slate-900/60 p-3.5 hover:border-slate-700 transition"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-mono-num text-sm font-bold text-white">{ord.ticker}</span>
                      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                        €{(ord.current_value_eur ?? ord.amount_eur ?? 35).toFixed(2)}
                      </span>
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 font-mono-num text-[11px] font-bold ${
                        isProfit
                          ? "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                          : "border border-rose-500/40 bg-rose-500/15 text-rose-300"
                      }`}
                    >
                      {isProfit ? "+" : ""}{pnl.toFixed(2)}%
                    </span>
                  </div>

                  <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
                    <span>Ingresso: <strong className="text-slate-200">{entry}</strong></span>
                    <span>Prezzo Live: <strong className="text-slate-200">{current}</strong></span>
                  </div>

                  {/* Barra di avanzamento verso TP1 */}
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                      <span>Avanzamento TP1 (+{tp1Target}%)</span>
                      <span className="font-mono-num font-semibold text-emerald-400">{progressTp1}%</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400 rounded-full transition-all duration-500"
                        style={{ width: `${progressTp1}%` }}
                      />
                    </div>
                  </div>

                  <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-500 border-t border-slate-800/60 pt-2">
                    <span>SL: {ord.stop_loss_pct ? `${ord.stop_loss_pct}%` : "-20%"}</span>
                    <span className="text-slate-400">{ord.broker || "Trading 212 (Paper)"}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Top 3-5 Daily Opportunities Highlight Strip */}
      {topDaily.length > 0 && (
        <section className="rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-emerald-950/25 via-slate-900/80 to-slate-950 p-4 sm:p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-emerald-300">
                <Flame className="h-4 w-4" />
                Top {topDaily.length} Opportunità Asimmetriche del Giorno
              </h2>
              <p className="text-xs text-slate-400">
                Titoli post-IPO / micro-cap con miglior rapporto catalizzatori vs rischio diluizione (Score ≥ 55)
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3 lg:grid-cols-5">
            {topDaily.map((opp, idx) => {
              const colors = getScoreColors(opp.asymmetry_score);
              const q = opp.quant_metrics || {};
              return (
                <button
                  key={opp.ticker}
                  type="button"
                  onClick={() => onSelectTicker(opp)}
                  className="group flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 text-left transition hover:border-emerald-500/50 hover:bg-slate-900"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-slate-500">
                        #{idx + 1} PICK
                      </span>
                      <span
                        className={`rounded-md border px-2 py-0.5 font-mono-num text-xs font-bold ${colors.ring}`}
                      >
                        {opp.asymmetry_score}/100
                      </span>
                    </div>
                    <div className="mt-2 flex items-baseline justify-between gap-2">
                      <span className="font-mono-num text-lg font-bold text-slate-50 group-hover:text-emerald-300">
                        {opp.ticker}
                      </span>
                      <span className="font-mono-num text-xs text-slate-300">
                        ${q.current_price ?? "N/D"}
                      </span>
                    </div>
                    <p className="truncate text-xs text-slate-400">{opp.company_name}</p>
                  </div>

                  <div className="mt-3 space-y-1.5 border-t border-slate-800/80 pt-2.5 text-[11px]">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Post-IPO</span>
                      <span className="font-mono-num font-semibold text-rose-300">
                        {q.post_ipo_drawdown_pct !== null && q.post_ipo_drawdown_pct !== undefined
                          ? `${q.post_ipo_drawdown_pct}%`
                          : "N/D"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Runway</span>
                      <span className="font-mono-num font-semibold text-emerald-300">
                        {q.is_cash_flow_positive ? "CF Positivo" : `${q.runway_months ?? "N/D"}m`}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* Filter Toolbar */}
      <section className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-3.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
            <Filter className="h-3.5 w-3.5" />
            Filtri:
          </span>
          {[
            { label: "Tutti", val: 0 },
            { label: "Score ≥ 60", val: 60 },
            { label: "Alert ≥ 75", val: 75 },
          ].map((opt) => (
            <button
              key={opt.val}
              type="button"
              onClick={() => setMinScoreFilter(opt.val)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                minScoreFilter === opt.val
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  : "border border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200"
              }`}
            >
              {opt.label}
            </button>
          ))}

          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            aria-label="Filtra per segnale"
            className="rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1 text-xs text-slate-200 focus:border-emerald-500 focus:outline-none"
          >
            {availableTags.map((t) => (
              <option key={t} value={t}>
                {t === "ALL" ? "Tutti i Segnali" : t}
              </option>
            ))}
          </select>
        </div>

        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Filtra per ticker, azienda o settore..."
          className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none sm:w-64"
        />
      </section>

      {/* Main Opportunity Cards Grid */}
      {filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
          <p className="text-sm text-slate-300">
            Nessun titolo corrisponde ai filtri selezionati.
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Riduci la soglia punteggio oppure scansiona un nuovo ticker dalla barra in alto.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {filtered.map((opp) => {
            const q = opp.quant_metrics || {};
            const aud = opp.debate?.auditor || {};
            const bear = opp.debate?.bear || {};
            const colors = getScoreColors(opp.asymmetry_score);

            return (
              <article
                key={opp.ticker}
                className="flex flex-col justify-between rounded-2xl border border-slate-800 bg-slate-900/75 p-5 transition hover:border-slate-700"
              >
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono-num text-xl font-bold tracking-tight text-slate-50">
                          {opp.ticker}
                        </span>
                        <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-300">
                          {opp.exchange}
                        </span>
                        <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${colors.badge}`}>
                          {colors.label}
                        </span>
                      </div>
                      <h3 className="mt-1 text-sm font-medium text-slate-200">
                        {opp.company_name}
                      </h3>
                      <p className="text-xs text-slate-400">
                        {opp.sector} · {opp.industry}
                      </p>
                    </div>

                    <div
                      className={`flex flex-col items-center justify-center rounded-xl border px-3.5 py-2 ${colors.ring}`}
                    >
                      <span className="text-[10px] font-semibold uppercase tracking-wider opacity-80">
                        Asymmetry
                      </span>
                      <span className="font-mono-num text-2xl font-bold leading-none mt-0.5">
                        {opp.asymmetry_score}
                      </span>
                      <span className="text-[10px] opacity-75">/ 100</span>
                    </div>
                  </div>

                  {/* Key Financial Metrics Row */}
                  <div className="mt-4 grid grid-cols-4 gap-2 rounded-xl border border-slate-800/80 bg-slate-950/60 p-3 text-xs">
                    <div>
                      <div className="text-[10px] text-slate-500">Prezzo / MCap</div>
                      <div className="mt-0.5 font-mono-num font-semibold text-slate-100">
                        ${q.current_price ?? "N/D"}
                      </div>
                      <div className="font-mono-num text-[10px] text-slate-400">
                        {formatCompactUsd(q.market_cap)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-500">Calo Post-IPO</div>
                      <div className="mt-0.5 flex items-center gap-1 font-mono-num font-semibold text-rose-300">
                        <TrendingDown className="h-3 w-3" />
                        {q.post_ipo_drawdown_pct !== null && q.post_ipo_drawdown_pct !== undefined
                          ? `${q.post_ipo_drawdown_pct}%`
                          : "N/D"}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {q.months_since_ipo ? `${q.months_since_ipo}m da IPO` : "Post-IPO"}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-500">Ricavi YoY</div>
                      <div
                        className={`mt-0.5 font-mono-num font-semibold ${
                          (q.revenue_growth_yoy_pct ?? 0) > 0 ? "text-emerald-300" : "text-rose-300"
                        }`}
                      >
                        {q.revenue_growth_yoy_pct !== null && q.revenue_growth_yoy_pct !== undefined
                          ? `${q.revenue_growth_yoy_pct > 0 ? "+" : ""}${q.revenue_growth_yoy_pct}%`
                          : "N/D"}
                      </div>
                      <div className="font-mono-num text-[10px] text-slate-500">
                        TTM {formatCompactUsd(q.revenue_ttm)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-500">Runway / Cassa</div>
                      <div className="mt-0.5 font-mono-num font-semibold text-cyan-300">
                        {q.is_cash_flow_positive ? "CF Positivo" : `${q.runway_months ?? "N/D"} mesi`}
                      </div>
                      <div className="font-mono-num text-[10px] text-slate-500">
                        Cash {formatCompactUsd(q.cash_and_equivalents)}
                      </div>
                    </div>
                  </div>

                  {/* Signal Tags */}
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {(opp.signal_tags || []).map((tag) => (
                      <span
                        key={tag}
                        className={`rounded-md border px-2 py-0.5 text-[11px] font-medium ${getTagStyle(tag)}`}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  {/* 5-Line Thesis Preview */}
                  <div className="mt-3.5 rounded-xl border border-slate-800/80 bg-slate-950/40 p-3">
                    <div className="mb-1.5 flex items-center justify-between text-[11px]">
                      <span className="font-semibold uppercase tracking-wider text-slate-400">
                        Sintesi Giudice (5 Righe)
                      </span>
                      <span className="flex items-center gap-1 text-cyan-300">
                        <ShieldCheck className="h-3.5 w-3.5" />
                        Audit {aud.verification_score !== undefined ? `${aud.verification_score}%` : "N/D"}
                      </span>
                    </div>
                    <ul className="space-y-1 text-xs leading-relaxed text-slate-300">
                      {(opp.thesis_5_lines || []).slice(0, 3).map((line, i) => (
                        <li key={i} className="line-clamp-1">
                          {line}
                        </li>
                      ))}
                    </ul>
                    {bear.dilution_risk_level === "ALTO" && (
                      <div className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-300">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                        Attenzione Bear: Rischio diluizione classificato ALTO
                      </div>
                    )}
                  </div>
                </div>

                {/* Card Actions */}
                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/80 pt-3.5">
                  <button
                    type="button"
                    onClick={() => onQuickLogOrder(opp)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-300 transition hover:bg-cyan-500/20"
                  >
                    <PlusCircle className="h-3.5 w-3.5" />
                    Registra Micro-Ordine
                  </button>

                  <button
                    type="button"
                    onClick={() => onSelectTicker(opp)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3.5 py-1.5 text-xs font-semibold text-slate-100 transition hover:bg-emerald-600 hover:text-white"
                  >
                    Dibattito Bull vs Bear &amp; SEC
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
