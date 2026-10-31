"""Test del protocollo robotico v1 e della validazione dei movimenti."""

from __future__ import annotations

import unittest

from amy.core.errors import RobotProtocolError
from amy.robot.protocol import (
    ESP32_L,
    ESP32_T,
    PI_ID,
    command_topic,
    default_limits,
    make_envelope,
    new_req_id,
    validate_envelope,
    validate_motion_target,
)


class ProtocolTests(unittest.TestCase):
    def test_req_id_is_ulid_like(self) -> None:
        req_id = new_req_id()
        self.assertEqual(len(req_id), 26)
        self.assertTrue(all(char in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in req_id))
        self.assertLessEqual(new_req_id(1000), new_req_id(2000))

    def test_valid_envelope(self) -> None:
        envelope = make_envelope(
            "command.ping",
            src=PI_ID,
            dst=ESP32_L,
            payload={},
            req_id=new_req_id(),
            seq=1,
        )
        self.assertIs(validate_envelope(envelope), envelope)

    def test_envelope_rejects_extra_fields(self) -> None:
        envelope = make_envelope("command.ping", src=PI_ID, dst=ESP32_L, payload={}, req_id=new_req_id(), seq=1)
        envelope["extra"] = True
        with self.assertRaises(RobotProtocolError):
            validate_envelope(envelope)

    def test_envelope_rejects_bad_source_and_version(self) -> None:
        envelope = make_envelope("command.ping", src="altro", dst=ESP32_L, payload={}, req_id=new_req_id(), seq=1)
        with self.assertRaises(RobotProtocolError):
            validate_envelope(envelope)
        envelope["src"] = PI_ID
        envelope["v"] = 99
        with self.assertRaises(RobotProtocolError):
            validate_envelope(envelope)

    def test_device_cannot_send_commands(self) -> None:
        envelope = make_envelope("motion.target", src=ESP32_L, dst=PI_ID, payload={}, req_id=new_req_id(), seq=1)
        with self.assertRaises(RobotProtocolError):
            validate_envelope(envelope)

    def test_motion_target_validation(self) -> None:
        limits = {limit.joint: limit for limit in default_limits()}
        validated = validate_motion_target(
            {
                "joints": [
                    {"joint": "head_pan", "position_deg": 10, "speed_limit_dps": 1000},
                    {"joint": "head_tilt", "position_deg": 5},
                ],
                "deadline_ms": 3000,
                "limits_version": 1,
            },
            {name: limits[name] for name in ("head_pan", "head_tilt")},
        )
        self.assertEqual(len(validated), 2)
        self.assertEqual(validated[0]["speed_limit_dps"], limits["head_pan"].max_speed_dps)
        self.assertIn("speed_limit_dps", validated[0]["clamped"])

    def test_motion_target_rejects_invalid_values(self) -> None:
        limits = {limit.joint: limit for limit in default_limits()}
        head = {name: limits[name] for name in ("head_pan", "head_tilt")}
        with self.assertRaises(RobotProtocolError):
            validate_motion_target({"joints": []}, head)
        with self.assertRaises(RobotProtocolError):
            validate_motion_target({"joints": [{"joint": "head_pan", "position_deg": 999}]}, head)
        with self.assertRaises(RobotProtocolError):
            validate_motion_target(
                {"joints": [{"joint": "head_pan", "position_deg": 1}, {"joint": "head_pan", "position_deg": 2}]},
                head,
            )
        with self.assertRaises(RobotProtocolError):
            validate_motion_target({"joints": [{"joint": "sconosciuto", "position_deg": 1}]}, head)
        with self.assertRaises(RobotProtocolError):
            validate_motion_target({"joints": [{"joint": "head_pan", "position_deg": 1}], "deadline_ms": 0}, head)
        with self.assertRaises(RobotProtocolError):
            validate_motion_target(
                {"joints": [{"joint": "head_pan", "position_deg": float("nan")}]},
                head,
            )

    def test_command_topics(self) -> None:
        self.assertEqual(command_topic("motion.target", ESP32_L), "amy/motion/esp32-l/target")
        self.assertEqual(command_topic("motion.head", ESP32_T), "amy/motion/esp32-t/head")
        self.assertEqual(command_topic("motion.stop", ESP32_L), "amy/motion/all/stop")
        self.assertEqual(command_topic("command.request", ESP32_L), "amy/commands/esp32-l/request")
        self.assertIsNone(command_topic("motion.target", ESP32_T))


if __name__ == "__main__":
    unittest.main()
