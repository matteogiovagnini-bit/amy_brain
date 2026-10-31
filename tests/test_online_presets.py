"""Test dei provider IA online gratuiti.

Il progetto accetta un servizio online solo se:

- è gratuito senza pagamenti obbligatori (niente carta di credito richiesta);
- l'utente lo sceglie esplicitamente e conferma che la conversazione lascia il Mac;
- il fallback resta locale e gratuito;
- il default del repository resta locale.
"""

from __future__ import annotations

import copy
import io
import json
import unittest
import urllib.error
from unittest import mock

from amy.ai.factory import FallbackProvider, build_primary, build_provider
from amy.ai.openai_compat import OpenAICompatibleProvider
from amy.ai.presets import PRESETS, get_preset, preset_names
from amy.core.config import DEFAULT_CONFIG, Config
from amy.core.errors import ConfigError


def _config_with(provider: str, *, consent: bool = True, key_env: str = "AMY_TEST_MISSING_GROQ_KEY") -> Config:
    data = copy.deepcopy(DEFAULT_CONFIG)
    data["ai"]["provider"] = provider
    data["ai"]["online"]["consent"] = consent
    data["ai"]["online"]["api_key_env"] = key_env
    return Config(data)


class PresetMetadataTests(unittest.TestCase):
    def test_presets_have_openai_compatible_https_endpoint(self) -> None:
        self.assertTrue(preset_names())
        for preset in PRESETS.values():
            self.assertTrue(preset.base_url.startswith("https://"), preset.id)
            self.assertTrue(preset.base_url.rstrip("/").endswith("/v1"), preset.id)
            self.assertTrue(preset.model, preset.id)
            self.assertTrue(preset.api_key_env.isupper(), preset.id)

    def test_free_terms_exclude_mandatory_payments(self) -> None:
        for preset in PRESETS.values():
            text = (preset.free_terms + " " + preset.limits).lower()
            self.assertIn("senza carta di credito", text, preset.id)
            for word in ("obbligatorio pagare", "crediti obbligatori", "abbonamento obbligatorio"):
                self.assertNotIn(word, text, preset.id)

    def test_license_and_verification_date_are_declared(self) -> None:
        for preset in PRESETS.values():
            self.assertTrue(preset.model_license, preset.id)
            self.assertRegex(preset.verified_on, r"^\d{4}-\d{2}-\d{2}$", preset.id)

    def test_preset_metadata_is_public_and_has_no_key(self) -> None:
        for preset in PRESETS.values():
            data = preset.as_dict()
            self.assertNotIn("api_key", data)
            self.assertIn("free_terms", data)
            self.assertIn("limits", data)


class ConfigConsentTests(unittest.TestCase):
    def test_default_provider_remains_local(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["ai"]["provider"], "ollama")
        self.assertFalse(DEFAULT_CONFIG["ai"]["online"]["consent"])
        self.assertEqual(DEFAULT_CONFIG["ai"]["fallback_provider"], "offline")

    def test_online_provider_without_consent_is_rejected(self) -> None:
        config = _config_with("groq", consent=False)
        with self.assertRaises(ConfigError) as context:
            config.validate()
        self.assertIn("consent", context.exception.detail)

    def test_online_provider_with_consent_is_accepted(self) -> None:
        config = _config_with("groq", consent=True)
        config.validate()
        self.assertEqual(config.get("ai.provider"), "groq")

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            _config_with("cloud-magico").validate()


class FactoryTests(unittest.TestCase):
    def test_preset_builds_remote_provider_with_free_metadata(self) -> None:
        provider = build_primary(_config_with("groq"))
        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertEqual(provider.name, "groq")
        self.assertEqual(provider.base_url, get_preset("groq").base_url)
        self.assertTrue(provider.require_api_key)
        self.assertTrue(provider.allow_remote)
        status = provider.status()
        self.assertTrue(status["free_tier"])
        self.assertTrue(status["data_leaves_device"])
        self.assertEqual(status["preset"]["id"], "groq")

    def test_preset_without_consent_is_rejected_by_factory(self) -> None:
        with self.assertRaises(Exception):
            build_primary(_config_with("groq", consent=False))

    def test_fallback_stays_local_and_free(self) -> None:
        provider = build_provider(_config_with("groq"))
        self.assertIsInstance(provider, FallbackProvider)
        self.assertEqual(provider.name, "groq")
        self.assertEqual(provider.fallback.name, "offline")

    def test_missing_key_marks_provider_unavailable_but_not_fallback(self) -> None:
        provider = build_provider(_config_with("groq"))
        status = provider.status()
        self.assertFalse(status["available"])
        self.assertTrue(status["fallback"]["available"])
        self.assertIn("Chiave API non configurata", status["primary"]["note"])


