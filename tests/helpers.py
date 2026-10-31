"""Supporto condiviso per i test di Amy.

Tutti i test usano una cartella temporanea: nessun file viene scritto in
``~/.amy`` e nessuna operazione tocca la configurazione reale dell'utente.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from amy.core.config import DEFAULT_CONFIG, Config


class TempAmy:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="amy-test-")
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.files = self.root / "files"
        self.files.mkdir(parents=True, exist_ok=True)

        data = copy.deepcopy(DEFAULT_CONFIG)
        data["ai"]["provider"] = "offline"
        data["ai"]["fallback_provider"] = "offline"
        data["memory"]["db_path"] = str(self.home / "amy.db")
        data["security"]["audit_path"] = str(self.home / "audit.jsonl")
        data["security"]["backup_dir"] = str(self.home / "backups")
        data["security"]["allowed_roots"] = [str(self.files)]
        data["logging"]["file"] = str(self.home / "amy.log")
        data["robot"]["transport"] = "simulated"
        data["voice"]["enabled"] = False

        self.config = Config(data, self.home / "config.json")
        self.config.ensure_dirs()

    def close(self) -> None:
        self._tmp.cleanup()
