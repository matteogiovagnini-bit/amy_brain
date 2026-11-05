"""Test dell'integrazione con OpenCode 2, senza avviare l'agente reale."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.security.risk import RiskLevel
from amy.tools import opencode_tools
from amy.tools.base import ToolContext
from tests.helpers import TempAmy


def events(text: str = "Fatto.", session: str = "ses_test") -> str:
    return "\n".join(
        [
            json.dumps({"type": "text", "sessionID": session, "part": {"type": "text", "text": text}}),
            json.dumps(
                {
                    "type": "step_finish",
                    "sessionID": session,
                    "part": {"cost": 0, "tokens": {"input": 10, "output": 2}},
                }
            ),
        ]
    )


class OpenCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.project = self.temp.files / "progetto"
        self.project.mkdir()
        self.guard = PathGuard([self.temp.files], max_file_bytes=1024)
        self.context = ToolContext(
            config=self.temp.config,
            memory=None,
            path_guard=self.guard,
            audit=NullAudit(),
        )
        self.temp.config.data["opencode"]["enabled"] = True

    def tearDown(self) -> None:
        self.temp.close()

    def _completed(self, stdout: str) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    def test_runs_and_remembers_the_session(self) -> None:
        with mock.patch("amy.tools.opencode_tools.shutil.which", return_value="/usr/local/bin/opencode2"):
            with mock.patch(
                "amy.tools.opencode_tools.subprocess.run",
                return_value=self._completed(events("Risposta di prova", "ses_abc")),
            ) as runner:
                data = opencode_tools.run_request(
                    "sistema il README", directory=str(self.project), context=self.context
                )
        command = runner.call_args[0][0]
        self.assertIn("run", command)
        self.assertIn("sistema il README", command)
        self.assertIn("--format", command)
        self.assertNotIn("--auto", command)
        self.assertEqual(data["session_id"], "ses_abc")
        self.assertEqual(data["text"], "Risposta di prova")
        self.assertEqual(runner.call_args.kwargs["cwd"], str(self.project.resolve()))
        sessions = json.loads((self.temp.home / "opencode_sessions.json").read_text(encoding="utf-8"))
        self.assertEqual(sessions["sessions"][str(self.project.resolve())]["id"], "ses_abc")

    def test_second_request_continues_the_session(self) -> None:
        with mock.patch("amy.tools.opencode_tools.shutil.which", return_value="/usr/local/bin/opencode2"):
            with mock.patch(
                "amy.tools.opencode_tools.subprocess.run",
                return_value=self._completed(events("Prima", "ses_abc")),
            ):
                opencode_tools.run_request("prima", directory=str(self.project), context=self.context)
            with mock.patch(
                "amy.tools.opencode_tools.subprocess.run",
                return_value=self._completed(events("Seconda", "ses_abc")),
            ) as runner:
                opencode_tools.run_request("seconda", directory=str(self.project), context=self.context)
        command = runner.call_args[0][0]
        self.assertIn("--session", command)
        self.assertIn("ses_abc", command)

    def test_new_session_does_not_reuse_the_id(self) -> None:
        with mock.patch("amy.tools.opencode_tools.shutil.which", return_value="/usr/local/bin/opencode2"):
            with mock.patch(
                "amy.tools.opencode_tools.subprocess.run",
                return_value=self._completed(events("Prima", "ses_abc")),
            ):
                opencode_tools.run_request("prima", directory=str(self.project), context=self.context)
            with mock.patch(
                "amy.tools.opencode_tools.subprocess.run",
                return_value=self._completed(events("Nuova", "ses_new")),
            ) as runner:
                opencode_tools.run_request(
                    "nuova", directory=str(self.project), new_session=True, context=self.context
                )
        self.assertNotIn("--session", runner.call_args[0][0])

    def test_disabled_is_refused(self) -> None:
        self.temp.config.data["opencode"]["enabled"] = False
        with self.assertRaises(opencode_tools.OpenCodeError):
            opencode_tools.run_request("ciao", directory=str(self.project), context=self.context)

    def test_directory_outside_roots_is_refused(self) -> None:
        with self.assertRaises(Exception):
            opencode_tools.run_request("ciao", directory="/tmp", context=self.context)

    def test_restart_after_schedules_the_restart(self) -> None:
        payload = {
            "session_id": "ses_abc",
            "directory": str(self.project),
            "text": "Fatto.",
            "truncated": False,
            "steps_text": 1,
            "cost": 0,
            "tokens": {},
            "returncode": 0,
            "new_session": False,
        }
        with mock.patch("amy.tools.opencode_tools.run_request", return_value=payload):
            with mock.patch(
                "amy.tools.opencode_tools.schedule_restart",
                return_value={"scheduled": True, "delay_s": 12},
            ) as scheduler:
                result = opencode_tools._run(
                    {"request": "implementa", "restart_after": True}, self.context
                )
        self.assertTrue(result.ok)
        self.assertTrue(result.data["restart"]["scheduled"])
        scheduler.assert_called_once()
        self.assertIn("riavvia", result.message)

    def test_sending_requires_confirmation(self) -> None:
        self.assertEqual(opencode_tools.OPENCODE_RUN.risk, RiskLevel.C)
        self.assertEqual(opencode_tools.OPENCODE_STATUS.risk, RiskLevel.A)


if __name__ == "__main__":
    unittest.main()
