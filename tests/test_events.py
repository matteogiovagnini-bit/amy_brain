"""Test del bus di eventi locale."""

from __future__ import annotations

import threading
import unittest

from amy.shared.events import ALL_TOPICS, EventBus


class EventBusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus(history_size=20)
        self.received = []

    def tearDown(self) -> None:
        self.bus.close()

    def test_delivers_to_topic_and_history(self) -> None:
        self.bus.subscribe("voice.state", self.received.append)
        self.bus.publish("voice.state", {"state": "listening"})
        self.assertTrue(self.bus.flush())
        self.assertEqual(self.received[0].payload["state"], "listening")
        history = self.bus.history()
        self.assertEqual(history[-1]["topic"], "voice.state")

    def test_wildcard_receives_everything(self) -> None:
        self.bus.subscribe(ALL_TOPICS, self.received.append)
        self.bus.publish("a", {"n": 1})
        self.bus.publish("b", {"n": 2})
        self.assertTrue(self.bus.flush())
        self.assertEqual([event.topic for event in self.received], ["a", "b"])

    def test_listener_error_does_not_stop_the_others(self) -> None:
        def broken(event):
            raise RuntimeError("rotto")

        self.bus.subscribe("t", broken)
        self.bus.subscribe("t", self.received.append)
        self.bus.publish("t", {"ok": True})
        self.assertTrue(self.bus.flush())
        self.assertEqual(len(self.received), 1)

    def test_unsubscribe(self) -> None:
        unsubscribe = self.bus.subscribe("t", self.received.append)
        unsubscribe()
        self.bus.publish("t", {})
        self.assertTrue(self.bus.flush())
        self.assertEqual(self.received, [])

    def test_history_is_bounded(self) -> None:
        bus = EventBus(history_size=2)
        try:
            for index in range(5):
                bus.publish("t", {"i": index})
            self.assertTrue(bus.flush())
            self.assertEqual(len(bus.history()), 2)
        finally:
            bus.close()

    def test_many_publishers_are_serialized(self) -> None:
        self.bus.subscribe("t", self.received.append)

        def publish(index):
            for _ in range(20):
                self.bus.publish("t", {"i": index})

        threads = [threading.Thread(target=publish, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertTrue(self.bus.flush())
        self.assertEqual(len(self.received), 80)


if __name__ == "__main__":
    unittest.main()
