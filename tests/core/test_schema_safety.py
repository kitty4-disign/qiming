from __future__ import annotations

from deeptutor.core.schema_safety import sanitize_raw_tool_schema
from deeptutor.core.tool_protocol import ToolDefinition


def test_raw_tool_schema_strips_unsupported_remote_keywords() -> None:
    raw = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": {"secret": {"type": "string"}},
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "search text",
                "pattern": ".*",
                "examples": ["ignored"],
            },
            "count": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query", "missing"],
        "allOf": [{"$ref": "#/$defs/secret"}],
        "patternProperties": {".*": {"type": "string"}},
    }

    safe = sanitize_raw_tool_schema(raw)

    assert safe == {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "search text"},
            "count": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    }


def test_raw_schema_is_bounded_in_depth_property_count_and_text_size() -> None:
    nested: dict = {"type": "string"}
    for _ in range(20):
        nested = {"type": "object", "properties": {"child": nested}}

    raw = {
        "type": "object",
        "description": "x" * 10_000,
        "properties": {
            **{f"p{i}": {"type": "string"} for i in range(100)},
            "nested": nested,
        },
        "enum": [str(i) for i in range(100)],
    }

    safe = sanitize_raw_tool_schema(raw)

    assert len(safe["description"]) == 2_000
    assert len(safe["properties"]) == 64
    # The sanitizer never emits the remote recursive combinators/references;
    # bounded property traversal also prevents an untrusted schema explosion.
    cursor = sanitize_raw_tool_schema(
        {"type": "object", "properties": {"nested": nested}}
    )["properties"]["nested"]
    depth = 0
    while cursor.get("properties"):
        depth += 1
        cursor = cursor["properties"]["child"]
    assert depth <= 7


def test_tool_definition_sanitizes_raw_parameters_before_llm_exposure() -> None:
    definition = ToolDefinition(
        name="mcp_remote_tool",
        description="remote",
        raw_parameters={
            "type": "object",
            "properties": {"value": {"type": ["string", "null"], "$ref": "evil"}},
            "oneOf": [{"type": "string"}],
        },
    )

    schema = definition.to_openai_schema()

    assert schema["function"]["parameters"] == {
        "type": "object",
        "properties": {"value": {"type": "string"}},
    }


def test_non_object_external_root_is_forced_to_function_argument_object() -> None:
    safe = sanitize_raw_tool_schema({"type": "array", "items": {"type": "string"}})

    assert safe == {"type": "object", "properties": {}}
