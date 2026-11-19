# IPO & Micro-Cap AI Scouter (+ Paper Trading Auto-Pilot)

Web app personale (single-user) progettata come scouter automatizzato di asimmetrie finanziarie su **aziende post-IPO (6–24 mesi)** e **micro-cap trascurate**, ottimizzata per una strategia disciplinata da **5 micro-ordini al mese** (es. €25–€50 su azioni frazionate), dotata di motore **Paper Trading Auto-Pilot** per validare la strategia prima di allocare capitale reale.

---

## Architettura Cloud a PC Spento (Zero-PC-On su GitHub)

**Non devi tenere il PC acceso.** Una volta caricato il progetto su GitHub (piano Free):
1. **[`.github/workflows/daily_scouter.yml`](.github/workflows/daily_scouter.yml)** gira automaticamente dal lunedì al venerdì alle **13:30 UTC** (prima dell'apertura dei mercati US): esegue lo screening quantitativo, il parsing SEC EDGAR, i 4 agenti AI, il controllo Auto-Pilot (`--auto-monitor --auto-register`) e salva lo stato aggiornato su Git + snapshot statico + notifiche Telegram.
2. **[`.github/workflows/autopilot_monitor.yml`](.github/workflows/autopilot_monitor.yml)** gira automaticamente ogni 2 ore durante la sessione US (`14:30–20:30 UTC`): aggiorna le quotazioni live, registra i checkpoint storici (`price_history`), chiude eventuali posizioni simulate al raggiungimento di Take Profit (`+60%`), Stop Loss (`-35%`) o Thesis Stop, e invia alert su Telegram.
3. **[`.github/workflows/deploy_pages.yml`](.github/workflows/deploy_pages.yml)** pubblica automaticamente la dashboard React su **GitHub Pages** in modalità `Cloud Read-Only` così puoi consultarla in qualsiasi momento anche da smartphone, con il PC spento.

---

## Architettura Tecnica & Funzionalità

- **Screening Quantitativo Multi-Fonte (`backend/services/quant_screener.py`)**: integra Finnhub IPO Calendar (opzionale) + `yfinance` su storia prezzi completa (`period="max"`) per filtrare drawdown post-IPO negativi (-15% / -88%), crescita ricavi YoY positiva, cassa / runway > 12 mesi (calcolata su FCF negativo se CapEx-heavy) e assenza di debito tossico.
- **Motore SEC EDGAR & Alternative Data (`backend/services/sec_edgar.py`, `backend/services/alt_data.py`)**:
  - Parsing XML diretto dei **Form 4** per distinguere gli acquisti reali sul mercato aperto (**Codice P**, incluso *Cluster Insider Buying*) da grant (`A`) o esercizi opzioni (`M`).
  - Estrazione **8-K** (Item `1.01`, `8.01`, `3.01`, `3.02`, `4.02`, `5.03`) e controllo a 3 anni su **`S-3` / `S-3ASR` / `424B5`** per prevenire trappole di diluizione.
  - News RSS con regex a confini di parola + rilevazione **Hiring Spike vs Tagli** tramite board ATS pubbliche (Greenhouse, Lever, Ashby) + check **Azioni Frazionate & Commissioni Zero** (Trading 212, IBKR, Trade Republic, Scalable, Revolut, Directa).
- **Pipeline Multi-Agente a 4 Fasi con Contro-Verifica (`backend/scouter_pipeline.py`)**:
  1. **Agente Bull**: catalizzatori verificabili (`[SEC-8K]`, `[FORM-4]`, `[FIN-DATA]`, `[NEWS]`, `[CAREERS]`).
  2. **Agente Bear**: red flag su diluizione S-3/ATM, burn rate, vendite insider e leva.
  3. **Agente Auditor / Verificatore (Contro-Verifica)**: controlla la coerenza matematica (Runway, Net Cash, Form 4 Codice P) e segnala esagerazioni o affermazioni non verificate di Bull e Bear.
  4. **Agente Giudice**: assegna `Asymmetry Score` (1–100) scomposto in 5 sub-score e genera la **tesi sintetica in 5 righe** + piano micro-ordine.
- **Paper Trading Auto-Pilot (`backend/services/autopilot.py`)**:
  - **Auto-Registrazione controllata da guardrail**: apre micro-ordini simulati `PAPER_AUTO` rispettando soglia AI Score, Audit %, Runway, anti-duplicato e limite 5/mese, con **Anteprima Dry-Run**.
  - **Auto-Monitoraggio & Protezione Ordini Reali**: aggiorna i checkpoint storici, chiude automaticamente solo posizioni simulate (`PAPER_AUTO` / `PAPER_MANUAL`) su TP/SL/Thesis Stop, e protegge rigorosamente gli ordini `REAL` (emettendo solo alert deduplicati).

---

## Pubblicazione su GitHub (Setup in 3 Minuti)

1. **Crea un repository vuoto su GitHub** (es. `ipo-microcap-ai-scouter`, pubblico o privato).
2. **Collega e carica il repository locale**:
   ```bash
   git remote add origin https://github.com/<TUO_USERNAME>/<TUO_REPO>.git
   git push -u origin main
   ```
3. **Abilita i permessi Cloud su GitHub**:
   - Vai su **Settings → Actions → General → Workflow permissions**: seleziona **Read and write permissions** e salva (serve ai workflow automatici per salvare `scouter_store.json` e `scouter_snapshot.json`).
   - Vai su **Settings → Pages → Build and deployment → Source**: seleziona **GitHub Actions**.
4. **Aggiungi i Secrets opzionali** in **Settings → Secrets and variables → Actions**:
   - `GEMINI_API_KEY`: attiva l'analisi live Gemini sui 4 agenti (altrimenti gira il motore forense locale).
   - `FINNHUB_API_KEY`: espande il feed con le nuove IPO da Finnhub.
   - `TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID`: ricevi avvisi istantanei su smartphone per nuovi alert, auto-registrazioni e chiusure TP/SL.
   - `SEC_USER_AGENT`: es. `IlTuoNome/1.0 (tua-email@example.com)`.
   - `FIREBASE_SERVICE_ACCOUNT_JSON`: opzionale se vuoi sincronizzare anche su Firebase Firestore.

---

## Sviluppo & Utilizzo in Locale (Modalità Interattiva Completa)

### 1. Backend (Python + FastAPI)
```bash
cd backend
cp .env.example .env
.venv\Scripts\activate      # Su Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

Comandi CLI utili:
```bash
cd backend
# Scansione completa + auto-monitoraggio + auto-registrazione paper
python scouter_pipeline.py --tickers RDW PL BKSY OUST TEM ASTS --auto-monitor --auto-register --no-notify

# Aggiornamento rapido prezzi live, TP/SL e snapshot per il frontend
python scouter_pipeline.py --monitor-only
```

### 2. Frontend (React + Vite + Tailwind)
```bash
cd frontend
npm install
npm run dev -- --port 5173
```
Apri `http://127.0.0.1:5173`.
