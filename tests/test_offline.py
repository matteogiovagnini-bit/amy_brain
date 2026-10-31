"""Test dell'interprete locale italiano (modalità offline)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from amy.ai.offline import HELP_TEXT, OfflineProvider


def action_for(text: str) -> dict:
    raw = OfflineProvider().chat([{"role": "user", "content": text}])
    return json.loads(raw)


class OfflineProviderTests(unittest.TestCase):
    def test_time(self) -> None:
        payload = action_for("che ore sono?")
        self.assertEqual(payload["action"]["tool"], "time.now")

    def test_system_and_processes(self) -> None:
        self.assertEqual(action_for("stato del sistema")["action"]["tool"], "system.info")
        processes = action_for("mostrami i processi che usano più memoria")
        self.assertEqual(processes["action"]["tool"], "system.processes")
        self.assertEqual(processes["action"]["args"]["sort_by"], "memory")

    def test_open_app_and_url(self) -> None:
        self.assertEqual(action_for("apri Safari")["action"], {"tool": "apps.open", "args": {"name": "Safari"}})
        self.assertEqual(action_for("apri https://example.com")["action"]["tool"], "web.open")
        self.assertEqual(action_for("chiudi Note")["action"]["tool"], "apps.quit")
        self.assertEqual(action_for("porta in primo piano Terminale")["action"]["tool"], "apps.focus")

    def test_web_search(self) -> None:
        payload = action_for("cerca documentazione ESP32-S3")
        self.assertEqual(payload["action"]["tool"], "web.search")
        self.assertEqual(payload["action"]["args"]["query"], "documentazione ESP32-S3")

    def test_file_search_is_not_web_search(self) -> None:
        payload = action_for("cerca il file relazione finale")
        self.assertEqual(payload["action"]["tool"], "files.search")
        self.assertEqual(payload["action"]["args"]["query"], "relazione finale")
        plural = action_for("cerca i file bilancio")
        self.assertEqual(plural["action"]["tool"], "files.search")

    def test_read_and_list_files(self) -> None:
        read = action_for("leggi ~/Progetti/README.md")
        self.assertEqual(read["action"]["tool"], "files.read")
        self.assertEqual(read["action"]["args"]["path"], "~/Progetti/README.md")
        listing = action_for("elenca ~/Progetti")
        self.assertEqual(listing["action"]["tool"], "files.list")
        self.assertEqual(listing["action"]["args"]["path"], "~/Progetti")

    def test_read_web_page(self) -> None:
        payload = action_for("leggi https://example.com/pagina")
        self.assertEqual(payload["action"]["tool"], "web.fetch")

    def test_memory(self) -> None:
        remember = action_for("ricorda che la città è Roma")
        self.assertEqual(remember["action"]["tool"], "memory.remember")
        self.assertEqual(remember["action"]["args"], {"key": "la città", "value": "Roma"})
        colon = action_for("ricorda colore preferito: blu")
        self.assertEqual(colon["action"]["args"], {"key": "colore preferito", "value": "blu"})
        forget = action_for("dimentica colore preferito")
        self.assertEqual(forget["action"]["tool"], "memory.forget")
        listing = action_for("cosa ricordi?")
        self.assertEqual(listing["action"]["tool"], "memory.list")

    def test_robot_safety_intents(self) -> None:
        self.assertEqual(action_for("emergenza")["action"]["tool"], "robot.estop")
        self.assertEqual(action_for("ferma il robot")["action"]["tool"], "robot.stop")
        self.assertEqual(action_for("stato del robot")["action"]["tool"], "robot.status")
        self.assertEqual(action_for("metti il robot in modalità test")["action"]["tool"], "robot.mode")

    def test_conversation(self) -> None:
        self.assertEqual(OfflineProvider().chat([{"role": "user", "content": "aiuto"}]), HELP_TEXT)
        self.assertIn("Prego", OfflineProvider().chat([{"role": "user", "content": "grazie"}]))
        self.assertIn("modalità offline", OfflineProvider().chat([{"role": "user", "content": "ciao"}]))

    def test_unknown_request_does_not_invent_actions(self) -> None:
        reply = OfflineProvider().chat([{"role": "user", "content": "analizza il mio codice e riscrivilo"}])
        self.assertIn("non ho capito", reply)
        self.assertNotIn('"action"', reply)

    def test_tool_result_summary(self) -> None:
        provider = OfflineProvider()
        content = json.dumps(
            {
                "ok": True,
                "message": "Stato del robot letto.",
                "tool": "robot.status",
                "data": {
                    "mode": "TEST",
                    "battery_pct": 87,
                    "estop_latched": False,
                    "calibrated": False,
                    "simulated": True,
                },
            }
        )
        summary = provider.chat([{"role": "user", "content": "RISULTATO STRUMENTO robot.status:\n" + content}])
        self.assertIn("Movimento simulato", summary)
        self.assertIn("modalità TEST", summary)

    def test_source_has_no_cyrillic_typo(self) -> None:
        source = Path("amy/ai/offline.py").read_text(encoding="utf-8")
        self.assertNotIn("\u043e", source)
        self.assertIn("Elenca il contenuto.", source)


if __name__ == "__main__":
    unittest.main()
