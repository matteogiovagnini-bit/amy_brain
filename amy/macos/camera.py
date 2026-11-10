"""Cattura di un fotogramma dalla telecamera, con AVFoundation.

L'helper Swift viene compilato una volta in ``~/.amy/bin/amy-camera``. La
telecamera è opzionale e spenta per default nella configurazione; il primo uso
richiede il permesso **Telecamera** in Impostazioni di Sistema.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from ..core.errors import AmyError


class CameraError(AmyError):
    code = "camera_error"


def _source() -> Path:
    return Path(__file__).resolve().parents[2] / "apps" / "AmyCore" / "Tools" / "camera.swift"


def _app_binary() -> Optional[Path]:
    """Binario dell'app Amy Core: ha il permesso TCC della fotocamera."""
    candidates = [
        Path.home() / "Applications" / "Amy Core.app" / "Contents" / "MacOS" / "AmyCore",
        Path(__file__).resolve().parents[2] / "apps" / "AmyCore" / "dist" / "Amy Core.app" / "Contents" / "MacOS" / "AmyCore",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _binary() -> Path:
    source = _source()
    if not source.is_file():
        raise CameraError("Helper della telecamera non trovato.", detail=str(source))
    binary = Path.home() / ".amy" / "bin" / "amy-camera"
    try:
        if binary.is_file() and binary.stat().st_mtime >= source.stat().st_mtime:
            return binary
    except OSError:
        pass
    compiler = shutil.which("swiftc")
    if not compiler:
        raise CameraError("swiftc non è disponibile: serve Xcode Command Line Tools.")
    binary.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.run(
            [compiler, "-O", "-o", str(binary), str(source)],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CameraError("Compilazione dell'helper telecamera non riuscita.", detail=str(exc)) from exc
    if process.returncode != 0 or not binary.is_file():
        raise CameraError(
            "Compilazione dell'helper telecamera non riuscita.",
            detail=(process.stderr or "")[-800:],
        )
    return binary


_capture_lock = threading.Lock()


def _capture_via_app(app: Path, target: Path) -> Path:
    """Chiede il fotogramma all'app già in esecuzione, che possiede il TCC."""
    home = Path.home() / ".amy"
    request = home / "camera_request.json"
    error = target.with_suffix(target.suffix + ".error")
    home.mkdir(parents=True, exist_ok=True)
    for stale in (request, error):
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass
    payload = {
        "id": uuid.uuid4().hex,
        "path": str(target),
        "error": str(error),
        "created": time.time(),
    }
    tmp = request.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(request)
    deadline = time.monotonic() + 60.0
    try:
        while time.monotonic() < deadline:
            if target.is_file() and target.stat().st_size >= 1000:
                return target
            if error.is_file():
                detail = error.read_text(encoding="utf-8", errors="replace").strip()
                raise CameraError(
                    "Cattura dalla telecamera non riuscita.",
                    detail=detail or "L'app Amy Core non ha completato la cattura.",
                )
            if not request.exists():
                # Il watcher ha preso la richiesta: attendi l'esito.
                pass
            time.sleep(0.1)
        raise CameraError(
            "Amy Core non ha risposto alla richiesta della telecamera.",
            detail="Verifica che l'app sia aperta e che il permesso Fotocamera sia attivo.",
        )
    finally:
        for stale in (request, error):
            try:
                stale.unlink(missing_ok=True)
            except OSError:
                pass


def capture_camera(path: Optional[Path] = None) -> Path:
    """Cattura un fotogramma e restituisce il percorso JPEG."""
    app = _app_binary()
    binary = app if app is not None else _binary()
    target = Path(path) if path else (
        Path.home() / "Downloads" / "Amy" / "camera" / time.strftime("camera-%Y%m%d-%H%M%S.jpg")
    )
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if app is not None:
        with _capture_lock:
            return _capture_via_app(app, target)
    command = [str(binary), str(target)]
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CameraError("Cattura dalla telecamera non riuscita.", detail=str(exc)) from exc
    if process.returncode != 0:
        raise CameraError(
            "Cattura dalla telecamera non riuscita.",
            detail=(process.stderr or "")[-500:],
        )
    if not target.is_file() or target.stat().st_size < 1000:
        raise CameraError(
            "La cattura dalla telecamera è vuota.",
            detail="Controlla il permesso Telecamera in Impostazioni di Sistema.",
        )
    return target
