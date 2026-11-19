import React, { useCallback, useEffect, useState } from "react";
import Navbar from "./components/Navbar";
import OpportunityFeed from "./components/OpportunityFeed";
import TickerDetailModal from "./components/TickerDetailModal";
import MicroOrderJournal from "./components/MicroOrderJournal";
import AutoPilotPanel from "./components/AutoPilotPanel";
import { apiClient } from "./api/client";

export default function App() {
  const [activeTab, setActiveTab] = useState("feed");
  const [opportunities, setOpportunities] = useState([]);
  const [journalData, setJournalData] = useState({ orders: [], summary: null });
  const [autopilotData, setAutopilotData] = useState({ config: {}, logs: [], last_monitor_at: null, journal: { orders: [], summary: {} } });
  const [health, setHealth] = useState(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState(null);
  const [prefillOrderOpp, setPrefillOrderOpp] = useState(null);

  const [loading, setLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [isRunningPipeline, setIsRunningPipeline] = useState(false);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [isRunningAutoReg, setIsRunningAutoReg] = useState(false);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [bannerMsg, setBannerMsg] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      const [oppsRes, journalRes, healthRes, apRes] = await Promise.all([
        apiClient.getOpportunities(0),
        apiClient.getJournal(),
        apiClient.getHealth(),
        apiClient.getAutopilotStatus(),
      ]);
      setOpportunities(oppsRes.items || []);
      setJournalData(journalRes);
      setHealth(healthRes);
      setAutopilotData(apRes);
      if (healthRes?.static_readonly) {
        const snapDate = healthRes.snapshot_generated_at
          ? new Date(healthRes.snapshot_generated_at).toLocaleString("it-IT")
          : "N/D";
        setBannerMsg({
          type: "info",
          text: `Modalità Cloud Read-Only attiva (snapshot del ${snapDate}): Auto-Pilot e screening girano automaticamente su GitHub Actions anche a PC spento.`,
        });
      }
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message || "Impossibile connettersi al backend FastAPI." });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleScanTicker = async (ticker) => {
    setIsScanning(true);
    setBannerMsg({ type: "info", text: `Scansione live SEC EDGAR + yfinance + 4 Agenti su ${ticker}...` });
    try {
      const result = await apiClient.scanTicker(ticker);
      await loadAll();
      setSelectedOpportunity(result);
      setBannerMsg({
        type: "success",
        text: `Analisi completata su ${result.ticker}: Asymmetry Score ${result.asymmetry_score}/100.`,
      });
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message });
    } finally {
      setIsScanning(false);
    }
  };

  const handleRunPipeline = async () => {
    setIsRunningPipeline(true);
    setBannerMsg({ type: "info", text: "Esecuzione pipeline quantitativa + 4 agenti in corso..." });
    try {
      const summary = await apiClient.runPipeline(null);
      await loadAll();
      setBannerMsg({
        type: "success",
        text: `Pipeline completata: analizzati ${summary.analyzed_count} titoli su ${summary.candidates_scanned} candidati.`,
      });
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message });
    } finally {
      setIsRunningPipeline(false);
    }
  };

  const handleQuickLogOrder = (opp) => {
    setSelectedOpportunity(null);
    setPrefillOrderOpp(opp);
    setActiveTab("journal");
  };

  const handleCreateOrder = async (payload) => {
    try {
      const res = await apiClient.createOrder(payload);
      setJournalData(res.journal);
      const apRes = await apiClient.getAutopilotStatus();
      setAutopilotData(apRes);
      setBannerMsg({
        type: "success",
        text: `Micro-ordine ${payload.ticker} (€${payload.amount_eur}) registrato nel Diario di Bordo.`,
      });
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message || "Errore registrazione micro-ordine." });
      throw err;
    }
  };

  const handleToggleOrderStatus = async (orderId, nextStatus, exitPriceUsd = null) => {
    try {
      const payload = { status: nextStatus };
      if (nextStatus === "CHIUSO" && exitPriceUsd) {
        payload.exit_price_usd = exitPriceUsd;
      }
      const res = await apiClient.updateOrder(orderId, payload);
      setJournalData(res.journal);
      const apRes = await apiClient.getAutopilotStatus();
      setAutopilotData(apRes);
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message || "Errore aggiornamento stato ordine." });
    }
  };

  const handleDeleteOrder = async (orderId) => {
    try {
      const res = await apiClient.deleteOrder(orderId);
      setJournalData(res.journal);
      const apRes = await apiClient.getAutopilotStatus();
      setAutopilotData(apRes);
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message || "Errore eliminazione ordine." });
    }
  };

  const handleSaveAutopilotConfig = async (payload) => {
    setIsSavingConfig(true);
    try {
      const res = await apiClient.updateAutopilotConfig(payload);
      if (res.journal) setJournalData(res.journal);
      setAutopilotData((prev) => ({
        ...prev,
        config: res.config,
        logs: res.logs,
        journal: res.journal || prev.journal,
      }));
      setHealth((prev) =>
        prev ? { ...prev, monthly_micro_order_limit: res.config.monthly_order_limit } : prev
      );
      setBannerMsg({ type: "success", text: "Regole Auto-Pilot salvate con successo." });
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message || "Errore salvataggio regole Auto-Pilot." });
    } finally {
      setIsSavingConfig(false);
    }
  };

  const handleRunAutoRegister = async (dryRun) => {
    setIsRunningAutoReg(true);
    try {
      const res = await apiClient.runAutoRegister(dryRun, false);
      if (!dryRun) {
        if (res.journal) setJournalData(res.journal);
        setAutopilotData((prev) => ({
          ...prev,
          config: res.config_used || prev.config,
          logs: res.logs || prev.logs,
          journal: res.journal || prev.journal,
        }));
        setBannerMsg({
          type: res.registered.length > 0 ? "success" : "info",
          text:
            res.message ||
            (res.registered.length > 0
              ? `Auto-Registrazione completata: aperti ${res.registered.length} ordini PAPER_AUTO (${res.registered
                  .map((r) => r.ticker)
                  .join(", ")}).`
              : `Nessun nuovo ordine registrato (${res.skipped.length} titoli filtrati dai guardrail).`),
        });
      }
      return res;
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message || "Errore Auto-Registrazione." });
      return null;
    } finally {
      setIsRunningAutoReg(false);
    }
  };

  const handleRunMonitor = async (refreshLivePrices = true, rescanAi = false) => {
    setIsMonitoring(true);
    setBannerMsg({
      type: "info",
      text: rescanAi
        ? "Auto-Monitoraggio con ri-analisi AI + SEC EDGAR in corso..."
        : "Aggiornamento prezzi live e controllo TP/SL in corso...",
    });
    try {
      const res = await apiClient.runPortfolioMonitor(refreshLivePrices, rescanAi);
      if (rescanAi) {
        await loadAll();
      } else {
        if (res.journal) setJournalData(res.journal);
        setAutopilotData((prev) => ({
          ...prev,
          last_monitor_at: res.monitored_at || prev.last_monitor_at,
          logs: res.logs || prev.logs,
          journal: res.journal || prev.journal,
        }));
      }
      setBannerMsg({
        type: (res.partial_exits?.length ?? 0) > 0 || res.auto_closed.length > 0 || res.alerts.length > 0 ? "info" : "success",
        text: `Monitoraggio completato su ${res.checked_count} posizioni aperte · ${res.partial_exits?.length ?? 0} TP1 parziali · ${res.auto_closed.length} chiusure Paper · ${res.alerts.length} alert reali.`,
      });
    } catch (err) {
      setBannerMsg({ type: "error", text: err.message || "Errore Auto-Monitoraggio." });
    } finally {
      setIsMonitoring(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        opportunitiesCount={opportunities.length}
        journalSummary={journalData.summary}
        autopilotEnabled={Boolean(autopilotData?.config?.enabled)}
        health={health}
        onScanTicker={handleScanTicker}
        onRunPipeline={handleRunPipeline}
        isScanning={isScanning}
        isRunningPipeline={isRunningPipeline}
      />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {bannerMsg && (
          <div
            className={`mb-5 flex items-center justify-between rounded-xl border px-4 py-2.5 text-xs ${
              bannerMsg.type === "error"
                ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
                : bannerMsg.type === "success"
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                  : "border-cyan-500/40 bg-cyan-500/10 text-cyan-200"
            }`}
          >
            <span>{bannerMsg.text}</span>
            <button
              type="button"
              onClick={() => setBannerMsg(null)}
              className="ml-4 text-slate-400 hover:text-white"
            >
              ✕
            </button>
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-64 animate-pulse rounded-2xl border border-slate-800 bg-slate-900/50" />
            ))}
          </div>
        ) : activeTab === "feed" ? (
          <OpportunityFeed
            opportunities={opportunities}
            journalSummary={journalData.summary}
            onSelectTicker={(opp) => setSelectedOpportunity(opp)}
            onQuickLogOrder={handleQuickLogOrder}
          />
        ) : activeTab === "journal" ? (
          <MicroOrderJournal
            journalData={journalData}
            opportunities={opportunities}
            isReadOnly={Boolean(health?.static_readonly)}
            prefillOpportunity={prefillOrderOpp}
            onClearPrefill={() => setPrefillOrderOpp(null)}
            onCreateOrder={handleCreateOrder}
            onToggleOrderStatus={handleToggleOrderStatus}
            onDeleteOrder={handleDeleteOrder}
            onRefreshLivePrices={() => handleRunMonitor(true, false)}
            isMonitoring={isMonitoring}
          />
        ) : (
          <AutoPilotPanel
            autopilotData={autopilotData}
            isReadOnly={Boolean(health?.static_readonly)}
            onSaveConfig={handleSaveAutopilotConfig}
            onRunAutoRegister={handleRunAutoRegister}
            onRunMonitor={handleRunMonitor}
            isSavingConfig={isSavingConfig}
            isRunningAutoReg={isRunningAutoReg}
            isMonitoring={isMonitoring}
          />
        )}
      </main>

      <TickerDetailModal
        opportunity={selectedOpportunity}
        onClose={() => setSelectedOpportunity(null)}
        onLogOrder={handleQuickLogOrder}
      />
    </div>
  );
}