class RemoteProbeTests(unittest.TestCase):
    def _provider(self) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            base_url="https://api.groq.com/openai/v1",
            model="openai/gpt-oss-120b",
            api_key_env="AMY_TEST_MISSING_GROQ_KEY",
            require_api_key=True,
            allow_remote=True,
            name="groq",
        )

    def test_probe_without_key_does_not_use_the_network(self) -> None:
        with mock.patch("urllib.request.urlopen") as opener:
            result = self._provider().check_remote()
        self.assertFalse(result["key_valid"])
        opener.assert_not_called()

    def test_probe_reads_models_with_the_key(self) -> None:
        payload = json.dumps({"data": [{"id": "openai/gpt-oss-120b"}]}).encode("utf-8")
        response = io.BytesIO(payload)
        response.__enter__ = lambda self=response: self  # type: ignore[attr-defined]
        response.__exit__ = lambda *args: False  # type: ignore[attr-defined]
        with mock.patch("urllib.request.urlopen", return_value=response) as opener:
            provider = self._provider()
            provider.api_key = "test-key-non-reale"
            result = provider.check_remote()
        self.assertTrue(result["key_valid"])
        self.assertTrue(result["model_available"])
        request = opener.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/models"))
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key-non-reale")
        # Cloudflare rifiuta il User-Agent predefinito di urllib con HTTP 403.
        self.assertTrue(request.get_header("User-agent").startswith("AmyBrain/"))

    def test_chat_request_declares_a_user_agent(self) -> None:
        payload = json.dumps({"choices": [{"message": {"content": "ciao"}}]}).encode("utf-8")
        response = io.BytesIO(payload)
        response.__enter__ = lambda self=response: self  # type: ignore[attr-defined]
        response.__exit__ = lambda *args: False  # type: ignore[attr-defined]
        with mock.patch("urllib.request.urlopen", return_value=response) as opener:
            provider = self._provider()
            provider.api_key = "test-key-non-reale"
            self.assertEqual(provider.chat([{"role": "user", "content": "ciao"}]), "ciao")
        request = opener.call_args[0][0]
        self.assertTrue(request.get_header("User-agent").startswith("AmyBrain/"))
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key-non-reale")

    def test_rate_limit_is_retried_once(self) -> None:
        payload = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")
        response = io.BytesIO(payload)
        response.__enter__ = lambda self=response: self  # type: ignore[attr-defined]
        response.__exit__ = lambda *args: False  # type: ignore[attr-defined]
        limited = urllib.error.HTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            429,
            "Too Many Requests",
            {"Retry-After": "0"},
            io.BytesIO(b'{"error":"rate limit"}'),
        )
        with mock.patch("urllib.request.urlopen", side_effect=[limited, response]) as opener:
            with mock.patch("amy.ai.openai_compat.time.sleep") as sleeper:
                provider = self._provider()
                provider.api_key = "test-key-non-reale"
                self.assertEqual(provider.chat([{"role": "user", "content": "ciao"}]), "ok")
        self.assertEqual(opener.call_count, 2)
        sleeper.assert_called_once()

    def test_rate_limit_twice_raises_and_falls_back(self) -> None:
        def limited() -> urllib.error.HTTPError:
            return urllib.error.HTTPError(
                "https://api.groq.com/openai/v1/chat/completions",
                429,
                "Too Many Requests",
                {"Retry-After": "0"},
                io.BytesIO(b'{"error":"rate limit"}'),
            )

        with mock.patch("urllib.request.urlopen", side_effect=[limited(), limited()]):
            with mock.patch("amy.ai.openai_compat.time.sleep"):
                provider = self._provider()
                provider.api_key = "test-key-non-reale"
                with self.assertRaises(Exception) as context:
                    provider.chat([{"role": "user", "content": "ciao"}])
        self.assertIn("Limite", str(getattr(context.exception, "message", context.exception)))


if __name__ == "__main__":
    unittest.main()
