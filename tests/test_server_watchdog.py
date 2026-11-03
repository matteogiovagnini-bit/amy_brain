"""Test del watchdog del backend locale.

L'app nativa Amy Core avvia il server come processo figlio: se l'app muore,
il backend non deve restare vivo come orfano. Il watchdog heartbeat chiude il
server quando il file di heartbeat sparisce o invecchia.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from amy.ui.server import _watch_heartbeat


class FakeServer:
    """Server finto: registra la richiesta di chiusura."""

    def __init__(self) -> None:
        self.shutdown_called = threading.Event()

    def shutdown(self) -> None:
        self.shutdown_called.set()


def _quiet_watchdog(server: FakeServer, path: str, max_age_s: float) -> None:
    """Esegue il watchdog senza sporcare l'output dei test."""
    with contextlib.redirect_stdout(io.StringIO()):
        _watch_heartbeat(server, path, max_age_s, interval_s=0.05)


class HeartbeatWatchdogTests(unittest.TestCase):
    def _run_watchdog(self, server: FakeServer, path: str, max_age_s: float = 8.0) -> threading.Thread:
        thread = threading.Thread(
            target=_quiet_watchdog,
            args=(server, path, max_age_s),
            daemon=True,
        )
        thread.start()
        return thread

    def test_closes_when_heartbeat_is_missing(self) -> None:
        server = FakeServer()
        with tempfile.TemporaryDirectory(prefix="amy-hb-") as tmp:
            missing = str(Path(tmp) / "heartbeat")
            self._run_watchdog(server, missing)
            self.assertTrue(server.shutdown_called.wait(5.0), "il server deve chiudersi")

    def test_closes_when_heartbeat_is_stale(self) -> None:
        server = FakeServer()
        with tempfile.TemporaryDirectory(prefix="amy-hb-") as tmp:
            path = Path(tmp) / "heartbeat"
            path.write_text("1", encoding="utf-8")
            # Rende il file vecchio di un'ora.
            old = time.time() - 3600
            os.utime(str(path), (old, old))
            self._run_watchdog(server, str(path), max_age_s=8.0)
            self.assertTrue(server.shutdown_called.wait(5.0), "il server deve chiudersi")

    def test_keeps_running_with_fresh_heartbeat(self) -> None:
        server = FakeServer()
        with tempfile.TemporaryDirectory(prefix="amy-hb-") as tmp:
            path = Path(tmp) / "heartbeat"
            path.write_text("1", encoding="utf-8")
            thread = self._run_watchdog(server, str(path), max_age_s=60.0)
            time.sleep(0.4)
            self.assertFalse(server.shutdown_called.is_set(), "non deve chiudersi con heartbeat fresco")
            # Il watchdog continua a girare: si ferma solo a fine test.
            self.assertTrue(thread.is_alive())

    def test_stale_heartbeat_does_not_close_when_parent_is_alive(self) -> None:
        """App Nap può fermare il timer dell'app: il PID vivo è la prova decisiva.

        Osservato il 3 novembre 2026: il backend si chiudeva ogni minuto con
        «Heartbeat del genitore scaduto» mentre l'app era aperta.
        """
        server = FakeServer()
        with tempfile.TemporaryDirectory(prefix="amy-hb-") as tmp:
            path = Path(tmp) / "heartbeat"
            path.write_text("1", encoding="utf-8")
            old = time.time() - 3600
            os.utime(str(path), (old, old))
            with mock.patch.dict(os.environ, {"AMY_PARENT_PID": str(os.getpid())}):
                self._run_watchdog(server, str(path), max_age_s=8.0)
                time.sleep(0.4)
                self.assertFalse(
                    server.shutdown_called.is_set(),
                    "il backend non deve chiudersi se il processo padre è vivo",
                )

    def test_default_tolerance_is_wide_enough_for_a_slow_app(self) -> None:
        """Il backend non deve chiudersi se l'app rallenta per qualche secondo.

        L'app nativa aggiorna l'heartbeat ogni 2 s, ma può bloccarsi (alert
        modale, carico CPU durante una trascrizione). Con una tolleranza di 8 s
        il backend si chiudeva da solo mentre l'app era viva.
        """
        import inspect

        default = inspect.signature(_watch_heartbeat).parameters["max_age_s"].default
        self.assertGreaterEqual(default, 20.0)


if __name__ == "__main__":
    unittest.main()
