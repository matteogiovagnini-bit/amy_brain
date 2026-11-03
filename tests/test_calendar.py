"""Test degli strumenti Calendar.

Non creano eventi reali: AppleScript è sostituito da un mock. Verificano la
costruzione delle date, l'escaping dei testi, la scelta del calendario e il
livello di rischio (la creazione richiede conferma).
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest import mock

from amy.macos.calendar import (
    CalendarError,
    create_event,
    list_events,
    parse_start,
    resolve_calendar,
)
from amy.security.risk import RiskLevel
from amy.tools import calendar_tools


def calendars() -> list:
    return [
        {"name": "Lavoro", "writable": True},
        {"name": "Calendario", "writable": True},
        {"name": "Festività in Italia", "writable": False},
        {"name": "Compleanni", "writable": False},
    ]


class ParseStartTests(unittest.TestCase):
    def test_accepts_iso_and_space(self) -> None:
        self.assertEqual(parse_start("2026-11-04T16:00"), datetime(2026, 11, 4, 16, 0))
        self.assertEqual(parse_start("2026-11-04 16:30"), datetime(2026, 11, 4, 16, 30))

    def test_accepts_date_only(self) -> None:
        self.assertEqual(parse_start("2026-11-04"), datetime(2026, 11, 4, 0, 0))

    def test_rejects_invalid_text(self) -> None:
        with self.assertRaises(CalendarError):
            parse_start("domani alle quattro")


class ResolveCalendarTests(unittest.TestCase):
    def test_exact_name_wins(self) -> None:
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            chosen = resolve_calendar("lavoro")
        self.assertEqual(chosen["name"], "Lavoro")

    def test_unknown_name_lists_alternatives(self) -> None:
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with self.assertRaises(CalendarError) as context:
                resolve_calendar("Personale")
        self.assertIn("Calendario", str(context.exception))

    def test_default_skips_system_calendars(self) -> None:
        rows = [
            {"name": "Compleanni", "writable": True},
            {"name": "Personale", "writable": True},
        ]
        with mock.patch("amy.macos.calendar.list_calendars", return_value=rows):
            chosen = resolve_calendar("", default_name="Calendario")
        self.assertEqual(chosen["name"], "Personale")

    def test_no_writable_calendar_is_an_error(self) -> None:
        with mock.patch(
            "amy.macos.calendar.list_calendars",
            return_value=[{"name": "Festività", "writable": False}],
        ):
            with self.assertRaises(CalendarError):
                resolve_calendar("")


class CreateEventTests(unittest.TestCase):
    def _create(self, **kwargs):
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.run_osascript", return_value="UID-123") as runner:
                result = create_event(**kwargs)
        return result, runner.call_args[0][0]

    def test_creates_event_with_components_and_escaping(self) -> None:
        result, script = self._create(
            title='Colloquio "importante"',
            start="2026-11-04T16:00",
            duration_minutes=30,
        )
        self.assertEqual(result["uid"], "UID-123")
        self.assertEqual(result["start"], "2026-11-04T16:00")
        self.assertEqual(result["end"], "2026-11-04T16:30")
        self.assertIn('summary:"Colloquio \\"importante\\""', script)
        self.assertIn("set year of startDate to 2026", script)
        self.assertIn("set hours of startDate to 16", script)
        self.assertIn("set minutes of endDate to 30", script)
        self.assertIn("allday event:false", script)

    def test_all_day_event_ends_next_day(self) -> None:
        result, script = self._create(title="Festa", start="2026-11-04", all_day=True)
        self.assertTrue(result["all_day"])
        self.assertEqual(result["end"], "2026-11-05T00:00")
        self.assertIn("allday event:true", script)

    def test_empty_title_is_rejected(self) -> None:
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with self.assertRaises(CalendarError):
                create_event(title="   ", start="2026-11-04T16:00")

    def test_duration_is_limited(self) -> None:
        result, _ = self._create(title="Lunga", start="2026-11-04T09:00", duration_minutes=5000)
        self.assertEqual(result["duration_minutes"], 24 * 60)


class ListEventsTests(unittest.TestCase):
    def test_reads_records_and_sorts_them(self) -> None:
        us = "\x1f"
        rs = "\x1e"
        # Dieci campi numerici, titolo, record separato.
        first = us.join(["2026", "11", "4", "9", "0", "2026", "11", "4", "10", "0", "Presto"]) + rs
        second = us.join(["2026", "11", "4", "17", "0", "2026", "11", "4", "18", "0", "Tardi"]) + rs
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.run_osascript", return_value=first + second):
                data = list_events(date="2026-11-04")
        self.assertEqual([item["title"] for item in data["events"]], ["Presto", "Tardi"])
        self.assertEqual(data["events"][0]["start"], "2026-11-04T09:00")


class CalendarToolSpecTests(unittest.TestCase):
    def test_creating_an_event_requires_confirmation(self) -> None:
        self.assertEqual(calendar_tools.CALENDAR_CREATE.risk, RiskLevel.B)
        self.assertIn("calendar.create", calendar_tools.CALENDAR_CREATE.name)

    def test_reading_events_is_automatic(self) -> None:
        self.assertEqual(calendar_tools.CALENDAR_LIST.risk, RiskLevel.A)
        self.assertEqual(calendar_tools.CALENDAR_EVENTS.risk, RiskLevel.A)


if __name__ == "__main__":
    unittest.main()
