"""Riavvio programmato dell'app nativa Amy Core.

Il backend non può riavviarsi da solo: se termina, termina anche il processo che
dovrebbe riaprirlo. Per questo viene lanciato un piccolo helper **staccato**
(`start_new_session=True`) che aspetta, chiude la vecchia app, la riapre e
verifica `/api/health`.

Lo script è fisso: non accetta comandi arbitrari, solo il percorso del bundle,
il PID e il ritardo.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import AmyError

HELPER = r'''
import os, subprocess, sys, time, urllib.request

app_path, parent_pid, delay = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
log_path = os.path.expanduser("~/.amy/restart.log")

def write(message):
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except OSError:
        pass

time.sleep(max(0.0, delay))
write("riavvio richiesto per %s" % app_path)
try:
    os.kill(parent_pid, 15)
    write("inviato SIGTERM a %d" % parent_pid)
except OSError:
    write("processo %d già terminato" % parent_pid)

# Attende che la vecchia app esca davvero prima di riaprirla.
for _ in range(60):
    try:
        os.kill(parent_pid, 0)
    except OSError:
        break
    time.sleep(0.25)
else:
    write("la vecchia app non è terminata: proseguo comunque")

try:
    subprocess.run(["open", "-a", app_path], check=False)
    write("riaperta %s" % app_path)
except Exception as exc:
    write("apertura fallita: %s" % exc)

# Verifica che il backend risponda, senza dichiarare un successo non verificato.
for port in range(8765, 8776):
    for _ in range(20):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=1) as response:
                if response.status == 200:
                    write("health OK sulla porta %d" % port)
                    sys.exit(0)
        except Exception:
            pass
        time.sleep(0.5)
write("health non disponibile dopo il riavvio")
'''


class RestartError(AmyError):
    code = "restart_error"


def app_bundle() -> Optional[str]:
    """Percorso del bundle dell'app nativa, se il backend è stato avviato da lei."""
    value = os.environ.get("AMY_APP_BUNDLE", "").strip()
    if value and Path(value).exists():
        return value
    return None


def parent_pid() -> Optional[int]:
    value = os.environ.get("AMY_PARENT_PID", "").strip()
    return int(value) if value.isdigit() else None


def schedule_restart(delay_s: float = 10.0) -> Dict[str, Any]:
    """Programma il riavvio dell'app nativa e restituisce l'esito della pianificazione."""
    bundle = app_bundle()
    pid = parent_pid()
    if not bundle:
        raise RestartError(
            "Il riavvio programmato è disponibile solo nell'app nativa Amy Core.",
            detail="Avvia Amy da ~/Applications/Amy Core.app e riprova.",
        )
    if not pid:
        raise RestartError(
            "Non conosco il processo dell'app da riavviare.",
            detail="AMY_PARENT_PID non è impostato.",
        )
    delay = max(1.0, min(float(delay_s), 60.0))
    try:
        subprocess.Popen(
            [sys.executable, "-c", HELPER, bundle, str(pid), str(delay)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        raise RestartError("Impossibile programmare il riavvio.", detail=str(exc)) from exc
    return {
        "scheduled": True,
        "delay_s": delay,
        "app": bundle,
        "pid": pid,
        "log": "~/.amy/restart.log",
    }
