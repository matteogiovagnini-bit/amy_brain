"""Provider locale deterministico (modalità offline).

Non è un modello linguistico: è un interprete di comandi italiani frequenti.
Serve a mantenere Amy utilizzabile quando Ollama o la rete non sono disponibili,
senza simulare capacità che non ha.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .base import AIProvider

HELP_TEXT = (
    "In modalità offline capisco comandi semplici in italiano. Per esempio:\n"
    "• «che ore sono?»\n"
    "• «stato del sistema» oppure «mostrami i processi»\n"
    "• «quanto è carica la batteria del Mac?»\n"
    "• «apri Safari», «chiudi Note», «porta in primo piano Terminale»\n"
    "• «cerca documentazione ESP32-S3» oppure «apri https://…»\n"
    "• «leggi ~/Progetti/…/README.md», «elenca ~/Progetti»\n"
    "• «ricorda che il progetto si chiama Amy», «cosa ricordi?»\n"
    "• «stato del robot», «ferma il robot», «emergenza»\n\n"
    "Le richieste articolate e il movimento dei giunti richiedono il motore IA "
    "completo: avvia Ollama e seleziona un modello in configurazione."
)

_ACTION = "action"
_SAY = "say"


def _clean_target(value: str) -> str:
    value = value.strip().strip("«»\"'").strip()
    value = re.sub(r"\s+(per favore|grazie|adesso|ora)$", "", value, flags=re.I).strip()
    return value


def _action_payload(tool: str, args: Dict[str, Any], say: str = "") -> str:
    return json.dumps({_SAY: say, _ACTION: {"tool": tool, "args": args}}, ensure_ascii=False)


class OfflineProvider(AIProvider):
    name = "offline"
    model = "regole-locali"

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "available": True,
            "note": "Interprete locale di comandi frequenti; nessun modello linguistico.",
        }

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        if not messages:
            return HELP_TEXT
        last = messages[-1]
        content = str(last.get("content", ""))

        if last.get("role") == "user" and content.startswith("RISULTATO STRUMENTO"):
            return self._summarize(content)
        if last.get("role") != "user":
            return "Non ho altro da aggiungere."

        text = content.strip()
        lowered = text.lower()
        if not text:
            return "Non ho ricevuto alcun testo."

        # Comandi di informazione.
        if re.search(r"\b(che ore sono|che ora e|che ora è|ora attuale|che giorno e)\b", lowered):
            return _action_payload("time.now", {}, "Controllo l'orologio.")
        if re.search(r"\b(stato del sistema|informazioni sul mac|info sistema|come stai)\b", lowered):
            return _action_payload("system.info", {}, "Leggo lo stato del Mac.")
        if re.search(r"\b(processi|usa piu memoria|usa più memoria|usa piu cpu|usa più cpu)\b", lowered):
            sort_by = "memory" if "memoria" in lowered else "cpu"
            return _action_payload("system.processes", {"limit": 10, "sort_by": sort_by}, "Controllo i processi.")
        if re.search(r"\b(impostazioni|permessi)\b", lowered):
            panel = "microphone" if "microfono" in lowered else "privacy"
            return _action_payload("system.settings", {"panel": panel}, "Apro le impostazioni pertinenti.")
        if re.search(r"\b(batteria|carica)\b", lowered) and re.search(
            r"\b(mac|macbook|portatile|computer|notebook)\b", lowered
        ):
            return _action_payload("system.battery", {}, "Controllo la batteria del Mac.")

        # Applicazioni.
        match = re.search(r"^(?:amy[, ]+)?(?:apri|avvia|lancia)\s+(?:l'app(?:licazione)?\s+|il programma\s+)?(.+)$", text, re.I)
        if match:
            target = _clean_target(match.group(1))
            if target.lower() in {"browser", "il browser"}:
                target = "Safari"
            if re.match(r"^(https?://|www\.)|\.[a-z]{2,}(/|$)", target, re.I):
                url = target if target.lower().startswith("http") else "https://" + target
                return _action_payload("web.open", {"url": url}, "Apro %s." % url)
            if target.lower().startswith("il sito "):
                target = target[8:].strip()
                url = target if target.lower().startswith("http") else "https://" + target
                return _action_payload("web.open", {"url": url}, "Apro il sito.")
            return _action_payload("apps.open", {"name": target}, "Apro %s." % target)

        match = re.search(r"^(?:amy[, ]+)?(?:chiudi|termina)\s+(?:l'app(?:licazione)?\s+)?(.+)$", text, re.I)
        if match:
            target = _clean_target(match.group(1))
            return _action_payload("apps.quit", {"name": target}, "Chiedo a %s di chiudersi." % target)

        match = re.search(r"^(?:amy[, ]+)?(?:porta in primo piano|vai su|passa a)\s+(.+)$", text, re.I)
        if match:
            target = _clean_target(match.group(1))
            return _action_payload("apps.focus", {"name": target}, "Porto %s in primo piano." % target)

        # File (prima del web: «cerca il file X» non è una ricerca web).
        match = re.search(r"^(?:amy[, ]+)?(?:leggi(?: il file)?)\s+(.+)$", text, re.I)
        if match:
            target = _clean_target(match.group(1))
            if target.startswith(("/", "~", ".")):
                return _action_payload("files.read", {"path": target}, "Leggo il file.")
        match = re.search(r"^(?:amy[, ]+)?(?:elenca|mostra(?: il contenuto di)?)\s+(?:la cartella\s+|i file in\s+)?(.+)$", text, re.I)
        if match:
            target = _clean_target(match.group(1))
            if target.startswith(("/", "~", ".")):
                return _action_payload("files.list", {"path": target}, "Elenca il contenuto.")
        match = re.search(r"^(?:amy[, ]+)?cerca\s+(?:il file|i file|un file|file)\s+(.+)$", text, re.I)
        if match:
            query = _clean_target(match.group(1))
            return _action_payload("files.search", {"query": query}, "Cerco file con quel nome.")

        # Web.
        match = re.search(
            r"^(?:amy[, ]+)?(?:cerca(?: sul web)?|cerca su internet)\s+"
            r"(?!il file\b|i file\b|un file\b|file\b)(.+)$",
            text,
            re.I,
        )
        if match:
            query = _clean_target(match.group(1))
            return _action_payload("web.search", {"query": query}, "Cerco «%s»." % query)
        match = re.search(r"^(?:amy[, ]+)?(?:leggi la pagina|leggi il sito|leggi)\s+(https?://\S+)$", text, re.I)
        if match:
            return _action_payload("web.fetch", {"url": match.group(1)}, "Leggo la pagina.")

        # Memoria.
        match = re.search(r"^(?:amy[, ]+)?ricorda(?: che)?\s+(.+?)\s+(?:è|e'|sono)\s+(.+)$", text, re.I)
        if match:
            key = _clean_target(match.group(1))
            value = _clean_target(match.group(2))
            return _action_payload("memory.remember", {"key": key, "value": value}, "Lo memorizzo.")
        match = re.search(r"^(?:amy[, ]+)?ricorda\s+([^:]+):\s*(.+)$", text, re.I)
        if match:
            return _action_payload(
                "memory.remember",
                {"key": _clean_target(match.group(1)), "value": _clean_target(match.group(2))},
                "Lo memorizzo.",
            )
        match = re.search(r"^(?:amy[, ]+)?(?:dimentica|elimina dalla memoria)\s+(.+)$", text, re.I)
        if match:
            return _action_payload("memory.forget", {"key": _clean_target(match.group(1))}, "Lo rimuovo dalla memoria.")
        if re.search(r"\b(cosa ricordi|memoria|preferenze salvate)\b", lowered):
            return _action_payload("memory.list", {"limit": 50}, "Controllo la memoria.")

        # Robot.
        if re.search(r"\b(emergenza|e-stop|estop|fermati subito|ferma tutto)\b", lowered):
            return _action_payload("robot.estop", {"reason": "comando vocale/testuale di emergenza"}, "Attivo subito l'E-stop software.")
        if re.search(r"\b(ferma il robot|stop robot|ferma il movimento|arresta il robot)\b", lowered):
            return _action_payload("robot.stop", {"reason": "richiesta utente"}, "Fermo il robot.")
        if re.search(r"\b(stato del robot|robot connesso|batteria|stato robot|come sta il robot)\b", lowered):
            return _action_payload("robot.status", {}, "Controllo il robot.")
        if re.search(r"\b(robot in test|modalita test|modalità test|test robot)\b", lowered):
            return _action_payload("robot.mode", {"mode": "test"}, "Porto il robot in modalità test, senza movimento fisico.")

        # Conversazione.
        if re.search(r"\b(aiuto|cosa sai fare|comandi|help)\b", lowered):
            return HELP_TEXT
        if re.search(r"^(ciao|salve|buongiorno|buonasera|ehi amy)\b", lowered):
            return "Ciao. Sono Amy, in modalità offline. Posso aprire applicazioni, leggere file, controllare il Mac e lo stato del robot. Chiedimi «aiuto» per l'elenco dei comandi."
        if re.search(r"^(grazie|perfetto|ok)\b", lowered):
            return "Prego."

        return (
            "In modalità offline non ho capito una richiesta abbastanza specifica. "
            "Posso eseguire comandi semplici su applicazioni, file, web, memoria e robot. "
            "Scrivi «aiuto» per gli esempi, oppure avvia Ollama per il dialogo completo."
        )

    def _summarize(self, content: str) -> str:
        payload_text = content.split(":", 1)[1].strip() if ":" in content else content
        try:
            data = json.loads(payload_text)
        except json.JSONDecodeError:
            return "Lo strumento ha restituito un risultato non leggibile."
        if not data.get("ok"):
            return "Non ho potuto completare l'operazione: %s" % data.get("message", "errore sconosciuto")
        result = data.get("data") or {}
        tool = data.get("tool", "")
        message = data.get("message") or "Operazione completata."
        if tool == "system.info" and isinstance(result, dict):
            return (
                "Mac: macOS %s, %s, %s CPU, RAM %s GB, disco libero %s GB."
                % (
                    result.get("macos", "?"),
                    result.get("architettura", "?"),
                    result.get("cpu_count", "?"),
                    result.get("ram_gb", "?"),
                    result.get("disco_libero_gb", "?"),
                )
            )
        if tool == "system.battery" and isinstance(result, dict):
            if not result.get("presente"):
                return "Nessuna batteria integrata rilevata su questo Mac: è collegato alla rete."
            parts = ["Batteria del Mac al %s%%" % result.get("percentuale", "?")]
            if result.get("stato"):
                parts.append(str(result["stato"]))
            remaining = result.get("tempo_rimanente")
            if remaining and remaining != "0:00":
                parts.append("%s rimanenti" % remaining)
            return ", ".join(parts) + "."
        if tool == "robot.status" and isinstance(result, dict):
            joints = result.get("joints") or []
            return (
                "Robot: modalità %s, batteria %s%%, E-stop %s, calibrazione %s. %s"
                % (
                    result.get("mode", "?"),
                    result.get("battery_pct", "?"),
                    "attivo" if result.get("estop_latched") else "non attivo",
                    "eseguita" if result.get("calibrated") else "non eseguita",
                    "Movimento simulato." if result.get("simulated") else "",
                )
            )
        if tool == "files.read" and isinstance(result, dict):
            text = str(result.get("content", ""))
            return text[:1500] + ("…" if len(text) > 1500 else "")
        if tool == "memory.list" and isinstance(result, dict):
            facts = result.get("fatti") or []
            if not facts:
                return "La memoria è vuota."
            return "Ricordo: " + "; ".join("%s = %s" % (f.get("key"), f.get("value")) for f in facts[:20])
        return message
