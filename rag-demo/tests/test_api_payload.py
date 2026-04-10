import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.api_payload import (
    create_chat_completion,
    ensure_json_safe_payload,
    sanitize_for_api_text,
    strip_disallowed_control_characters,
    validate_openai_chat_completions_payload,
)


class _FakeChatCompletions:
    def __init__(self) -> None:
        self.called = False
        self.kwargs = None

    def create(self, **kwargs):
        self.called = True
        self.kwargs = kwargs
        return {"ok": True}


class _FakeClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _FakeChatCompletions()})()


def test_strip_disallowed_control_characters_preserves_common_whitespace():
    raw = "a\x00b\x07c\n\t\rd"
    assert strip_disallowed_control_characters(raw) == "abc\n\t\rd"


def test_sanitize_for_api_text_replaces_invalid_surrogates_and_controls():
    raw = "bad\ud800text\x00"
    sanitized = sanitize_for_api_text(raw)
    assert "\ud800" not in sanitized
    assert "\x00" not in sanitized


def test_ensure_json_safe_payload_rejects_non_finite_float():
    with pytest.raises(ValueError, match="Non-finite float"):
        ensure_json_safe_payload({"score": math.nan})


def test_validate_openai_chat_completions_payload_rejects_responses_fields():
    with pytest.raises(RuntimeError, match="Responses API field"):
        validate_openai_chat_completions_payload(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hello"}],
                "input": "wrong endpoint shape",
            }
        )


def test_create_chat_completion_fails_fast_before_network_call():
    client = _FakeClient()
    with pytest.raises(RuntimeError, match="messages\\[0\\]\\.content"):
        create_chat_completion(
            client,
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "\x00\x01"}],
            },
        )

    assert client.chat.completions.called is False


def test_create_chat_completion_sanitizes_strings_before_send():
    client = _FakeClient()
    create_chat_completion(
        client,
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello\x00world"}],
        },
    )

    assert client.chat.completions.called is True
    assert client.chat.completions.kwargs["messages"][0]["content"] == "helloworld"


def test_validate_openai_chat_completions_payload_rejects_missing_required_property_keys():
    payload = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "bad_schema",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "citations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["answer"],
                },
            },
        },
    }

    with pytest.raises(RuntimeError, match="missing required entries for properties: citations"):
        validate_openai_chat_completions_payload(payload)


def test_validate_openai_chat_completions_payload_rejects_missing_nested_required_list():
    payload = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "bad_schema",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "quotes": {
                            "type": "array",
                            "items": {
                                "type": ["object", "null"],
                                "properties": {
                                    "quote": {"type": "string"},
                                },
                            },
                        }
                    },
                    "required": ["quotes"],
                },
            },
        },
    }

    with pytest.raises(RuntimeError, match="must define a 'required' list"):
        validate_openai_chat_completions_payload(payload)
