"""Scoring orchestration for raw response records."""

from __future__ import annotations

import csv
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from oecd_ai_visibility.judges.base import Judge, LiveJudgeAdapter
from oecd_ai_visibility.judges.dry_run import DryRunJudge
from oecd_ai_visibility.judges.heuristic import HeuristicJudge
from oecd_ai_visibility.schemas import (
    JudgeScore,
    QuerySet,
    QuerySpec,
    RawResponseRecord,
    ScoredRecord,
    StudyConfig,
)

LOGGER = logging.getLogger(__name__)

#: Filenames for the tidy relational helper tables written next to the aggregated
#: scored CSV. Each splits one nested column of ``scored_responses.csv`` into a
#: long table that joins back on provider/model/query_id/run_index.
PUBLICATIONS_CSV_NAME = "scored_publications.csv"
COMPETITORS_CSV_NAME = "scored_competitors.csv"
CITATIONS_CSV_NAME = "scored_citations.csv"

#: Phase 5.5 stratified manual-review artifacts, written into ``scored_dir`` next to
#: (but never overwriting) the default ``validation_sample.csv``. The blind file holds
#: the responses plus empty ``human_*`` label columns; the key file holds the heuristic's
#: own scores and is joined back on provider/model/query_id/run_index for later scoring.
STRATIFIED_VALIDATION_SAMPLE_CSV_NAME = "validation_sample_stratified.csv"
VALIDATION_SAMPLE_HEURISTIC_KEY_CSV_NAME = "validation_sample_heuristic_key.csv"

#: Default number of rows drawn from each provider x category stratum.
DEFAULT_STRATIFIED_PER_CELL = 2


@dataclass(frozen=True)
class ScoreResult:
    """Summary of one scoring run."""

    generated_files: list[Path] = field(default_factory=list)
    cache_hits: list[Path] = field(default_factory=list)
    missing_raw_files: list[Path] = field(default_factory=list)
    validation_sample_path: Path | None = None
    aggregated_csv_path: Path | None = None
    helper_csv_paths: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class StratifiedSampleResult:
    """Summary of one stratified validation-sample export."""

    sample_path: Path
    heuristic_key_path: Path
    row_count: int
    #: ``(provider, category) -> rows drawn`` for the 12 stratification cells.
    stratum_counts: dict[tuple[str, str], int] = field(default_factory=dict)
    #: Number of selected rows carrying each forced edge-case reason.
    edge_case_counts: dict[str, int] = field(default_factory=dict)


