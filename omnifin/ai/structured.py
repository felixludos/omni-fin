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
    max_tokens: int = 16384,
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
                    "Return only valid JSON. Do not include markdown fences or explanatory prose."
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
    max_tokens: int = 16384,
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


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------

_SYSTEM_MSG = (
    "Return only valid JSON matching the provided JSON schema. "
    "Do not include markdown fences or explanatory prose."
)


class LLMProvider:
    """Base provider interface for structured and streaming completions."""

    def structured_completion(
        self,
        prompt: str,
        response_model: type[T],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        timeout: float = 90.0,
    ) -> T:
        raise NotImplementedError

    def stream_completion(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        timeout: float = 90.0,
    ):
        """Yield text chunks as they arrive from the LLM."""
        raise NotImplementedError

    @classmethod
    def from_url(cls, url_or_name: str | None, model: str | None = None) -> LLMProvider:
        """Factory: ``"gemini"`` → GeminiProvider, URL/``"ollama"``/None → OllamaProvider."""
        name = (url_or_name or "").strip().lower()
        if name == "gemini":
            return GeminiProvider(model=model)
        base_url = (
            url_or_name
            if url_or_name and url_or_name.startswith("http")
            else "http://localhost:11434/v1"
        )
        return OllamaProvider(base_url=base_url, model=model)


class OllamaProvider(LLMProvider):
    """OpenAI-compatible provider (Ollama, vLLM, LM Studio, etc.)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "ollama",
        model: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.default_model = model or "gemma4:31b"

    def structured_completion(
        self,
        prompt: str,
        response_model: type[T],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        timeout: float = 90.0,
    ) -> T:
        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=timeout)
        response = client.chat.completions.parse(
            model=model or self.default_model,
            messages=[
                {"role": "system", "content": _SYSTEM_MSG},
                {"role": "user", "content": prompt},
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

    def stream_completion(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        timeout: float = 90.0,
    ):
        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=timeout)
        stream = client.chat.completions.create(
            model=model or self.default_model,
            messages=[
                {
                    "role": "system",
                    "content": "Return only valid JSON. Do not include markdown fences or explanatory prose.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


class GeminiProvider(LLMProvider):
    """Google Gemini / GenAI provider."""

    def __init__(self, model: str | None = None) -> None:
        self.default_model = model or "gemini-2.5-flash"

    def _get_client(self):
        import os

        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Gemini provider requires GEMINI_API_KEY or GOOGLE_API_KEY environment variable"
            )
        return genai.Client(api_key=api_key)

    def structured_completion(
        self,
        prompt: str,
        response_model: type[T],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        timeout: float = 90.0,
    ) -> T:
        client = self._get_client()
        response = client.models.generate_content(
            model=model or self.default_model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": response_model,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        text = response.text or "{}"
        try:
            return response_model.model_validate_json(text)
        except Exception:
            return response_model.model_validate_json(text)

    def stream_completion(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        timeout: float = 90.0,
    ):
        client = self._get_client()
        for chunk in client.models.generate_content_stream(
            model=model or self.default_model,
            contents=prompt,
            config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        ):
            if chunk.text:
                yield chunk.text
