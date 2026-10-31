"""Test delle informazioni di sistema locali usate dalla dashboard.

Le informazioni devono essere reali, locali e senza segreti: nessun valore
inventato, nessun dato robot Raspberry Pi, nessuna chiave API.
"""

from __future__ import annotations

import os
import platform
import tempfile
import unittest
from pathlib import Path

from amy.core.system_info import collect_system_info


class SystemInfoTests(unittest.TestCase):
    def test_returns_expected_keys(self) -> None:
        info = collect_system_info()
        for key in ("os", "os_name", "arch", "python", "cpu_count", "load_average", "disk"):
            self.assertIn(key, info)

    def test_values_match_the_running_machine(self) -> None:
        info = collect_system_info()
        self.assertEqual(info["arch"], platform.machine())
        self.assertEqual(info["python"], platform.python_version())
        self.assertEqual(info["os_name"], platform.system())
        self.assertEqual(info["cpu_count"], os.cpu_count())
        self.assertTrue(info["os"], "il sistema operativo deve essere identificato")

    def test_load_average_is_a_triplet_or_none(self) -> None:
        load = collect_system_info()["load_average"]
        if load is not None:
            self.assertIsInstance(load, list)
            self.assertEqual(len(load), 3)
            for item in load:
                self.assertIsInstance(item, float)

    def test_disk_reports_real_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="amy-sysinfo-") as tmp:
            info = collect_system_info(Path(tmp))
            disk = info["disk"]
            self.assertIsNotNone(disk)
            assert disk is not None
            self.assertEqual(disk["path"], str(Path(tmp)))
            self.assertGreater(disk["total_gb"], 0)
            self.assertGreaterEqual(disk["free_gb"], 0)
            self.assertGreaterEqual(disk["used_pct"], 0)
            self.assertLessEqual(disk["used_pct"], 100)

    def test_no_secret_or_remote_keys(self) -> None:
        info = collect_system_info()
        forbidden = ("api_key", "token", "secret", "password", "email")
        for key in info:
            for word in forbidden:
                self.assertNotIn(word, key.lower(), key)
        self.assertNotIn("robot", info)
        self.assertNotIn("battery", info)


if __name__ == "__main__":
    unittest.main()
