from __future__ import annotations

import logging
from pathlib import Path

from oecd_ai_visibility.providers.base import build_live_providers
from oecd_ai_visibility.runner import run_collection
from oecd_ai_visibility.schemas import (
    QuerySet,
    RawResponseRecord,
    load_query_set,
    load_study_config,
)

ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_creates_valid_raw_response_records(tmp_path: Path) -> None:
    config = _config_with_raw_dir(tmp_path / "raw")
    query_set = _fixture_query_set()

    result = run_collection(
        config=config,
        query_set=query_set,
        project_root=ROOT,
        dry_run=True,
    )

    raw_files = sorted((tmp_path / "raw").glob("*.json"))
    assert len(raw_files) == len(query_set.queries)
    assert sorted(result.generated_files) == raw_files

    records = [
        RawResponseRecord.model_validate_json(path.read_text(encoding="utf-8"))
        for path in raw_files
    ]
    assert {record.provider for record in records} == {"fixture"}
    assert any(record.citations for record in records)
    assert any("World Bank" in record.response_text for record in records)
    assert any("OECD" not in record.response_text for record in records)


def test_dry_run_cache_reuse_skips_regeneration(tmp_path: Path) -> None:
    config = _config_with_raw_dir(tmp_path / "raw")
    query_set = _fixture_query_set()

    first_result = run_collection(
        config=config,
        query_set=query_set,
        project_root=ROOT,
        dry_run=True,
    )
    first_contents = {
        path.name: path.read_text(encoding="utf-8") for path in first_result.generated_files
    }

    second_result = run_collection(
        config=config,
        query_set=query_set,
        project_root=ROOT,
        dry_run=True,
    )

    assert second_result.generated_files == []
    assert sorted(path.name for path in second_result.cache_hits) == sorted(first_contents)
    assert {
        path.name: path.read_text(encoding="utf-8") for path in second_result.cache_hits
    } == first_contents


def test_live_provider_builder_skips_missing_keys(
    monkeypatch,
    caplog,
) -> None:
    config = load_study_config(ROOT / "config" / "study.yaml")
    for provider in config.providers:
        if provider.env_var:
            monkeypatch.delenv(provider.env_var, raising=False)

    caplog.set_level(logging.WARNING)

    providers = build_live_providers(config.providers)

    assert providers == []
    for provider in config.providers:
        assert f"Skipping provider {provider.name}" in caplog.text


def _config_with_raw_dir(raw_dir: Path):
    config = load_study_config(ROOT / "config" / "study.yaml")
    return config.model_copy(update={"paths": config.paths.model_copy(update={"raw_dir": raw_dir})})


def _fixture_query_set() -> QuerySet:
    query_set = load_query_set(ROOT / "data" / "queries.yaml")
    selected_ids = {
        "product_pisa",
        "compare_economic_advice",
        "geo_citable_sources_ai_governance",
        "policy_sme_digitalisation",
    }
    return query_set.model_copy(
        update={"queries": [query for query in query_set.queries if query.id in selected_ids]}
    )
