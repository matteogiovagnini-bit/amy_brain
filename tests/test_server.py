"""Test della dashboard HTTP locale: API, sessione, conferme e statici."""

from __future__ import annotations

import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from unittest import mock

from amy.core.assistant import Assistant
from amy.core.config import Config
from amy.core.errors import ConfigError
from amy.memory.store import MemoryStore
from amy.robot.links import SimulatedLink
from amy.robot.simulator import RobotSimulator
from amy.security.audit import NullAudit
from amy.ui.server import AmyHTTPServer, _schedule_greeting, run_server
from tests.helpers import TempAmy


class FakeVoice:
    def __init__(self) -> None:
        self.config = Config({"voice": {"wake_word": {"enabled": True}}})
        self.running = False
        self.started = 0
        self.on_command = None

    def status(self):
        return {
            "enabled": True,
            "speaking": False,
            "tts": {"available": False, "engine": "none"},
            "stt": {"available": False, "engine": "none"},
            "recorder": {"available": False, "engine": "none"},
            "wake_word": {
                "phrase": "amy",
                "enabled": True,
                "running": self.running,
                "available": True,
            },
            "ready_for_voice_commands": False,
        }

    def start_wake_loop(self, on_command, *, max_minutes=None):
        self.running = True
        self.started += 1
        self.on_command = on_command
        return None

    def stop_wake_loop(self):
        self.running = False

    def greet(self, text=None):
        return {"spoken": True, "text": text or "Amy è attiva e operativa."}

    def speak(self, text, *, block=False):
        return {"spoken": True, "test": True}

    def stop_speaking(self):
        return None

    def listen_once(self, seconds=None):
        return "che ore sono"


