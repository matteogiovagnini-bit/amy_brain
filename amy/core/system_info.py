"""Informazioni locali di sistema per la dashboard.

Solo dati realmente disponibili tramite la libreria standard. Nessun dato viene
inviato fuori dal Mac e nessun valore viene stimato o inventato.
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, Optional


def _gb(value: int) -> float:
    return round(float(value) / (1024.0 ** 3), 1)


def collect_system_info(home: Optional[Path] = None) -> Dict[str, Any]:
    """Restituisce un sottoinsieme stabile di informazioni di sistema.

    I campi non disponibili restano ``None``: il frontend li mostra come
    «Non disponibile» invece di inventare un valore.
    """
    path = Path(home) if home is not None else Path.home()
    load_average = None
    if hasattr(os, "getloadavg"):
        try:
            load_average = [round(value, 2) for value in os.getloadavg()]
        except OSError:
            load_average = None

    disk: Optional[Dict[str, Any]] = None
    try:
        usage = shutil.disk_usage(str(path))
        disk = {
            "path": str(path),
            "total_gb": _gb(usage.total),
            "free_gb": _gb(usage.free),
            "used_pct": round((usage.used / usage.total) * 100, 1) if usage.total else None,
        }
    except OSError:
        disk = None

    return {
        "os": platform.mac_ver()[0] or platform.system(),
        "os_name": platform.system(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "load_average": load_average,
        "disk": disk,
    }
