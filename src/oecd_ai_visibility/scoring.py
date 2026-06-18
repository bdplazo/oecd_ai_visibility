"""Scoring orchestration for raw response records."""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from oecd_ai_visibility.judges.base import Judge, LiveJudgeAdapter
from oecd_ai_visibility.judges.dry_run import DryRunJudge
from oecd_ai_visibility.schemas import (
    QuerySet,
    QuerySpec,
    RawResponseRecord,
    ScoredRecord,
    StudyConfig,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoreResult:
    """Summary of one scoring run."""

    generated_files: list[Path] = field(default_factory=list)
    cache_hits: list[Path] = field(default_factory=list)
    missing_raw_files: list[Path] = field(default_factory=list)
    validation_sample_path: Path | None = None


def score_collection(
    *,
    config: StudyConfig,
    query_set: QuerySet,
    project_root: Path,
    dry_run: bool,
    use_cache: bool = True,
    export_validation_sample: bool = True,
    logger: logging.Logger | None = None,
) -> ScoreResult:
    """Score cached raw response records."""

    log = logger or LOGGER
    judge = _build_judge(config=config, dry_run=dry_run)
    raw_dir = _resolve_project_path(config.paths.raw_dir, project_root)
    scored_dir = _resolve_project_path(config.paths.scored_dir, project_root)
    scored_dir.mkdir(parents=True, exist_ok=True)

    generated_files: list[Path] = []
    cache_hits: list[Path] = []
    missing_raw_files: list[Path] = []
    queries_by_id = {query.id: query for query in query_set.queries}

    for provider, model in _expected_provider_models(config=config, dry_run=dry_run):
        for query in query_set.queries:
            for run_index in range(config.n_runs):
                raw_path = cache_path(
                    output_dir=raw_dir,
                    provider=provider,
                    model=model,
                    query_id=query.id,
                    run_index=run_index,
                )
                if not raw_path.exists():
                    log.warning("Missing raw response, skipping scoring: %s", raw_path)
                    missing_raw_files.append(raw_path)
                    continue

                scored_path = cache_path(
                    output_dir=scored_dir,
                    provider=provider,
                    model=model,
                    query_id=query.id,
                    run_index=run_index,
                )
                if use_cache and scored_path.exists():
                    log.info("Score cache hit: %s", scored_path)
                    cache_hits.append(scored_path)
                    continue

                raw_record = RawResponseRecord.model_validate_json(
                    raw_path.read_text(encoding="utf-8")
                )
                scored_record = _score_record(
                    raw_record=raw_record,
                    query=queries_by_id[raw_record.query_id],
                    judge=judge,
                )
                scored_path.write_text(
                    scored_record.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                log.info("Wrote scored response: %s", scored_path)
                generated_files.append(scored_path)

    validation_sample_path = None
    if export_validation_sample:
        validation_sample_path = export_validation_sample_csv(
            config=config,
            project_root=project_root,
            logger=log,
        )

    return ScoreResult(
        generated_files=generated_files,
        cache_hits=cache_hits,
        missing_raw_files=missing_raw_files,
        validation_sample_path=validation_sample_path,
    )


def export_validation_sample_csv(
    *,
    config: StudyConfig,
    project_root: Path,
    logger: logging.Logger | None = None,
) -> Path:
    """Export a stable manual-review sample from scored records."""

    log = logger or LOGGER
    scored_dir = _resolve_project_path(config.paths.scored_dir, project_root)
    sample_path = _resolve_project_path(config.paths.validation_sample_csv, project_root)
    sample_path.parent.mkdir(parents=True, exist_ok=True)

    scored_records = [
        ScoredRecord.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(scored_dir.glob("*.json"))
    ]
    scored_records.sort(
        key=lambda record: (record.provider, record.model, record.query_id, record.run_index)
    )
    sample = scored_records[: config.judge.validation_sample_size]

    with sample_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=_validation_sample_fields())
        writer.writeheader()
        for record in sample:
            writer.writerow(_validation_sample_row(record))

    log.info("Wrote validation sample: %s", sample_path)
    return sample_path


def cache_path(
    *,
    output_dir: Path,
    provider: str,
    model: str,
    query_id: str,
    run_index: int,
) -> Path:
    """Return the stable path for one provider/model/query/run tuple."""

    filename = "__".join(
        [
            _slug(provider),
            _slug(model),
            _slug(query_id),
            str(run_index),
        ]
    )
    return output_dir / f"{filename}.json"


def _score_record(
    *,
    raw_record: RawResponseRecord,
    query: QuerySpec,
    judge: Judge,
) -> ScoredRecord:
    score = judge.score(raw_record=raw_record, query=query)
    return ScoredRecord(
        provider=raw_record.provider,
        model=raw_record.model,
        query_id=raw_record.query_id,
        category=query.category,
        run_index=raw_record.run_index,
        response_text=raw_record.response_text,
        citations=raw_record.citations,
        judge_provider=judge.provider,
        judge_model=judge.model,
        score=score,
    )


def _build_judge(*, config: StudyConfig, dry_run: bool) -> Judge:
    if dry_run:
        return DryRunJudge(peer_organisations=config.peer_organisations)
    return LiveJudgeAdapter(config=config.judge)


def _expected_provider_models(*, config: StudyConfig, dry_run: bool) -> list[tuple[str, str]]:
    if dry_run:
        return [(config.dry_run.mock_provider_name, config.dry_run.mock_model)]
    return [(provider.name, provider.model) for provider in config.providers if provider.enabled]


def _validation_sample_fields() -> list[str]:
    return [
        "provider",
        "model",
        "query_id",
        "category",
        "run_index",
        "response_text",
        "citations",
        "oecd_mentioned",
        "oecd_prominence",
        "oecd_publications_named",
        "oecd_url_referenced",
        "competitors_mentioned",
        "factual_issues",
        "judge_confidence",
    ]


def _validation_sample_row(record: ScoredRecord) -> dict[str, str | int | bool]:
    score = record.score
    return {
        "provider": record.provider,
        "model": record.model,
        "query_id": record.query_id,
        "category": record.category,
        "run_index": record.run_index,
        "response_text": record.response_text,
        "citations": json.dumps(
            [citation.model_dump(mode="json") for citation in record.citations],
            sort_keys=True,
        ),
        "oecd_mentioned": score.oecd_mentioned,
        "oecd_prominence": score.oecd_prominence,
        "oecd_publications_named": json.dumps(score.oecd_publications_named, sort_keys=True),
        "oecd_url_referenced": score.oecd_url_referenced,
        "competitors_mentioned": json.dumps(score.competitors_mentioned, sort_keys=True),
        "factual_issues": score.factual_issues,
        "judge_confidence": score.judge_confidence,
    }


def _resolve_project_path(path: Path, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-").lower()
