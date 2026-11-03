"""Test degli strumenti Promemoria, senza toccare dati reali."""

from __future__ import annotations

import unittest
from unittest import mock

from amy.macos.reminders import (
    RemindersError,
    complete_reminder,
    create_reminder,
    delete_reminder,
    list_reminders,
    resolve_list,
)
from amy.security.risk import RiskLevel
from amy.tools import reminders_tools


def lists() -> list:
    return [{"name": "Reminders", "id": "LIST-1"}, {"name": "Casa", "id": "LIST-2"}]


class ResolveListTests(unittest.TestCase):
    def test_exact_name_wins(self) -> None:
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            self.assertEqual(resolve_list("casa")["id"], "LIST-2")

    def test_unknown_name_lists_alternatives(self) -> None:
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            with self.assertRaises(RemindersError) as context:
                resolve_list("Lavoro")
        self.assertIn("Casa", str(getattr(context.exception, "detail", "")))

    def test_default_is_the_first_list(self) -> None:
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            self.assertEqual(resolve_list("")["name"], "Reminders")


class CreateReminderTests(unittest.TestCase):
    def test_creates_with_due_date_and_notes(self) -> None:
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            with mock.patch(
                "amy.macos.reminders.run_osascript", return_value="x-apple-reminder://ABC"
            ) as runner:
                data = create_reminder(name="Chiamare il dentista", due="2026-11-04T09:30", notes="Portare tessera")
        script = runner.call_args[0][0]
        self.assertEqual(data["id"], "x-apple-reminder://ABC")
        self.assertEqual(data["due"], "2026-11-04T09:30")
        self.assertIn('name:"Chiamare il dentista"', script)
        self.assertIn("set hours of dueDate to 9", script)
        self.assertIn("set minutes of dueDate to 30", script)

    def test_empty_name_is_rejected(self) -> None:
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            with self.assertRaises(RemindersError):
                create_reminder(name="   ")


class ListRemindersTests(unittest.TestCase):
    def test_parses_due_and_missing_values(self) -> None:
        us, rs = "\x1f", "\x1e"
        with_due = us.join(["ID-1", "Bollo", "false", "2026", "11", "4", "9", "30", "nota"]) + rs
        without = us.join(["ID-2", "Casa", "false", "", "", "", "", "", "missing value"]) + rs
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            with mock.patch("amy.macos.reminders.run_osascript", return_value=with_due + without):
                data = list_reminders()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["reminders"][0]["due"], "2026-11-04T09:30")
        self.assertEqual(data["reminders"][0]["notes"], "nota")
        self.assertEqual(data["reminders"][1]["due"], "")
        self.assertEqual(data["reminders"][1]["notes"], "")

    def test_limit_is_respected(self) -> None:
        us, rs = "\x1f", "\x1e"
        record = us.join(["ID-1", "Uno", "false", "", "", "", "", "", ""]) + rs
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            with mock.patch("amy.macos.reminders.run_osascript", return_value=record * 3):
                data = list_reminders(limit=2)
        self.assertEqual(len(data["reminders"]), 2)


class CompleteAndDeleteTests(unittest.TestCase):
    def test_complete_uses_id(self) -> None:
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            with mock.patch(
                "amy.macos.reminders.run_osascript", side_effect=["x-apple-reminder://ABC", "completato"]
            ) as runner:
                data = complete_reminder(identifier="x-apple-reminder://ABC")
        self.assertTrue(data["completed"])
        self.assertIn('first reminder whose id is "x-apple-reminder://ABC"', runner.call_args[0][0])

    def test_delete_by_name(self) -> None:
        with mock.patch("amy.macos.reminders.list_reminder_lists", return_value=lists()):
            with mock.patch(
                "amy.macos.reminders.run_osascript", side_effect=["x-apple-reminder://ABC", "eliminato"]
            ) as runner:
                data = delete_reminder(identifier="Bollo")
        self.assertTrue(data["deleted"])
        self.assertIn('name is "Bollo"', runner.call_args_list[0][0][0])


class RemindersToolSpecTests(unittest.TestCase):
    def test_write_actions_require_confirmation(self) -> None:
        self.assertEqual(reminders_tools.REMINDERS_CREATE.risk, RiskLevel.B)
        self.assertEqual(reminders_tools.REMINDERS_COMPLETE.risk, RiskLevel.B)

    def test_delete_is_level_c(self) -> None:
        self.assertEqual(reminders_tools.REMINDERS_DELETE.risk, RiskLevel.C)

    def test_read_actions_are_automatic(self) -> None:
        self.assertEqual(reminders_tools.REMINDERS_LISTS.risk, RiskLevel.A)
        self.assertEqual(reminders_tools.REMINDERS_LIST.risk, RiskLevel.A)


if __name__ == "__main__":
    unittest.main()
