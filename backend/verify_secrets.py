"""Script di diagnostica per verificare la validità dei Secret configurati.

Può essere eseguito sia in locale sia tramite GitHub Actions (workflow dispatch).
Verifica:
1. GEMINI_API_KEY
2. FINNHUB_API_KEY
3. SEC_USER_AGENT
4. TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()


def mask(val: str | None) -> str:
    if not val:
        return "[NON IMPOSTATO]"
    clean = val.strip()
    if len(clean) <= 6:
        return "***"
    return f"{clean[:3]}...{clean[-3:]}"


def test_gemini(api_key: str | None) -> bool:
    print("\n--- 1. Verifica GEMINI_API_KEY ---")
    if not api_key or not api_key.strip():
        print("❌ GEMINI_API_KEY: ASSENTE")
        print("   -> Vai su GitHub Settings > Secrets and variables > Actions e aggiungi GEMINI_API_KEY")
        return False

    print(f"   Valore rilevato: {mask(api_key)}")
    try:
        import time
        from google import genai

        client = genai.Client(api_key=api_key.strip())

        # 1. Interroga direttamente le API di Google per avere l'elenco esatto dei modelli abilitati
        print("   Interrogazione ModelService di Google AI Studio per modelli attivi...")
        available_models: list[str] = []
        try:
            for m in client.models.list():
                m_name = getattr(m, "name", "") or ""
                clean_name = m_name.replace("models/", "").strip()
                actions = getattr(m, "supported_actions", None) or []
                if not actions or "generateContent" in actions:
                    available_models.append(clean_name)
        except Exception as list_exc:
            print(f"   ⚠️ Enumerazione automatica modelli non riuscita: {list_exc}")

        if available_models:
            print(f"   Modelli disponibili sul tuo account ({len(available_models)}): {', '.join(available_models[:8])}")

        # 2. Costruisci la lista prioritaria di test
        preferred = [os.getenv("GEMINI_MODEL_FAST", "").strip(), "gemini-3.8-flash"]
        models_to_test = [m for m in preferred if m] + [m for m in available_models if m not in preferred]
        if not models_to_test:
            models_to_test = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

        # 3. Testa con retry intelligente per gestire spike di traffico temporanei (503 UNAVAILABLE)
        for model_name in models_to_test:
            for attempt in range(1, 4):
                try:
                    print(f"   Tentativo {attempt}/3 con modello: '{model_name}'...")
                    resp = client.models.generate_content(
                        model=model_name,
                        contents="Rispondi solo con la parola 'FUNZIONA'.",
                    )
                    reply = resp.text.strip() if resp and resp.text else ""
                    print(f"✅ GEMINI_API_KEY: VALIDO E FUNZIONANTE! (Modello attivo: {model_name})")
                    print(f"   Risposta AI: {reply}")
                    return True
                except Exception as exc:
                    err_msg = str(exc)
                    if "503" in err_msg or "UNAVAILABLE" in err_msg:
                        print(f"   ⚠️ Spike temporaneo di traffico (503) su '{model_name}'. Attendo 3 secondi e riprovo...")
                        time.sleep(3)
                        continue
                    elif "404" in err_msg or "NOT_FOUND" in err_msg:
                        print(f"   ⚠️ Modello '{model_name}' non disponibile su questa versione API, passo al successivo...")
                        break
                    elif "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        print(f"   ⚠️ Rate limit temporaneo (429) su '{model_name}'. Attendo 3 secondi...")
                        time.sleep(3)
                        continue
                    else:
                        print(f"   ⚠️ Errore con '{model_name}': {exc}")
                        break

        print("❌ GEMINI_API_KEY: Nessun modello ha risposto con successo dopo i tentativi di retry.")
        return False
    except Exception as exc:
        print(f"❌ GEMINI_API_KEY: Errore inizializzazione client: {exc}")
        return False


def test_finnhub(api_key: str | None) -> bool:
    print("\n--- 2. Verifica FINNHUB_API_KEY ---")
    if not api_key or not api_key.strip():
        print("❌ FINNHUB_API_KEY: ASSENTE")
        print("   -> Vai su GitHub Settings > Secrets and variables > Actions e aggiungi FINNHUB_API_KEY")
        return False

    print(f"   Valore rilevato: {mask(api_key)}")
    try:
        url = "https://finnhub.io/api/v1/quote"
        resp = requests.get(url, params={"symbol": "AAPL", "token": api_key.strip()}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            curr_price = data.get("c")
            print(f"✅ FINNHUB_API_KEY: VALIDO E FUNZIONANTE!")
            print(f"   Quotazione di prova (AAPL): ${curr_price}")
            return True
        elif resp.status_code in (401, 403):
            print(f"❌ FINNHUB_API_KEY: NON VALIDO (HTTP {resp.status_code}: Token respinto da Finnhub)")
            return False
        else:
            print(f"⚠️ FINNHUB_API_KEY: Risposta inattesa HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as exc:
        print(f"❌ FINNHUB_API_KEY: Errore di connessione: {exc}")
        return False


def test_sec_user_agent(user_agent: str | None) -> bool:
    print("\n--- 3. Verifica SEC_USER_AGENT ---")
    if not user_agent or not user_agent.strip():
        print("⚠️ SEC_USER_AGENT: ASSENTE (verrà usato il fallback di sistema)")
        print("   -> Consiglio: imposta una stringa come 'FinanceToolApp tuonome@example.com'")
        return False

    ua = user_agent.strip()
    print(f"   Valore rilevato: {ua}")
    if "@" not in ua:
        print("⚠️ ATTENZIONE: La SEC richiede obbligatoriamente un indirizzo email di contatto nel formato: 'NomeApp contatto@dominio.com'.")

    try:
        # Test di download su CIK Apple (0000320193)
        url = "https://data.sec.gov/submissions/CIK0000320193.json"
        headers = {
            "User-Agent": ua,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            name = resp.json().get("name", "EDGAR Entity")
            print(f"✅ SEC_USER_AGENT: VALIDO E ACCETTATO DA SEC EDGAR!")
            print(f"   Connessione test riuscita con successo ({name})")
            return True
        elif resp.status_code == 403:
            print(f"❌ SEC_USER_AGENT: RIFIUTATO DA SEC EDGAR (HTTP 403 Forbidden).")
            print("   La SEC blocca richieste senza email valida. Esempio corretto: 'FinanceToolApp info@tuodominio.com'")
            return False
        else:
            print(f"⚠️ SEC_USER_AGENT: Risposta HTTP {resp.status_code}")
            return False
    except Exception as exc:
        print(f"❌ SEC_USER_AGENT: Errore di connessione a data.sec.gov: {exc}")
        return False


def test_telegram(token: str | None, chat_id: str | None) -> bool:
    print("\n--- 4. Verifica TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID ---")
    if not token or not token.strip():
        print("ℹ️ TELEGRAM_BOT_TOKEN: Non ancora configurato (opzionale per alert push in tempo reale).")
        return False

    print(f"   Token rilevato: {mask(token)}")
    try:
        me_resp = requests.get(f"https://api.telegram.org/bot{token.strip()}/getMe", timeout=10)
        if not me_resp.ok:
            print(f"❌ TELEGRAM_BOT_TOKEN: Token non valido (HTTP {me_resp.status_code}: {me_resp.text})")
            return False

        bot_info = me_resp.json().get("result", {})
        bot_username = bot_info.get("username", "UnknownBot")
        print(f"✅ TELEGRAM_BOT_TOKEN: VALIDO! Collegato al bot @{bot_username}")

        if not chat_id or not chat_id.strip():
            print("⚠️ TELEGRAM_CHAT_ID: Non ancora impostato. Il bot non sa a quale utente recapitare i messaggi.")
            return False

        print(f"   Chat ID rilevata: {mask(chat_id)}")
        send_resp = requests.post(
            f"https://api.telegram.org/bot{token.strip()}/sendMessage",
            json={
                "chat_id": chat_id.strip(),
                "text": f"🎉 Test Secret GitHub riuscito!\nIl bot @{bot_username} è connesso correttamente a FinanceTool.",
            },
            timeout=10,
        )
        if send_resp.ok:
            print(f"✅ TELEGRAM_CHAT_ID: VALIDO! Notifica di prova inviata con successo sul tuo Telegram.")
            return True
        else:
            print(f"❌ TELEGRAM_CHAT_ID: Impossibile inviare messaggio (HTTP {send_resp.status_code}: {send_resp.text})")
            print("   Assicurati di aver aperto la chat con il bot su Telegram e cliccato su AVVIA (/start)!")
            return False
    except Exception as exc:
        print(f"❌ TELEGRAM: Errore di connessione: {exc}")
        return False


def main() -> int:
    print("=" * 60)
    print("   FINANCETOOL - VERIFICA DIAGNOSTICA DEI SECRET GITHUB")
    print("=" * 60)

    gemini_key = os.getenv("GEMINI_API_KEY")
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    sec_ua = os.getenv("SEC_USER_AGENT")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")

    r1 = test_gemini(gemini_key)
    r2 = test_finnhub(finnhub_key)
    r3 = test_sec_user_agent(sec_ua)
    r4 = test_telegram(tg_token, tg_chat)

    print("\n" + "=" * 60)
    print("RIEPILOGO FINALE:")
    print(f"  • Gemini API:     {'✅ OK' if r1 else '❌ NON FUNZIONANTE'}")
    print(f"  • Finnhub API:    {'✅ OK' if r2 else '❌ NON FUNZIONANTE'}")
    print(f"  • SEC User-Agent: {'✅ OK' if r3 else '⚠️ DA CONTROLLARE'}")
    print(f"  • Telegram Alert: {'✅ OK' if r4 else 'ℹ️ IN ATTESA O NON CONFIGURATO'}")
    print("=" * 60)

    # Esce con 0 se almeno le chiavi core (Gemini e Finnhub) sono OK
    if r1 and r2:
        print("\n🚀 Tutto pronto! I servizi principali sono operativi.")
        return 0
    else:
        print("\n⚠️ Alcune chiavi essenziali non sono ancora configurate o valide.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
