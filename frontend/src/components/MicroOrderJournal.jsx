import React, { useEffect, useState } from "react";
import {
  BookOpen,
  Plus,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Lock,
  RefreshCw,
} from "lucide-react";

const BROKER_OPTIONS = [
  "Trading 212",
  "Interactive Brokers (IBKR)",
  "Trade Republic",
  "Scalable Capital",
  "Revolut",
  "Directa SIM",
];

function DriftBadge({ status }) {
  if (status === "TESI_CONFERMATA") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
        <CheckCircle2 className="h-3 w-3" /> Tesi Confermata
      </span>
    );
  }
  if (status === "ATTENZIONE_DILUIZIONE" || status === "DEGRADO_TESI") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/30 bg-rose-500/15 px-2 py-0.5 text-[10px] font-semibold text-rose-300">
        <AlertTriangle className="h-3 w-3" /> {status.replace("_", " ")}
      </span>
    );
  }
  return (
    <span className="rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-300">
      Stabile
    </span>
  );
}

function OrderModeBadge({ mode }) {
  if (mode === "PAPER_AUTO") {
    return (
      <span className="rounded border border-emerald-500/30 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
        PAPER AUTO
      </span>
    );
  }
  if (mode === "REAL") {
    return (
      <span className="rounded border border-amber-500/40 bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
        REALE
      </span>
    );
  }
  return (
    <span className="rounded border border-cyan-500/30 bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-300">
      PAPER
    </span>
  );
}

