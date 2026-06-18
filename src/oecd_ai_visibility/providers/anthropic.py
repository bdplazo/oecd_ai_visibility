"""Anthropic provider adapter."""

from __future__ import annotations

from typing import Any

from oecd_ai_visibility.providers.base import Provider, ProviderResponse
from oecd_ai_visibility.schemas import QuerySpec, TokenUsage


class AnthropicProvider(Provider):
    """Adapter for Anthropic Messages API responses."""

    def generate(self, query: QuerySpec, run_index: int) -> ProviderResponse:
        from anthropic import Anthropic

        client = Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=self.config.max_output_tokens or 900,
            temperature=self.config.temperature,
            messages=[{"role": "user", "content": query.text}],
        )

        raw_payload = _model_dump(response)
        usage = getattr(response, "usage", None)

        return ProviderResponse(
            response_text=_extract_response_text(raw_payload),
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
    parts: list[str] = []
    for block in raw_payload.get("content", []):
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts).strip()


def _token_usage(usage: Any) -> TokenUsage | None:
    if usage is None:
        return None

    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = None
    if input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
