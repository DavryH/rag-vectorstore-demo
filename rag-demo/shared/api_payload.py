import math
from typing import Any

_ALLOWED_CONTROL_CHARS = {"\n", "\r", "\t"}


def strip_disallowed_control_characters(text: str) -> str:
    """Drop disallowed ASCII control chars while preserving common whitespace controls."""
    return "".join(
        char
        for char in text
        if (ord(char) >= 32 or char in _ALLOWED_CONTROL_CHARS)
    )


def sanitize_for_api_text(value: Any) -> str:
    """Normalize arbitrary input into UTF-8-safe text for API payloads."""
    text = value if isinstance(value, str) else str(value)
    utf8_safe = text.encode("utf-8", "replace").decode("utf-8")
    return strip_disallowed_control_characters(utf8_safe)


def _path(parent: str, key: str) -> str:
    if parent == "$":
        return f"$.{key}"
    return f"{parent}.{key}"


def ensure_json_safe_payload(payload: Any, path: str = "$") -> Any:
    """Recursively sanitize and validate payload values so json encoding is deterministic and safe."""
    if payload is None or isinstance(payload, bool):
        return payload

    if isinstance(payload, str):
        return sanitize_for_api_text(payload)

    if isinstance(payload, int):
        return payload

    if isinstance(payload, float):
        if not math.isfinite(payload):
            raise ValueError(f"Non-finite float at {path}: {payload}")
        return payload

    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if not isinstance(key, str):
                raise TypeError(f"Non-string key at {path}: {key!r}")
            cleaned[key] = ensure_json_safe_payload(value, path=_path(path, key))
        return cleaned

    if isinstance(payload, list):
        return [ensure_json_safe_payload(item, path=f"{path}[{idx}]") for idx, item in enumerate(payload)]

    if isinstance(payload, tuple):
        return [ensure_json_safe_payload(item, path=f"{path}[{idx}]") for idx, item in enumerate(payload)]

    raise TypeError(f"Unsupported payload value type at {path}: {type(payload).__name__}")


def validate_openai_chat_completions_payload(payload: dict[str, Any]) -> None:
    """Fail fast on malformed chat.completions payloads."""
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise RuntimeError("chat.completions payload requires non-empty 'model'.")

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise RuntimeError("chat.completions payload requires non-empty 'messages' array.")

    responses_only_fields = {"input", "instructions"}
    misplaced_fields = sorted(field for field in responses_only_fields if field in payload)
    if misplaced_fields:
        raise RuntimeError(
            "chat.completions payload contains Responses API field(s): " + ", ".join(misplaced_fields)
        )

    for idx, message in enumerate(messages):
        if not isinstance(message, dict):
            raise RuntimeError(f"messages[{idx}] must be an object.")

        role = message.get("role")
        if not isinstance(role, str) or not role.strip():
            raise RuntimeError(f"messages[{idx}].role must be a non-empty string.")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"messages[{idx}].content must be a non-empty string.")

    response_format = payload.get("response_format")
    if response_format is None:
        return

    if not isinstance(response_format, dict):
        raise RuntimeError("chat.completions response_format must be an object.")

    if response_format.get("type") != "json_schema":
        raise RuntimeError("chat.completions response_format.type must be 'json_schema'.")

    json_schema = response_format.get("json_schema")
    if not isinstance(json_schema, dict):
        raise RuntimeError("chat.completions response_format.json_schema must be an object.")

    schema = json_schema.get("schema")
    if not isinstance(schema, dict):
        raise RuntimeError("chat.completions response_format.json_schema.schema must be an object.")
    validate_response_format_json_schema(schema, schema_path="$.response_format.json_schema.schema")


def validate_response_format_json_schema(schema: dict[str, Any], schema_path: str) -> None:
    _validate_schema_node(schema, path=schema_path)


def _validate_schema_node(node: Any, path: str) -> None:
    if not isinstance(node, dict):
        return

    _validate_object_required_keys(node, path)

    properties = node.get("properties")
    if isinstance(properties, dict):
        for property_name, property_schema in properties.items():
            _validate_schema_node(property_schema, path=f"{path}.properties.{property_name}")

    items = node.get("items")
    if isinstance(items, dict):
        _validate_schema_node(items, path=f"{path}.items")
    elif isinstance(items, list):
        for index, item_schema in enumerate(items):
            _validate_schema_node(item_schema, path=f"{path}.items[{index}]")

    for keyword in ("anyOf", "oneOf", "allOf"):
        alternatives = node.get(keyword)
        if not isinstance(alternatives, list):
            continue
        for index, alternative_schema in enumerate(alternatives):
            _validate_schema_node(alternative_schema, path=f"{path}.{keyword}[{index}]")

    for keyword in ("additionalProperties", "not", "if", "then", "else"):
        nested = node.get(keyword)
        if isinstance(nested, dict):
            _validate_schema_node(nested, path=f"{path}.{keyword}")


def _validate_object_required_keys(node: dict[str, Any], path: str) -> None:
    if not _schema_node_declares_object_type(node):
        return

    properties = node.get("properties")
    if not isinstance(properties, dict):
        return

    required = node.get("required")
    if required is None:
        raise RuntimeError(f"{path} must define a 'required' list for object properties.")
    if not isinstance(required, list):
        raise RuntimeError(f"{path}.required must be a list.")

    required_values = [item for item in required if isinstance(item, str)]
    missing_required_keys = sorted(property_name for property_name in properties.keys() if property_name not in required_values)
    if missing_required_keys:
        raise RuntimeError(
            f"{path} is missing required entries for properties: {', '.join(missing_required_keys)}"
        )


def _schema_node_declares_object_type(node: dict[str, Any]) -> bool:
    schema_type = node.get("type")
    if schema_type == "object":
        return True
    if isinstance(schema_type, list):
        return "object" in schema_type
    return False


def create_chat_completion(client: Any, payload: dict[str, Any]) -> Any:
    """Sanitize + validate payload before issuing chat.completions.create."""
    sanitized_payload = ensure_json_safe_payload(payload)
    if not isinstance(sanitized_payload, dict):
        raise RuntimeError("chat.completions payload must be an object.")
    validate_openai_chat_completions_payload(sanitized_payload)
    return client.chat.completions.create(**sanitized_payload)
