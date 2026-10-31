"""Test del vincolo globale: Amy non deve introdurre costi obbligatori."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from amy.core.config import DEFAULT_CONFIG, is_local_endpoint

ROOT = Path(__file__).resolve().parent.parent

# Host di servizi IA commerciali noti. Non devono comparire nel codice: un
# eventuale endpoint compatibile OpenAI deve essere locale o esplicitamente scelto
# dall'utente nella propria configurazione, non cablato nel progetto.
PAID_HOSTS = (
    "api.openai.com",
    "api.anthropic.com",
    "openai.azure.com",
    "generativelanguage.googleapis.com",
    "api.cohere.ai",
    "api.mistral.ai",
)

OPTIONAL_DEPENDENCIES_ALLOWED = {"paho-mqtt"}


class FreeOnlyTests(unittest.TestCase):
    def test_no_mandatory_python_dependencies(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        project = text.split("[project]", 1)[1].split("[project.optional-dependencies]", 1)[0]
        self.assertRegex(project, r"dependencies\s*=\s*\[\s*\]")

    def test_optional_dependencies_are_known_free(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        optional = text.split("[project.optional-dependencies]", 1)[1].split(
            "[project.scripts]", 1
        )[0]
        listed = set(re.findall(r'"([A-Za-z0-9_.-]+)', optional))
        self.assertLessEqual(
            listed,
            OPTIONAL_DEPENDENCIES_ALLOWED,
            "Dipendenza opzionale non verificata: %s" % sorted(listed - OPTIONAL_DEPENDENCIES_ALLOWED),
        )

    def test_optional_requirements_have_no_billing_terms(self) -> None:
        text = (ROOT / "requirements-optional.txt").read_text(encoding="utf-8").lower()
        for word in ("stripe", "billing", "subscription", "premium", "paid"):
            self.assertNotIn(word, text)

    def test_default_ai_is_local_and_free(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["ai"]["provider"], "ollama")
        self.assertEqual(DEFAULT_CONFIG["ai"]["fallback_provider"], "offline")
        self.assertTrue(is_local_endpoint(DEFAULT_CONFIG["ai"]["base_url"]))
        self.assertTrue(is_local_endpoint(DEFAULT_CONFIG["ai"]["openai"]["base_url"]))
        self.assertFalse(DEFAULT_CONFIG["ai"]["openai"]["allow_remote"])
        self.assertFalse(DEFAULT_CONFIG["ai"]["openai"]["require_api_key"])

    def test_no_paid_ai_hosts_are_hardcoded(self) -> None:
        offenders = []
        for path in (ROOT / "amy").rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for host in PAID_HOSTS:
                if host in text:
                    offenders.append("%s: %s" % (path, host))
        self.assertEqual(offenders, [])

    def test_default_config_has_no_billing_fields(self) -> None:
        # La configurazione predefinita non deve contenere chiavi che suggeriscano
        # piani, crediti o fatturazione.
        text = repr(DEFAULT_CONFIG).lower()
        for word in ("billing", "subscription", "premium", "credits", "paid_plan"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