export default function MicroOrderJournal({
  journalData,
  opportunities,
  isReadOnly,
  prefillOpportunity,
  onClearPrefill,
  onCreateOrder,
  onToggleOrderStatus,
  onDeleteOrder,
  onRefreshLivePrices,
  isMonitoring,
}) {
  const [ticker, setTicker] = useState("");
  const [amountEur, setAmountEur] = useState("35");
  const [entryPriceUsd, setEntryPriceUsd] = useState("");
  const [broker, setBroker] = useState("Trading 212");
  const [mode, setMode] = useState("PAPER_MANUAL");
  const [takeProfitPct, setTakeProfitPct] = useState("80");
  const [stopLossPct, setStopLossPct] = useState("-30");
  const [fractional, setFractional] = useState(true);
  const [orderDate, setOrderDate] = useState(new Date().toISOString().slice(0, 10));
  const [initialThesis, setInitialThesis] = useState("");
  const [invalidationRule, setInvalidationRule] = useState("");
  const [overrideLimit, setOverrideLimit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    if (prefillOpportunity) {
      setTicker(prefillOpportunity.ticker);
      setEntryPriceUsd(String(prefillOpportunity.quant_metrics?.current_price ?? ""));
      setAmountEur(String(prefillOpportunity.micro_strategy?.recommended_bullet_eur ?? 35));
      setInitialThesis((prefillOpportunity.thesis_5_lines || []).slice(0, 2).join(" "));
      setInvalidationRule(prefillOpportunity.micro_strategy?.invalidation_trigger || "");
      setFormError("");
    }
  }, [prefillOpportunity]);

  const handleSelectOpp = (selectedTicker) => {
    setTicker(selectedTicker);
    const found = opportunities.find((o) => o.ticker === selectedTicker);
    if (found) {
      setEntryPriceUsd(String(found.quant_metrics?.current_price ?? ""));
      setAmountEur(String(found.micro_strategy?.recommended_bullet_eur ?? 35));
      setInitialThesis((found.thesis_5_lines || []).slice(0, 2).join(" "));
      setInvalidationRule(found.micro_strategy?.invalidation_trigger || "");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError("");
    if (!ticker.trim() || !entryPriceUsd || initialThesis.trim().length < 3) {
      setFormError("Compila ticker, prezzo d'ingresso e una tesi di almeno 3 caratteri.");
      return;
    }
    setSubmitting(true);
    try {
      await onCreateOrder({
        ticker: ticker.trim().toUpperCase(),
        order_date: orderDate,
        amount_eur: Number(amountEur),
        entry_price_usd: Number(entryPriceUsd),
        broker,
        mode,
        take_profit_pct: takeProfitPct ? Number(takeProfitPct) : null,
        stop_loss_pct: stopLossPct ? Number(stopLossPct) : null,
        fractional,
        initial_thesis: initialThesis.trim(),
        invalidation_rule: invalidationRule.trim(),
        override_monthly_limit: overrideLimit,
      });
      setTicker("");
      setEntryPriceUsd("");
      setInitialThesis("");
      setInvalidationRule("");
      setOverrideLimit(false);
      onClearPrefill();
    } catch (err) {
      setFormError(err.message || "Errore durante la registrazione dell'ordine.");
    } finally {
      setSubmitting(false);
    }
  };

  const orders = journalData?.orders || [];
  const summary = journalData?.summary || {
    monthly_orders_used: 0,
    monthly_orders_limit: 10,
    monthly_slots_remaining: 10,
    monthly_allocated_eur: 0,
    total_invested_eur: 0,
    total_current_value_eur: 0,
    total_pnl_eur: 0,
    total_pnl_pct: 0,
  };
  const selectedYm = (orderDate || "").slice(0, 7);
  const selectedMonthUsed = orders.filter((o) => (o.order_date || "").slice(0, 7) === selectedYm).length;
  const selectedMonthLimitReached = selectedMonthUsed >= (summary.monthly_orders_limit || 10);

  return (
    <div className="space-y-6">
      {/* Monthly 5-Bullet Discipline Banner */}
      <section className="rounded-2xl border border-cyan-500/25 bg-gradient-to-br from-cyan-950/20 via-slate-900/80 to-slate-950 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-100">
              <BookOpen className="h-5 w-5 text-cyan-400" />
              Diario di Bordo Micro-Ordini (Disciplina {summary.monthly_orders_limit || 10} Cartucce / Mese)
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              Budget virtuale: €{(summary.virtual_budget_eur ?? 1000).toFixed(0)} (cassa disponibile €
              {(summary.paper_cash_available_eur ?? 1000).toFixed(2)}) · Monitora TP1/TP2, Trailing Stop e deriva tesi AI.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onRefreshLivePrices}
              disabled={isMonitoring || isReadOnly}
              className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-500/35 bg-indigo-500/15 px-3.5 py-2 text-xs font-semibold text-indigo-200 transition hover:bg-indigo-500/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isMonitoring ? "animate-spin" : ""}`} />
              {isMonitoring ? "Aggiorno..." : "Aggiorna Prezzi Live"}
            </button>

            <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-2.5">
              <div className="text-[10px] uppercase tracking-wider text-slate-400">
                Slot Mese Corrente ({summary.current_month})
              </div>
              <div className="mt-1.5 flex items-center gap-1.5">
                {Array.from({ length: summary.monthly_orders_limit || 10 }).map((_, i) => {
                  const used = i < summary.monthly_orders_used;
                  return (
                    <span
                      key={i}
                      className={`h-3 w-4 rounded-sm transition ${
                        used ? "bg-cyan-400" : "border border-slate-700 bg-slate-900"
                      }`}
                      title={used ? "Slot utilizzato" : "Slot disponibile"}
                    />
                  );
                })}
                <span className="ml-2 font-mono-num text-xs font-bold text-cyan-300">
                  {summary.monthly_orders_used}/{summary.monthly_orders_limit}
                </span>
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-2.5">
              <div className="text-[10px] uppercase tracking-wider text-slate-400">
                Valore Stimato / P&amp;L Aperto
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="font-mono-num text-lg font-bold text-slate-100">
                  €{summary.total_current_value_eur.toFixed(2)}
                </span>
                <span
                  className={`font-mono-num text-xs font-semibold ${
                    summary.total_pnl_eur >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {summary.total_pnl_eur >= 0 ? "+" : ""}
                  €{summary.total_pnl_eur.toFixed(2)} ({summary.total_pnl_pct >= 0 ? "+" : ""}
                  {summary.total_pnl_pct}%)
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Manual Entry Form */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-100">Nuovo Micro-Ordine</h3>
            {summary.monthly_slots_remaining === 0 && (
              <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                <Lock className="h-3 w-3" /> Soglia {summary.monthly_orders_limit || 10}/mese raggiunta
              </span>
            )}
          </div>

          {formError && (
            <div className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 p-2.5 text-xs text-rose-200">
              {formError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-4 space-y-3">
            <div>
              <label className="block text-[11px] font-medium text-slate-400">
                Seleziona da Scouter o inserisci Ticker
              </label>
              <div className="mt-1 flex gap-2">
                <input
                  type="text"
                  required
                  maxLength={12}
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="Es. RDW"
                  className="w-1/2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono-num text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
                />
                <select
                  value=""
                  onChange={(e) => e.target.value && handleSelectOpp(e.target.value)}
                  className="w-1/2 rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-slate-300 focus:border-cyan-500 focus:outline-none"
                >
                  <option value="">Carica da Feed...</option>
                  {opportunities.map((o) => (
                    <option key={o.ticker} value={o.ticker}>
                      {o.ticker} (Score {o.asymmetry_score})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] font-medium text-slate-400">Modalità</label>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                >
                  <option value="PAPER_MANUAL">Simulazione (Paper)</option>
                  <option value="REAL">Ordine Reale (Solo Alert)</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-400">Data Ordine</label>
                <input
                  type="date"
                  value={orderDate}
                  onChange={(e) => setOrderDate(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 font-mono-num text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] font-medium text-slate-400">Importo (€)</label>
                <input
                  type="number"
                  step="any"
                  min="0.01"
                  max="5000"
                  required
                  value={amountEur}
                  onChange={(e) => setAmountEur(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono-num text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-400">Prezzo Ingresso ($)</label>
                <input
                  type="number"
                  step="any"
                  min="0.0001"
                  required
                  value={entryPriceUsd}
                  onChange={(e) => setEntryPriceUsd(e.target.value)}
                  placeholder="Es. 10.45"
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono-num text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div className="col-span-1">
                <label className="block text-[11px] font-medium text-slate-400">TP (+%)</label>
                <input
                  type="number"
                  step="any"
                  min="0.5"
                  max="1000"
                  value={takeProfitPct}
                  onChange={(e) => setTakeProfitPct(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 font-mono-num text-xs text-emerald-300 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div className="col-span-1">
                <label className="block text-[11px] font-medium text-slate-400">SL (-%)</label>
                <input
                  type="number"
                  step="any"
                  max="-0.5"
                  min="-99"
                  value={stopLossPct}
                  onChange={(e) => setStopLossPct(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 font-mono-num text-xs text-rose-300 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div className="col-span-1">
                <label className="block text-[11px] font-medium text-slate-400">Broker</label>
                <select
                  value={broker}
                  onChange={(e) => setBroker(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                >
                  {BROKER_OPTIONS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={fractional}
                onChange={(e) => setFractional(e.target.checked)}
                className="rounded border-slate-600 bg-slate-900 text-cyan-500"
              />
              Eseguito in azioni frazionate
            </label>

            <div>
              <label className="block text-[11px] font-medium text-slate-400">
                Tesi d&apos;Investimento Iniziale
              </label>
              <textarea
                rows={3}
                required
                minLength={3}
                maxLength={1000}
                value={initialThesis}
                onChange={(e) => setInitialThesis(e.target.value)}
                placeholder="Perché questo titolo ha un vantaggio asimmetrico?"
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 p-2.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-slate-400">
                Condizione di Invalidazione (Stop Tesi)
              </label>
              <input
                type="text"
                maxLength={500}
                value={invalidationRule}
                onChange={(e) => setInvalidationRule(e.target.value)}
                placeholder="Es. Runway < 9m o emissione S-3 diluitiva"
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {selectedMonthLimitReached && (
              <label className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-200">
                <input
                  type="checkbox"
                  checked={overrideLimit}
                  onChange={(e) => setOverrideLimit(e.target.checked)}
                />
                Forza ordine extra per {selectedYm} oltre il limite di {summary.monthly_orders_limit || 10} cartucce
              </label>
            )}

            <button
              type="submit"
              disabled={submitting || isReadOnly}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-cyan-600 py-2.5 text-xs font-semibold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />
              {submitting ? "Salvataggio..." : "Annota nel Diario di Bordo"}
            </button>
          </form>
        </section>

        {/* Journal Entries Cards */}
        <section className="lg:col-span-2 space-y-3">
          {orders.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
              <p className="text-sm text-slate-300">Nessun micro-ordine registrato finora.</p>
              <p className="mt-1 text-xs text-slate-500">
                Usa il modulo a sinistra, &ldquo;Registra Micro-Ordine&rdquo; da una scheda titolo oppure attiva l&apos;Auto-Pilot.
              </p>
            </div>
          ) : (
            orders.map((ord) => {
              const isPos = ord.pnl_pct >= 0;
              return (
                <div
                  key={ord.id}
                  className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4 transition hover:border-slate-700"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono-num text-lg font-bold text-slate-100">
                          {ord.ticker}
                        </span>
                        <OrderModeBadge mode={ord.mode} />
                        <span className="rounded bg-slate-800 px-2 py-0.5 font-mono-num text-[11px] text-slate-300">
                          {ord.order_date}
                        </span>
                        <span className="rounded border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                          {ord.broker} {ord.fractional ? "· Frazionato" : "· Intero"}
                        </span>
                        <DriftBadge status={ord.thesis_drift_status} />
                        {ord.tp1_executed && (
                          <span className="rounded border border-cyan-500/30 bg-cyan-500/15 px-1.5 py-0.5 font-mono-num text-[10px] font-semibold text-cyan-300">
                            TP1 +€{(ord.partial_realized_pnl_eur ?? 0).toFixed(2)}
                          </span>
                        )}
                      </div>
                      <p className="mt-2 text-xs leading-relaxed text-slate-300">
                        <span className="font-semibold text-slate-400">Tesi: </span>
                        {ord.initial_thesis}
                      </p>
                      {ord.invalidation_rule && (
                        <p className="mt-1 text-[11px] text-rose-300/90">
                          <span className="font-semibold">Invalidazione:</span> {ord.invalidation_rule}
                        </p>
                      )}
                      {ord.tp1_note && (
                        <p className="mt-1 text-[11px] font-medium text-emerald-300">
                          {ord.tp1_note}
                        </p>
                      )}
                      {ord.close_reason && (
                        <p className="mt-1 text-[11px] font-semibold text-indigo-300">
                          Chiusura automatica: {ord.close_reason}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-col items-end gap-1">
                      <div className="font-mono-num text-sm font-bold text-slate-100">
                        €{ord.amount_eur.toFixed(2)} → €{ord.current_value_eur.toFixed(2)}
                      </div>
                      <div
                        className={`flex items-center gap-1 font-mono-num text-xs font-semibold ${
                          isPos ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {isPos ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                        {isPos ? "+" : ""}
                        {ord.pnl_pct}% (${ord.entry_price_usd} → ${ord.latest_price_usd})
                      </div>
                      <div className="text-[11px] text-slate-400">
                        TP +{ord.take_profit_pct ?? 80}% / {ord.tp1_executed && ord.stop_loss_pct === 0 ? "BE 0%" : `SL ${ord.stop_loss_pct ?? -30}%`} · Score{" "}
                        <span className="font-mono-num text-slate-200">{ord.initial_ai_score ?? "N/D"}</span>
                        {" → "}
                        <span className="font-mono-num text-cyan-300">{ord.latest_ai_score ?? "N/D"}</span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 flex items-center justify-between border-t border-slate-800/80 pt-2.5 text-xs">
                    <button
                      type="button"
                      disabled={isReadOnly}
                      onClick={() =>
                        onToggleOrderStatus(
                          ord.id,
                          ord.status === "APERTO" ? "CHIUSO" : "APERTO",
                          ord.status === "APERTO" ? (ord.raw_latest_price_usd || ord.latest_price_usd) : null
                        )
                      }
                      className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${
                        ord.status === "APERTO"
                          ? "bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
                          : "bg-slate-800 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Stato: {ord.status} {isReadOnly ? "" : "(clicca per cambiare)"}
                    </button>

                    <button
                      type="button"
                      disabled={isReadOnly}
                      onClick={() => onDeleteOrder(ord.id)}
                      className="inline-flex items-center gap-1 text-slate-500 transition hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Rimuovi
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </section>
      </div>
    </div>
  );
}
