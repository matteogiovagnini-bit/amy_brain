"""Test del simulatore robotico: limiti, E-stop, watchdog e deduplicazione.

Questi test verificano il *simulatore*, non l'hardware: ogni risultato è
etichettato come simulato e non dimostra nulla sul robot fisico.
"""

from __future__ import annotations

import unittest

from amy.core.errors import RobotProtocolError
from amy.robot.links import SimulatedLink
from amy.robot.protocol import ESP32_L, ESP32_T, PI_ID, make_envelope, new_req_id
from amy.robot.simulator import RobotSimulator


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def command(simulator: RobotSimulator, msg_type: str, dst: str, payload: dict, seq: int) -> dict:
    return simulator.handle(
        make_envelope(
            msg_type,
            src=PI_ID,
            dst=dst,
            payload=payload,
            req_id=new_req_id(),
            seq=seq,
        )
    )


class SimulatorTests(unittest.TestCase):
    def make(self, **kwargs) -> tuple:
        clock = FakeClock()
        simulator = RobotSimulator(clock=clock, **kwargs)
        return simulator, clock

    def test_initial_state_is_test_and_uncalibrated(self) -> None:
        simulator, _ = self.make()
        status = simulator.status()
        self.assertEqual(status["mode"], "TEST")
        self.assertFalse(status["calibrated"])
        self.assertTrue(status["simulated"])
        self.assertFalse(status["physical_motion"])
        self.assertTrue(all(limit["zero_offset_deg"] is None for limit in status["limits"]))

    def test_ready_requires_calibration(self) -> None:
        simulator, _ = self.make()
        with self.assertRaises(RobotProtocolError):
            simulator.set_mode("READY")
        simulator.simulation_calibrate()
        self.assertTrue(simulator.status()["calibrated"])
        self.assertEqual(simulator.set_mode("READY")["mode"], "READY")

    def test_simulated_move_completes(self) -> None:
        simulator, _ = self.make()
        link = SimulatedLink(simulator)
        result = link.move(
            [{"joint": "head_pan", "position_deg": 10}],
            deadline_ms=3000,
            head=True,
        )
        self.assertEqual(result["ack"]["type"], "command.ack")
        self.assertTrue(result["simulated"])
        self.assertFalse(result["physical_motion"])
        self.assertTrue(result["completion_verified"])
        self.assertEqual(result["status"]["joints"][-2]["current_deg"], 10)

    def test_sequence_is_per_destination(self) -> None:
        simulator, _ = self.make()
        link = SimulatedLink(simulator)
        link.move([{"joint": "head_pan", "position_deg": 1}], deadline_ms=3000, head=True)
        link.ping()
        self.assertEqual(simulator.last_pi_seq[ESP32_T], 1)
        self.assertEqual(simulator.last_pi_seq[ESP32_L], 1)

    def test_out_of_limits_is_rejected(self) -> None:
        simulator, _ = self.make()
        link = SimulatedLink(simulator)
        result = link.move(
            [{"joint": "head_pan", "position_deg": 90}],
            deadline_ms=3000,
            head=True,
        )
        self.assertEqual(result["ack"]["type"], "command.nack")
        self.assertEqual(result["ack"]["payload"]["code"], "out_of_limits")
        self.assertFalse(result["completion_verified"])
        self.assertEqual(simulator.status()["motion_phase"], "IDLE")

    def test_estop_blocks_motion_and_reset_requires_ack(self) -> None:
        simulator, _ = self.make()
        link = SimulatedLink(simulator)
        link.estop("test")
        self.assertTrue(simulator.status()["estop_latched"])
        blocked = link.move(
            [{"joint": "head_pan", "position_deg": 1}],
            deadline_ms=3000,
            head=True,
        )
        self.assertEqual(blocked["ack"]["payload"]["code"], "node_safe")
        with self.assertRaises(RobotProtocolError):
            link.reset_estop(operator_ack=False)
        reset = link.reset_estop(operator_ack=True)
        self.assertTrue(reset["reset"])
        self.assertFalse(simulator.status()["estop_latched"])
        self.assertEqual(simulator.status()["mode"], "TEST")

    def test_low_battery_is_rejected(self) -> None:
        simulator, _ = self.make(battery_pct=4.0)
        result = command(
            simulator,
            "motion.head",
            ESP32_T,
            {"joints": [{"joint": "head_pan", "position_deg": 1}], "deadline_ms": 3000},
            seq=1,
        )
        self.assertEqual(result["payload"]["code"], "node_degraded")

    def test_watchdog_stops_motion(self) -> None:
        simulator, clock = self.make(watchdog_timeout_s=5.0)
        accepted = command(
            simulator,
            "motion.head",
            ESP32_T,
            {"joints": [{"joint": "head_pan", "position_deg": 30}], "deadline_ms": 3000},
            seq=1,
        )
        self.assertEqual(accepted["payload"]["outcome"], "accepted")
        self.assertEqual(simulator.status()["motion_phase"], "MOVING")
        clock.advance(6.0)
        result = simulator.advance(0.1)
        self.assertIsNotNone(result)
        self.assertEqual(result["payload"]["result"], "aborted")
        self.assertEqual(simulator.status()["mode"], "SAFE")
        self.assertTrue(simulator.status()["fault_latched"])
        self.assertEqual(simulator.status()["fault_code"], "watchdog_s2")

    def test_heartbeat_prevents_watchdog(self) -> None:
        simulator, clock = self.make(watchdog_timeout_s=5.0)
        command(
            simulator,
            "motion.head",
            ESP32_T,
            {"joints": [{"joint": "head_pan", "position_deg": 30}], "deadline_ms": 3000},
            seq=1,
        )
        clock.advance(4.0)
        simulator.handle(
            make_envelope(
                "system.heartbeat",
                src=PI_ID,
                dst=ESP32_T,
                payload={},
                req_id=None,
                seq=0,
            )
        )
        clock.advance(4.0)
        simulator.advance(0.1)
        self.assertEqual(simulator.status()["mode"], "TEST")
        self.assertFalse(simulator.status()["fault_latched"])

    def test_deduplication(self) -> None:
        simulator, _ = self.make()
        envelope = make_envelope(
            "motion.head",
            src=PI_ID,
            dst=ESP32_T,
            payload={"joints": [{"joint": "head_pan", "position_deg": 1}], "deadline_ms": 3000},
            req_id=new_req_id(),
            seq=1,
        )
        first = simulator.handle(envelope)
        self.assertEqual(first["payload"]["outcome"], "accepted")
        second = simulator.handle(dict(envelope))
        self.assertEqual(second["payload"]["outcome"], "already_done")

        conflict = dict(envelope)
        conflict["payload"] = {"joints": [{"joint": "head_pan", "position_deg": 2}], "deadline_ms": 3000}
        third = simulator.handle(conflict)
        self.assertEqual(third["payload"]["code"], "duplicate_conflict")

    def test_sequence_gap_and_stale(self) -> None:
        simulator, _ = self.make()
        first = command(
            simulator,
            "command.ping",
            ESP32_L,
            {},
            seq=1,
        )
        self.assertEqual(first["payload"]["outcome"], "accepted")
        gap = command(simulator, "command.ping", ESP32_L, {}, seq=3)
        self.assertEqual(gap["payload"]["code"], "seq_gap")
        stale = command(simulator, "command.ping", ESP32_L, {}, seq=1)
        self.assertEqual(stale["payload"]["code"], "stale_seq")

    def test_controlled_stop(self) -> None:
        simulator, _ = self.make()
        command(
            simulator,
            "motion.head",
            ESP32_T,
            {"joints": [{"joint": "head_pan", "position_deg": 30}], "deadline_ms": 3000},
            seq=1,
        )
        stopped = command(
            simulator,
            "motion.stop",
            ESP32_T,
            {"reason": "test"},
            seq=2,
        )
        self.assertEqual(stopped["payload"]["result"], "aborted")
        self.assertEqual(simulator.status()["motion_phase"], "HOLD")


if __name__ == "__main__":
    unittest.main()
