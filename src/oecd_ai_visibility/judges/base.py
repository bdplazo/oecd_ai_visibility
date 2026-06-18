"""Shared judge contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod

from oecd_ai_visibility.schemas import JudgeConfig, JudgeScore, QuerySpec, RawResponseRecord


class Judge(ABC):
    """Abstract scoring adapter used by deterministic and future live judges."""

    def __init__(self, *, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model

    @abstractmethod
    def score(self, *, raw_record: RawResponseRecord, query: QuerySpec) -> JudgeScore:
        """Score one raw response against the study rubric."""


class LiveJudgeAdapter(Judge):
    """Placeholder interface for a later live LLM judge implementation."""

    def __init__(self, *, config: JudgeConfig) -> None:
        super().__init__(provider=config.provider, model=config.model)
        self.config = config

    def score(self, *, raw_record: RawResponseRecord, query: QuerySpec) -> JudgeScore:
        msg = "Live judge scoring is not implemented in Phase 3; use dry-run scoring."
        raise NotImplementedError(msg)
