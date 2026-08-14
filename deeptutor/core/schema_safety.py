"""Provider-safe normalization for externally supplied tool JSON Schemas."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import islice
from typing import Any

_MAX_DEPTH = 8
_MAX_PROPERTIES = 64
_MAX_REQUIRED = 64
_MAX_ENUM_VALUES = 64
_MAX_TEXT_CHARS = 2_000
_MAX_PROPERTY_NAME_CHARS = 128
_SUPPORTED_TYPES = {"string", "integer", "number", "boolean", "array", "object", "null"}
_NUMERIC_KEYS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
}


def _text(value: Any, *, limit: int = _MAX_TEXT_CHARS) -> str | None:
    if not isinstance(value, str):
        return None
    return value[:limit]


def _primitive(value: Any) -> str | int | float | bool | None | object:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str):
            return value[:_MAX_TEXT_CHARS]
        return value
    return _UNSAFE


_UNSAFE = object()


def _schema_type(value: Any) -> str | None:
    if isinstance(value, str) and value in _SUPPORTED_TYPES:
        return value
    # JSON Schema may express nullable values as ["string", "null"]. Most
    # function-calling providers are more interoperable with a single concrete
    # type, so retain the first supported non-null type.
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item in _SUPPORTED_TYPES and item != "null":
                return item
        if "null" in value:
            return "null"
    return None


def _sanitize_schema_node(value: Any, *, depth: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or depth > _MAX_DEPTH:
        return {}

    safe: dict[str, Any] = {}
    schema_type = _schema_type(value.get("type"))
    if schema_type is not None:
        safe["type"] = schema_type

    description = _text(value.get("description"))
    if description:
        safe["description"] = description

    fmt = _text(value.get("format"), limit=64)
    if fmt:
        safe["format"] = fmt

    enum = value.get("enum")
    if isinstance(enum, list):
        safe_enum: list[Any] = []
        for item in islice(enum, _MAX_ENUM_VALUES):
            sanitized = _primitive(item)
            if sanitized is not _UNSAFE:
                safe_enum.append(sanitized)
        if safe_enum:
            safe["enum"] = safe_enum

    for key in _NUMERIC_KEYS:
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            safe[key] = item

    properties = value.get("properties")
    safe_properties: dict[str, Any] = {}
    if isinstance(properties, Mapping) and depth < _MAX_DEPTH:
        for raw_name, child in islice(properties.items(), _MAX_PROPERTIES):
            if not isinstance(raw_name, str) or not raw_name:
                continue
            name = raw_name[:_MAX_PROPERTY_NAME_CHARS]
            if name in safe_properties:
                continue
            safe_properties[name] = _sanitize_schema_node(child, depth=depth + 1)
        safe["properties"] = safe_properties
        safe.setdefault("type", "object")

    required = value.get("required")
    if isinstance(required, list) and safe_properties:
        safe_required: list[str] = []
        for item in islice(required, _MAX_REQUIRED):
            if not isinstance(item, str):
                continue
            name = item[:_MAX_PROPERTY_NAME_CHARS]
            if name in safe_properties and name not in safe_required:
                safe_required.append(name)
        if safe_required:
            safe["required"] = safe_required

    if "items" in value and depth < _MAX_DEPTH:
        safe["items"] = _sanitize_schema_node(value.get("items"), depth=depth + 1)
        safe.setdefault("type", "array")

    additional = value.get("additionalProperties")
    if isinstance(additional, bool):
        safe["additionalProperties"] = additional
    elif isinstance(additional, Mapping) and depth < _MAX_DEPTH:
        safe["additionalProperties"] = _sanitize_schema_node(additional, depth=depth + 1)

    return safe


def sanitize_raw_tool_schema(schema: Any) -> dict[str, Any]:
    """Return a bounded provider-compatible schema for an external tool.

    Raw adapter schemas (notably MCP ``inputSchema``) are controlled by a
    remote process. Function-calling providers accept only a practical subset
    of JSON Schema, while unrestricted recursive schemas can also inflate a
    request dramatically. This function therefore:

    - forces the function-argument root to an object;
    - keeps the common cross-provider keywords DeepTutor needs;
    - strips references/combinators/definitions and arbitrary metadata;
    - bounds nesting, properties, enum entries, names and descriptive text;
    - filters ``required`` to properties that survived sanitization.

    It does not validate runtime arguments; the actual tool/server remains the
    source of truth for execution-time validation.
    """
    safe = _sanitize_schema_node(schema, depth=0)
    properties = safe.get("properties")
    if not isinstance(properties, dict):
        properties = {}

    # Function arguments must have an object root. Scalar/array-only keywords
    # inherited from a malformed upstream root would make the resulting schema
    # internally contradictory, so keep only object-level metadata here.
    root: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    description = safe.get("description")
    if isinstance(description, str) and description:
        root["description"] = description
    required = safe.get("required")
    if isinstance(required, list) and required and properties:
        root["required"] = required
    additional = safe.get("additionalProperties")
    if isinstance(additional, (bool, dict)):
        root["additionalProperties"] = additional
    return root


__all__ = ["sanitize_raw_tool_schema"]
