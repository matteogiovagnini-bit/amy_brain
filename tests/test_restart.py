"""Test del riavvio programmato dell'app nativa."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from amy.core.restart import RestartError, schedule_restart
from amy.security.risk import RiskLevel
from amy.tools import system
from tests.helpers import TempAmy


class ScheduleRestartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.app = self.temp.root / "Amy Core.app"
        self.app.mkdir()

    def tearDown(self) -> None:
        self.temp.close()

    def test_spawns_a_detached_helper(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"AMY_APP_BUNDLE": str(self.app), "AMY_PARENT_PID": "4242"},
        ):
            with mock.patch("amy.core.restart.subprocess.Popen") as popen:
                data = schedule_restart(5)
        args, kwargs = popen.call_args
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(args[0][1], "-c")
        self.assertIn("os.kill", args[0][2])
        self.assertEqual(data["delay_s"], 5)
        self.assertEqual(data["pid"], 4242)

    def test_without_the_native_app_is_refused(self) -> None:
        with mock.patch.dict(os.environ, {"AMY_APP_BUNDLE": "", "AMY_PARENT_PID": ""}):
            with self.assertRaises(RestartError):
                schedule_restart(5)

    def test_delay_is_bounded(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"AMY_APP_BUNDLE": str(self.app), "AMY_PARENT_PID": "1"},
        ):
            with mock.patch("amy.core.restart.subprocess.Popen"):
                data = schedule_restart(999)
        self.assertEqual(data["delay_s"], 60.0)


class RestartToolTests(unittest.TestCase):
    def test_restart_is_level_c(self) -> None:
        self.assertEqual(system.APP_RESTART.risk, RiskLevel.C)

    def test_tool_schedules_the_restart(self) -> None:
        with mock.patch(
            "amy.tools.system.schedule_restart",
            return_value={"scheduled": True, "delay_s": 7, "app": "/tmp/Amy.app", "pid": 1, "log": ""},
        ) as scheduler:
            result = system._restart({"delay_s": 7}, None)
        self.assertTrue(result.ok)
        scheduler.assert_called_once_with(7.0)
        self.assertIn("7 secondi", result.message)


if __name__ == "__main__":
    unittest.main()
