"""Small structured-output wrapper for local LLM calls.

The function is intentionally standalone: pass a prompt and a Pydantic response
model, get a validated Pydantic object back. It defaults to an Ollama-compatible
OpenAI endpoint.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def structured_completion(
    prompt: str,
    response_model: type[T],
    *,
    model: str = "llama3.1",
    base_url: str = "http://localhost:11434/v1",
    api_key: str = "ollama",
    temperature: float = 0.0,
    max_tokens: int = 1000,
    timeout: float = 60.0,
) -> T:
    """Return ``response_model`` parsed from a local OpenAI-compatible LLM.

    The prompt is augmented with the JSON schema for the desired response model.
    The wrapper stays small on purpose so ingestion code can mock or replace it.
    """

    from openai import OpenAI

    schema = response_model.model_json_schema()
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    response = client.chat.completions.create(
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
                "content": f"Schema:\n{schema}\n\nPrompt:\n{prompt}",
            },
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return response_model.model_validate_json(content)
