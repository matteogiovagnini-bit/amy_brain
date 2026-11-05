"""Test degli strumenti di posta, senza leggere email reali."""

from __future__ import annotations

import unittest
from unittest import mock

from amy.macos import mail as mail_module
from amy.macos.mail import (
    MailError,
    list_accounts,
    list_messages,
    read_message,
    resolve_account,
    search_messages,
)
from amy.security.risk import RiskLevel
from amy.tools import mail_tools


def accounts() -> list:
    return [
        {"name": "Ewp", "addresses": ["info@ewp.it"]},
        {"name": "Google", "addresses": ["matteo.giovagnini@gmail.com"]},
    ]


US, RS = "\x1f", "\x1e"


class AccountsCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        mail_module._ACCOUNTS_CACHE["at"] = 0.0
        mail_module._ACCOUNTS_CACHE["items"] = []

    def test_accounts_are_cached(self) -> None:
        record = US.join(["Ewp", "info@ewp.it"]) + RS
        with mock.patch("amy.macos.mail.run_osascript", return_value=record) as runner:
            first = list_accounts(force=True)
            second = list_accounts()
        self.assertEqual(first, second)
        self.assertEqual(runner.call_count, 1)


class ResolveAccountTests(unittest.TestCase):
    def test_by_name_or_address(self) -> None:
        with mock.patch("amy.macos.mail.list_accounts", return_value=accounts()):
            self.assertEqual(resolve_account("ewp")["name"], "Ewp")
            self.assertEqual(resolve_account("info@ewp.it")["name"], "Ewp")

    def test_unknown_account_lists_alternatives(self) -> None:
        with mock.patch("amy.macos.mail.list_accounts", return_value=accounts()):
            with self.assertRaises(MailError) as context:
                resolve_account("altro@example.it")
        self.assertIn("Ewp", str(getattr(context.exception, "detail", "")))


class ListMessagesTests(unittest.TestCase):
    def test_parses_records(self) -> None:
        record = US.join(
            ["6159", "Oggetto di prova", "Mittente <m@example.it>", "false", "2026", "11", "4", "17", "21"]
        ) + RS
        with mock.patch("amy.macos.mail.list_accounts", return_value=accounts()):
            with mock.patch("amy.macos.mail.run_osascript", return_value=record) as runner:
                data = list_messages(account_name="Ewp", limit=5)
        self.assertEqual(data["messages"][0]["id"], "6159")
        self.assertEqual(data["messages"][0]["received"], "2026-11-04T17:21")
        self.assertFalse(data["messages"][0]["read"])
        self.assertIn('mailbox "INBOX" of account "Ewp"', runner.call_args[0][0])

    def test_unread_only_adds_the_filter(self) -> None:
        with mock.patch("amy.macos.mail.list_accounts", return_value=accounts()):
            with mock.patch("amy.macos.mail.run_osascript", return_value="") as runner:
                list_messages(account_name="Ewp", unread_only=True)
        self.assertIn("read status is false", runner.call_args[0][0])


class ReadMessageTests(unittest.TestCase):
    def test_reads_subject_sender_and_body(self) -> None:
        raw = US.join(
            ["Oggetto", "Mittente <m@example.it>", "2026", "11", "4", "17", "21", "Corpo del messaggio"]
        )
        with mock.patch("amy.macos.mail.list_accounts", return_value=accounts()):
            with mock.patch("amy.macos.mail.run_osascript", return_value=raw) as runner:
                data = read_message(message_id="6159", account_name="Ewp")
        self.assertEqual(data["subject"], "Oggetto")
        self.assertEqual(data["body"], "Corpo del messaggio")
        self.assertIn("whose id is 6159", runner.call_args[0][0])

    def test_rejects_non_numeric_id(self) -> None:
        with mock.patch("amy.macos.mail.list_accounts", return_value=accounts()):
            with self.assertRaises(MailError):
                read_message(message_id="../../etc/passwd", account_name="Ewp")

    def test_truncates_long_body(self) -> None:
        long_body = "x" * 9000
        raw = US.join(
            ["Oggetto", "Mittente", "2026", "11", "4", "17", "21", long_body]
        )
        with mock.patch("amy.macos.mail.list_accounts", return_value=accounts()):
            with mock.patch("amy.macos.mail.run_osascript", return_value=raw):
                data = read_message(message_id="1", account_name="Ewp", max_chars=500)
        self.assertEqual(len(data["body"]), 500)
        self.assertTrue(data["truncated"])


class SearchTests(unittest.TestCase):
    def test_filters_by_subject_or_sender(self) -> None:
        messages = {
            "account": "Ewp",
            "mailbox": "INBOX",
            "unread_only": False,
            "messages": [
                {"id": "1", "subject": "Fattura novembre", "sender": "amministrazione@example.it", "read": True, "received": ""},
                {"id": "2", "subject": "Newsletter", "sender": "info@altro.it", "read": False, "received": ""},
            ],
        }
        with mock.patch("amy.macos.mail.list_messages", return_value=dict(messages)):
            data = search_messages(query="fattura", account_name="Ewp")
        self.assertEqual([m["id"] for m in data["messages"]], ["1"])


class MailToolSpecTests(unittest.TestCase):
    def test_reading_the_body_requires_confirmation(self) -> None:
        self.assertEqual(mail_tools.MAIL_READ.risk, RiskLevel.B)

    def test_metadata_tools_are_automatic(self) -> None:
        for spec in (mail_tools.MAIL_ACCOUNTS, mail_tools.MAIL_MAILBOXES, mail_tools.MAIL_LIST, mail_tools.MAIL_SEARCH):
            self.assertEqual(spec.risk, RiskLevel.A, spec.name)


if __name__ == "__main__":
    unittest.main()
