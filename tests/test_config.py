"""Test dei test: Amy non deve mai dipendere dalla macchina di sviluppo."""

from __future__ import annotations

import copy
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from amy.core.config import (
    DEFAULT_CONFIG,
    Config,
    ConfigError,
    get_secret,
    init_config,
    is_local_endpoint,
    load_secrets,
)
from tests.helpers import TempAmy


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()

    def tearDown(self) -> None:
        self.temp.close()

    def test_defaults_are_coherent(self) -> None:
        config = Config(copy.deepcopy(DEFAULT_CONFIG), self.temp.home / "config.json")
        config.validate()
        self.assertIn(config.get("ai.provider"), {"ollama", "openai", "offline"})
        self.assertIn(config.get("robot.transport"), {"simulated", "mqtt"})
        self.assertEqual(config.get("ui.host"), "127.0.0.1")
        self.assertTrue(config.allowed_roots())

    def test_defaults_are_free_only(self) -> None:
        config = Config(copy.deepcopy(DEFAULT_CONFIG), self.temp.home / "config.json")
        self.assertEqual(config.get("ai.provider"), "ollama")
        self.assertEqual(config.get("ai.fallback_provider"), "offline")
        self.assertTrue(config.get("ai.base_url").startswith("http://127.0.0.1"))
        self.assertTrue(is_local_endpoint(config.get("ai.openai.base_url")))
        self.assertFalse(config.get("ai.openai.allow_remote"))
        self.assertFalse(config.get("ai.openai.require_api_key"))

    def test_remote_openai_endpoint_requires_explicit_consent(self) -> None:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["ai"]["provider"] = "openai"
        data["ai"]["openai"]["base_url"] = "https://api.example-paid.invalid/v1"
        with self.assertRaises(ConfigError):
            Config(data, self.temp.home / "config.json").validate()

    def test_remote_openai_endpoint_can_be_enabled_explicitly(self) -> None:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["ai"]["provider"] = "openai"
        data["ai"]["openai"]["base_url"] = "https://api.example-free.invalid/v1"
        data["ai"]["openai"]["allow_remote"] = True
        Config(data, self.temp.home / "config.json").validate()

    def test_private_openai_endpoint_is_allowed(self) -> None:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["ai"]["provider"] = "openai"
        data["ai"]["openai"]["base_url"] = "http://192.168.1.50:8000/v1"
        Config(data, self.temp.home / "config.json").validate()

    def test_paid_fallback_provider_is_rejected(self) -> None:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["ai"]["fallback_provider"] = "openai"
        with self.assertRaises(ConfigError):
            Config(data, self.temp.home / "config.json").validate()

    def test_openai_url_scheme_is_validated(self) -> None:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["ai"]["provider"] = "openai"
        data["ai"]["openai"]["base_url"] = "ftp://127.0.0.1/v1"
        data["ai"]["openai"]["allow_remote"] = True
        with self.assertRaises(ConfigError):
            Config(data, self.temp.home / "config.json").validate()

    def test_invalid_provider_is_rejected(self) -> None:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["ai"]["provider"] = "cloud-magico"
        with self.assertRaises(ConfigError):
            Config(data, self.temp.home / "config.json").validate()

    def test_invalid_robot_transport_is_rejected(self) -> None:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["robot"]["transport"] = "seriale"
        with self.assertRaises(ConfigError):
            Config(data, self.temp.home / "config.json").validate()

    def test_env_overrides(self) -> None:
        path = self.temp.home / "config.json"
        env = {
            "AMY_AI_PROVIDER": "offline",
            "AMY_AI_MODEL": "modello-test",
            "AMY_UI_PORT": "9123",
            "AMY_ROBOT_TRANSPORT": "simulated",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            config = Config.load(path=path)
        self.assertEqual(config.get("ai.provider"), "offline")
        self.assertEqual(config.get("ai.model"), "modello-test")
        self.assertEqual(config.get("ui.port"), 9123)
        self.assertEqual(config.get("robot.transport"), "simulated")

    def test_invalid_env_number_is_rejected(self) -> None:
        with mock.patch.dict(os.environ, {"AMY_UI_PORT": "non-un-numero"}, clear=False):
            with self.assertRaises(ConfigError):
                Config.load(path=self.temp.home / "config.json")

    def test_save_and_redacted(self) -> None:
        config = self.temp.config
        config.data["secrets"] = {"token": "da-non-mostrare"}
        path = config.save()
        self.assertTrue(path.exists())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0)
        redacted = config.redacted()
        self.assertNotIn("secrets", redacted)

    def test_init_does_not_overwrite(self) -> None:
        path = self.temp.home / "config.json"
        created = init_config(path=path)
        self.assertTrue(created.exists())
        original = created.read_text(encoding="utf-8")
        again = init_config(path=path)
        self.assertEqual(again, created)
        self.assertEqual(again.read_text(encoding="utf-8"), original)

    def test_load_secrets_requires_private_permissions(self) -> None:
        secrets_path = self.temp.home / "secrets.json"
        secrets_path.write_text(json.dumps({"OPENAI_API_KEY": "segreto"}), encoding="utf-8")
        os.chmod(secrets_path, 0o600)
        self.assertEqual(load_secrets(secrets_path)["OPENAI_API_KEY"], "segreto")
        os.chmod(secrets_path, 0o644)
        with self.assertRaises(ConfigError):
            load_secrets(secrets_path)

    def test_get_secret_required(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMY_TEST_MISSING_SECRET", None)
            with self.assertRaises(ConfigError):
                get_secret("AMY_TEST_MISSING_SECRET", required=True, secrets={})

    def test_path_value_expands_user(self) -> None:
        config = self.temp.config
        value = config.path_value("memory.db_path")
        self.assertTrue(value.is_absolute())
        self.assertNotIn("~", str(value))


if __name__ == "__main__":
    unittest.main()
