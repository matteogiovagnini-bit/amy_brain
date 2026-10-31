"""Test della cache delle voci macOS.

`say -v ?` costa alcuni secondi: l'elenco delle voci italiane deve essere
calcolato una sola volta per processo, altrimenti ogni richiesta di stato
rallenta la dashboard (e il self-test dell'app nativa).
"""

from __future__ import annotations

import unittest

from amy.voice.tts import MacSayTTS


class MacSayTTSCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls = 0
        # Si salva il descrittore originale (staticmethod), non la funzione:
        # riassegnare la funzione nuda la renderebbe metodo di istanza.
        self.original = MacSayTTS.__dict__["voices"]

        def fake_voices():
            self.calls += 1
            return [
                {"name": "Alice", "locale": "it_IT", "sample": "ciao"},
                {"name": "Alex", "locale": "en_US", "sample": "hello"},
            ]

        MacSayTTS.voices = staticmethod(fake_voices)  # type: ignore[assignment]

    def tearDown(self) -> None:
        MacSayTTS.voices = self.original  # type: ignore[assignment]

    def test_status_computes_voices_only_once(self) -> None:
        tts = MacSayTTS("Alice", 185)
        first = tts.status()
        second = tts.status()
        self.assertEqual(first["italian_voices"], ["Alice"])
        self.assertEqual(second["italian_voices"], ["Alice"])
        self.assertEqual(self.calls, 1, "l'elenco delle voci non va ricalcolato a ogni stato")

    def test_italian_voices_helper_is_cached(self) -> None:
        tts = MacSayTTS("Alice", 185)
        self.assertEqual(tts.italian_voices(), ["Alice"])
        self.assertEqual(tts.italian_voices(), ["Alice"])
        self.assertEqual(self.calls, 1)


if __name__ == "__main__":
    unittest.main()
