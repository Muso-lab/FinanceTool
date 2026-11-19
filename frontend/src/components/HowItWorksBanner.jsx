import React, { useState } from "react";
import {
  HelpCircle,
  ChevronDown,
  ChevronUp,
  Filter,
  FileText,
  Bot,
  Zap,
  Bell,
  ArrowRight,
  TrendingUp,
  ShieldAlert,
} from "lucide-react";

export default function HowItWorksBanner() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="overflow-hidden rounded-2xl border border-cyan-500/30 bg-gradient-to-r from-slate-900/90 via-slate-900/70 to-slate-900/90 shadow-lg shadow-cyan-950/20 backdrop-blur-sm">
      {/* Intestazione cliccabile per aprire/chiudere */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-5 py-4 text-left transition hover:bg-slate-800/40"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-500/40 bg-cyan-500/10 text-cyan-300">
            <HelpCircle className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-100">
                Come Funziona IPO & Micro-Cap AI Scouter?
              </h3>
              <span className="rounded-full border border-cyan-500/40 bg-cyan-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-300">
                Guida & Metodologia
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-400">
              Pipeline autonoma a 5 fasi: dallo screening fondamentale all'Auto-Pilot di simulazione ordini.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="hidden sm:inline">{isOpen ? "Nascondi guida" : "Mostra spiegazione dettagliata"}</span>
          {isOpen ? <ChevronUp className="h-4 w-4 text-cyan-400" /> : <ChevronDown className="h-4 w-4 text-cyan-400" />}
        </div>
      </button>

      {/* Contenuto espanso con le 5 fasi */}
      {isOpen && (
        <div className="border-t border-slate-800/80 bg-slate-950/40 px-5 py-5 text-xs text-slate-300">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-5">
            {/* Step 1 */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
              <div className="flex items-center gap-2 font-semibold text-cyan-300">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-cyan-500/20 text-[10px]">1</span>
                <Filter className="h-4 w-4" />
                <span>Screening Rigoroso</span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                Filtra aziende quotate negli ultimi <strong className="text-slate-200">6–24 mesi</strong> con calo post-IPO <strong className="text-slate-200">&ge; 15%</strong>. Verifica crescita ricavi YoY positiva, cassa sufficiente (<strong className="text-slate-200">runway &gt; 12 mesi</strong>) e assenza di debiti tossici.
              </p>
            </div>

            {/* Step 2 */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
              <div className="flex items-center gap-2 font-semibold text-indigo-300">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500/20 text-[10px]">2</span>
                <FileText className="h-4 w-4" />
                <span>Alternative Data</span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                Scarica dalla <strong className="text-slate-200">SEC EDGAR</strong> i moduli <strong className="text-slate-200">Form 4</strong> (acquisti dei dirigenti) e <strong className="text-slate-200">8-K</strong> (nuovi brevetti/accordi). Scansiona le offerte di lavoro (ATS Careers) per captare espansioni prima delle trimestrali.
              </p>
            </div>

            {/* Step 3 */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
              <div className="flex items-center gap-2 font-semibold text-purple-300">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-purple-500/20 text-[10px]">3</span>
                <Bot className="h-4 w-4" />
                <span>Dibattito 4 Agenti</span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                L'<strong className="text-emerald-400">Agente Bull</strong> cerca i catalizzatori. L'<strong className="text-rose-400">Agente Bear</strong> cerca diluizione e red flag. L'<strong className="text-amber-400">Auditor</strong> verifica i fatti e il <strong className="text-purple-300">Giudice</strong> sintetizza con lo score da 1 a 100.
              </p>
            </div>

            {/* Step 4 */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
              <div className="flex items-center gap-2 font-semibold text-emerald-300">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/20 text-[10px]">4</span>
                <Zap className="h-4 w-4" />
                <span>Paper Auto-Pilot</span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                Se lo score è <strong className="text-emerald-400">&ge; 75</strong>, acquista quote frazionate sul budget virtuale (\$1.000). Gestisce uscite asimmetriche: <strong className="text-emerald-300">TP1 a +25%</strong> (vende il 50% e lascia correre a costo zero), <strong className="text-cyan-300">TP2 a +50%</strong> e <strong className="text-rose-400">Trailing Stop a -15%</strong>.
              </p>
            </div>

            {/* Step 5 */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
              <div className="flex items-center gap-2 font-semibold text-amber-300">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500/20 text-[10px]">5</span>
                <Bell className="h-4 w-4" />
                <span>Telegram & Cloud</span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                Gira su <strong className="text-slate-200">GitHub Actions a PC spento</strong>. Notifica su Telegram in tempo reale ogni nuovo acquisto e ogni uscita TP/SL, aggiornando la dashboard online e tenendo traccia del P&L e delle revenue.
              </p>
            </div>
          </div>

          {/* Domande Frequenti & Regole Chiave */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800/80 bg-slate-900/40 p-3 text-[11px]">
            <div className="flex items-center gap-2 text-slate-300">
              <ShieldAlert className="h-4 w-4 text-amber-400 shrink-0" />
              <span>
                <strong>Perché max 10 ordini al mese?</strong> Disciplina di portafoglio: evita l'over-trading su titoli rischiosi e concentra il budget (\$1.000) solo sulle asimmetrie a più alta convinzione.
              </span>
            </div>
            <div className="flex items-center gap-2 text-slate-400">
              <TrendingUp className="h-4 w-4 text-emerald-400 shrink-0" />
              <span><strong>TP1 "Free Ride":</strong> a +25% si incassa il capitale investito; il resto corre a rischio zero.</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
