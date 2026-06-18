"""Deterministic local judge for existing live raw-response caches."""

from __future__ import annotations

from oecd_ai_visibility.judges.dry_run import DryRunJudge


class HeuristicJudge(DryRunJudge):
    """Transparent heuristic scoring bridge; it does not call any LLM judge."""

    def __init__(self, *, peer_organisations: list[str]) -> None:
        super().__init__(
            peer_organisations=peer_organisations,
            provider="heuristic-local",
            model="deterministic-v1",
        )
