import os
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_get_openai_client_retries_without_optional_kwargs(monkeypatch):
    from shared import openai_client as module

    calls: list[dict[str, object]] = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if "organization" in kwargs:
                raise AttributeError("'_GeneratorContextManager' object has no attribute 'args'")

    fake_openai_module = ModuleType("openai")
    fake_openai_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai_module)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ORG_ID", "org-test")
    monkeypatch.delenv("OPENAI_PROJECT", raising=False)

    client = module.get_openai_client()

    assert isinstance(client, FakeOpenAI)
    assert calls == [
        {"api_key": "test-key", "organization": "org-test"},
        {"api_key": "test-key"},
    ]


def test_get_openai_client_raises_unrelated_attribute_error(monkeypatch):
    from shared import openai_client as module

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            raise AttributeError("different attribute error")

    fake_openai_module = ModuleType("openai")
    fake_openai_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai_module)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_ORG_ID", raising=False)
    monkeypatch.delenv("OPENAI_PROJECT", raising=False)

    try:
        module.get_openai_client()
        raise AssertionError("Expected AttributeError")
    except AttributeError as exc:
        assert str(exc) == "different attribute error"
