"""Deterministic fixture-backed provider for dry runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from oecd_ai_visibility.providers.base import Provider, ProviderResponse
from oecd_ai_visibility.schemas import Citation, ProviderConfig, QuerySpec, TokenUsage


class DryRunProvider(Provider):
    """Provider that returns committed fixture responses without API keys or network."""

    def __init__(
        self,
        *,
        provider_name: str,
        model: str,
        fixture_dir: Path,
    ) -> None:
        super().__init__(
            config=ProviderConfig(name=provider_name, model=model, enabled=True),
            api_key=None,
        )
        self.fixture_dir = fixture_dir
        self._fixtures = _load_fixtures(fixture_dir)

    def generate(self, query: QuerySpec, run_index: int) -> ProviderResponse:
        fixture_id = self._fixture_id_for_query(query)
        fixture = self._fixtures[fixture_id]

        return ProviderResponse(
            response_text=fixture["response_text"],
            citations=[
                Citation.model_validate(citation) for citation in fixture.get("citations", [])
            ],
            token_usage=TokenUsage.model_validate(fixture["token_usage"])
            if fixture.get("token_usage")
            else None,
            raw_payload={
                "fixture_id": fixture_id,
                "query_id": query.id,
                "query_text": query.text,
                "run_index": run_index,
                "fixture_payload": fixture.get("raw_payload", {}),
            },
        )

    @staticmethod
    def _fixture_id_for_query(query: QuerySpec) -> str:
        if query.category == "generative_search_referral":
            return "oecd_org_citation"
        if query.category == "comparative_peer":
            return "peer_comparison"
        if query.id == "policy_sme_digitalisation":
            return "no_oecd_mention"
        return "oecd_primary"


def _load_fixtures(fixture_dir: Path) -> dict[str, dict[str, Any]]:
    fixture_path = fixture_dir / "dry_run_responses.yaml"
    with fixture_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict) or not isinstance(data.get("responses"), list):
        msg = f"Expected responses list in {fixture_path}"
        raise ValueError(msg)

    fixtures: dict[str, dict[str, Any]] = {}
    for fixture in data["responses"]:
        if not isinstance(fixture, dict) or not isinstance(fixture.get("id"), str):
            msg = f"Invalid fixture entry in {fixture_path}"
            raise ValueError(msg)
        fixtures[fixture["id"]] = fixture

    required = {"oecd_primary", "peer_comparison", "oecd_org_citation", "no_oecd_mention"}
    missing = required.difference(fixtures)
    if missing:
        msg = f"Missing dry-run fixtures: {', '.join(sorted(missing))}"
        raise ValueError(msg)

    return fixtures
