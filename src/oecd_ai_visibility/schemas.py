"""Validated data contracts for the OECD AI visibility study."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, NonNegativeFloat, PositiveInt

Prominence = Literal["none", "incidental", "supporting", "primary"]
JudgeConfidence = Literal["low", "medium", "high"]


class ProviderConfig(BaseModel):
    """Configuration for one model served by one provider."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    enabled: bool = True
    model: str = Field(..., min_length=1)
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    max_output_tokens: PositiveInt | None = None
    supports_citations: bool = False
    env_var: str | None = None


class JudgeConfig(BaseModel):
    """Configuration for the fixed LLM-as-judge model."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    validation_sample_size: PositiveInt = 12


class PathConfig(BaseModel):
    """Filesystem locations used by the study pipeline."""

    model_config = ConfigDict(extra="forbid")

    queries: Path
    raw_dir: Path
    scored_dir: Path
    aggregated_csv: Path
    validation_sample_csv: Path
    figures_dir: Path
    report_md: Path


class DryRunConfig(BaseModel):
    """Defaults for zero-cost dry-run execution."""

    model_config = ConfigDict(extra="forbid")

    enabled_by_default: bool = True
    fixture_dir: Path = Path("data/fixtures")
    mock_provider_name: str = "fixture"
    mock_model: str = "fixture-v1"


class StudyConfig(BaseModel):
    """Top-level study configuration loaded from ``config/study.yaml``."""

    model_config = ConfigDict(extra="forbid")

    study_name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    n_runs: PositiveInt = 1
    budget_eur: NonNegativeFloat = 0.0
    providers: list[ProviderConfig] = Field(..., min_length=1)
    judge: JudgeConfig
    paths: PathConfig
    peer_organisations: list[str] = Field(..., min_length=1)
    dry_run: DryRunConfig = Field(default_factory=DryRunConfig)


class QuerySpec(BaseModel):
    """One transparent prompt in the designed query framework."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    category: str = Field(..., min_length=1)
    text: str = Field(..., min_length=10)
    expected_topic: str | None = None


class QuerySet(BaseModel):
    """Versioned collection of query prompts."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(..., min_length=1)
    design_note: str = Field(..., min_length=1)
    queries: list[QuerySpec] = Field(..., min_length=1)


class Citation(BaseModel):
    """A citation or URL surfaced by a provider response."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl | str
    title: str | None = None
    source: str | None = None


class TokenUsage(BaseModel):
    """Provider-reported token usage when available."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class RawResponseRecord(BaseModel):
    """Raw provider response plus provenance needed for auditability."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    query_id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    run_index: int = Field(..., ge=0)
    requested_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latency_seconds: NonNegativeFloat
    response_text: str = Field(..., min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    token_usage: TokenUsage | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class JudgeScore(BaseModel):
    """Validated output of the fixed LLM-as-judge rubric."""

    model_config = ConfigDict(extra="forbid")

    oecd_mentioned: bool
    oecd_prominence: Prominence
    oecd_publications_named: list[str] = Field(default_factory=list)
    oecd_url_referenced: bool
    competitors_mentioned: dict[str, Prominence] = Field(default_factory=dict)
    factual_issues: str = ""
    judge_confidence: JudgeConfidence


class ScoredRecord(BaseModel):
    """A raw response joined to its judge score for tidy export."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    query_id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    category: str = Field(..., min_length=1)
    run_index: int = Field(..., ge=0)
    scored_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    judge_provider: str = Field(..., min_length=1)
    judge_model: str = Field(..., min_length=1)
    score: JudgeScore


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping from disk."""

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        msg = f"Expected YAML mapping in {path}"
        raise ValueError(msg)
    return data


def load_study_config(path: Path | str) -> StudyConfig:
    """Load and validate the study configuration."""

    return StudyConfig.model_validate(_load_yaml(Path(path)))


def load_query_set(path: Path | str) -> QuerySet:
    """Load and validate the query framework."""

    return QuerySet.model_validate(_load_yaml(Path(path)))
