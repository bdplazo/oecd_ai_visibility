"""Perplexity provider adapter."""

from __future__ import annotations

from typing import Any

from oecd_ai_visibility.providers.base import Provider, ProviderResponse
from oecd_ai_visibility.schemas import Citation, QuerySpec, TokenUsage

PERPLEXITY_CHAT_COMPLETIONS_URL = "https://api.perplexity.ai/chat/completions"


class PerplexityProvider(Provider):
    """Adapter for Perplexity's OpenAI-compatible chat completions endpoint."""

    def generate(self, query: QuerySpec, run_index: int) -> ProviderResponse:
        import httpx

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": query.text}],
            "temperature": self.config.temperature,
        }
        if self.config.max_output_tokens:
            payload["max_tokens"] = self.config.max_output_tokens

        response = httpx.post(
            PERPLEXITY_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        raw_payload = response.json()

        return ProviderResponse(
            response_text=_extract_response_text(raw_payload),
            citations=_extract_citations(raw_payload),
            token_usage=_token_usage(raw_payload.get("usage")),
            raw_payload=raw_payload,
        )


def _extract_response_text(raw_payload: dict[str, Any]) -> str:
    choices = raw_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _extract_citations(raw_payload: dict[str, Any]) -> list[Citation]:
    citations: list[Citation] = []
    seen_urls: set[str] = set()

    for citation in raw_payload.get("citations", []):
        if isinstance(citation, str):
            _append_citation(citations, seen_urls, url=citation, source="perplexity")
        elif isinstance(citation, dict):
            _append_citation(
                citations,
                seen_urls,
                url=citation.get("url"),
                title=citation.get("title"),
                source=citation.get("source") or "perplexity",
            )

    for result in raw_payload.get("search_results", []):
        if not isinstance(result, dict):
            continue
        _append_citation(
            citations,
            seen_urls,
            url=result.get("url"),
            title=result.get("title"),
            source=result.get("source") or result.get("domain") or "perplexity",
        )

    return citations


def _append_citation(
    citations: list[Citation],
    seen_urls: set[str],
    *,
    url: Any,
    title: Any = None,
    source: Any = None,
) -> None:
    if not isinstance(url, str) or not url or url in seen_urls:
        return
    seen_urls.add(url)
    citations.append(
        Citation(
            url=url,
            title=title if isinstance(title, str) else None,
            source=source if isinstance(source, str) else None,
        )
    )


def _token_usage(usage: Any) -> TokenUsage | None:
    if not isinstance(usage, dict):
        return None

    return TokenUsage(
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )
