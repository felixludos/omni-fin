"""Small structured-output wrapper for local LLM calls.

The function is intentionally standalone: pass a prompt and a Pydantic response
model, get a validated Pydantic object back. It defaults to an Ollama-compatible
OpenAI endpoint.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def raw_completion(
    prompt: str,
    *,
    model: str = "gemma4:31b",
    base_url: str = "http://localhost:11434/v1",
    api_key: str = "ollama",
    temperature: float = 0.0,
    max_tokens: int = 5000,
    timeout: float = 90.0,
) -> tuple[str, str | None]:
    """Run a raw LLM completion and return ``(content, reasoning)``.

    ``reasoning`` is ``None`` for standard models and contains the reasoning /
    thinking trace for models that expose it (e.g. deepseek-r1).
    """

    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Return only valid JSON. "
                    "Do not include markdown fences or explanatory prose."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    msg = response.choices[0].message
    content = msg.content or ""
    reasoning = getattr(msg, "reasoning_content", None)
    return content, reasoning


def structured_completion(
    prompt: str,
    response_model: type[T],
    *,
    model: str = "gemma4:31b",
    base_url: str = "http://localhost:11434/v1",
    api_key: str = "ollama",
    temperature: float = 0.0,
    max_tokens: int = 5000,
    timeout: float = 90.0,
) -> T:
    """Return ``response_model`` parsed from a local OpenAI-compatible LLM.

    The prompt is augmented with the JSON schema for the desired response model.
    The wrapper stays small on purpose so ingestion code can mock or replace it.
    """

    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    # Newer versions of the OpenAI library (>= 1.32.0) support ``parse()`` which
    # accepts a Pydantic model and returns a ParsedChatCompletion with a ``.parsed``
    # attribute containing the validated object directly. Older versions only have
    # ``create()`` and require manual JSON extraction + validation.

    response = client.chat.completions.parse(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Return only valid JSON matching the provided JSON schema. "
                    "Do not include markdown fences or explanatory prose."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        response_format=response_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    msg = response.choices[0].message
    content = msg.content or "{}"
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return parsed
    return response_model.model_validate_json(content)
