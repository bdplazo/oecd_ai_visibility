"""Shared provider contracts and live-provider construction."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from oecd_ai_visibility.schemas import Citation, ProviderConfig, QuerySpec, TokenUsage

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderResponse:
    """Normalized provider output before provenance fields are attached."""

    response_text: str
    citations: list[Citation] = field(default_factory=list)
    token_usage: TokenUsage | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """Abstract provider adapter used by live and dry-run execution."""

    def __init__(self, config: ProviderConfig, api_key: str | None = None) -> None:
        self.config = config
        self.name = config.name
        self.model = config.model
        self._api_key = api_key

    @abstractmethod
    def generate(self, query: QuerySpec, run_index: int) -> ProviderResponse:
        """Generate one response for one query."""


def build_live_providers(
    provider_configs: list[ProviderConfig],
    logger: logging.Logger | None = None,
) -> list[Provider]:
    """Build enabled live providers, skipping missing credentials with a warning."""

    log = logger or LOGGER
    providers: list[Provider] = []
    adapter_classes = _adapter_classes()

    for config in provider_configs:
        if not config.enabled:
            log.info("Provider disabled: %s", config.name)
            continue

        adapter_class = adapter_classes.get(config.name.lower())
        if adapter_class is None:
            log.warning("Skipping unsupported provider: %s", config.name)
            continue

        if not config.env_var:
            log.warning("Skipping provider without env_var configured: %s", config.name)
            continue

        api_key = os.getenv(config.env_var)
        if not api_key:
            log.warning(
                "Skipping provider %s because environment variable %s is not set",
                config.name,
                config.env_var,
            )
            continue

        providers.append(adapter_class(config=config, api_key=api_key))

    return providers


def _adapter_classes() -> dict[str, type[Provider]]:
    """Import adapter classes lazily so SDK imports stay isolated to adapters."""

    from oecd_ai_visibility.providers.anthropic import AnthropicProvider
    from oecd_ai_visibility.providers.gemini import GeminiProvider
    from oecd_ai_visibility.providers.openai import OpenAIProvider
    from oecd_ai_visibility.providers.perplexity import PerplexityProvider

    return {
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
        "openai": OpenAIProvider,
        "perplexity": PerplexityProvider,
    }
