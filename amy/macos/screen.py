"""Screenshot e OCR locale con i framework di macOS.

La cattura usa ``screencapture``; il testo viene estratto con Vision tramite un
piccolo helper Swift compilato in locale. Nessuna immagine lascia il Mac: solo il
testo può essere inviato al provider IA configurato, se l'utente lo chiede.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.errors import AmyError

SCREENCAPTURE = "/usr/sbin/screencapture"


class ScreenError(AmyError):
    code = "screen_error"


def _ocr_source() -> Path:
    return Path(__file__).resolve().parents[2] / "apps" / "AmyCore" / "Tools" / "ocr.swift"


def _ocr_binary() -> Path:
    """Compila l'helper OCR una volta e lo riusa finché il sorgente non cambia."""
    source = _ocr_source()
    if not source.is_file():
        raise ScreenError("Helper OCR non trovato.", detail=str(source))
    binary = Path.home() / ".amy" / "bin" / "amy-ocr"
    try:
        if binary.is_file() and binary.stat().st_mtime >= source.stat().st_mtime:
            return binary
    except OSError:
        pass
    compiler = shutil.which("swiftc")
    if not compiler:
        raise ScreenError(
            "swiftc non è disponibile: serve Xcode Command Line Tools (gratuite).",
        )
    binary.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.run(
            [compiler, "-O", "-o", str(binary), str(source)],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScreenError("Compilazione dell'helper OCR non riuscita.", detail=str(exc)) from exc
    if process.returncode != 0 or not binary.is_file():
        raise ScreenError(
            "Compilazione dell'helper OCR non riuscita.",
            detail=(process.stderr or "")[-800:],
        )
    return binary


def capture(path: Optional[Path] = None) -> Path:
    """Salva uno screenshot PNG e restituisce il percorso reale."""
    if not Path(SCREENCAPTURE).exists():
        raise ScreenError("Il comando screencapture di macOS non è disponibile.")
    # La cartella deve stare in una radice autorizzata: così screen.read può
    # rileggere lo stesso file senza violare il path guard.
    target = Path(path) if path else (
        Path.home() / "Downloads" / "Amy" / "screenshots"
        / time.strftime("schermo-%Y%m%d-%H%M%S.png")
    )
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.run(
            [SCREENCAPTURE, "-x", "-t", "png", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScreenError("Cattura dello schermo non riuscita.", detail=str(exc)) from exc
    if process.returncode != 0:
        raise ScreenError(
            "Cattura dello schermo non riuscita.",
            detail=(process.stderr or "")[-500:],
        )
    if not target.is_file() or target.stat().st_size < 1000:
        raise ScreenError(
            "La cattura è vuota o non autorizzata.",
            detail="Controlla Impostazioni di Sistema → Privacy e Sicurezza → Registrazione schermo.",
        )
    return target


def ocr_image(path: Path, *, max_chars: int = 8000) -> str:
    """Estrae il testo dall'immagine con Vision, senza rete."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise ScreenError("Immagine non trovata.", detail=str(path))
    binary = _ocr_binary()
    try:
        process = subprocess.run(
            [str(binary), str(path)],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScreenError("OCR non riuscito.", detail=str(exc)) from exc
    if process.returncode != 0:
        raise ScreenError("OCR non riuscito.", detail=(process.stderr or "")[-500:])
    text = process.stdout.strip()
    limit = max(200, min(int(max_chars), 20000))
    return text[:limit]


def read_screen(*, image_path: Optional[Path] = None, max_chars: int = 8000) -> Dict[str, Any]:
    """Cattura lo schermo (o legge un'immagine) e restituisce il testo riconosciuto."""
    path = Path(image_path) if image_path else capture()
    text = ocr_image(path, max_chars=max_chars)
    return {
        "image": str(path),
        "text": text,
        "chars": len(text),
        "captured": image_path is None,
    }
