# Roadmap

La roadmap descrive intenzioni, non promesse. Ogni voce diventa "fatta" solo dopo
test e verifica reale. Lo stato aggiornato è in [STATO_PROGETTO.md](STATO_PROGETTO.md).

Tutte le fasi, comprese quelle future, sono soggette al vincolo permanente descritto
in [GRATUITO.md](GRATUITO.md): nessuna funzionalità può richiedere abbonamenti, API a
fatturazione, crediti o piani premium. Una voce che non abbia un'alternativa gratuita
concretamente utilizzabile non entra in roadmap come requisito.

## Fase 0 — Fondamenta (completata)

- Configurazione locale e segreti.
- Logging con redazione.
- Memoria SQLite.
- Errori applicativi con codici stabili.
- Test suite di base.

## Fase 1 — Cervello testuale (completata)

- Provider Ollama, compatibile OpenAI e offline.
- Fallback locale.
- Protocollo d'azione JSON.
- Orchestrazione con limite passaggi.
- Prompt italiano con regole di non invenzione.

## Fase 2 — Sicurezza e strumenti (completata)

- Livelli A/B/C e conferme in due fasi.
- Path guard, deny-list, backup e cestino.
- Shell a enum chiuso.
- Web con protezione SSRF.
- Audit append-only.
- 38 strumenti macOS, file, web, memoria, voce e robot.

## Fase 3 — Interfaccia (completata per uso locale)

- Applicazione macOS nativa «Amy Core» (Swift + AppKit + WebKit): finestra,
  Dock, menu, schermo intero, icona generata localmente.
- CLI interattiva e non.
- Dashboard «Amy Core» con tre aree: chat, nucleo centrale e pannello dati.
- Nucleo a otto stati derivati solo da segnali reali del backend.
- Chat con cronologia, invio da tastiera, nuova sessione, conferme in due fasi.
- Pannello con motore IA, sistema locale, voce, robot, memoria, attività e strumenti.
- Schermo intero, layout responsivo, focus visibile, movimento ridotto.
- Comandi E-stop/stop dalla dashboard.
- Protezioni statiche: CSP, nessun CDN, nessun `innerHTML`, nessuno stile inline.
- Bind locale obbligatorio salvo consenso esplicito.
- Heartbeat: il backend non resta orfano se l'app viene chiusa o uccisa.
- Verifica manuale a mano nella finestra ancora da completare: aspetto dei
  pannelli, ridimensionamento, schermo intero, navigazione da tastiera.

## Fase 4 — Robot simulato (completata)

- Protocollo v1 e validazione envelope.
- Simulatore con limiti, ACK/NACK, deduplicazione, sequenza, watchdog, E-stop.
- Modalità TEST e rifiuto di READY senza calibrazione.
- Strumenti robotici con livello di rischio corretto.

## Fase 5 — Voce (parziale)

Fatto:

- TTS macOS con voce italiana.
- Interruzione della sintesi.
- Adattatori STT opzionali.
- Registratore configurabile.
- Rilevamento testuale della wake word.
- Stato vocale esposto in CLI e dashboard.

Da fare per considerarla completa:

- installazione e verifica di `ffmpeg`/`sox`;
- installazione e verifica di un motore STT locale;
- prova con microfono reale e rumore ambiente;
- misura della latenza e della qualità italiana;
- wake word audio dedicata, se necessaria;
- test di interruzione durante una risposta lunga.

## Fase 6 — Robot reale (da fare)

- Collegamento a un broker MQTT di laboratorio.
- Verifica del dispatcher sul Raspberry Pi.
- Test di ACK/NACK con nodi reali.
- Verifica del watchdog con heartbeat reale.
- Calibrazione meccanica e limiti reali.
- Prova di E-stop fisico e software.
- Registrazione dei risultati in `docs/TEST.md` e nel repository `../amy/`.

Nessuna di queste voci è stata eseguita.

## Fase 7 — Affidabilità e continuità (da fare)

- Test end-to-end ripetibili.
- Rotazione e pulizia della memoria.
- Esportazione/importazione completa.
- Servizio di avvio e recupero dopo crash.
- Metriche di latenza ed errori.
- Verifica di sicurezza della dashboard se si aggiunge autenticazione.
- Packaging e installer.

## Priorità consigliate

1. Completare la voce con STT e microfono reali.
2. Verificare il link MQTT su hardware di laboratorio.
3. Verificare la catena di sicurezza con E-stop fisico.
4. Solo dopo, valutare accesso remoto e automazioni più ambiziose.

## Criterio per dichiarare una fase completata

Una fase è completata solo se:

- il codice è implementato;
- i test automatici passano;
- esiste una verifica reale della funzione, se la funzione dipende da hardware o
  servizi esterni;
- la documentazione distingue ciò che è verificato da ciò che non lo è.
