"""Validatore di schemi JSON ridotto, senza dipendenze esterne.

Supporta il sottoinsieme usato dagli strumenti di Amy: oggetti, stringhe,
numeri, interi, booleani, array, enum, limiti, pattern e proprietà obbligatorie.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ..core.errors import ToolValidationError


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if expected == "null":
        return value is None
    return False


def validate_arguments(schema: Dict[str, Any], args: Dict[str, Any], *, path: str = "argomenti") -> None:
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolValidationError(
            "I parametri devono essere un oggetto JSON.",
            detail="%s: ricevuto %s" % (path, _type_name(args)),
        )

    expected_type = schema.get("type")
    if expected_type and not _matches_type(args, expected_type):
        raise ToolValidationError("Tipo dei parametri non valido: atteso %s." % expected_type)

    properties: Dict[str, Any] = schema.get("properties", {}) or {}
    required: List[str] = schema.get("required", []) or []

    for key in required:
        if key not in args:
            raise ToolValidationError("Parametro obbligatorio mancante: %s." % key)

    if schema.get("additionalProperties", False) is False:
        unknown = [key for key in args if key not in properties]
        if unknown:
            raise ToolValidationError(
                "Parametri non riconosciuti: %s." % ", ".join(sorted(unknown)),
                detail="Parametri ammessi: %s" % ", ".join(sorted(properties)),
            )

    for key, value in args.items():
        child_schema = properties.get(key)
        if not child_schema:
            continue
        _validate_value(child_schema, value, "%s.%s" % (path, key))


def _validate_value(schema: Dict[str, Any], value: Any, path: str) -> None:
    expected_type = schema.get("type")
    if expected_type:
        if isinstance(expected_type, list):
            if not any(_matches_type(value, item) for item in expected_type):
                raise ToolValidationError(
                    "Tipo non valido per %s: atteso %s." % (path, "/".join(expected_type))
                )
        elif not _matches_type(value, expected_type):
            raise ToolValidationError(
                "Tipo non valido per %s: atteso %s, ricevuto %s."
                % (path, expected_type, _type_name(value))
            )

    if "enum" in schema and value not in schema["enum"]:
        raise ToolValidationError(
            "Valore non ammesso per %s: %r." % (path, value),
            detail="Valori ammessi: %s" % ", ".join(map(str, schema["enum"])),
        )

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ToolValidationError("Il valore di %s è troppo corto." % path)
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ToolValidationError("Il valore di %s è troppo lungo." % path)
        if "pattern" in schema and not re.search(str(schema["pattern"]), value):
            raise ToolValidationError("Formato non valido per %s." % path)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ToolValidationError(
                "%s deve essere almeno %s." % (path, schema["minimum"])
            )
        if "maximum" in schema and value > schema["maximum"]:
            raise ToolValidationError(
                "%s deve essere al massimo %s." % (path, schema["maximum"])
            )

    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ToolValidationError("%s deve contenere almeno %s elementi." % (path, schema["minItems"]))
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ToolValidationError("%s deve contenere al massimo %s elementi." % (path, schema["maxItems"]))
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_value(item_schema, item, "%s[%d]" % (path, index))

    if isinstance(value, dict):
        properties = schema.get("properties", {}) or {}
        required = schema.get("required", []) or []
        for key in required:
            if key not in value:
                raise ToolValidationError("Parametro obbligatorio mancante: %s.%s" % (path, key))
        if schema.get("additionalProperties", False) is False:
            unknown = [key for key in value if key not in properties]
            if unknown:
                raise ToolValidationError(
                    "Parametri non riconosciuti in %s: %s" % (path, ", ".join(sorted(unknown)))
                )
        for key, item in value.items():
            if key in properties:
                _validate_value(properties[key], item, "%s.%s" % (path, key))