class VoiceAnswerTests(unittest.TestCase):
    """La conferma vocale deve capire sì e no senza ambiguità."""

    def test_yes_answers(self) -> None:
        for text in ("sì", "Sì, procedi", "confermo", "ok", "fallo"):
            self.assertIs(AmyHTTPServer._voice_answer(text), True, text)

    def test_no_answers(self) -> None:
        for text in ("no", "annulla", "lascia stare", "stop"):
            self.assertIs(AmyHTTPServer._voice_answer(text), False, text)

    def test_unclear_answers(self) -> None:
        for text in ("forse", "", "che ore sono"):
            self.assertIsNone(AmyHTTPServer._voice_answer(text), text)


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.memory = MemoryStore(str(self.temp.home / "server.db"))
        self.assistant = Assistant(
            self.temp.config,
            memory=self.memory,
            audit=NullAudit(),
            robot_link=SimulatedLink(RobotSimulator()),
            voice=FakeVoice(),
        )
        self.server = AmyHTTPServer(("127.0.0.1", 0), self.assistant)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.assistant.close()
        self.temp.close()

    def call(self, method: str, path: str, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            if "application/json" in response.headers.get("Content-Type", ""):
                return response, json.loads(body) if body else {}
            return response, body

    def test_health_and_state(self) -> None:
        response, data = self.call("GET", "/api/health")
        self.assertEqual(response.status, 200)
        self.assertTrue(data["ok"])
        _, state = self.call("GET", "/api/state")
        self.assertEqual(state["assistant"]["name"], "Amy")
        self.assertIn("facts", state)
        self.assertIn("config_path", state["config"])
        self.assertEqual(state["config"]["robot_transport"], "simulated")
        self.assertIn("speaking", state["voice"])
        self.assertIs(state["voice"]["speaking"], False)

    def test_modules_endpoint_and_state(self) -> None:
        _, data = self.call("GET", "/api/modules")
        names = {item["manifest"]["name"] for item in data["modules"]}
        self.assertEqual(
            names,
            {"voice", "mac_control", "personal", "memory", "developer", "vision", "home", "robot"},
        )
        for item in data["modules"]:
            self.assertIn("status", item)
            self.assertIn("enabled", item)
        _, state = self.call("GET", "/api/state")
        self.assertEqual(len(state["modules"]), 8)

    def test_disable_and_enable_a_module_changes_the_tools(self) -> None:
        _, before = self.call("GET", "/api/tools")
        total = len(before["tools"])
        _, result = self.call("POST", "/api/modules/vision/enabled", {"enabled": False})
        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["enabled"])
        _, after = self.call("GET", "/api/tools")
        self.assertEqual(len(after["tools"]), total - 2)
        self.assertNotIn("screen.read", [tool["name"] for tool in after["tools"]])
        _, result = self.call("POST", "/api/modules/vision/enabled", {"enabled": True})
        self.assertTrue(result["result"]["enabled"])
        _, restored = self.call("GET", "/api/tools")
        self.assertEqual(len(restored["tools"]), total)

    def test_memory_is_essential_and_cannot_be_disabled(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.call("POST", "/api/modules/memory/enabled", {"enabled": False})
        self.assertEqual(context.exception.code, 400)

    def test_permissions_endpoint_and_revocation(self) -> None:
        _, data = self.call("GET", "/api/permissions")
        capabilities = {item["capability"] for item in data["capabilities"]}
        self.assertIn("vision.screen", capabilities)
        _, state = self.call("GET", "/api/state")
        self.assertIn("permissions", state)

        _, result = self.call("POST", "/api/permissions/revoke", {"capability": "vision.screen"})
        self.assertIn("vision.screen", result["permissions"]["revoked"])
        from amy.security.risk import RiskLevel
        self.assertFalse(self.assistant.authorization.check("screen.read", RiskLevel.B).allowed)

        _, result = self.call("POST", "/api/permissions/restore", {"capability": "vision.screen"})
        self.assertNotIn("vision.screen", result["permissions"]["revoked"])
        self.assertTrue(self.assistant.authorization.check("screen.read", RiskLevel.B).allowed)

    def test_unknown_capability_is_rejected(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.call("POST", "/api/permissions/revoke", {"capability": "inesistente"})
        self.assertEqual(context.exception.code, 400)

    def test_disabling_a_module_cancels_its_pending_confirmation(self) -> None:
        from amy.core.assistant import _Pending, _Turn
        from amy.security.policy import ConfirmationRequest
        from amy.security.risk import RiskLevel

        pending = _Pending(
            turn=_Turn(session_id="s", messages=[]),
            request=ConfirmationRequest(
                pending_id="cfm_test",
                tool="screen.read",
                args={},
                risk=RiskLevel.B,
                reason="prova",
                consequences="",
                undo="",
            ),
            action={"tool": "screen.read", "args": {}},
            risk=RiskLevel.B,
        )
        self.assistant._pending["cfm_test"] = pending
        self.call("POST", "/api/modules/vision/enabled", {"enabled": False})
        self.assertEqual(self.assistant.pending_confirmations(), [])

    def test_unknown_module_is_rejected(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.call("POST", "/api/modules/inesistente/enabled", {"enabled": False})
        self.assertEqual(context.exception.code, 400)

    def test_state_includes_real_local_system_info(self) -> None:
        _, state = self.call("GET", "/api/state")
        system = state["system"]
        for key in ("os", "os_name", "arch", "python", "cpu_count", "load_average", "disk"):
            self.assertIn(key, system)
        self.assertTrue(system["python"])
        self.assertTrue(system["arch"])
        # Nessun dato robot o Raspberry Pi viene inventato dal lato sistema.
        self.assertNotIn("battery_pct", system)
        self.assertNotIn("pi_status", system)

    def test_tools_catalog(self) -> None:
        _, data = self.call("GET", "/api/tools")
        names = [item["name"] for item in data["tools"]]
        self.assertGreaterEqual(len(names), 30)
        self.assertIn("robot.estop", names)
        self.assertIn("files.write", names)

    def test_calendar_upcoming_reads_events_with_calendar_events(self) -> None:
        today = date.today()
        tomorrow = today + timedelta(days=1)

        def by_date(**kwargs):
            day = kwargs["date"]
            events = []
            # Un evento sul secondo giorno è sempre futuro, qualunque sia l'ora.
            if day == tomorrow.isoformat():
                events = [{
                    "uid": "U1", "title": "Riunione", "start": day + "T10:00",
                    "end": day + "T11:00", "calendar": "Calendario",
                }]
            return {"date": day, "calendar": "Calendario", "events": events}

        with mock.patch("amy.tools.calendar_tools.list_events", side_effect=by_date) as reader:
            response, data = self.call("GET", "/api/calendar/upcoming?days=2")
        self.assertEqual(response.status, 200)
        self.assertIs(data["available"], True)
        self.assertEqual(data["days"], 2)
        self.assertEqual(data["calendar"], "Calendario")
        self.assertEqual([item["title"] for item in data["events"]], ["Riunione"])
        self.assertEqual([call[1]["date"] for call in reader.call_args_list],
                         [today.isoformat(), tomorrow.isoformat()])
        # La risposta non contiene chiavi che il client interpreta come errore.
        self.assertNotIn("error", data)

    def test_calendar_upcoming_declares_an_unreadable_calendar(self) -> None:
        with mock.patch("amy.tools.registry._log"):
            with mock.patch("amy.tools.calendar_tools.list_events", side_effect=RuntimeError("negato")):
                _, data = self.call("GET", "/api/calendar/upcoming?days=2")
        self.assertIs(data["available"], False)
        self.assertEqual(data["events"], [])
        self.assertEqual(data["failed_days"], 2)
        self.assertTrue(data["reason"])

    def test_calendar_upcoming_clamps_the_requested_window(self) -> None:
        empty = {"date": "", "calendar": "Calendario", "events": []}
        with mock.patch("amy.tools.calendar_tools.list_events", return_value=empty):
            _, short = self.call("GET", "/api/calendar/upcoming?days=0")
            _, long = self.call("GET", "/api/calendar/upcoming?days=999")
            _, invalid = self.call("GET", "/api/calendar/upcoming?days=abc")
        self.assertEqual(short["days"], 1)
        self.assertEqual(long["days"], 14)
        self.assertEqual(invalid["days"], 7)

    def test_new_session_and_transcript(self) -> None:
        _, created = self.call("POST", "/api/new_session", {"title": "Test"})
        session = created["session_id"]
        self.assertTrue(session.startswith("ses_"))
        _, transcript = self.call("GET", "/api/transcript?session=" + session)
        self.assertEqual(transcript["session_id"], session)
        self.assertEqual(transcript["messages"], [])

    def test_chat_offline_turn(self) -> None:
        _, created = self.call("POST", "/api/new_session", {})
        session = created["session_id"]
        _, result = self.call("POST", "/api/chat", {"message": "che ore sono?", "session_id": session})
        self.assertEqual(result["status"], "ok")
        self.assertIn("Sono le", result["reply"])
        _, transcript = self.call("GET", "/api/transcript?session=" + session)
        self.assertEqual(transcript["messages"][0]["content"], "che ore sono?")

    def test_memory_fact_appears_in_state(self) -> None:
        _, created = self.call("POST", "/api/new_session", {})
        session = created["session_id"]
        _, result = self.call(
            "POST",
            "/api/chat",
            {"message": "ricorda che la città è Roma", "session_id": session},
        )
        self.assertEqual(result["status"], "ok")
        _, state = self.call("GET", "/api/state")
        facts = {item["key"]: item["value"] for item in state["facts"]}
        self.assertEqual(facts.get("la città"), "Roma")

    def test_confirmation_endpoint_requires_pending_id(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.call("POST", "/api/confirm", {"approved": True})
        self.assertEqual(context.exception.code, 400)

    def test_unknown_pending_returns_error_turn(self) -> None:
        _, result = self.call("POST", "/api/confirm", {"pending_id": "cfm_x", "approved": True})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "pending_not_found")

    def test_robot_estop_from_dashboard(self) -> None:
        _, result = self.call("POST", "/api/robot/estop", {"reason": "test"})
        self.assertTrue(result["ok"])
        _, state = self.call("GET", "/api/state")
        self.assertTrue(state["robot"]["estop_latched"])

    def test_voice_endpoints(self) -> None:
        _, spoken = self.call("POST", "/api/speak", {"text": "ciao"})
        self.assertTrue(spoken["spoken"])
        _, listened = self.call("POST", "/api/voice/listen", {"seconds": 1})
        self.assertEqual(listened["text"], "che ore sono")
        _, stopped = self.call("POST", "/api/voice/stop", {})
        self.assertTrue(stopped["stopped"])

    def test_static_files_and_csp(self) -> None:
        response, _ = self.call("GET", "/")
        self.assertEqual(response.status, 200)
        csp = response.headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        response, _ = self.call("GET", "/static/app.js")
        self.assertEqual(response.status, 200)
        self.assertIn("javascript", response.headers.get("Content-Type", ""))

    def test_voice_greet_endpoint_speaks(self) -> None:
        response, data = self.call("POST", "/api/voice/greet", {})
        self.assertEqual(response.status, 200)
        self.assertIs(data.get("spoken"), True)

    def test_startup_greeting_is_scheduled_and_can_be_disabled(self) -> None:
        """All'avvio Amy saluta; l'ambiente può disattivarlo (test automatici)."""
        spoken = []

        class FakeAssistant:
            class voice:  # noqa: N801 - semplice contenitore finto
                @staticmethod
                def greet(text=None):
                    spoken.append(text)
                    return {"spoken": True, "text": text}

        with mock.patch.dict(os.environ, {"AMY_STARTUP_GREETING": "0"}):
            _schedule_greeting(FakeAssistant(), delay=0.0)
            time.sleep(0.3)
        self.assertEqual(spoken, [])

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMY_STARTUP_GREETING", None)
            _schedule_greeting(FakeAssistant(), delay=0.0)
            deadline = time.monotonic() + 3
            while not spoken and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertEqual(len(spoken), 1)

    def test_voice_wake_endpoints_start_and_stop(self) -> None:
        response, _ = self.call("POST", "/api/voice/wake/start", {})
        self.assertEqual(response.status, 200)
        self.assertIs(self.assistant.voice.running, True)
        response, _ = self.call("POST", "/api/voice/wake/stop", {})
        self.assertEqual(response.status, 200)
        self.assertIs(self.assistant.voice.running, False)

    def test_voice_wake_requires_explicit_configuration(self) -> None:
        self.assistant.voice.config = Config({"voice": {"wake_word": {"enabled": False}}})
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.call("POST", "/api/voice/wake/start", {})
        self.assertEqual(context.exception.code, 400)

    def test_remote_bind_requires_explicit_consent(self) -> None:
        with self.assertRaises(ConfigError):
            run_server(self.temp.config, host="0.0.0.0", port=0)


    def test_static_path_traversal_is_blocked(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.call("GET", "/static/../server.py")
        self.assertEqual(context.exception.code, 400)

    def test_unknown_endpoint(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.call("GET", "/api/inesistente")
        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()

class VoiceConfirmationServerTests(unittest.TestCase):
    def _server(self):
        server = object.__new__(AmyHTTPServer)
        server.assistant = mock.Mock()
        server.assistant.voice = mock.Mock()
        server.assistant.resolve_confirmation.return_value = mock.Mock(reply="Eliminato.")
        return server

    def test_yes_resolves_and_speaks(self) -> None:
        server = self._server()
        self.assertTrue(server._resolve_voice_confirmation("sì", "cfm_1"))
        server.assistant.resolve_confirmation.assert_called_once_with("cfm_1", True)
        server.assistant.voice.speak.assert_called_once()

    def test_no_rejects(self) -> None:
        server = self._server()
        self.assertTrue(server._resolve_voice_confirmation("no", "cfm_1"))
        server.assistant.resolve_confirmation.assert_called_once_with("cfm_1", False)

    def test_unclear_keeps_waiting(self) -> None:
        server = self._server()
        self.assertFalse(server._resolve_voice_confirmation("forse", "cfm_1"))
        server.assistant.resolve_confirmation.assert_not_called()
        self.assertIn("sì oppure no", server.assistant.voice.speak.call_args[0][0])

    def test_expired_pending_is_reported(self) -> None:
        server = self._server()
        server.assistant.resolve_confirmation.side_effect = RuntimeError("scaduta")
        self.assertTrue(server._resolve_voice_confirmation("sì", "cfm_1"))
        self.assertIn("non è più valida", server.assistant.voice.speak.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
