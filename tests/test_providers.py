"""Test dei provider IA: stato del fallback e contratto minimo."""

from __future__ import annotations

import unittest

from amy.ai.factory import FallbackProvider
from amy.ai.offline import OfflineProvider
from amy.ai.openai_compat import OpenAICompatibleProvider
from amy.core.errors import AIUnavailableError


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


if __name__ == "__main__":
    unittest.main()
