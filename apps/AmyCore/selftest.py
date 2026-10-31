#!/usr/bin/env python3
"""Esegue il self-test dell'app nativa Amy Core.

Avvia `AmyCore --selftest`, che:
1. avvia il backend Python locale;
2. carica la dashboard nella WebView;
3. invia un messaggio reale dal DOM e attende la risposta in chat;
4. esce con codice 0 se tutto funziona, 1 altrimenti.

Usa solo la libreria standard. Non modifica nulla fuori da `~/.amy`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "apps" / "AmyCore" / "dist" / "Amy Core.app" / "Contents" / "MacOS" / "AmyCore"
TIMEOUT_S = 120


def main() -> int:
    if not BINARY.is_file():
        print("Applicazione non compilata. Esegui prima: ./apps/AmyCore/build.sh")
        return 2

    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")

    print("Avvio self-test: %s" % BINARY)
    try:
        completed = subprocess.run(
            [str(BINARY), "--selftest"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        print("TIMEOUT: l'app non ha concluso il self-test entro %d secondi." % TIMEOUT_S)
        return 1

    output = (completed.stdout or "") + (completed.stderr or "")
    for line in output.splitlines():
        print(line)
    print("Codice di uscita: %d" % completed.returncode)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
