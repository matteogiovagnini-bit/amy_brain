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
from unittest import mock

from amy.core.system_info import collect_system_info
from amy.macos import applescript


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

class MacSystemInfoTests(unittest.TestCase):
    def test_system_info_includes_load_and_ram(self) -> None:
        info = applescript.system_info()
        for key in ("carico_1m", "ram_liberi_gb", "ram_usati_gb", "ram_percent", "disco_libero_gb"):
            self.assertIn(key, info)

    def test_memory_usage_parses_vm_stat(self) -> None:
        output = """Mach Virtual Memory Statistics: (page size of 4096 bytes)
Pages free: 1000000.
Pages active: 4000000.
Pages inactive: 500000.
Pages speculative: 500000.
Pages wired down: 1000000.
Pages occupied by compressor: 1000000.
"""
        with mock.patch("amy.macos.applescript._run_readonly", return_value=output):
            data = applescript.memory_usage()
        self.assertGreater(data["ram_usati_gb"], 0)
        self.assertGreater(data["ram_percent"], 0)

    def test_top_processes_uses_macos_sort_flags_and_comma_decimals(self) -> None:
        output = "  100  12,5  1,2 /usr/bin/example\n"
        with mock.patch("amy.macos.applescript._run_readonly", return_value=output) as runner:
            rows = applescript.top_processes(1, sort_by="cpu")
        self.assertEqual(rows[0]["cpu_percent"], 12.5)
        self.assertEqual(rows[0]["mem_percent"], 1.2)
        self.assertIn("-r", runner.call_args[0][0])
        with mock.patch("amy.macos.applescript._run_readonly", return_value=output) as runner:
            applescript.top_processes(1, sort_by="memory")
        self.assertIn("-m", runner.call_args[0][0])
