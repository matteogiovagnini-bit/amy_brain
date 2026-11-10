# Stato corrente di Amy

Sintesi operativa al **10 novembre 2026**. La fonte completa resta
[`../STATO_PROGETTO.md`](../STATO_PROGETTO.md); questo file serve come punto di
ingresso rapido per agenti e collaboratori.

## Architettura

- **Amy Core**: orchestrazione, provider IA, memoria, policy A/B/C, audit, voce,
  dashboard locale e app macOS nativa.
- **Nove moduli**: Voice, Mac Control, Personal, Memory, Developer, Vision,
  Smart Home, Robot, Telegram.
- **Adapter-first**: il codice esistente è avvolto da `amy/modules/`, senza
  duplicazioni e senza riscrivere i tool.
- **Autorizzazioni**: `AuthorizationBroker` controlla modulo, capacità e revoca
  prima della policy. Il livello C non è mai automatico.

## Verificato

- **483 test** superati; **80 strumenti** registrati.
- App macOS «Amy Core» compilata, installata in `~/Applications` e verificata con
  self-test end-to-end.
- Voce locale completa (`sounddevice`, `faster-whisper`, `say`, wake word «Amy»)
  verificata con parlato reale; eco half-duplex verificata dal vivo.
- Memoria SQLite con `memory_items`, task e note; migrazione da `facts` con backup.
- Personal Manager: calendario, promemoria, mail, task, note e agenda unica.
  `calendar.update` verificato dal vivo.
- Vision: OCR locale; `vision.capture` verificato con un JPEG 1280×720 e
  permesso Fotocamera concesso dall'utente.
- Developer Assistant nativo: `dev.status`, `dev.diff`, `dev.analyze`,
  `dev.test`; suite reale eseguita sul repository.
- Dashboard: moduli, permessi, memoria, provider, attività/note, progetto e log
  locali redatti. `project.js` è il primo modulo locale estratto da `app.js`.
- Telegram: modulo opzionale con chat, note vocali trascritte in locale, sessioni,
  conferme a pulsanti, invio automatico delle foto e `telegram.send_last_photo`
  su richiesta. Bot collegato come `@AmyCoreAssistantBot`.
- Nucleo con neuroni fluttuanti su canvas (`neurons.js`) e HUD radiale con archi,
  tacche e dati reali. Neuroni a 12 fps in attesa e 24 fps durante l'interazione;
  archi CSS in pausa in attesa/offline e tutto fermo in finestra non attiva.

## Non verificato o parziale

- Robot fisico, broker MQTT reale e uso prolungato.
- Smart Home con dispositivi reali: solo configurazione e mock.
- `vision.describe`: non implementato.
- Qualità della wake word con parlanti diversi e con altoparlanti.
- Split di `app.js`: solo il pannello Progetto è stato estratto.
- Telegram con un messaggio in arrivo reale: il bot è collegato, ma non è stato
  possibile simulare il messaggio dell’utente dagli strumenti.
- Chiamate vocali Telegram: non supportate dalla Bot API.

## Vincoli permanenti

- Solo risorse gratuite o open source; nessun servizio a pagamento obbligatorio.
- Nessun GPIO/PWM o comando diretto ai servi.
- Nessuna shell arbitraria.
- Segreti mai in codice, log, prompt, memoria o dashboard.
- Dashboard locale su `127.0.0.1`, salvo consenso esplicito.
