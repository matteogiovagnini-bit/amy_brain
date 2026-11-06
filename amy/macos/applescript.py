"""Integrazione macOS tramite AppleScript, ``open`` e comandi di sola lettura.

Qui non viene mai usata una shell: ogni processo è avviato con una lista di
argomenti. I nomi delle applicazioni sono verificati sul filesystem e le
stringhe AppleScript sono sempre escapate.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.errors import AmyError

APP_DIRECTORIES = [
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
]


class MacOSError(AmyError):
    code = "macos_error"


def escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run_osascript(script: str, *, timeout: float = 10.0) -> str:
    try:
        process = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise MacOSError("osascript non è disponibile su questo sistema.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MacOSError(
            "macOS non ha risposto in tempo.",
            detail="AppleScript interrotto dopo %.0f secondi." % timeout,
        ) from exc
    if process.returncode != 0:
        stderr = process.stderr.strip()
        message = "Operazione macOS non riuscita."
        if "-1743" in stderr or "not authorized" in stderr.lower() or "non autorizzato" in stderr.lower():
            message = (
                "macOS ha negato l'autorizzazione. Apri Impostazioni di Sistema → "
                "Privacy e Sicurezza → Automazione e consenti ad Amy (Terminale o app host) "
                "di controllare l'applicazione richiesta."
            )
        elif "-600" in stderr or "application isn't running" in stderr.lower():
            message = "L'applicazione richiesta non è in esecuzione."
        elif "-1728" in stderr:
            message = "L'applicazione o l'oggetto richiesto non esiste."
        raise MacOSError(message, detail=stderr[:1000])
    return process.stdout.strip()


def list_installed_apps() -> List[Dict[str, str]]:
    apps: Dict[str, Path] = {}
    for directory in APP_DIRECTORIES:
        if not directory.exists():
            continue
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.suffix == ".app" and entry.is_dir():
                apps.setdefault(entry.stem, entry)
    return [{"name": name, "path": str(path)} for name, path in sorted(apps.items(), key=lambda item: item[0].lower())]


def find_application(name: str) -> Optional[Path]:
    query = (name or "").strip()
    if not query:
        return None
    direct = Path(os.path.expanduser(query))
    if direct.suffix == ".app" and direct.exists():
        return direct.resolve()
    lowered = query.lower()
    for app in list_installed_apps():
        if app["name"].lower() == lowered or app["name"].lower() == lowered + ".app":
            return Path(app["path"])
    for app in list_installed_apps():
        if lowered in app["name"].lower():
            return Path(app["path"])
    return None


def open_application(name_or_path: str) -> Dict[str, Any]:
    path = find_application(name_or_path)
    if not path:
        raise MacOSError(
            "Applicazione non trovata: %s" % name_or_path,
            detail="Cerca il nome esatto in /Applications o indica il percorso del bundle .app.",
        )
    try:
        process = subprocess.run(["open", "-a", str(path)], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired as exc:
        raise MacOSError("Apertura dell'applicazione scaduta.") from exc
    if process.returncode != 0:
        raise MacOSError(
            "Non è stato possibile aprire %s." % path.stem,
            detail=process.stderr.strip()[:500],
        )
    return {"name": path.stem, "path": str(path), "opened": True}


def quit_application(name: str) -> Dict[str, Any]:
    path = find_application(name)
    app_name = path.stem if path else name.strip()
    if not app_name:
        raise MacOSError("Nome dell'applicazione mancante.")
    script = 'tell application "%s" to quit' % escape_applescript(app_name)
    run_osascript(script, timeout=15)
    return {"name": app_name, "quit_requested": True}


def application_is_running(name: str) -> bool:
    path = find_application(name)
    app_name = path.stem if path else name.strip()
    if not app_name:
        return False
    output = run_osascript(
        'application "%s" is running' % escape_applescript(app_name),
        timeout=5,
    )
    return output.strip().lower() == "true"


def frontmost_application() -> str:
    script = (
        'tell application "System Events" to get name of first application process '
        "whose frontmost is true"
    )
    return run_osascript(script, timeout=5)


def activate_application(name: str) -> Dict[str, Any]:
    path = find_application(name)
    app_name = path.stem if path else name.strip()
    run_osascript('tell application "%s" to activate' % escape_applescript(app_name), timeout=10)
    return {"name": app_name, "activated": True}


def open_url(url: str) -> Dict[str, Any]:
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise MacOSError("Sono ammessi solo indirizzi http:// o https://.")
    process = subprocess.run(["open", url], capture_output=True, text=True, timeout=15)
    if process.returncode != 0:
        raise MacOSError("Impossibile aprire l'indirizzo nel browser.", detail=process.stderr.strip()[:500])
    return {"url": url, "opened": True}


def open_system_settings(panel: str = "") -> Dict[str, Any]:
    allowed = {
        "privacy": "x-apple.systempreferences:com.apple.preference.security?Privacy",
        "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
        "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
        "sound": "x-apple.systempreferences:com.apple.preference.sound",
        "network": "x-apple.systempreferences:com.apple.Network-Settings.extension",
    }
    key = panel.strip().lower()
    target = allowed.get(key, "x-apple.systempreferences:com.apple.preference.security?Privacy")
    process = subprocess.run(["open", target], capture_output=True, text=True, timeout=15)
    if process.returncode != 0:
        raise MacOSError("Impossibile aprire Impostazioni di Sistema.")
    return {"panel": key or "privacy", "opened": True}


def _run_readonly(command: List[str], *, timeout: float = 5.0) -> str:
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MacOSError("Comando di sistema non disponibile.", detail=str(exc)) from exc
    return process.stdout.strip()


_BATTERY_LINE = re.compile(
    r"(?P<percent>\d{1,3})%;\s*(?P<state>[a-zA-Z][a-zA-Z ]*?)"
    r"(?:;\s*(?P<remaining>[0-9]{1,2}:[0-9]{2})\s*remaining)?"
    r"\s*present:\s*(?P<present>true|false)",
    re.IGNORECASE,
)

_POWER_SOURCE = re.compile(r"drawing from '(?P<source>[^']+)'", re.IGNORECASE)

_BATTERY_STATES = {
    "discharging": "in scarica",
    "charging": "in carica",
    "charged": "carica",
    "finishing charge": "in carica, quasi piena",
    "ac attached": "collegata alla rete",
}


def parse_battery_output(text: str) -> Dict[str, Any]:
    """Converte l'output di ``pmset -g batt`` in dati verificabili.

    Non inventa valori: se la riga della batteria non c'è il dizionario
    riporta ``presente: False`` e campi vuoti.
    """
    source_match = _POWER_SOURCE.search(text or "")
    source = ""
    if source_match:
        raw_source = source_match.group("source").strip().lower()
        source = "rete" if "ac power" in raw_source else "batteria"

    line_match = _BATTERY_LINE.search(text or "")
    if not line_match:
        return {
            "presente": False,
            "percentuale": None,
            "stato": None,
            "tempo_rimanente": None,
            "alimentazione": source or None,
        }

    raw_state = line_match.group("state").strip().lower()
    return {
        "presente": line_match.group("present").strip().lower() == "true",
        "percentuale": int(line_match.group("percent")),
        "stato": _BATTERY_STATES.get(raw_state, raw_state or None),
        "tempo_rimanente": line_match.group("remaining"),
        "alimentazione": source or None,
    }


def battery_status() -> Dict[str, Any]:
    """Stato della batteria del Mac, letto con ``pmset`` (sola lettura)."""
    output = _run_readonly(["pmset", "-g", "batt"], timeout=5)
    return parse_battery_output(output)


def battery_summary(data: Dict[str, Any]) -> str:
    """Riassunto in italiano dello stato della batteria."""
    if not data.get("presente"):
        if data.get("alimentazione") == "rete":
            return "Nessuna batteria integrata rilevata su questo Mac: è collegato alla rete."
        return "Nessuna batteria rilevata su questo Mac."
    parts = ["Batteria del Mac al %d%%" % int(data.get("percentuale") or 0)]
    if data.get("stato"):
        parts.append(str(data["stato"]))
    remaining = data.get("tempo_rimanente")
    if remaining and remaining != "0:00":
        parts.append("%s rimanenti" % remaining)
    return ", ".join(parts) + "."


def memory_usage() -> Dict[str, Any]:
    """RAM libera e usata da ``vm_stat``, senza dipendenze esterne."""
    try:
        output = _run_readonly(["vm_stat"], timeout=5)
    except MacOSError:
        return {}
    page_size = 4096
    match = re.search(r"page size of (\d+) bytes", output)
    if match:
        page_size = int(match.group(1))
    pages: Dict[str, int] = {}
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        try:
            pages[key.strip()] = int(value.strip().rstrip("."))
        except ValueError:
            continue
    free_pages = sum(
        pages.get(name, 0) for name in ("Pages free", "Pages inactive", "Pages speculative")
    )
    used_pages = sum(
        pages.get(name, 0)
        for name in ("Pages active", "Pages wired down", "Pages occupied by compressor")
    )
    total_pages = free_pages + used_pages
    if total_pages <= 0:
        return {}
    return {
        "ram_totale_gb": round(total_pages * page_size / (1024 ** 3), 1),
        "ram_liberi_gb": round(free_pages * page_size / (1024 ** 3), 1),
        "ram_usati_gb": round(used_pages * page_size / (1024 ** 3), 1),
        "ram_percent": round(used_pages * 100.0 / total_pages, 1),
    }


def system_info() -> Dict[str, Any]:
    mem_bytes = 0
    try:
        mem_bytes = int(_run_readonly(["sysctl", "-n", "hw.memsize"]) or 0)
    except (ValueError, MacOSError):
        mem_bytes = 0
    disk = shutil.disk_usage(str(Path.home()))
    memory = memory_usage()
    try:
        load = [round(value, 2) for value in os.getloadavg()]
    except OSError:
        load = [None, None, None]
    return {
        "macos": platform.mac_ver()[0],
        "architettura": platform.machine(),
        "python": platform.python_version(),
        "hostname": platform.node(),
        "utente": os.environ.get("USER", ""),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "carico_1m": load[0],
        "carico_5m": load[1],
        "carico_15m": load[2],
        "ram_gb": round(mem_bytes / (1024 ** 3), 1) if mem_bytes else None,
        "ram_liberi_gb": memory.get("ram_liberi_gb"),
        "ram_usati_gb": memory.get("ram_usati_gb"),
        "ram_percent": memory.get("ram_percent"),
        "disco_libero_gb": round(disk.free / (1024 ** 3), 1),
        "disco_totale_gb": round(disk.total / (1024 ** 3), 1),
    }


def top_processes(limit: int = 10, *, sort_by: str = "cpu") -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 30))
    # Su macOS `ps` ordina con -r (CPU) e -m (memoria); `-pcpu` viene letto
    # come un PID e il comando fallisce.
    sort_flag = "-r" if sort_by == "cpu" else "-m"
    output = _run_readonly(["ps", "-axo", "pid=,pcpu=,pmem=,comm=", sort_flag], timeout=5)
    rows: List[Dict[str, Any]] = []
    for line in output.splitlines()[:limit]:
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            # Con locale italiano `ps` usa la virgola come separatore decimale.
            cpu = float(parts[1].replace(",", "."))
            mem = float(parts[2].replace(",", "."))
            rows.append(
                {
                    "pid": int(parts[0]),
                    "cpu_percent": cpu,
                    "mem_percent": mem,
                    "command": parts[3],
                }
            )
        except ValueError:
            continue
    return rows
