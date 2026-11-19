# IPO & Micro-Cap AI Scouter (+ Paper Trading Auto-Pilot)

Web app personale (single-user) progettata come scouter automatizzato di asimmetrie finanziarie su **aziende post-IPO (6–24 mesi)** e **micro-cap trascurate**, ottimizzata per una strategia disciplinata fino a **10 micro-ordini al mese** (es. €35 su azioni frazionate), dotata di **Budget Virtuale (€1.000)** e motore **Paper Trading Auto-Pilot** con obiettivi di rendita multi-livello per validare la strategia prima di allocare capitale reale.

---

## Architettura Cloud a PC Spento (Zero-PC-On su GitHub)

**Non devi tenere il PC acceso.** Una volta caricato il progetto su GitHub:
1. **[`.github/workflows/daily_scouter.yml`](.github/workflows/daily_scouter.yml)** gira dal lunedì al venerdì alle **13:30 UTC** (prima dell'apertura USA): analizza i titoli, applica i guardrail su budget virtuale e soglia 10/mese (`--auto-monitor --auto-register`), salva lo stato su [`scouter_store.json`](backend/data/scouter_store.json) e rigenera [`scouter_snapshot.json`](frontend/public/scouter_snapshot.json).
2. **[`.github/workflows/autopilot_monitor.yml`](.github/workflows/autopilot_monitor.yml)** gira ogni 2 ore durante la sessione USA (`14:30, 16:30, 18:30, 20:30 UTC`, lun–ven): aggiorna i prezzi live, calcola i picchi e applica gli obiettivi automatici di uscita (**TP1 Parziale +35% Free-Ride**, **TP2 Finale +80%**, **Trailing Stop -15%**, **Stop Loss -30%**, **Thesis Stop**).
3. **[`.github/workflows/deploy_pages.yml`](.github/workflows/deploy_pages.yml)** pubblica automaticamente la dashboard su **GitHub Pages** in modalità `Cloud Read-Only`.

---

## Obiettivi di Rendita & Budget Virtuale (Paper Trading)

- **Budget Virtuale iniziale:** `€1.000` (configurabile) · **Obiettivo Portafoglio:** `+20%` (`€1.200`).
- **Scala di Uscita Automatica (solo su ordini simulati `PAPER`):**
  1. **TP1 Parziale ("Free Ride") a `+35%`:** incassa metà posizione (`50%`) sul budget virtuale e sposta automaticamente lo Stop Loss della metà rimanente a `0%` (Break-Even).
  2. **TP2 Finale a `+80%`:** chiude l'intera posizione rimanente incassando il target asimmetrico.
  3. **Trailing Stop Protettivo (`-15%` dal picco):** si attiva automaticamente quando il titolo supera `+25%` per non restituire i guadagni al mercato.
  4. **Hard Stop Loss (`-30%`) & Thesis Stop:** chiude se il titolo viola lo stop o se l'AI Score scende sotto `55` (o cala di `≥ 18` punti).
  5. **Protezione Ordini Reali (`REAL`):** non vengono mai chiusi automaticamente (inviano solo alert su Telegram/Audit Log).

---

## Dove trovare le chiavi per i GitHub Secrets

Vai su **Repository → Settings → Secrets and variables → Actions → New repository secret** e inserisci solo quelle che ti servono (tutte hanno un piano gratuito):

| Secret Name | Dove ottenerlo (Gratis) | A cosa serve |
| :--- | :--- | :--- |
| **`GEMINI_API_KEY`** | [Google AI Studio](https://aistudio.google.com/apikey) → *Create API key* | Attiva Gemini live sui 4 agenti (Bull, Bear, Auditor, Giudice) invece del motore forense locale. |
| **`TELEGRAM_BOT_TOKEN`** | Apri Telegram → cerca **`@BotFather`** → invia `/newbot` → segui le istruzioni | Permette al tool di inviarti notifiche sul telefono su nuovi alert, TP1, TP2 e Stop Loss. |
| **`TELEGRAM_CHAT_ID`** | Apri Telegram → cerca **`@userinfobot`** → premi *Start* (ti mostra il tuo ID numerico) — ricordati di inviare prima un `/start` anche al tuo nuovo bot! | Indica a Telegram a quale chat personale recapitare gli avvisi. |
| **`FINNHUB_API_KEY`** | [finnhub.io/register](https://finnhub.io/register) → copia la *API Key* dalla dashboard | Aggiunge le nuove IPO dal calendario Finnhub al radar giornaliero. |
| **`SEC_USER_AGENT`** | Nessuna registrazione: scrivi es. `FinanceTool/1.0 (tua-email@dominio.com)` | Identificativo richiesto dai server ufficiali SEC EDGAR per evitare errori 403. |

---

## Avvio Locale (Modalità Interattiva Completa)

```bash
# Backend FastAPI (http://127.0.0.1:8000)
cd backend
.venv\Scripts\activate
uvicorn api:app --reload --port 8000

# Frontend React + Vite (http://127.0.0.1:5173)
cd frontend
npm run dev -- --port 5173
```
