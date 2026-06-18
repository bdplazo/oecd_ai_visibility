"""OpenAI provider adapter."""

from __future__ import annotations

from typing import Any

from oecd_ai_visibility.providers.base import Provider, ProviderResponse
from oecd_ai_visibility.schemas import QuerySpec, TokenUsage


class OpenAIProvider(Provider):
    """Adapter for OpenAI responses."""

    def generate(self, query: QuerySpec, run_index: int) -> ProviderResponse:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        response = client.responses.create(
            model=self.model,
            input=query.text,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
        )

        raw_payload = _model_dump(response)
        response_text = getattr(response, "output_text", None) or _extract_response_text(
            raw_payload
        )
        usage = getattr(response, "usage", None)

        return ProviderResponse(
            response_text=response_text,
            token_usage=_token_usage(usage),
            raw_payload=raw_payload,
        )


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"repr": repr(value)}


def _extract_response_text(raw_payload: dict[str, Any]) -> str:
    output = raw_payload.get("output")
    if not isinstance(output, list):
        return ""

    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _token_usage(usage: Any) -> TokenUsage | None:
    if usage is None:
        return None

    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )
