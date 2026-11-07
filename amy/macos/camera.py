"""Cattura di un fotogramma dalla telecamera, con AVFoundation.

L'helper Swift viene compilato una volta in ``~/.amy/bin/amy-camera``. La
telecamera è opzionale e spenta per default nella configurazione; il primo uso
richiede il permesso **Telecamera** in Impostazioni di Sistema.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from ..core.errors import AmyError


class CameraError(AmyError):
    code = "camera_error"


def _source() -> Path:
    return Path(__file__).resolve().parents[2] / "apps" / "AmyCore" / "Tools" / "camera.swift"


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


def capture_camera(path: Optional[Path] = None) -> Path:
    """Cattura un fotogramma e restituisce il percorso JPEG."""
    binary = _binary()
    target = Path(path) if path else (
        Path.home() / "Downloads" / "Amy" / "camera" / time.strftime("camera-%Y%m%d-%H%M%S.jpg")
    )
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.run(
            [str(binary), str(target)],
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
