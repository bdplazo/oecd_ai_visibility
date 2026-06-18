"""Gemini provider adapter."""

from __future__ import annotations

from typing import Any

from oecd_ai_visibility.providers.base import Provider, ProviderResponse
from oecd_ai_visibility.schemas import QuerySpec, TokenUsage


class GeminiProvider(Provider):
    """Adapter for Google Gemini responses."""

    def generate(self, query: QuerySpec, run_index: int) -> ProviderResponse:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self.model,
            contents=query.text,
            config=types.GenerateContentConfig(
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_output_tokens,
            ),
        )

        raw_payload = _model_dump(response)
        usage = getattr(response, "usage_metadata", None)

        return ProviderResponse(
            response_text=getattr(response, "text", "") or _extract_response_text(raw_payload),
            token_usage=_token_usage(usage),
            raw_payload=raw_payload,
        )


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_json_dict"):
        return value.to_json_dict()
    if isinstance(value, dict):
        return value
    return {"repr": repr(value)}


def _extract_response_text(raw_payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for candidate in raw_payload.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "\n".join(parts).strip()


def _token_usage(usage: Any) -> TokenUsage | None:
    if usage is None:
        return None

    input_tokens = getattr(usage, "prompt_token_count", None)
    output_tokens = getattr(usage, "candidates_token_count", None)
    total_tokens = getattr(usage, "total_token_count", None)

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
