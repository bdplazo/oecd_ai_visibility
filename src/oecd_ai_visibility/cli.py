"""Command-line interface for the OECD AI visibility study."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from oecd_ai_visibility.analysis import build_summary_tables
from oecd_ai_visibility.runner import run_collection
from oecd_ai_visibility.schemas import load_query_set, load_study_config
from oecd_ai_visibility.scoring import score_collection

app = typer.Typer(help="Collect and analyse OECD AI visibility study data.")


@app.callback()
def main() -> None:
    """Collect and analyse OECD AI visibility study data."""


@app.command("run")
def run_command(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to the study YAML configuration."),
    ] = Path("config/study.yaml"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Use fixture-backed provider with no API calls."),
    ] = False,
    live: Annotated[
        bool,
        typer.Option("--live", help="Use live providers with configured API keys."),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Regenerate responses even when raw JSON exists."),
    ] = False,
) -> None:
    """Collect raw provider responses."""

    if dry_run and live:
        raise typer.BadParameter("Use either --dry-run or --live, not both.")

    _configure_logging()
    config_path = config.resolve()
    project_root = _project_root_for_config(config_path)
    load_dotenv(project_root / ".env")

    study_config = load_study_config(config_path)
    effective_dry_run = dry_run or (not live and study_config.dry_run.enabled_by_default)
    queries_path = _resolve_project_path(study_config.paths.queries, project_root)
    query_set = load_query_set(queries_path)

    result = run_collection(
        config=study_config,
        query_set=query_set,
        project_root=project_root,
        dry_run=effective_dry_run,
        use_cache=not no_cache,
    )

    typer.echo(
        "Completed raw collection: "
        f"{len(result.generated_files)} generated, {len(result.cache_hits)} cache hits."
    )


@app.command("score")
def score_command(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to the study YAML configuration."),
    ] = Path("config/study.yaml"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Use deterministic local judge with no API calls."),
    ] = False,
    heuristic_live_cache: Annotated[
        bool,
        typer.Option(
            "--heuristic-live-cache",
            help=(
                "Score existing live raw caches with the deterministic local heuristic; "
                "no judge API calls are made."
            ),
        ),
    ] = False,
    live: Annotated[
        bool,
        typer.Option("--live", help="Use live judge adapter when implemented."),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Regenerate scored JSON even when cached files exist."),
    ] = False,
    validation_sample: Annotated[
        bool,
        typer.Option(
            "--validation-sample/--no-validation-sample",
            help="Export deterministic CSV sample for manual review.",
        ),
    ] = True,
    aggregate: Annotated[
        bool,
        typer.Option(
            "--aggregate/--no-aggregate",
            help="Export a tidy scored CSV to the configured aggregated_csv path.",
        ),
    ] = False,
) -> None:
    """Score cached raw provider responses."""

    selected_modes = [dry_run, heuristic_live_cache, live]
    if sum(selected_modes) > 1:
        raise typer.BadParameter("Use only one scoring mode.")

    _configure_logging()
    config_path = config.resolve()
    project_root = _project_root_for_config(config_path)
    load_dotenv(project_root / ".env")

    study_config = load_study_config(config_path)
    effective_dry_run = dry_run or (
        not heuristic_live_cache and not live and study_config.dry_run.enabled_by_default
    )
    if live:
        raise typer.BadParameter("Live judge scoring is not implemented in Phase 3.")

    queries_path = _resolve_project_path(study_config.paths.queries, project_root)
    query_set = load_query_set(queries_path)

    result = score_collection(
        config=study_config,
        query_set=query_set,
        project_root=project_root,
        dry_run=effective_dry_run,
        use_cache=not no_cache,
        export_validation_sample=validation_sample,
        heuristic_live_cache=heuristic_live_cache,
        export_aggregated_csv=aggregate,
    )

    typer.echo(
        "Completed scoring: "
        f"{len(result.generated_files)} generated, "
        f"{len(result.cache_hits)} cache hits, "
        f"{len(result.missing_raw_files)} missing raw records."
    )
    if result.validation_sample_path:
        typer.echo(f"Validation sample: {result.validation_sample_path}")
    if result.aggregated_csv_path:
        typer.echo(f"Aggregated CSV: {result.aggregated_csv_path}")


@app.command("analyse")
def analyse_command(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to the study YAML configuration."),
    ] = Path("config/study.yaml"),
) -> None:
    """Build Power BI friendly summary tables from the aggregated scored CSV.

    Reshapes existing scored data only; makes no provider or judge calls.
    """

    _configure_logging()
    config_path = config.resolve()
    project_root = _project_root_for_config(config_path)

    study_config = load_study_config(config_path)
    aggregated_csv = _resolve_project_path(study_config.paths.aggregated_csv, project_root)
    tables_dir = _resolve_project_path(study_config.paths.tables_dir, project_root)

    result = build_summary_tables(aggregated_csv=aggregated_csv, tables_dir=tables_dir)

    typer.echo(f"Wrote {len(result.written_files)} summary tables to {result.tables_dir}")


def _configure_logging() -> None:
    try:
        from rich.logging import RichHandler
    except ImportError:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(markup=False, show_path=False)],
    )


def _project_root_for_config(config_path: Path) -> Path:
    if config_path.parent.name == "config":
        return config_path.parent.parent
    return config_path.parent


def _resolve_project_path(path: Path, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path
