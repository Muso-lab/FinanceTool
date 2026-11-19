# IPO & Micro-Cap AI Scouter — Documentazione Ufficiale di Progetto

> **Versione:** 1.2.0  
> **Autore:** Luciano Liberati & Antigravity  
> **Web App:** [https://muso-lab.github.io/FinanceTool/](https://muso-lab.github.io/FinanceTool/)  
> **Repository GitHub:** [https://github.com/Muso-lab/FinanceTool](https://github.com/Muso-lab/FinanceTool)  
> **Bot Telegram Ufficiale:** `@musolab_financetooo_bot`

---

## 1. Obiettivo e Filosofia d'Investimento

Lo scopo principale del progetto è fornire uno **scouter automatizzato personale** capace di intercettare opportunità finanziarie ad **alta asimmetria informativa** prima che diventino di dominio pubblico mainstream.

### Target di Mercato
1. **Aziende appena quotate (post-IPO)**: finestra temporale tra **6 e 24 mesi dalla quotazione**, momento in cui l'hype iniziale svanisce, i titoli subiscono spesso un forte calo (*drawdown post-IPO* $\ge 15\%$) ma i fondamentali aziendali continuano a crescere.
2. **Micro-Cap trascurate**: società a bassa capitalizzazione trascurate dai grandi fondi di Wall Street e dagli analisti retail.

### Approccio Operativo
- **Non è trading ad alta frequenza**: non cerca oscillazioni di pochi secondi o minuti.
- **Segnali lenti e asimmetrici**: monitora catalizzatori reali (nuovi brevetti approvati, accordi commerciali istituzionali, assunzioni chiave e insider buying dei dirigenti).
- **Micro-investimenti disciplinati**: ottimizzato per frazionamenti mensili controllati (fino a 10 operazioni al mese da poche decine di euro) con regole matematiche rigide di presa profitto e taglio delle perdite.

---

## 2. Architettura del Sistema

Il sistema adotta un'architettura **Full-Stack resiliente e ibrida**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FONTI DATI & INTELLIGENZA                       │
│  Yahoo Finance (Prezzi Live) · SEC EDGAR (Form 4 & 8-K) · Finnhub API   │
│                 Google Gemini 3.8 Flash (4 Agenti AI)                  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
┌───────────────────────────────┐             ┌────────────────────────────────┐
│   CLOUD 24/7 (A PC SPENTO)    │             │      ESECUZIONE IN LOCALE      │
│  GitHub Actions (Serverless)  │             │   FastAPI (Python) + Vite      │
│  • daily_scouter.yml (13:30)  │             │   Launcher: avvia_locale.bat   │
│  • autopilot_monitor.yml (2h) │             │   Web server su localhost:5173 │
│  • Storage: scouter_store.json│             │   Scansione live in 3 secondi  │
└───────────────┬───────────────┘             └────────────────┬───────────────┘
                │                                              │
                ▼                                              ▼
┌───────────────────────────────┐             ┌────────────────────────────────┐
│      OUTPUT & NOTIFICHE       │             │         DASHBOARD WEB          │
│   Telegram Bot in Tempo Reale │             │   React 19 + Tailwind v4       │
│   • Briefing Portafoglio      │ ──────────► │   GitHub Pages (Cloud)         │
│   • Alert Asimmetrici (≥75)   │             │   Portafoglio Live + Guida     │
│   • Esecuzione TP1 / TP2 / SL │             │   Diario Ordini + Auto-Pilot   │
└───────────────────────────────┘             └────────────────────────────────┘
```

### Stack Tecnologico
- **Backend**: Python 3.12/3.14 con FastAPI, yfinance, Requests, BeautifulSoup4, Feedparser e Google GenAI SDK.
- **Frontend**: React 19, Vite, Tailwind CSS v4, Lucide Icons.
- **Motore AI**: Google Gemini 3.8 Flash con catena di fallback multi-modello e gestione automatica dei picchi di traffico (503 UNAVAILABLE / 429).
- **Storage Duale**: persistenza JSON atomica locale/cloud (`scouter_store.json` e snapshot statico `scouter_snapshot.json`) con connettore opzionale Firebase Firestore.

---

## 3. La Pipeline Multi-Agente & Forensic Analysis

Ogni candidato viene sottoposto a un'analisi forense suddivisa in 4 fasi:

### Fase 1: Filtro Quantitativo Rigoroso
- **Data IPO**: compresa tra 6 e 24 mesi fa.
- **Drawdown post-IPO**: calo $\ge 15\%$ dal massimo storico post-IPO (prezzo a sconto).
- **Crescita Ricavi YoY**: variazione positiva dei ricavi anno su anno.
- **Runway di Cassa**: mesi di liquidità residua $> 12$ mesi rispetto al monthly burn rate (oppure Cash-Flow positivo).
- **Assenza di Debiti Tossici**: verifica dell'indice di liquidità (*Current Ratio* $> 1.0$) ed esame delle note per escludere note convertibili a sconto o prestiti predatori.

### Fase 2: Ingestion di Alternative Data
- **SEC EDGAR Form 4**: traccia gli acquisti sul mercato aperto da parte di CEO, CFO e membri del CdA (*Insider Buying reale a mercato*, escludendo le stock option di compenso).
- **SEC EDGAR 8-K**: rileva comunicazioni straordinarie su nuovi contratti industriali, licenze o brevetti approvati.
- **Pagine Careers (ATS)**: monitoraggio dei trend di assunzione su Greenhouse, Lever e Workday (segnale di espansione aziendale vs tagli dell'organico).
- **News RSS & Sentiment**: analisi delle ultime notizie con classificazione tematica ad espressioni regolari con confini di parola esatti.

### Fase 3: Il Dibattito dei 4 Agenti AI
1. **Agente Bull (Ottimista)**: estrae dai documenti i catalizzatori di espansione, la scalabilità del modello di business e i vantaggi competitivi.
2. **Agente Bear (Scettico)**: scandaglia i rischi di diluizione (prospetti S-3 Shelf imminenti), il burn rate, la scadenza dei contratti chiave e i rischi normativi.
3. **Agente Auditor (Controverificatore)**: verifica oggettivamente ogni affermazione di Bull e Bear incrociandola con i dati di bilancio e assegna un *Verification Score* (0–100%).
4. **Agente Giudice**: emette il verdetto finale con una sintesi in 5 righe e l'**Asymmetry Score (1–100)**:
   - **Score $\ge 75$**: `STRONG_ASYMMETRIC_BUY` (promosso per l'acquisto Auto-Pilot e notificato su Telegram).
   - **Score 55–74**: `WATCHLIST_ACCUMULATE` (titolo solido da monitorare).
   - **Score $< 55$**: `AVOID_HIGH_RISK` (red flag o diluizione imminente).

---

## 4. Motore di Paper Trading & Exit Strategy

Il modulo Auto-Pilot simula un portafoglio reale con contabilità rigorosa:

### Parametri di Base
- **Budget Virtuale Iniziale**: 1.000,00 €.
- **Limite Mensile**: massimo 10 micro-ordini al mese per evitare l'over-trading.
- **Quote Frazionate**: calcolo esatto delle azioni fino a 4 cifre decimali.

### Migliorie Avanzate Attive
1. **Dynamic Position Sizing (Ticket proporzionale alla convinzione)**:
   - Score 75–79: **35,00 €** (ticket base prudente).
   - Score 80–89: **50,00 €** (1.43x ticket base, convinzione solida).
   - Score 90–100: **70,00 €** (2.0x ticket base, massima asimmetria con forte insider buying).
2. **Sector Concentration Cap**: tetto massimo di **2 posizioni aperte per singolo settore economico** per garantire la diversificazione.
3. **La Scala di Uscita Asimmetrica (Exit Ladder)**:
   - **TP1 (+25% / +35%)**: vende il **50% delle quote**, incassa il profitto realizzato e **sposta lo Stop Loss a Break-Even (0%)**: la restante metà corre a costo zero (*Free-Ride*).
   - **TP2 (+50% / +80%)**: chiusura totale della posizione con profitto pieno.
   - **Trailing Stop Protettivo (-15% dal picco)**: dopo un guadagno $\ge +25\%$, se il titolo ritraccia del 15% dal suo massimo, scatta la vendita automatica a protezione del profitto accumulato.
   - **Stop Loss Fisso (-20% / -30%)**: taglia le perdite se l'ipotesi viene smentita dal mercato.
   - **Time-Stop (60 giorni)**: se dopo 60 giorni il titolo rimane piatto (oscillazione entro $\pm 10\%$) senza catalizzatori, la posizione viene chiusa e il capitale viene riallocato su nuove opportunità.
4. **Compounding Ricorsivo (Effetto Valanga)**:
   $$\text{Cassa Disponibile} = \text{Budget Iniziale} - \text{Capitale Attualmente Investito} + \text{Profitti Realizzati}$$
   Ogni vendita in guadagno accresce direttamente la liquidità disponibile per i mesi successivi.

---

## 5. Automazione Cloud (GitHub Actions)

L'intera applicazione gira nel cloud di GitHub a costo zero e senza necessità di tenere il computer acceso:

| Workflow | Frequenza | Azione Svolta |
| :--- | :--- | :--- |
| **`daily_scouter.yml`** | Lun–Ven ore 13:30 UTC | Screening quantitativo, dibattito 4 agenti, acquisto Auto-Pilot, **invio Briefing Mattutino su Telegram** e pubblicazione su GitHub Pages. |
| **`autopilot_monitor.yml`** | Lun–Ven ogni 2 ore (sessione US) | Controllo prezzi live delle posizioni aperte, esecuzione TP1, TP2, Trailing Stop e Stop Loss con alert Telegram. |
| **`verify_secrets.yml`** | Manuale (`workflow_dispatch`) | Test diagnostico immediato delle chiavi Gemini, Finnhub, SEC EDGAR e Telegram. |
| **`deploy_pages.yml`** | Ad ogni commit su `main` | Compilazione Vite e pubblicazione automatica della Dashboard su GitHub Pages. |

---

## 6. Sistema di Notifiche Telegram

Il bot dedicato **`@musolab_financetooo_bot`** è configurato con politica **zero spam**:

1. **Briefing Giornaliero Mattutino (ore 13:30 UTC)**:
   - Valore complessivo dell'Equity e P&L totale.
   - Cassa disponibile e capitale investito.
   - Elenco delle posizioni aperte con prezzo live, percentuale di guadagno e indicatore *Free-Ride*.
   - Top opportunità scovate nella sessione.
2. **Alert su Nuove Opportunità (Score $\ge 75$)**: notifica immediata con tesi di investimento dell'AI in 5 righe.
3. **Alert Operativi Auto-Pilot**:
   - `AUTO_REGISTER`: apertura di un nuovo micro-ordine simulato.
   - `PARTIAL_TP1`: incasso del 50% di profitto e protezione a Break-Even.
   - `AUTO_CLOSE`: chiusura completa per Trailing Stop, TP Finale o Time-Stop.

---

## 7. Guida all'Utilizzo della Dashboard Web

### Accesso Cloud
👉 **[https://muso-lab.github.io/FinanceTool/](https://muso-lab.github.io/FinanceTool/)**
- **Home Page**:
  - Banner interattivo espandibile **"Come Funziona"**;
  - Widget in tempo reale **"Il Tuo Portafoglio Attivo"** con quotazioni live, controvalore e barra di avanzamento verso il Take Profit;
  - Feed delle opportunità del giorno con filtri per punteggio e tag.
- **Diario Micro-Ordini**: storico contabile, inserimento ordini manuali e performance.
- **Pannello Auto-Pilot**: regolazione dei parametri, Dynamic Sizing e tetto settoriale salvati istantaneamente nel browser.
- **Pulsante "Esegui Pipeline Cloud ↗"**: permette di avviare una scansione manuale su GitHub Actions con un solo clic.

### Accesso Locale Full-Live (Sul Tuo PC)
Nel caso tu voglia scansionare qualsiasi ticker al volo con risposta immediata:
1. Apri la cartella del progetto: `c:\Sviluppo\TOOL FINANZIARIO`.
2. Fai doppio clic sul file **`avvia_locale.bat`**.
3. Il file avvia il backend FastAPI sulla porta 8000, il frontend Vite sulla porta 5173 e apre il browser su `http://localhost:5173`.
4. In locale tutte le chiamate API e le scansioni live sono operative al 100% in tempo reale.

---

## 8. Stato del Portafoglio di Test al Lancio

| Parametro | Valore Attuale |
| :--- | :--- |
| **Budget Virtuale** | € 1.000,00 |
| **Cassa Residua Disponibile** | € 895,00 |
| **Capitale Investito** | € 105,00 (3 posizioni aperte da € 35,00) |
| **P&L Complessivo** | **+3,71 € (+3,53%)** 🟢 |
| **Equity Totale Portafoglio** | **€ 1.003,71** |

### Dettaglio Posizioni Aperte
- **`RDW` (Redwire Corp)**: Ingresso \$6.40 $\to$ Prezzo Live \$6.82 (**+6,56%** 🟢)
- **`ASTS` (AST SpaceMobile)**: Ingresso \$24.50 $\to$ Prezzo Live \$25.49 (**+4,04%** 🟢)
- **`RKLB` (Rocket Lab USA)**: Ingresso \$53.07 $\to$ Prezzo Live \$53.07 (**0,00%** ⚪)

---

## 9. Manutenzione & Secret su GitHub

I Secret configurati in **Settings > Secrets and variables > Actions** sono:
- `GEMINI_API_KEY`: chiave Google AI Studio (modello attivo: `gemini-3.8-flash`).
- `FINNHUB_API_KEY`: token per calendario IPO e quotazioni rapide.
- `SEC_USER_AGENT`: intestazione conforme alle linee guida SEC EDGAR (`Nome contatto@email.com`).
- `TELEGRAM_BOT_TOKEN`: token HTTP generato da `@BotFather`.
- `TELEGRAM_CHAT_ID`: ID numerico della chat privata ricevuto da `@userinfobot`.

Per verificare in ogni momento la validità dei Secret, basta eseguire il workflow:  
👉 [Verify GitHub Secrets](https://github.com/Muso-lab/FinanceTool/actions/workflows/verify_secrets.yml).
