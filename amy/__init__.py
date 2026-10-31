"""Amy — assistente personale per macOS e ponte sicuro verso il robot.

Il pacchetto è organizzato per responsabilità:

- ``core``     orchestrazione, configurazione, logging, ciclo conversazionale
- ``ai``       provider linguistici intercambiabili
- ``memory``   memoria persistente SQLite (conversazioni, fatti, attività)
- ``security`` policy di autorizzazione, conferme e audit
- ``tools``    strumenti reali eseguibili da Amy
- ``macos``    integrazione con macOS (AppleScript, applicazioni)
- ``robot``    protocollo v1, simulatore e link MQTT
- ``voice``    sintesi, riconoscimento e wake word
- ``ui``       dashboard web locale

Tutti i messaggi rivolti all'utente sono in italiano.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
