"""Test del budget del prompt di sistema.

I piani gratuiti dei provider online hanno un limite di token al minuto stretto
(per esempio 8.000 token/minuto). Il catalogo degli strumenti inviato al modello
deve restare compatto: i campi destinati all'interfaccia non servono alla scelta
dello strumento e non vanno spediti.
"""

from __future__ import annotations

import unittest

from amy.core.prompts import build_system_prompt, model_tools_catalog
from amy.tools.builtin import build_default_registry

# Limite prudente: circa 4.000 token stimati a 4 caratteri per token. Lascia spazio
# alla conversazione e alla risposta dentro il limite gratuito di 8.000 token/minuto.
MAX_SYSTEM_PROMPT_CHARS = 16000

UI_ONLY_FIELDS = ("risk", "reason", "consequences", "undo", "tags", "timeout_s")


class PromptBudgetTests(unittest.TestCase):
    def test_system_prompt_fits_a_free_tier_minute(self) -> None:
        registry = build_default_registry()
        prompt = build_system_prompt(
            assistant_name="Amy",
            user_name="",
            tools_catalog=registry.catalog(),
            facts=[],
            robot_context="",
        )
        self.assertLess(len(prompt), MAX_SYSTEM_PROMPT_CHARS)

    def test_model_catalog_omits_ui_only_fields(self) -> None:
        slim = model_tools_catalog(build_default_registry().catalog())
        self.assertTrue(slim)
        for tool in slim:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)
            for field in UI_ONLY_FIELDS:
                self.assertNotIn(field, tool)


if __name__ == "__main__":
    unittest.main()
