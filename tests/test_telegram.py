"""Test del collegamento Telegram, senza rete reale."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from amy.modules.telegram import TelegramAdapter
from amy.security.risk import RiskLevel
from amy.telegram.service import TelegramService
from tests.helpers import TempAmy


class FakeAPI:
    def __init__(self) -> None:
        self.messages = []
        self.callbacks = []
        self.audio = []
        self.downloads = []
        self.file_info = {"file_path": "voice/nota.ogg"}

    def send_message(self, chat_id, text, *, reply_markup=None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return {"message_id": len(self.messages)}

    def answer_callback_query(self, callback_id, text=""):
        self.callbacks.append((callback_id, text))
        return True

    def get_file(self, file_id):
        return dict(self.file_info)

    def download_file(self, file_path, destination, *, max_bytes):
        self.downloads.append((file_path, str(destination), max_bytes))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"OggS" + b"0" * 2000)
        return destination

    def send_audio(self, chat_id, audio_path, caption=""):
        self.audio.append((chat_id, str(audio_path), caption))
        return {"message_id": 99}


class FakeSTT:
    available = True

    def __init__(self) -> None:
        self.paths = []

    def transcribe(self, path):
        self.paths.append(Path(path))
        return "che ore sono"


class FakeVoice:
    def __init__(self) -> None:
        self.stt = FakeSTT()
        self.stopped = False

    def stop_speaking(self):
        self.stopped = True


class FakeHandler:
    def __init__(self, reply="Risposta di prova", pending=None) -> None:
        self.reply = reply
        self.pending = pending
        self.calls = []

    def __call__(self, text, session_id=None):
        self.calls.append((text, session_id))
        return SimpleNamespace(reply=self.reply, pending=self.pending)


class TelegramServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.temp.config.data["telegram"]["enabled"] = True
        self.temp.config.data["telegram"]["allowed_user_ids"] = [42]
        self.temp.config.data["telegram"]["voice_replies"] = False
        self.api = FakeAPI()
        self.voice = FakeVoice()
        self.handler = FakeHandler()
        self.resolver = mock.Mock(return_value=SimpleNamespace(reply="Conferma risolta."))
        self.service = TelegramService(
            self.temp.config,
            handler=self.handler,
            resolver=self.resolver,
            voice=self.voice,
            new_session=lambda title: "S-1",
            sessions_path=self.temp.home / "telegram_sessions.json",
            api=self.api,
        )
        self.service._allowed_ids = {42}

    def tearDown(self) -> None:
        self.temp.close()

    def _message(self, text="", *, user=42, chat=42, voice=None):
        payload = {
            "chat": {"id": chat, "type": "private"},
            "from": {"id": user},
        }
        if text:
            payload["text"] = text
        if voice is not None:
            payload["voice"] = voice
        return payload

    def test_text_message_goes_to_assistant(self) -> None:
        self.service._handle_update({"update_id": 1, "message": self._message("che ore sono?")})
        self.assertEqual(self.handler.calls, [("che ore sono?", "S-1")])
        self.assertEqual(self.api.messages[-1]["text"], "Risposta di prova")
        saved = json.loads((self.temp.home / "telegram_sessions.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["42"], "S-1")

    def test_unauthorized_user_is_ignored(self) -> None:
        self.service._handle_update({"message": self._message("ciao", user=99, chat=99)})
        self.assertEqual(self.handler.calls, [])
        self.assertEqual(self.api.messages, [])

    def test_group_chat_is_ignored(self) -> None:
        message = self._message("ciao")
        message["chat"]["type"] = "group"
        self.service._handle_update({"message": message})
        self.assertEqual(self.handler.calls, [])

    def test_voice_note_is_downloaded_and_transcribed(self) -> None:
        voice = {"file_id": "FILE-1", "duration": 4, "file_size": 2000}
        self.service._handle_update({"message": self._message(voice=voice)})
        self.assertEqual(self.handler.calls[0][0], "che ore sono")
        self.assertTrue(any("trascrivendo" in item["text"].lower() for item in self.api.messages))
        self.assertEqual(len(self.api.downloads), 1)
        self.assertEqual(len(self.voice.stt.paths), 1)

    def test_voice_note_too_long_is_refused(self) -> None:
        voice = {"file_id": "FILE-1", "duration": 999, "file_size": 2000}
        self.service._handle_update({"message": self._message(voice=voice)})
        self.assertIn("limite", self.api.messages[-1]["text"].lower())
        self.assertEqual(self.handler.calls, [])
        self.assertEqual(self.api.downloads, [])

    def test_confirmation_buttons_resolve_pending(self) -> None:
        pending = SimpleNamespace(
            pending_id="P-1",
            tool="files.write",
            risk=RiskLevel.B,
        )
        self.handler.pending = pending
        self.handler.reply = "Vuoi scrivere il file?"
        self.service._handle_update({"message": self._message("scrivi il file")})
        sent = self.api.messages[-1]
        self.assertIsNotNone(sent["reply_markup"])
        self.assertIn("yes:P-1", json.dumps(sent["reply_markup"]))
        callback = {
            "id": "CB-1",
            "from": {"id": 42},
            "data": "yes:P-1",
            "message": {"chat": {"id": 42, "type": "private"}},
        }
        self.service._handle_update({"callback_query": callback})
        self.resolver.assert_called_once_with("P-1", True)
        self.assertEqual(self.api.messages[-1]["text"], "Conferma risolta.")
        self.assertTrue(self.api.callbacks)

    def test_text_yes_resolves_pending(self) -> None:
        pending = SimpleNamespace(pending_id="P-2", tool="files.write", risk=RiskLevel.B)
        self.handler.pending = pending
        self.handler.reply = "Confermi?"
        self.service._handle_update({"message": self._message("scrivi")})
        self.service._handle_update({"message": self._message("sì")})
        self.resolver.assert_called_once_with("P-2", True)

    def test_new_session_command(self) -> None:
        self.service._handle_update({"message": self._message("/new")})
        self.assertIn("Nuova sessione", self.api.messages[-1]["text"])
        self.assertEqual(self.handler.calls, [])

    def test_status_command_reports_connection(self) -> None:
        self.service._handle_update({"message": self._message("/status")})
        self.assertIn("Amy è collegata", self.api.messages[-1]["text"])

    def test_start_without_token_fails_honestly(self) -> None:
        self.temp.config.data["telegram"]["token_env"] = "AMY_TEST_TOKEN_ASSENTE"
        with mock.patch("amy.telegram.service.get_secret", return_value=None):
            status = self.service.start()
        self.assertEqual(status["state"], "error")
        self.assertIn("Token", status["error"])

    def test_start_without_allowlist_fails_honestly(self) -> None:
        self.temp.config.data["telegram"]["allowed_user_ids"] = []
        with mock.patch("amy.telegram.service.get_secret", return_value="123:fake"):
            status = self.service.start()
        self.assertEqual(status["state"], "error")
        self.assertIn("Allowlist", status["error"])

    def test_chunks_respect_telegram_limit(self) -> None:
        text = "\n".join(["riga %d" % i for i in range(1000)])
        chunks = list(TelegramService._chunks(text, limit=200))
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 200 for chunk in chunks))

    def test_module_status_reflects_running_service(self) -> None:
        class FakeService:
            def status(self):
                return {
                    "enabled": True,
                    "state": "running",
                    "running": True,
                    "connected": True,
                    "username": "AmyCoreBot",
                    "allowed_users": 1,
                    "voice_replies": True,
                    "error": "",
                }

        adapter = TelegramAdapter(FakeService())
        status = adapter.status()
        self.assertEqual(status.state.value, "ready")
        self.assertTrue(status.available)
        self.assertIn("@AmyCoreBot", status.detail)


if __name__ == "__main__":
    unittest.main()
