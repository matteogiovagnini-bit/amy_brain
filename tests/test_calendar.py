"""Test degli strumenti Calendar.

Non creano eventi reali: AppleScript è sostituito da un mock. Verificano la
costruzione delle date, l'escaping dei testi, la scelta del calendario e il
livello di rischio (la creazione richiede conferma).
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime
from unittest import mock

from amy.macos.calendar import (
    CalendarError,
    create_event,
    delete_event,
    update_event,
    list_events,
    parse_start,
    resolve_calendar,
)
from amy.security.risk import RiskLevel
from amy.tools import calendar_tools
from amy.tools.base import FunctionTool
from amy.tools.registry import ToolRegistry


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
        first = us.join(["2026", "11", "4", "9", "0", "2026", "11", "4", "10", "0", "Presto", "UID-A"]) + rs
        second = us.join(["2026", "11", "4", "17", "0", "2026", "11", "4", "18", "0", "Tardi", "UID-B"]) + rs
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.run_osascript", return_value=first + second):
                data = list_events(date="2026-11-04")
        self.assertEqual([item["title"] for item in data["events"]], ["Presto", "Tardi"])
        self.assertEqual(data["events"][0]["start"], "2026-11-04T09:00")
        self.assertEqual(data["events"][0]["uid"], "UID-A")




class DeleteEventTests(unittest.TestCase):
    def test_deletes_by_uid(self) -> None:
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.run_osascript", return_value="eliminato") as runner:
                data = delete_event(uid="UID-1")
        self.assertTrue(data["deleted"])
        self.assertIn('whose uid is "UID-1"', runner.call_args[0][0])

    def test_deletes_by_title_and_date(self) -> None:
        day = {
            "date": "2026-11-04",
            "calendar": "Calendario",
            "events": [{"uid": "UID-2", "title": "Dentista", "start": "2026-11-04T16:00", "end": "2026-11-04T17:00"}],
        }
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.list_events", return_value=day):
                with mock.patch("amy.macos.calendar.run_osascript", return_value="eliminato") as runner:
                    data = delete_event(title="dentista", date="2026-11-04")
        self.assertEqual(data["uid"], "UID-2")
        self.assertIn('whose uid is "UID-2"', runner.call_args[0][0])

    def test_missing_event_is_reported(self) -> None:
        day = {"date": "2026-11-04", "calendar": "Calendario", "events": []}
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.list_events", return_value=day):
                with self.assertRaises(CalendarError):
                    delete_event(title="Dentista", date="2026-11-04")

    def test_ambiguous_title_requires_uid(self) -> None:
        day = {
            "date": "2026-11-04",
            "calendar": "Calendario",
            "events": [
                {"uid": "UID-1", "title": "Dentista", "start": "2026-11-04T09:00", "end": "2026-11-04T10:00"},
                {"uid": "UID-2", "title": "Dentista", "start": "2026-11-04T16:00", "end": "2026-11-04T17:00"},
            ],
        }
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.list_events", return_value=day):
                with self.assertRaises(CalendarError) as context:
                    delete_event(title="Dentista", date="2026-11-04")
        self.assertIn("UID", str(context.exception))


def upcoming_registry():
    registry = ToolRegistry()
    calendar_tools.register(registry)
    return registry


def upcoming_context():
    context = mock.Mock()
    context.config.get.return_value = "Calendario"
    return context


def fake_event(uid, title, start, end, calendar="Calendario"):
    return {"uid": uid, "title": title, "start": start, "end": end, "calendar": calendar}


def fake_day(date, events, calendar="Calendario"):
    return {"date": date, "calendar": calendar, "events": events}


class UpcomingEventsTests(unittest.TestCase):
    """Il riquadro della dashboard legge solo tramite calendar.events (livello A)."""

    def test_reads_each_day_with_calendar_events(self) -> None:
        registry = upcoming_registry()
        days = [
            fake_day("2026-11-06", [fake_event("U1", "Riunione", "2026-11-06T10:00", "2026-11-06T11:00")]),
            fake_day("2026-11-07", []),
            fake_day("2026-11-08", [fake_event("U2", "Dentista", "2026-11-08T16:00", "2026-11-08T17:00")]),
        ]
        with mock.patch("amy.tools.calendar_tools.list_events", side_effect=days) as reader:
            with mock.patch.object(registry, "execute", wraps=registry.execute) as execute:
                data = calendar_tools.collect_upcoming(
                    registry, upcoming_context(), days=3, now=datetime(2026, 11, 6, 9, 0)
                )
        self.assertTrue(data["available"])
        self.assertEqual(data["days"], 3)
        self.assertEqual(data["checked_days"], 3)
        self.assertEqual(data["failed_days"], 0)
        self.assertEqual(data["calendar"], "Calendario")
        self.assertEqual([item["title"] for item in data["events"]], ["Riunione", "Dentista"])
        # Ogni lettura passa dallo strumento esistente, non da una chiamata diretta.
        self.assertEqual([call[0][0] for call in execute.call_args_list], ["calendar.events"] * 3)
        self.assertEqual([call[0][1]["date"] for call in execute.call_args_list],
                         ["2026-11-06", "2026-11-07", "2026-11-08"])
        self.assertEqual(reader.call_count, 3)

    def test_drops_past_events_sorts_and_limits(self) -> None:
        day = fake_day("2026-11-06", [
            fake_event("U1", "Già finito", "2026-11-06T08:00", "2026-11-06T08:30"),
            fake_event("U2", "Tardi", "2026-11-06T18:00", "2026-11-06T19:00"),
            fake_event("U3", "Presto", "2026-11-06T10:00", "2026-11-06T11:00"),
            fake_event("U4", "Mezzogiorno", "2026-11-06T12:00", "2026-11-06T13:00"),
        ])
        with mock.patch("amy.tools.calendar_tools.list_events", return_value=day):
            data = calendar_tools.collect_upcoming(
                upcoming_registry(), upcoming_context(), days=1, limit=2,
                now=datetime(2026, 11, 6, 9, 0),
            )
        self.assertEqual([item["title"] for item in data["events"]], ["Presto", "Mezzogiorno"])

    def test_deduplicates_events_spanning_more_days(self) -> None:
        shared = fake_event("U-LUNGO", "Conferenza", "2026-11-06T09:00", "2026-11-08T18:00")
        days = [
            fake_day("2026-11-06", [shared]),
            fake_day("2026-11-07", [shared]),
            fake_day("2026-11-08", [shared, fake_event("U2", "Cena", "2026-11-08T20:00", "2026-11-08T21:00")]),
        ]
        with mock.patch("amy.tools.calendar_tools.list_events", side_effect=days):
            data = calendar_tools.collect_upcoming(
                upcoming_registry(), upcoming_context(), days=3, now=datetime(2026, 11, 6, 8, 0)
            )
        self.assertEqual([item["title"] for item in data["events"]], ["Conferenza", "Cena"])

    def test_declares_unavailable_when_every_day_fails(self) -> None:
        with mock.patch("amy.tools.registry._log"):
            with mock.patch("amy.tools.calendar_tools.list_events", side_effect=RuntimeError("negato")):
                data = calendar_tools.collect_upcoming(
                    upcoming_registry(), upcoming_context(), days=2, now=datetime(2026, 11, 6, 9, 0)
                )
        self.assertFalse(data["available"])
        self.assertEqual(data["events"], [])
        self.assertEqual(data["failed_days"], 2)
        self.assertTrue(data["reason"])

    def test_reports_partial_failure_without_inventing_events(self) -> None:
        def by_date(**kwargs):
            day = kwargs["date"]
            if day == "2026-11-07":
                raise RuntimeError("giorno non leggibile")
            return fake_day(day, [
                fake_event("U-" + day, "Riunione", day + "T10:00", day + "T11:00")
            ])

        with mock.patch("amy.tools.registry._log"):
            with mock.patch("amy.tools.calendar_tools.list_events", side_effect=by_date):
                data = calendar_tools.collect_upcoming(
                    upcoming_registry(), upcoming_context(), days=3, now=datetime(2026, 11, 6, 9, 0)
                )
        self.assertTrue(data["available"])
        self.assertEqual(data["failed_days"], 1)
        self.assertEqual(data["checked_days"], 2)
        self.assertIn("Lettura parziale", data["reason"])
        self.assertEqual(len(data["events"]), 2)

    def test_blocks_the_read_if_the_tool_is_no_longer_level_a(self) -> None:
        registry = ToolRegistry()
        registry.register(FunctionTool(
            replace(calendar_tools.CALENDAR_EVENTS, risk=RiskLevel.B), lambda args, ctx: None
        ))
        with mock.patch("amy.tools.calendar_tools.list_events") as reader:
            data = calendar_tools.collect_upcoming(
                registry, upcoming_context(), days=2, now=datetime(2026, 11, 6, 9, 0)
            )
        self.assertFalse(data["available"])
        self.assertEqual(data["events"], [])
        self.assertIn("livello A", data["reason"])
        reader.assert_not_called()

    def test_the_window_is_clamped(self) -> None:
        empty = fake_day("2026-11-06", [])
        registry = upcoming_registry()
        with mock.patch("amy.tools.calendar_tools.list_events", return_value=empty):
            with mock.patch.object(registry, "execute", wraps=registry.execute) as execute:
                short = calendar_tools.collect_upcoming(
                    registry, upcoming_context(), days=0, now=datetime(2026, 11, 6, 9, 0)
                )
        self.assertEqual(short["days"], 1)
        self.assertEqual(len(execute.call_args_list), 1)
        registry = upcoming_registry()
        with mock.patch("amy.tools.calendar_tools.list_events", return_value=empty):
            with mock.patch.object(registry, "execute", wraps=registry.execute) as execute:
                long = calendar_tools.collect_upcoming(
                    registry, upcoming_context(), days=99, now=datetime(2026, 11, 6, 9, 0)
                )
        self.assertEqual(long["days"], 14)
        self.assertEqual(len(execute.call_args_list), 14)


class CalendarUpdateTests(unittest.TestCase):
    def test_updates_by_uid_with_new_title_and_time(self) -> None:
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.run_osascript", return_value="aggiornato") as runner:
                data = update_event(
                    uid="UID-1",
                    new_title="Riunione spostata",
                    start="2026-11-04T11:00",
                    duration_minutes=45,
                )
        script = runner.call_args[0][0]
        self.assertTrue(data["updated"])
        self.assertIn('set summary of theEvent to "Riunione spostata"', script)
        self.assertIn("set hours of startDate to 11", script)
        self.assertIn("set hours of endDate to 11", script)
        self.assertIn("set minutes of endDate to 45", script)

    def test_updates_by_title_and_date(self) -> None:
        day = {
            "date": "2026-11-04",
            "calendar": "Calendario",
            "events": [{"uid": "UID-2", "title": "Dentista", "start": "2026-11-04T16:00", "end": "2026-11-04T17:00"}],
        }
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with mock.patch("amy.macos.calendar.list_events", return_value=day):
                with mock.patch("amy.macos.calendar.run_osascript", return_value="aggiornato") as runner:
                    data = update_event(title="dentista", date="2026-11-04", notes="nuova nota")
        self.assertEqual(data["uid"], "UID-2")
        self.assertIn('set description of theEvent to "nuova nota"', runner.call_args[0][0])

    def test_no_changes_are_refused(self) -> None:
        with mock.patch("amy.macos.calendar.list_calendars", return_value=calendars()):
            with self.assertRaises(CalendarError):
                update_event(uid="UID-1")

    def test_update_requires_confirmation(self) -> None:
        from amy.tools import calendar_tools
        self.assertEqual(calendar_tools.CALENDAR_UPDATE.risk, RiskLevel.B)

class CalendarToolSpecTests(unittest.TestCase):
    def test_creating_an_event_requires_confirmation(self) -> None:
        self.assertEqual(calendar_tools.CALENDAR_CREATE.risk, RiskLevel.B)
        self.assertIn("calendar.create", calendar_tools.CALENDAR_CREATE.name)

    def test_reading_events_is_automatic(self) -> None:
        self.assertEqual(calendar_tools.CALENDAR_LIST.risk, RiskLevel.A)
        self.assertEqual(calendar_tools.CALENDAR_EVENTS.risk, RiskLevel.A)


if __name__ == "__main__":
    unittest.main()
