import React, { useState } from "react";
import { Radar, BookOpen, Search, RefreshCw, Sparkles, ShieldCheck, Bot, ArrowUpRight } from "lucide-react";

export default function Navbar({
  activeTab,
  setActiveTab,
  opportunitiesCount,
  journalSummary,
  autopilotEnabled,
  health,
  onScanTicker,
  onRunPipeline,
  isScanning,
  isRunningPipeline,
}) {
  const [tickerInput, setTickerInput] = useState("");

  const busy = isScanning || isRunningPipeline;
  const isReadOnly = Boolean(health?.static_readonly);

  const handleSubmit = (e) => {
    e.preventDefault();
    const cleaned = tickerInput.trim().toUpperCase();
    if (!cleaned || busy) return;
    if (isReadOnly) {
      window.open("https://github.com/Muso-lab/FinanceTool/actions/workflows/daily_scouter.yml", "_blank");
    } else {
      onScanTicker(cleaned);
    }
    setTickerInput("");
  };

  const used = journalSummary?.monthly_orders_used ?? 0;
  const limit = journalSummary?.monthly_orders_limit ?? 10;

  return (
    <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-[#090d16]/95 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-3 py-3.5 lg:flex-row lg:items-center lg:justify-between">
          {/* Brand */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 shadow-inner">
                <Radar className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-base font-bold tracking-tight text-slate-50 sm:text-lg">
                    IPO &amp; Micro-Cap AI Scouter
                  </h1>
                  <span className="hidden rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-300 sm:inline-flex items-center gap-1">
                    <ShieldCheck className="h-3 w-3" />
                    4-Agenti Verificati
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Segnali asimmetrici lenti post-IPO · SEC EDGAR &amp; Contro-Verifica ·{" "}
                  <span className="text-slate-300">
                    {isReadOnly
                      ? "Cloud Read-Only (GitHub Actions)"
                      : health?.gemini_configured
                        ? "Gemini AI Attivo"
                        : "Engine Forense Locale"}
                  </span>
                </p>
              </div>
            </div>
          </div>

          {/* Navigation Tabs + Quick Scanner */}
          <div className="flex flex-wrap items-center gap-2.5">
            <nav className="flex rounded-lg border border-slate-800 bg-slate-900/70 p-1">
              <button
                type="button"
                onClick={() => setActiveTab("feed")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  activeTab === "feed"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                Feed Opportunità
                <span className="ml-1 rounded bg-slate-800 px-1.5 py-0.5 font-mono-num text-[10px] text-slate-300">
                  {opportunitiesCount}
                </span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("journal")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  activeTab === "journal"
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <BookOpen className="h-3.5 w-3.5" />
                Diario Micro-Ordini
                <span
                  className={`ml-1 rounded px-1.5 py-0.5 font-mono-num text-[10px] ${
                    used >= limit
                      ? "bg-amber-500/20 text-amber-300"
                      : "bg-slate-800 text-cyan-300"
                  }`}
                >
                  {used}/{limit}
                </span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("autopilot")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  activeTab === "autopilot"
                    ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Bot className="h-3.5 w-3.5" />
                Auto-Pilot
                <span
                  className={`ml-1 h-2 w-2 rounded-full ${
                    autopilotEnabled ? "bg-emerald-400" : "bg-slate-600"
                  }`}
                  title={autopilotEnabled ? "Auto-Pilot attivo" : "Auto-Pilot in pausa"}
                />
              </button>
            </nav>

            {/* Live Single Ticker Scan or Cloud Dispatch */}
            <form onSubmit={handleSubmit} className="flex items-center gap-1.5">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                <input
                  type="text"
                  value={tickerInput}
                  onChange={(e) => setTickerInput(e.target.value)}
                  disabled={busy}
                  placeholder="Scansiona Ticker (es. RKLB)"
                  aria-label="Scansiona ticker live"
                  className="w-40 rounded-lg border border-slate-700/80 bg-slate-900/90 py-1.5 pl-8 pr-2.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none sm:w-44"
                />
              </div>
              <button
                type="submit"
                disabled={busy || !tickerInput.trim()}
                title={isReadOnly ? "In modalità Cloud le scansioni possono essere lanciate su GitHub Actions" : "Scansiona ticker in tempo reale"}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isScanning ? (
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Radar className="h-3.5 w-3.5" />
                )}
                {isScanning ? "Analisi..." : "Scansiona"}
              </button>
            </form>

            {isReadOnly ? (
              <a
                href="https://github.com/Muso-lab/FinanceTool/actions/workflows/daily_scouter.yml"
                target="_blank"
                rel="noreferrer"
                title="Apri GitHub Actions per eseguire la pipeline manuale nel Cloud"
                className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-300 transition hover:bg-cyan-500/20"
              >
                <ArrowUpRight className="h-3.5 w-3.5 text-cyan-400" />
                Esegui Pipeline Cloud ↗
              </a>
            ) : (
              <button
                type="button"
                onClick={onRunPipeline}
                disabled={busy}
                title="Esegui pipeline batch su nuovi candidati post-IPO"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-slate-600 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isRunningPipeline ? "animate-spin text-emerald-400" : ""}`} />
                {isRunningPipeline ? "Pipeline..." : "Aggiorna Pipeline"}
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
