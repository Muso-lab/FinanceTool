/**
 * Client API unificato con fallback automatico su snapshot statico.
 * - In locale comunica con FastAPI via proxy Vite (`/api`).
 * - Su GitHub Pages (senza backend Python attivo) legge `./scouter_snapshot.json`
 *   generato e aggiornato dai workflow automatici di GitHub Actions.
 */

const API_BASE = "./api";
const SNAPSHOT_URL = "./scouter_snapshot.json";
const READONLY_ERR_MSG =
  "Modalità Cloud Read-Only (GitHub Pages): l'Auto-Pilot gira automaticamente via GitHub Actions anche a PC spento. Per operazioni manuali usa il backend locale o avvia il workflow su GitHub.";

let cachedSnapshot = null;
let snapshotInFlight = null;
let staticReadOnlyMode = false;

function formatApiErrorDetail(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
        return field ? `${field}: ${item.msg}` : item.msg || JSON.stringify(item);
      })
      .join("; ");
  }
  return typeof detail === "object" ? JSON.stringify(detail) : String(detail);
}

async function loadStaticSnapshot() {
  if (cachedSnapshot) return cachedSnapshot;
  if (snapshotInFlight) return snapshotInFlight;

  snapshotInFlight = (async () => {
    const res = await fetch(SNAPSHOT_URL, { cache: "no-cache" });
    if (!res.ok) {
      throw new Error("Backend non raggiungibile e snapshot cloud non disponibile.");
    }
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      throw new Error("Snapshot cloud non valido (formato non JSON).");
    }
    cachedSnapshot = await res.json();
    staticReadOnlyMode = true;
    return cachedSnapshot;
  })();

  try {
    return await snapshotInFlight;
  } finally {
    snapshotInFlight = null;
  }
}

function resolveSnapshotEndpoint(path, snapshot) {
  if (path === "/health" || path.startsWith("/health?")) {
    return {
      ...(snapshot.health || {}),
      static_readonly: true,
      snapshot_generated_at: snapshot.generated_at,
    };
  }
  if (path === "/opportunities" || path.startsWith("/opportunities?")) {
    const query = path.split("?")[1] || "";
    const params = new URLSearchParams(query);
    const minScore = Number(params.get("min_score") || 0);
    const allItems = snapshot.opportunities?.items || [];
    const items = allItems.filter((o) => (o.asymmetry_score || 0) >= minScore);
    return {
      count: items.length,
      top_daily: items.filter((o) => (o.asymmetry_score || 0) >= 55).slice(0, 5),
      items,
    };
  }
  if (path === "/journal" || path.startsWith("/journal?")) {
    return snapshot.journal || { orders: [], summary: {} };
  }
  if (path === "/autopilot/status") {
    return snapshot.autopilot || { config: {}, logs: [], last_monitor_at: null, journal: { orders: [], summary: {} } };
  }
  return null;
}

async function request(path, options = {}) {
  const { headers: customHeaders, ...restOptions } = options;
  const method = (restOptions.method || "GET").toUpperCase();
  const isRead = method === "GET";

  if (staticReadOnlyMode && !isRead) {
    throw new Error(READONLY_ERR_MSG);
  }

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...restOptions,
      headers: {
        "Content-Type": "application/json",
        ...(customHeaders || {}),
      },
    });

    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    if (!res.ok) {
      if (!isJson && (res.status === 404 || res.status === 405 || res.status >= 500)) {
        if (isRead) {
          const snap = await loadStaticSnapshot();
          const data = resolveSnapshotEndpoint(path, snap);
          if (data !== null) return data;
        } else {
          staticReadOnlyMode = true;
          throw new Error(READONLY_ERR_MSG);
        }
      }

      let message = `Errore HTTP ${res.status}`;
      if (isJson) {
        try {
          const errBody = await res.json();
          if (errBody.detail !== undefined) {
            message = formatApiErrorDetail(errBody.detail, message);
          }
        } catch {
          // ignore parse error
        }
      }
      throw new Error(message);
    }

    if (!isJson) {
      if (isRead) {
        const snap = await loadStaticSnapshot();
        const data = resolveSnapshotEndpoint(path, snap);
        if (data !== null) return data;
      }
      staticReadOnlyMode = true;
      throw new Error(READONLY_ERR_MSG);
    }

    staticReadOnlyMode = false;
    return await res.json();
  } catch (err) {
    if (isRead) {
      try {
        const snap = await loadStaticSnapshot();
        const data = resolveSnapshotEndpoint(path, snap);
        if (data !== null) return data;
      } catch {
        // se manca anche lo snapshot, propaga l'errore originale
      }
    }
    throw err;
  }
}

export const apiClient = {
  getHealth: () => request("/health"),
  getOpportunities: (minScore = 0) => request(`/opportunities?min_score=${minScore}`),
  scanTicker: (ticker) => request(`/scan/${encodeURIComponent(ticker)}`, { method: "POST" }),
  runPipeline: (tickers = null) =>
    request("/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ tickers, max_candidates: 8, notify: false }),
    }),
  getJournal: () => request("/journal"),
  createOrder: (payload) =>
    request("/journal", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateOrder: (orderId, payload) =>
    request(`/journal/${orderId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteOrder: (orderId) =>
    request(`/journal/${orderId}`, {
      method: "DELETE",
    }),
  getAutopilotStatus: () => request("/autopilot/status"),
  updateAutopilotConfig: (payload) =>
    request("/autopilot/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  runAutoRegister: (dryRun = false, force = false) =>
    request("/autopilot/auto-register", {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun, force }),
    }),
  runPortfolioMonitor: (refreshLivePrices = true, rescanAi = false) =>
    request("/autopilot/monitor", {
      method: "POST",
      body: JSON.stringify({ refresh_live_prices: refreshLivePrices, rescan_ai: rescanAi }),
    }),
};
