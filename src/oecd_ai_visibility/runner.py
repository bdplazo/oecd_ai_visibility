"""Run orchestration for raw provider collection."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from oecd_ai_visibility.providers.base import Provider, build_live_providers
from oecd_ai_visibility.providers.dry_run import DryRunProvider
from oecd_ai_visibility.schemas import QuerySet, RawResponseRecord, StudyConfig

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    """Summary of one raw-response collection run."""

    generated_files: list[Path] = field(default_factory=list)
    cache_hits: list[Path] = field(default_factory=list)
    skipped_providers: int = 0


def run_collection(
    *,
    config: StudyConfig,
    query_set: QuerySet,
    project_root: Path,
    dry_run: bool,
    use_cache: bool = True,
    logger: logging.Logger | None = None,
) -> RunResult:
    """Collect raw responses for configured providers and queries."""

    log = logger or LOGGER
    providers = _build_providers(
        config=config, project_root=project_root, dry_run=dry_run, logger=log
    )
    raw_dir = _resolve_project_path(config.paths.raw_dir, project_root)
    raw_dir.mkdir(parents=True, exist_ok=True)

    if not providers:
        log.warning("No providers available; no raw responses will be collected")
        return RunResult(skipped_providers=len(config.providers))

    generated_files: list[Path] = []
    cache_hits: list[Path] = []

    for provider in providers:
        for query in query_set.queries:
            for run_index in range(config.n_runs):
                raw_path = cache_path(
                    raw_dir=raw_dir,
                    provider=provider.name,
                    model=provider.model,
                    query_id=query.id,
                    run_index=run_index,
                )
                if use_cache and raw_path.exists():
                    log.info("Cache hit: %s", raw_path)
                    cache_hits.append(raw_path)
                    continue

                started = time.perf_counter()
                requested_at_utc = datetime.now(UTC)
                provider_response = provider.generate(query=query, run_index=run_index)
                latency_seconds = time.perf_counter() - started

                record = RawResponseRecord(
                    provider=provider.name,
                    model=provider.model,
                    query_id=query.id,
                    run_index=run_index,
                    requested_at_utc=requested_at_utc,
                    latency_seconds=latency_seconds,
                    response_text=provider_response.response_text,
                    citations=provider_response.citations,
                    token_usage=provider_response.token_usage,
                    raw_payload=provider_response.raw_payload,
                )
                raw_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
                log.info("Wrote raw response: %s", raw_path)
                generated_files.append(raw_path)

    return RunResult(generated_files=generated_files, cache_hits=cache_hits)


def cache_path(
    *,
    raw_dir: Path,
    provider: str,
    model: str,
    query_id: str,
    run_index: int,
) -> Path:
    """Return the stable cache path for one provider/model/query/run tuple."""

    filename = "__".join(
        [
            _slug(provider),
            _slug(model),
            _slug(query_id),
            str(run_index),
        ]
    )
    return raw_dir / f"{filename}.json"


def _build_providers(
    *,
    config: StudyConfig,
    project_root: Path,
    dry_run: bool,
    logger: logging.Logger,
) -> list[Provider]:
    if dry_run:
        fixture_dir = _resolve_project_path(config.dry_run.fixture_dir, project_root)
        logger.info(
            "Using dry-run provider %s/%s",
            config.dry_run.mock_provider_name,
            config.dry_run.mock_model,
        )
        return [
            DryRunProvider(
                provider_name=config.dry_run.mock_provider_name,
                model=config.dry_run.mock_model,
                fixture_dir=fixture_dir,
            )
        ]

    return build_live_providers(config.providers, logger=logger)


def _resolve_project_path(path: Path, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-").lower()
