"""Test dei provider IA: stato del fallback e contratto minimo."""

from __future__ import annotations

import io
import unittest
import urllib.error
from email.message import Message

from amy.ai.factory import FallbackProvider
from amy.ai.offline import OfflineProvider
from amy.ai.openai_compat import OpenAICompatibleProvider
from amy.core.errors import AIError, AIUnavailableError


class _FakePrimary:
    name = "fake"
    model = "modello-test"

    def __init__(self, *, available: bool = True, model_installed=True) -> None:
        self._available = available
        self._model_installed = model_installed

    def chat(self, messages, *, temperature=None, max_tokens=None):
        return "ok"

    def status(self):
        return {
            "provider": self.name,
            "model": self.model,
            "available": self._available,
            "model_installed": self._model_installed,
        }


class FallbackProviderTests(unittest.TestCase):
    def test_status_exposes_primary_availability(self) -> None:
        provider = FallbackProvider(_FakePrimary(), OfflineProvider())
        status = provider.status()
        self.assertTrue(status["available"])
        self.assertTrue(status["model_installed"])
        self.assertEqual(status["provider"], "fake")
        self.assertEqual(status["primary"]["model"], "modello-test")
        self.assertTrue(status["fallback"]["available"])

    def test_unavailable_primary_is_reported(self) -> None:
        provider = FallbackProvider(_FakePrimary(available=False), OfflineProvider())
        status = provider.status()
        self.assertFalse(status["available"])


class OpenAICompatibleProviderTests(unittest.TestCase):
    def test_local_endpoint_works_without_api_key(self) -> None:
        provider = OpenAICompatibleProvider(
            base_url="http://127.0.0.1:8000/v1",
            api_key_env="AMY_TEST_KEY_THAT_DOES_NOT_EXIST",
        )
        status = provider.status()
        self.assertTrue(status["available"])
        self.assertTrue(status["local_endpoint"])
        self.assertFalse(status["api_key_configured"])

    def test_remote_endpoint_is_rejected_without_consent(self) -> None:
        with self.assertRaises(AIUnavailableError):
            OpenAICompatibleProvider(base_url="https://api.example-paid.invalid/v1")

    def test_remote_endpoint_can_be_enabled_explicitly(self) -> None:
        provider = OpenAICompatibleProvider(
            base_url="https://api.example-free.invalid/v1",
            allow_remote=True,
        )
        self.assertFalse(provider.status()["local_endpoint"])
        self.assertTrue(provider.status()["remote_allowed"])

    def test_key_is_required_when_configured(self) -> None:
        provider = OpenAICompatibleProvider(
            base_url="http://127.0.0.1:8000/v1",
            require_api_key=True,
            api_key_env="AMY_TEST_MISSING_OPENAI_KEY",
        )
        self.assertFalse(provider.status()["available"])


class FallbackMessageTests(unittest.TestCase):
    def test_offline_fallback_explains_the_online_failure(self) -> None:
        """Se il provider online cade, non suggerire Ollama all'utente.

        Osservato il 3 novembre 2026: «come va?» finiva nel messaggio offline
        che invitava ad avviare Ollama, mentre l'utente vuole solo servizi
        online gratuiti.
        """

        class Broken:
            name = "groq"
            model = "openai/gpt-oss-120b"

            def chat(self, messages, **kwargs):
                raise AIError("Limite di utilizzo del provider raggiunto.")

            def status(self):
                return {"available": False}

        provider = FallbackProvider(Broken(), OfflineProvider())
        reply = provider.chat([{"role": "user", "content": "come va?"}])
        self.assertIn("provider online non è disponibile", reply)
        self.assertNotIn("Ollama", reply)


class RetryHintTests(unittest.TestCase):
    """L'attesa indicata dal provider non deve essere ignorata.

    Groq mette il suggerimento nel corpo JSON, non sempre nell'header: con
    l'attesa predefinita di 2 s il secondo tentativo falliva e Amy scivolava
    subito nel fallback offline.
    """

    def _error(self, header=None):
        headers = Message()
        if header is not None:
            headers["Retry-After"] = str(header)
        return urllib.error.HTTPError(
            "https://example.invalid/v1", 429, "Too Many Requests", headers, io.BytesIO(b"")
        )

    def test_body_hint_in_seconds_is_used(self) -> None:
        wait = OpenAICompatibleProvider._retry_wait_seconds(
            self._error(),
            '{"error":{"message":"Please try again in 6.3s"}}',
        )
        self.assertAlmostEqual(wait, 6.3, places=1)

    def test_body_hint_in_milliseconds_is_used(self) -> None:
        wait = OpenAICompatibleProvider._retry_wait_seconds(
            self._error(),
            '{"error":{"message":"Please try again in 420ms"}}',
        )
        self.assertAlmostEqual(wait, 0.42, places=2)

    def test_header_is_capped(self) -> None:
        wait = OpenAICompatibleProvider._retry_wait_seconds(self._error("999"), "")
        self.assertEqual(wait, 20.0)

    def test_default_without_hints(self) -> None:
        self.assertEqual(OpenAICompatibleProvider._retry_wait_seconds(self._error(), ""), 2.0)


if __name__ == "__main__":
    unittest.main()
