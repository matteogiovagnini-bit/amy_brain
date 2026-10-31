# OpenCode.md — promemoria operativo

Le istruzioni complete del repository sono in [AGENTS.md](AGENTS.md). In caso di
differenza, prevale `AGENTS.md`. Questo file esiste solo per rendere visibile anche
agli agenti OpenCode il vincolo economico già approvato.

## Vincolo obbligatorio e permanente: solo strumenti gratuiti

Ogni nuova implementazione, in ogni fase futura, deve usare esclusivamente strumenti,
librerie, modelli IA, API e servizi utilizzabili gratuitamente, senza costi
obbligatori presenti o futuri.

Vale per:

- nucleo conversazionale e orchestrazione;
- modelli IA, con preferenza per Ollama e l'esecuzione locale;
- voce, sintesi, riconoscimento e wake word;
- controllo del Mac e automazioni;
- CLI, dashboard e futura interfaccia grafica;
- robot Raspberry Pi, protocollo e comunicazione;
- test, sviluppo, packaging e distribuzione.

Non sono ammessi come requisiti: abbonamenti, API con fatturazione obbligatoria,
crediti acquistabili, piani premium, licenze commerciali a pagamento o funzionalità
bloccate dietro un pagamento.

Prima di integrare un componente: verifica licenza e condizioni economiche, preferisci
open source e locale, documenta limiti e alternative, mantieni un fallback gratuito.
Se non esiste un'alternativa gratuita adeguata, fermati e chiedi all'utente.

Riferimenti: [docs/GRATUITO.md](docs/GRATUITO.md) e
[docs/DECISIONI.md](docs/DECISIONI.md) (D-018).
