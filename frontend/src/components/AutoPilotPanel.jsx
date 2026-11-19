import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  Activity,
  ShieldAlert,
  Play,
  Eye,
  RefreshCw,
  Save,
  CheckCircle2,
  XCircle,
  Clock,
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  Wallet,
  Target,
} from "lucide-react";

function PriceSparkline({ history }) {
  const pts = (history || []).filter((h) => typeof h.price_usd === "number");
  if (pts.length < 2) {
    return (
      <div className="flex h-10 items-center justify-center rounded border border-slate-800/80 bg-slate-950/60 px-2 text-[10px] text-slate-500">
        {pts.length === 1 ? `1 checkpoint ($${pts[0].price_usd})` : "Nessun checkpoint"}
      </div>
    );
  }
  const width = 150;
  const height = 38;
  const prices = pts.map((p) => p.price_usd);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const coords = prices
    .map((p, i) => {
      const x = (i / (prices.length - 1)) * (width - 8) + 4;
      const y = height - 4 - ((p - min) / span) * (height - 8);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const isUp = prices[prices.length - 1] >= prices[0];

  return (
    <div className="flex items-center gap-2 rounded border border-slate-800/80 bg-slate-950/60 px-2 py-1">
      <svg width={width} height={height} className="overflow-visible">
        <polyline
          fill="none"
          stroke={isUp ? "#34d399" : "#fb7185"}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          points={coords}
        />
      </svg>
      <span className="font-mono-num text-[10px] text-slate-400">{pts.length} pt</span>
    </div>
  );
}

function TpSlMeter({ pnlPct, slPct, tp1Pct, tp2Pct, tp1Executed }) {
  const min = slPct ?? -30;
  const max = tp2Pct ?? 80;
  const span = max - min || 1;
  const clamped = Math.max(min, Math.min(max, pnlPct));
  const markerPos = ((clamped - min) / span) * 100;
  const zeroPos = ((0 - min) / span) * 100;
  const tp1Pos = tp1Pct && tp1Pct < max ? ((tp1Pct - min) / span) * 100 : null;

  return (
    <div className="mt-2">
      <div className="flex justify-between font-mono-num text-[10px] text-slate-400">
        <span className="text-rose-400">{tp1Executed && min === 0 ? "BE 0%" : `SL ${min}%`}</span>
        {tp1Pos !== null && (
          <span className={tp1Executed ? "text-emerald-400 font-semibold" : "text-cyan-400"}>
            TP1 +{tp1Pct}% {tp1Executed ? "✓" : ""}
          </span>
        )}
        <span className="text-emerald-400">TP2 +{max}%</span>
      </div>
      <div className="relative mt-1 h-2 w-full rounded-full bg-slate-800">
        <div className="absolute top-0 bottom-0 w-0.5 bg-slate-500/60" style={{ left: `${zeroPos}%` }} />
        {tp1Pos !== null && (
          <div className="absolute top-0 bottom-0 w-0.5 bg-cyan-400/70" style={{ left: `${tp1Pos}%` }} />
        )}
        <div
          className={`absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-slate-950 ${
            pnlPct >= 0 ? "bg-emerald-400" : "bg-rose-400"
          }`}
          style={{ left: `${markerPos}%` }}
        />
      </div>
    </div>
  );
}

function ModeBadge({ mode }) {
  if (mode === "PAPER_AUTO") {
    return (
      <span className="rounded border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
        PAPER AUTO
      </span>
    );
  }
  if (mode === "REAL") {
    return (
      <span className="rounded border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
        REALE (Solo Alert)
      </span>
    );
  }
  return (
    <span className="rounded border border-cyan-500/30 bg-cyan-500/15 px-2 py-0.5 text-[10px] font-semibold text-cyan-300">
      PAPER MANUALE
    </span>
  );
}

function ActionLogBadge({ action }) {
  const styles = {
    AUTO_REGISTER: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    PARTIAL_TP1: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
    AUTO_CLOSE: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30",
    ALERT: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    SKIPPED_GUARDRAIL: "bg-slate-800 text-slate-400 border-slate-700",
    MONITOR_CHECK: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
    CONFIG_UPDATE: "bg-slate-800 text-slate-300 border-slate-700",
  };
  return (
    <span
      className={`rounded border px-1.5 py-0.5 font-mono-num text-[10px] font-semibold ${
        styles[action] || styles.CONFIG_UPDATE
      }`}
    >
      {action}
    </span>
  );
}

export default function AutoPilotPanel({
  autopilotData,
  isReadOnly,
  onSaveConfig,
  onRunAutoRegister,
  onRunMonitor,
  isSavingConfig,
  isRunningAutoReg,
  isMonitoring,
}) {
  const config = autopilotData?.config || {};
  const logs = autopilotData?.logs || [];
  const journal = autopilotData?.journal || { orders: [], summary: {} };
  const summary = journal.summary || {};
  const orders = journal.orders || [];

  const [formCfg, setFormCfg] = useState(config);
  const [cfgError, setCfgError] = useState("");
  const [previewResult, setPreviewResult] = useState(null);
  const lastSyncedCfgRef = useRef("");

  useEffect(() => {
    const serialized = JSON.stringify(config);
    if (serialized !== lastSyncedCfgRef.current) {
      lastSyncedCfgRef.current = serialized;
      setFormCfg(config);
    }
  }, [config]);

  const handleField = (key, value) => {
    setCfgError("");
    setFormCfg((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setCfgError("");
    const requiredNumeric = [
      "virtual_budget_eur",
      "monthly_order_limit",
      "portfolio_roi_target_pct",
      "monitor_interval_minutes",
      "min_asymmetry_score",
      "min_audit_score",
      "min_runway_months",
      "default_ticket_eur",
      "tp1_pct",
      "take_profit_pct",
      "trailing_stop_pct",
      "stop_loss_pct",
      "thesis_degrade_min_score",
    ];
    for (const k of requiredNumeric) {
      if (formCfg[k] === "" || formCfg[k] === null || formCfg[k] === undefined || Number.isNaN(Number(formCfg[k]))) {
        setCfgError("Tutti i parametri numerici delle regole devono essere compilati con valori validi.");
        return;
      }
    }
    if (Number(formCfg.thesis_degrade_min_score) >= Number(formCfg.min_asymmetry_score)) {
      setCfgError("La soglia Thesis Stop deve essere inferiore al Min AI Score d'ingresso.");
      return;
    }
    if (formCfg.enable_partial_tp1 && Number(formCfg.tp1_pct) >= Number(formCfg.take_profit_pct)) {
      setCfgError("Il target parziale TP1 deve essere inferiore al target finale TP2.");
      return;
    }

    await onSaveConfig({
      enabled: Boolean(formCfg.enabled),
      background_monitor_enabled: Boolean(formCfg.background_monitor_enabled),
      monitor_interval_minutes: Number(formCfg.monitor_interval_minutes),
      monthly_order_limit: Number(formCfg.monthly_order_limit),
      virtual_budget_eur: Number(formCfg.virtual_budget_eur),
      portfolio_roi_target_pct: Number(formCfg.portfolio_roi_target_pct),
      min_asymmetry_score: Number(formCfg.min_asymmetry_score),
      min_audit_score: Number(formCfg.min_audit_score),
      min_runway_months: Number(formCfg.min_runway_months),
      block_high_dilution_risk: Boolean(formCfg.block_high_dilution_risk),
      default_ticket_eur: Number(formCfg.default_ticket_eur),
      respect_monthly_5_limit: Boolean(formCfg.respect_monthly_5_limit),
      enable_partial_tp1: Boolean(formCfg.enable_partial_tp1),
      tp1_pct: Number(formCfg.tp1_pct),
      take_profit_pct: Number(formCfg.take_profit_pct),
      stop_loss_pct: Number(formCfg.stop_loss_pct),
      enable_trailing_stop: Boolean(formCfg.enable_trailing_stop),
      trailing_stop_pct: Number(formCfg.trailing_stop_pct),
      auto_close_on_tp_sl: Boolean(formCfg.auto_close_on_tp_sl),
      auto_close_on_thesis_degrade: Boolean(formCfg.auto_close_on_thesis_degrade),
      thesis_degrade_min_score: Number(formCfg.thesis_degrade_min_score),
    });
  };

  const handleDryRun = async () => {
    const res = await onRunAutoRegister(true);
    if (res) setPreviewResult(res);
  };

  const handleRealAutoReg = async () => {
    const res = await onRunAutoRegister(false);
    if (res) setPreviewResult(res);
  };

  const virtualBudget = summary.virtual_budget_eur ?? Number(config.virtual_budget_eur || 1000);
  const cashAvail = summary.paper_cash_available_eur ?? virtualBudget;
  const totalEquity = summary.paper_total_equity_eur ?? virtualBudget;
  const totalRoi = summary.paper_total_roi_pct ?? 0;
  const roiTarget = summary.portfolio_roi_target_pct ?? Number(config.portfolio_roi_target_pct || 20);
  const targetEur = summary.portfolio_target_eur ?? virtualBudget * (1 + roiTarget / 100);
  const targetProgress = roiTarget > 0 ? Math.max(0, Math.min(100, Math.round((totalRoi / roiTarget) * 100))) : 0;

  const paperRealized = summary.paper_realized_pnl_eur ?? 0;
  const paperUnrealized = summary.paper_unrealized_pnl_eur ?? 0;

  return (
    <div className="space-y-6">
      {/* Top KPI Strip: Virtual Portfolio + Goal + Cash + Monthly Cap */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-emerald-500/25 bg-slate-900/70 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Equity Virtuale &amp; Obiettivo</span>
            <Target className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-mono-num text-2xl font-bold text-slate-100">
              €{totalEquity.toFixed(2)}
            </span>
            <span
              className={`font-mono-num text-xs font-semibold ${
                totalRoi >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {totalRoi >= 0 ? "+" : ""}
              {totalRoi}%
            </span>
          </div>
          <div className="mt-2">
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>Obiettivo +{roiTarget}%</span>
              <span className="font-mono-num text-emerald-300">€{targetEur.toFixed(0)}</span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
              <div className="h-full bg-emerald-500 transition-all" style={{ width: `${targetProgress}%` }} />
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Cassa Virtuale Disponibile</span>
            <Wallet className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-mono-num text-2xl font-bold text-slate-100">
              €{cashAvail.toFixed(2)}
            </span>
            <span className="text-xs text-slate-400">su €{virtualBudget.toFixed(0)}</span>
          </div>
          <div className="mt-1.5 text-[11px] text-slate-400">
            Investito Paper: <strong className="font-mono-num text-slate-200">€{(summary.paper_invested_eur ?? 0).toFixed(2)}</strong> ·{" "}
            {summary.paper_open_count ?? 0} aperte
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Win Rate &amp; Realizzato Paper</span>
            <ShieldCheck className="h-4 w-4 text-indigo-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-mono-num text-2xl font-bold text-slate-100">
              {summary.paper_win_rate_pct !== null && summary.paper_win_rate_pct !== undefined
                ? `${summary.paper_win_rate_pct}%`
                : "N/D"}
            </span>
            <span
              className={`font-mono-num text-xs font-semibold ${
                paperRealized >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              Realiz. {paperRealized >= 0 ? "+" : ""}€{paperRealized.toFixed(2)}
            </span>
          </div>
          <div className="mt-1.5 text-[11px] text-slate-400">
            Non realizzato:{" "}
            <span className={`font-mono-num font-semibold ${paperUnrealized >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
              {paperUnrealized >= 0 ? "+" : ""}€{paperUnrealized.toFixed(2)}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Auto-Pilot &amp; Slot Mensili</span>
            <Clock className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span
              className={`rounded-md px-2 py-0.5 text-xs font-bold ${
                config.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-800 text-slate-400"
              }`}
            >
              {config.enabled ? "ATTIVO" : "IN PAUSA"}
            </span>
            <span className="font-mono-num text-xs font-semibold text-cyan-300">
              {summary.monthly_orders_used ?? 0}/{summary.monthly_orders_limit ?? 10} ordini
            </span>
          </div>
          <div className="mt-1.5 font-mono-num text-[10px] text-slate-400">
            Monitor:{" "}
            {autopilotData?.last_monitor_at
              ? new Date(autopilotData.last_monitor_at).toLocaleString("it-IT")
              : "Mai eseguito"}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Panel: Guardrails & Exit Ladder Configuration */}
        <section className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/75 p-5">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-bold text-slate-100">
              <Bot className="h-4 w-4 text-emerald-400" />
              Regole, Budget &amp; Obiettivi Exit
            </h2>
            <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono-num text-[10px] text-slate-300">
              Slot {summary.monthly_orders_used ?? 0}/{summary.monthly_orders_limit ?? 10}
            </span>
          </div>

          {isReadOnly && (
            <div className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-3 text-xs text-slate-300">
              <div className="flex items-center gap-1.5 font-semibold text-cyan-300 mb-1">
                <Bot className="h-4 w-4" />
                <span>Esecuzione Cloud (GitHub Actions)</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed mb-2">
                Su GitHub Pages il monitoraggio prezzi e l'auto-trading girano nel cloud a PC spento (schedulati ogni 2h e alle 13:30 UTC). Puoi lanciarli al volo con 1 click:
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <a
                  href="https://github.com/Muso-lab/FinanceTool/actions/workflows/daily_scouter.yml"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 hover:bg-emerald-500/20 transition"
                >
                  <Play className="h-3 w-3" /> Esegui Scouter Cloud ↗
                </a>
                <a
                  href="https://github.com/Muso-lab/FinanceTool/actions/workflows/autopilot_monitor.yml"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-2.5 py-1 text-[11px] font-medium text-indigo-300 hover:bg-indigo-500/20 transition"
                >
                  <RefreshCw className="h-3 w-3" /> Esegui Monitor TP/SL ↗
                </a>
              </div>
            </div>
          )}

          {cfgError && (
            <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-2.5 text-xs text-rose-200">
              {cfgError}
            </div>
          )}

          <form onSubmit={handleSave} className="space-y-3 text-xs">
            {/* Virtual Budget & Monthly Cap */}
            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] text-slate-400">Budget Virtuale (€)</label>
                <input
                  type="number"
                  min={1}
                  max={1000000}
                  step="any"
                  value={formCfg.virtual_budget_eur ?? 1000}
                  onChange={(e) => handleField("virtual_budget_eur", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-cyan-300 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400">Ordini Max / Mese</label>
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={formCfg.monthly_order_limit ?? 10}
                  onChange={(e) => handleField("monthly_order_limit", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-slate-100 focus:border-emerald-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] text-slate-400">Obiettivo Portafoglio (+%)</label>
                <input
                  type="number"
                  min={0.5}
                  max={500}
                  step="any"
                  value={formCfg.portfolio_roi_target_pct ?? 20}
                  onChange={(e) => handleField("portfolio_roi_target_pct", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-emerald-300 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400">Ticket Paper (€)</label>
                <input
                  type="number"
                  min={0.5}
                  max={5000}
                  step="any"
                  value={formCfg.default_ticket_eur ?? 35}
                  onChange={(e) => handleField("default_ticket_eur", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-slate-100 focus:border-emerald-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Entry Guardrails */}
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-[11px] text-slate-400">Min AI Score</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={formCfg.min_asymmetry_score ?? 75}
                  onChange={(e) => handleField("min_asymmetry_score", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono-num text-slate-100 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400">Min Audit %</label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={formCfg.min_audit_score ?? 80}
                  onChange={(e) => handleField("min_audit_score", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono-num text-slate-100 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400">Runway (m)</label>
                <input
                  type="number"
                  min={0}
                  max={120}
                  step="any"
                  value={formCfg.min_runway_months ?? 12}
                  onChange={(e) => handleField("min_runway_months", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono-num text-slate-100 focus:border-emerald-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Multi-Tier Exit Goals */}
            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] text-slate-400">TP1 Parziale (+%)</label>
                <input
                  type="number"
                  min={1}
                  max={500}
                  step="any"
                  value={formCfg.tp1_pct ?? 35}
                  onChange={(e) => handleField("tp1_pct", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-cyan-300 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400">TP2 Finale (+%)</label>
                <input
                  type="number"
                  min={1}
                  max={1000}
                  step="any"
                  value={formCfg.take_profit_pct ?? 80}
                  onChange={(e) => handleField("take_profit_pct", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-emerald-300 focus:border-emerald-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] text-slate-400">Trailing Stop (-% picco)</label>
                <input
                  type="number"
                  min={3}
                  max={80}
                  step="any"
                  value={formCfg.trailing_stop_pct ?? 15}
                  onChange={(e) => handleField("trailing_stop_pct", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-amber-300 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400">Stop Loss (-%)</label>
                <input
                  type="number"
                  max={-0.1}
                  min={-99}
                  step="any"
                  value={formCfg.stop_loss_pct ?? -30}
                  onChange={(e) => handleField("stop_loss_pct", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-rose-300 focus:border-emerald-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] text-slate-400">Thesis Stop Score &lt;</label>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={formCfg.thesis_degrade_min_score ?? 55}
                  onChange={(e) => handleField("thesis_degrade_min_score", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-amber-300 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400">Intervallo Polling (min)</label>
                <input
                  type="number"
                  min={5}
                  max={1440}
                  value={formCfg.monitor_interval_minutes ?? 60}
                  onChange={(e) => handleField("monitor_interval_minutes", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono-num text-slate-100 focus:border-emerald-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <label className="flex items-center justify-between gap-2 text-slate-300">
                <span>Auto-Registrazione Attiva</span>
                <input
                  type="checkbox"
                  checked={Boolean(formCfg.enabled)}
                  onChange={(e) => handleField("enabled", e.target.checked)}
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-slate-300">
                <span>TP1 Parziale Free-Ride (vendi {formCfg.tp1_sell_ratio_pct ?? 50}% + SL 0%)</span>
                <input
                  type="checkbox"
                  checked={Boolean(formCfg.enable_partial_tp1)}
                  onChange={(e) => handleField("enable_partial_tp1", e.target.checked)}
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-slate-300">
                <span>Trailing Stop Protettivo (da +{formCfg.trailing_activation_pct ?? 25}%)</span>
                <input
                  type="checkbox"
                  checked={Boolean(formCfg.enable_trailing_stop)}
                  onChange={(e) => handleField("enable_trailing_stop", e.target.checked)}
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-slate-300">
                <span>Auto-Chiusura Paper su TP2/SL</span>
                <input
                  type="checkbox"
                  checked={Boolean(formCfg.auto_close_on_tp_sl)}
                  onChange={(e) => handleField("auto_close_on_tp_sl", e.target.checked)}
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-slate-300">
                <span>Thesis Stop Automatico</span>
                <input
                  type="checkbox"
                  checked={Boolean(formCfg.auto_close_on_thesis_degrade)}
                  onChange={(e) => handleField("auto_close_on_thesis_degrade", e.target.checked)}
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-slate-300">
                <span>Rispetta Limite {formCfg.monthly_order_limit ?? 10} Ordini/Mese</span>
                <input
                  type="checkbox"
                  checked={Boolean(formCfg.respect_monthly_5_limit)}
                  onChange={(e) => handleField("respect_monthly_5_limit", e.target.checked)}
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-slate-300">
                <span>Blocca se Diluizione S-3 ALTA</span>
                <input
                  type="checkbox"
                  checked={Boolean(formCfg.block_high_dilution_risk)}
                  onChange={(e) => handleField("block_high_dilution_risk", e.target.checked)}
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-slate-300">
                <span>Polling Background Locale</span>
                <input
                  type="checkbox"
                  checked={Boolean(formCfg.background_monitor_enabled)}
                  onChange={(e) => handleField("background_monitor_enabled", e.target.checked)}
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={isSavingConfig || isReadOnly}
              title={isReadOnly ? "Modalità Cloud Read-Only: modifica regole in locale o via GitHub" : "Salva regole Auto-Pilot"}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 py-2 font-semibold text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              {isSavingConfig ? "Salvataggio..." : "Salva Regole Auto-Pilot"}
            </button>
          </form>

          {/* Action Buttons */}
          <div className="space-y-2 border-t border-slate-800 pt-3">
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={handleDryRun}
                disabled={isRunningAutoReg || isReadOnly}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-cyan-500/35 bg-cyan-500/10 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Eye className="h-3.5 w-3.5" />
                Anteprima Dry-Run
              </button>
              <button
                type="button"
                onClick={handleRealAutoReg}
                disabled={isRunningAutoReg || isReadOnly}
                className="flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5" />
                {isRunningAutoReg ? "Esecuzione..." : "Auto-Registra"}
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => onRunMonitor(true, false)}
                disabled={isMonitoring || isReadOnly}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-indigo-500/35 bg-indigo-500/10 py-2 text-xs font-semibold text-indigo-300 transition hover:bg-indigo-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isMonitoring ? "animate-spin" : ""}`} />
                {isMonitoring ? "Aggiorno..." : "Monitora Prezzi Live"}
              </button>
              <button
                type="button"
                onClick={() => onRunMonitor(true, true)}
                disabled={isMonitoring || isReadOnly}
                title="Ricalcola prezzi live + ri-esegue i 4 agenti AI e SEC EDGAR sui titoli aperti"
                className="flex items-center justify-center gap-1.5 rounded-lg border border-amber-500/35 bg-amber-500/10 py-2 text-xs font-semibold text-amber-300 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ShieldAlert className="h-3.5 w-3.5" />
                Ri-Verifica AI/SEC
              </button>
            </div>
          </div>

          {/* Dry-Run / Guardrail Preview Box */}
          {previewResult && (
            <div className="rounded-xl border border-slate-700 bg-slate-950/80 p-3 text-xs">
              <div className="mb-2 flex items-center justify-between font-semibold text-slate-200">
                <span>{previewResult.dry_run ? "Esito Anteprima Dry-Run" : "Esito Auto-Registrazione"}</span>
                <button
                  type="button"
                  onClick={() => setPreviewResult(null)}
                  className="text-slate-500 hover:text-white"
                >
                  ✕
                </button>
              </div>
              {previewResult.message && <p className="mb-2 text-amber-300">{previewResult.message}</p>}
              <div className="space-y-1.5">
                {(previewResult.registered || []).map((r) => (
                  <div key={r.ticker} className="flex items-center justify-between rounded bg-emerald-500/10 px-2 py-1 text-emerald-300">
                    <span className="flex items-center gap-1 font-mono-num font-bold">
                      <CheckCircle2 className="h-3.5 w-3.5" /> {r.ticker}
                    </span>
                    <span className="font-mono-num">
                      €{r.amount_eur} @ ${r.entry_price_usd}
                    </span>
                  </div>
                ))}
                {(previewResult.skipped || []).map((s) => (
                  <div key={s.ticker} className="rounded bg-slate-900 px-2 py-1 text-[11px] text-slate-400">
                    <span className="inline-flex items-center gap-1 font-mono-num font-semibold text-slate-200">
                      <XCircle className="h-3 w-3 text-rose-400" /> {s.ticker}:
                    </span>{" "}
                    {(s.reasons || []).join(" · ")}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Right Panel: Monitored Positions with TP1/TP2/SL Meter & Sparkline */}
        <section className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-100">
              Posizioni sotto Auto-Monitoraggio ({orders.length})
            </h2>
            <span className="text-[11px] text-slate-400">
              Le posizioni <strong className="text-amber-300">REALI</strong> generano solo alert (mai chiuse automaticamente)
            </span>
          </div>

          {orders.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
              <p className="text-sm text-slate-300">Nessuna posizione attiva o simulata nel registro.</p>
              <p className="mt-1 text-xs text-slate-500">
                Usa &ldquo;Anteprima Dry-Run&rdquo; o &ldquo;Auto-Registra&rdquo; per avviare ordini simulati dal budget virtuale.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {orders.map((ord) => {
                const isPos = ord.pnl_pct >= 0;
                return (
                  <div key={ord.id} className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono-num text-lg font-bold text-slate-100">{ord.ticker}</span>
                          <ModeBadge mode={ord.mode} />
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
                              ord.status === "APERTO"
                                ? "bg-emerald-500/15 text-emerald-300"
                                : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {ord.status}
                          </span>
                          {ord.tp1_executed && (
                            <span className="rounded border border-cyan-500/30 bg-cyan-500/15 px-2 py-0.5 font-mono-num text-[10px] font-semibold text-cyan-300">
                              TP1 +€{(ord.partial_realized_pnl_eur ?? 0).toFixed(2)} INCASSATO
                            </span>
                          )}
                          {ord.close_reason && (
                            <span className="rounded border border-indigo-500/30 bg-indigo-500/15 px-2 py-0.5 font-mono-num text-[10px] text-indigo-300">
                              {ord.close_reason}
                            </span>
                          )}
                        </div>
                        <p className="mt-1.5 text-xs text-slate-300 line-clamp-2">{ord.initial_thesis}</p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
                          <span>
                            Ingresso: <strong className="font-mono-num text-slate-200">${ord.entry_price_usd}</strong>
                          </span>
                          <span>
                            Live/Exit: <strong className="font-mono-num text-slate-200">${ord.latest_price_usd}</strong>
                          </span>
                          <span>
                            Picco: <strong className="font-mono-num text-emerald-300">${Number(ord.peak_price_usd ?? ord.entry_price_usd).toFixed(2)}</strong>
                          </span>
                          <span>
                            AI Score: <strong className="font-mono-num text-cyan-300">{ord.initial_ai_score ?? "N/D"} → {ord.latest_ai_score ?? "N/D"}</strong>
                          </span>
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-2">
                        <div className="text-right">
                          <div className="font-mono-num text-sm font-bold text-slate-100">
                            €{ord.amount_eur.toFixed(2)} → €{ord.current_value_eur.toFixed(2)}
                          </div>
                          <div
                            className={`inline-flex items-center gap-1 font-mono-num text-xs font-semibold ${
                              isPos ? "text-emerald-400" : "text-rose-400"
                            }`}
                          >
                            {isPos ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                            {isPos ? "+" : ""}
                            {ord.pnl_pct}% ({ord.pnl_eur >= 0 ? "+" : ""}€{(ord.pnl_eur ?? 0).toFixed(2)}
                            {ord.tp1_executed
                              ? ` | tot. ${(ord.total_order_pnl_eur ?? 0) >= 0 ? "+" : ""}€${(ord.total_order_pnl_eur ?? 0).toFixed(2)}`
                              : ""}
                            )
                          </div>
                        </div>
                        <PriceSparkline history={ord.price_history} />
                      </div>
                    </div>

                    {ord.status === "APERTO" && (
                      <TpSlMeter
                        pnlPct={ord.pnl_pct}
                        slPct={ord.stop_loss_pct}
                        tp1Pct={config.enable_partial_tp1 ? config.tp1_pct : null}
                        tp2Pct={ord.take_profit_pct}
                        tp1Executed={ord.tp1_executed}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* Audit Log Section */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h3 className="text-sm font-semibold text-slate-100">
          Registro Audit Auto-Pilot (Decisioni &amp; Checkpoint)
        </h3>
        {logs.length === 0 ? (
          <p className="mt-2 text-xs text-slate-500">
            Nessun evento registrato finora. Esegui un controllo prezzi o un&apos;auto-registrazione per popolare l&apos;audit log.
          </p>
        ) : (
          <div className="mt-3 max-h-60 space-y-2 overflow-y-auto pr-1">
            {logs.map((lg) => (
              <div
                key={lg.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800/80 bg-slate-950/60 px-3 py-2 text-xs"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <ActionLogBadge action={lg.action} />
                  <span className="font-mono-num font-bold text-slate-200">{lg.ticker}</span>
                  <span className="text-slate-300">{lg.summary}</span>
                </div>
                <span className="font-mono-num text-[10px] text-slate-500">
                  {new Date(lg.ts).toLocaleString("it-IT")}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