def score_collection(
    *,
    config: StudyConfig,
    query_set: QuerySet,
    project_root: Path,
    dry_run: bool,
    use_cache: bool = True,
    export_validation_sample: bool = True,
    heuristic_live_cache: bool = False,
    export_aggregated_csv: bool = False,
    logger: logging.Logger | None = None,
) -> ScoreResult:
    """Score cached raw response records."""

    if dry_run and heuristic_live_cache:
        msg = "Use either dry-run scoring or heuristic live-cache scoring, not both."
        raise ValueError(msg)

    log = logger or LOGGER
    judge = _build_judge(
        config=config,
        dry_run=dry_run,
        heuristic_live_cache=heuristic_live_cache,
    )
    raw_dir = _resolve_project_path(config.paths.raw_dir, project_root)
    scored_dir = _resolve_project_path(config.paths.scored_dir, project_root)
    scored_dir.mkdir(parents=True, exist_ok=True)

    generated_files: list[Path] = []
    cache_hits: list[Path] = []
    missing_raw_files: list[Path] = []
    queries_by_id = {query.id: query for query in query_set.queries}

    provider_models = _expected_provider_models(
        config=config,
        query_set=query_set,
        raw_dir=raw_dir,
        dry_run=dry_run,
        existing_raw_only=heuristic_live_cache,
    )
    for provider, model in provider_models:
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

    aggregated_csv_path = None
    helper_csv_paths: list[Path] = []
    if export_aggregated_csv:
        provider_model_filter = provider_models if heuristic_live_cache else None
        aggregated_csv_path = export_scored_responses_csv(
            config=config,
            project_root=project_root,
            provider_models=provider_model_filter,
            logger=log,
        )
        helper_csv_paths = export_helper_tables(
            config=config,
            project_root=project_root,
            provider_models=provider_model_filter,
            logger=log,
        )

    return ScoreResult(
        generated_files=generated_files,
        cache_hits=cache_hits,
        missing_raw_files=missing_raw_files,
        validation_sample_path=validation_sample_path,
        aggregated_csv_path=aggregated_csv_path,
        helper_csv_paths=helper_csv_paths,
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


def export_stratified_validation_sample_csv(
    *,
    config: StudyConfig,
    project_root: Path,
    per_cell: int = DEFAULT_STRATIFIED_PER_CELL,
    logger: logging.Logger | None = None,
) -> StratifiedSampleResult:
    """Export the Phase 5.5 stratified manual-review sample as two new CSVs.

    Reshapes already-scored data only: it reads ``scored_dir/*.json`` and writes
    ``validation_sample_stratified.csv`` (blind review layout — responses plus empty
    ``human_*`` columns) and ``validation_sample_heuristic_key.csv`` (the heuristic's own
    scores, kept separate so labelling is not anchored). The default
    ``validation_sample.csv`` and every ``data/raw/`` file are left untouched. Makes no
    live provider or judge calls.

    Only the configured (enabled) live providers form the population, so the ``fixture``
    dry-run artifacts that share ``scored_dir`` are excluded — matching the filter the
    aggregated CSV uses.
    """

    log = logger or LOGGER
    scored_dir = _resolve_project_path(config.paths.scored_dir, project_root)
    sample_path = scored_dir / STRATIFIED_VALIDATION_SAMPLE_CSV_NAME
    key_path = scored_dir / VALIDATION_SAMPLE_HEURISTIC_KEY_CSV_NAME
    scored_dir.mkdir(parents=True, exist_ok=True)

    provider_models = [
        (provider.name, provider.model) for provider in config.providers if provider.enabled
    ]
    records = _load_scored_records(
        config=config,
        project_root=project_root,
        provider_models=provider_models,
    )
    selected, reasons = _select_stratified_validation_sample(records, per_cell=per_cell)

    _write_rows(
        sample_path,
        _stratified_sample_fields(),
        (_stratified_sample_row(record) for record in selected),
    )
    _write_rows(
        key_path,
        _heuristic_key_fields(),
        (_heuristic_key_row(record, reasons[_sample_sort_key(record)]) for record in selected),
    )

    stratum_counts: dict[tuple[str, str], int] = {}
    edge_case_counts: dict[str, int] = {}
    for record in selected:
        for reason in reasons[_sample_sort_key(record)]:
            if reason == "stratum":
                cell = (record.provider, record.category)
                stratum_counts[cell] = stratum_counts.get(cell, 0) + 1
            else:
                edge_case_counts[reason] = edge_case_counts.get(reason, 0) + 1

    log.info("Wrote stratified validation sample (%d rows): %s", len(selected), sample_path)
    log.info("Wrote stratified heuristic key: %s", key_path)
    return StratifiedSampleResult(
        sample_path=sample_path,
        heuristic_key_path=key_path,
        row_count=len(selected),
        stratum_counts=stratum_counts,
        edge_case_counts=edge_case_counts,
    )


def select_stratified_validation_sample(
    records: list[ScoredRecord],
    *,
    per_cell: int = DEFAULT_STRATIFIED_PER_CELL,
) -> list[ScoredRecord]:
    """Return the deterministic stratified + forced-edge-case review sample.

    Selection: stratify by ``provider`` x ``category`` and take the first ``per_cell``
    rows of each cell after sorting by ``(provider, model, query_id, run_index)``, then
    union in every forced edge case (``oecd_mentioned`` false, ``oecd_prominence``
    ``primary``, or ``oecd_url_referenced`` true). The result is deduplicated on the join
    key and returned in stable sort order.
    """

    selected, _ = _select_stratified_validation_sample(records, per_cell=per_cell)
    return selected


def export_scored_responses_csv(
    *,
    config: StudyConfig,
    project_root: Path,
    provider_models: list[tuple[str, str]] | None = None,
    logger: logging.Logger | None = None,
) -> Path:
    """Export validated scored records as a tidy CSV for analysis tools."""

    log = logger or LOGGER
    aggregated_path = _resolve_project_path(config.paths.aggregated_csv, project_root)
    aggregated_path.parent.mkdir(parents=True, exist_ok=True)

    records = _load_scored_records(
        config=config,
        project_root=project_root,
        provider_models=provider_models,
    )

    _write_rows(
        aggregated_path,
        _aggregated_fields(),
        (_aggregated_row(record) for record in records),
    )

    log.info("Wrote aggregated scored responses: %s", aggregated_path)
    return aggregated_path


def export_helper_tables(
    *,
    config: StudyConfig,
    project_root: Path,
    provider_models: list[tuple[str, str]] | None = None,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Export tidy relational helper tables alongside the aggregated scored CSV.

    Splits the nested columns of ``scored_responses.csv`` (publications, competitors,
    citations) into long tables — one publication, competitor, or citation per row —
    that join back on ``provider``/``model``/``query_id``/``run_index``. This keeps
    Power BI models clean without parsing JSON in the dashboard. Reshapes already-scored
    data only; makes no live provider or judge calls.
    """

    log = logger or LOGGER
    aggregated_path = _resolve_project_path(config.paths.aggregated_csv, project_root)
    output_dir = aggregated_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    records = _load_scored_records(
        config=config,
        project_root=project_root,
        provider_models=provider_models,
    )

    helpers = [
        (output_dir / PUBLICATIONS_CSV_NAME, _publication_fields(), _publication_rows(records)),
        (output_dir / COMPETITORS_CSV_NAME, _competitor_fields(), _competitor_rows(records)),
        (output_dir / CITATIONS_CSV_NAME, _citation_fields(), _citation_rows(records)),
    ]

    written: list[Path] = []
    for path, fieldnames, rows in helpers:
        _write_rows(path, fieldnames, rows)
        log.info("Wrote helper table: %s", path)
        written.append(path)
    return written


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


def _build_judge(
    *,
    config: StudyConfig,
    dry_run: bool,
    heuristic_live_cache: bool,
) -> Judge:
    if dry_run:
        return DryRunJudge(peer_organisations=config.peer_organisations)
    if heuristic_live_cache:
        return HeuristicJudge(peer_organisations=config.peer_organisations)
    return LiveJudgeAdapter(config=config.judge)


def _expected_provider_models(
    *,
    config: StudyConfig,
    query_set: QuerySet,
    raw_dir: Path,
    dry_run: bool,
    existing_raw_only: bool,
) -> list[tuple[str, str]]:
    if dry_run:
        return [(config.dry_run.mock_provider_name, config.dry_run.mock_model)]
    provider_models = [
        (provider.name, provider.model) for provider in config.providers if provider.enabled
    ]
    if not existing_raw_only:
        return provider_models
    return [
        (provider, model)
        for provider, model in provider_models
        if _has_existing_raw_record(
            raw_dir=raw_dir,
            provider=provider,
            model=model,
            query_set=query_set,
            n_runs=config.n_runs,
        )
    ]


def _load_scored_records(
    *,
    config: StudyConfig,
    project_root: Path,
    provider_models: list[tuple[str, str]] | None,
) -> list[ScoredRecord]:
    """Load scored records, optionally filtered, sorted by stable join keys."""

    scored_dir = _resolve_project_path(config.paths.scored_dir, project_root)
    provider_model_filter = set(provider_models) if provider_models is not None else None

    records = [
        ScoredRecord.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(scored_dir.glob("*.json"))
    ]
    if provider_model_filter is not None:
        records = [
            record for record in records if (record.provider, record.model) in provider_model_filter
        ]

    records.sort(
        key=lambda record: (record.provider, record.model, record.query_id, record.run_index)
    )
    return records


def _write_rows(
    path: Path,
    fieldnames: list[str],
    rows: Iterable[dict[str, str | int | bool]],
) -> None:
    """Write ``rows`` to ``path`` as a UTF-8 CSV with the given header."""

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _join_keys(record: ScoredRecord) -> dict[str, str | int]:
    """Stable keys that join every helper row back to ``scored_responses.csv``."""

    return {
        "provider": record.provider,
        "model": record.model,
        "query_id": record.query_id,
        "run_index": record.run_index,
    }


def _publication_fields() -> list[str]:
    return ["provider", "model", "query_id", "run_index", "oecd_publication"]


def _competitor_fields() -> list[str]:
    return ["provider", "model", "query_id", "run_index", "competitor", "prominence"]


def _citation_fields() -> list[str]:
    return [
        "provider",
        "model",
        "query_id",
        "run_index",
        "citation_url",
        "citation_title",
        "citation_source",
    ]


def _publication_rows(records: list[ScoredRecord]) -> Iterable[dict[str, str | int]]:
    """One row per named OECD publication, sorted for deterministic output."""

    for record in records:
        for publication in sorted(record.score.oecd_publications_named):
            yield {**_join_keys(record), "oecd_publication": publication}


def _competitor_rows(records: list[ScoredRecord]) -> Iterable[dict[str, str | int]]:
    """One row per competitor mention with its prominence, sorted by name."""

    for record in records:
        for competitor, prominence in sorted(record.score.competitors_mentioned.items()):
            yield {**_join_keys(record), "competitor": competitor, "prominence": prominence}


def _citation_rows(records: list[ScoredRecord]) -> Iterable[dict[str, str | int]]:
    """One row per citation, preserving each response's citation order."""

    for record in records:
        for citation in record.citations:
            dumped = citation.model_dump(mode="json")
            yield {
                **_join_keys(record),
                "citation_url": str(dumped["url"]),
                "citation_title": dumped.get("title") or "",
                "citation_source": dumped.get("source") or "",
            }


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


def _aggregated_fields() -> list[str]:
    return [
        "provider",
        "model",
        "query_id",
        "category",
        "run_index",
        "oecd_mentioned",
        "oecd_prominence",
        "oecd_url_referenced",
        "oecd_publications_named",
        "competitors_mentioned",
        "judge_confidence",
        "response_text",
        "citations",
        "factual_issues",
        "judge_provider",
        "judge_model",
        "scored_at_utc",
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


def _sample_sort_key(record: ScoredRecord) -> tuple[str, str, str, int]:
    """The stable, reviewer-independent ordering key used for selection and output."""

    return (record.provider, record.model, record.query_id, record.run_index)


def _edge_case_reasons(score: JudgeScore) -> list[str]:
    """Forced-include reasons the heuristic is most likely to get wrong."""

    reasons: list[str] = []
    if not score.oecd_mentioned:
        reasons.append("edge_oecd_not_mentioned")
    if score.oecd_prominence == "primary":
        reasons.append("edge_prominence_primary")
    if score.oecd_url_referenced:
        reasons.append("edge_url_referenced")
    return reasons


def _select_stratified_validation_sample(
    records: list[ScoredRecord],
    *,
    per_cell: int,
) -> tuple[list[ScoredRecord], dict[tuple[str, str, str, int], list[str]]]:
    """Deterministic stratified + forced-edge selection; returns rows and their reasons.

    Sorting everything by the stable key first means both the per-cell ``[:per_cell]``
    slice and the final output are reproducible and independent of filesystem order.
    """

    ordered = sorted(records, key=_sample_sort_key)

    cells: dict[tuple[str, str], list[ScoredRecord]] = {}
    for record in ordered:
        cells.setdefault((record.provider, record.category), []).append(record)
    stratum_keys = {
        _sample_sort_key(record)
        for cell_records in cells.values()
        for record in cell_records[:per_cell]
    }

    selected: dict[tuple[str, str, str, int], ScoredRecord] = {}
    reasons: dict[tuple[str, str, str, int], list[str]] = {}
    for record in ordered:
        key = _sample_sort_key(record)
        record_reasons: list[str] = []
        if key in stratum_keys:
            record_reasons.append("stratum")
        record_reasons.extend(_edge_case_reasons(record.score))
        if record_reasons:
            selected[key] = record
            reasons[key] = record_reasons

    ordered_keys = sorted(selected)
    return [selected[key] for key in ordered_keys], {key: reasons[key] for key in ordered_keys}


#: Empty label columns the manual reviewer fills in, blind to the heuristic output.
_HUMAN_LABEL_FIELDS = [
    "human_oecd_mentioned",
    "human_oecd_prominence",
    "human_oecd_url_referenced",
    "human_oecd_publications_named",
    "human_competitors_mentioned",
    "human_factual_issues",
    "reviewer_notes",
]


def _stratified_sample_fields() -> list[str]:
    return [
        "provider",
        "model",
        "query_id",
        "category",
        "run_index",
        "response_text",
        "citations",
        *_HUMAN_LABEL_FIELDS,
    ]


def _heuristic_key_fields() -> list[str]:
    return [
        "provider",
        "model",
        "query_id",
        "run_index",
        "category",
        "oecd_mentioned",
        "oecd_prominence",
        "oecd_url_referenced",
        "oecd_publications_named",
        "competitors_mentioned",
        "factual_issues",
        "judge_confidence",
        "selection_reason",
    ]


def _stratified_sample_row(record: ScoredRecord) -> dict[str, str | int | bool]:
    """Blind review row: response content plus empty ``human_*`` label columns.

    Deliberately omits every heuristic score so the reviewer is not anchored; those live
    in the separate heuristic-key file and join back on the four key columns.
    """

    row: dict[str, str | int | bool] = {
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
    }
    for field_name in _HUMAN_LABEL_FIELDS:
        row[field_name] = ""
    return row


def _heuristic_key_row(record: ScoredRecord, reasons: list[str]) -> dict[str, str | int | bool]:
    """The heuristic's own scores for one sampled row, for joining after blind review."""

    score = record.score
    return {
        "provider": record.provider,
        "model": record.model,
        "query_id": record.query_id,
        "run_index": record.run_index,
        "category": record.category,
        "oecd_mentioned": score.oecd_mentioned,
        "oecd_prominence": score.oecd_prominence,
        "oecd_url_referenced": score.oecd_url_referenced,
        "oecd_publications_named": json.dumps(score.oecd_publications_named, sort_keys=True),
        "competitors_mentioned": json.dumps(score.competitors_mentioned, sort_keys=True),
        "factual_issues": score.factual_issues,
        "judge_confidence": score.judge_confidence,
        "selection_reason": "|".join(reasons),
    }


def _aggregated_row(record: ScoredRecord) -> dict[str, str | int | bool]:
    score = record.score
    return {
        "provider": record.provider,
        "model": record.model,
        "query_id": record.query_id,
        "category": record.category,
        "run_index": record.run_index,
        "oecd_mentioned": score.oecd_mentioned,
        "oecd_prominence": score.oecd_prominence,
        "oecd_url_referenced": score.oecd_url_referenced,
        "oecd_publications_named": json.dumps(score.oecd_publications_named, sort_keys=True),
        "competitors_mentioned": json.dumps(score.competitors_mentioned, sort_keys=True),
        "judge_confidence": score.judge_confidence,
        "response_text": record.response_text,
        "citations": json.dumps(
            [citation.model_dump(mode="json") for citation in record.citations],
            sort_keys=True,
        ),
        "factual_issues": score.factual_issues,
        "judge_provider": record.judge_provider,
        "judge_model": record.judge_model,
        "scored_at_utc": record.scored_at_utc.isoformat(),
    }


def _has_existing_raw_record(
    *,
    raw_dir: Path,
    provider: str,
    model: str,
    query_set: QuerySet,
    n_runs: int,
) -> bool:
    return any(
        cache_path(
            output_dir=raw_dir,
            provider=provider,
            model=model,
            query_id=query.id,
            run_index=run_index,
        ).exists()
        for query in query_set.queries
        for run_index in range(n_runs)
    )


def _resolve_project_path(path: Path, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-").lower()
