import os
from typing import Any

from shared.api_payload import create_chat_completion

DETERMINISTIC_SEED_ENV = "RAG_DETERMINISTIC_SEED"
DEFAULT_DETERMINISTIC_SEED = 0


def get_openai_client():
    """Create an OpenAI client from environment variables."""
    from openai import OpenAI

    kwargs: dict[str, Any] = {}
    if os.getenv("OPENAI_ORG_ID"):
        kwargs["organization"] = os.environ["OPENAI_ORG_ID"]
    if os.getenv("OPENAI_PROJECT"):
        kwargs["project"] = os.environ["OPENAI_PROJECT"]

    # Some environments accidentally resolve `openai.OpenAI` to an unexpected
    # callable (for example via a conflicting package). Calling that object with
    # optional kwargs can surface confusing errors like
    # `'_GeneratorContextManager' object has no attribute 'args'`.
    # Retry without optional kwargs to stay compatible with minimal clients.
    api_key = os.environ.get("OPENAI_API_KEY")
    try:
        return OpenAI(api_key=api_key, **kwargs)
    except AttributeError as exc:
        if "_GeneratorContextManager" not in str(exc):
            raise
        return OpenAI(api_key=api_key)


def deterministic_seed() -> int:
    """Return the integer seed used to keep model calls deterministic across runs."""
    raw_seed = os.getenv(DETERMINISTIC_SEED_ENV, str(DEFAULT_DETERMINISTIC_SEED)).strip()
    try:
        return int(raw_seed)
    except ValueError:
        return DEFAULT_DETERMINISTIC_SEED


def chat_completion(prompt: str, model: str | None = None) -> str:
    """Minimal helper for text generation in this demo."""
    client = get_openai_client()
    response = create_chat_completion(
        client,
        payload={
            "model": model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
            "seed": deterministic_seed(),
        },
    )

    message_content = response.choices[0].message.content
    if not isinstance(message_content, str) or not message_content.strip():
        raise RuntimeError("Chat completion returned empty content.")

    return message_content
