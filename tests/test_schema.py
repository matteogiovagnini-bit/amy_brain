"""Test del validatore di schemi JSON ridotto."""

from __future__ import annotations

import unittest

from amy.core.errors import ToolValidationError
from amy.tools.schema import validate_arguments

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 2, "maxLength": 10},
        "count": {"type": "integer", "minimum": 1, "maximum": 5},
        "mode": {"type": "string", "enum": ["test", "ready"]},
        "flag": {"type": "boolean"},
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {"value": {"type": "number"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["name"],
    "additionalProperties": False,
}


class SchemaTests(unittest.TestCase):
    def test_valid_payload(self) -> None:
        validate_arguments(SCHEMA, {"name": "ok", "count": 3, "mode": "test", "flag": True, "items": [{"value": 1.5}]})

    def test_missing_required(self) -> None:
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"count": 1})

    def test_unknown_property(self) -> None:
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "sconosciuto": 1})

    def test_wrong_type(self) -> None:
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "count": True})
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": 123})

    def test_enum(self) -> None:
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "mode": "vola"})

    def test_limits(self) -> None:
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "x"})
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "12345678901"})
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "count": 0})
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "count": 6})

    def test_nested_items(self) -> None:
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "items": [{}]})
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "items": [{"value": 1, "extra": 2}]})
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "items": []})
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, {"name": "ok", "items": [{"value": 1}] * 3})

    def test_args_not_object(self) -> None:
        with self.assertRaises(ToolValidationError):
            validate_arguments(SCHEMA, [])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
