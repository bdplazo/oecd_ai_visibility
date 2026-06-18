from __future__ import annotations

import csv
from pathlib import Path

from oecd_ai_visibility.judges.dry_run import DryRunJudge
from oecd_ai_visibility.runner import run_collection
from oecd_ai_visibility.schemas import (
    JudgeScore,
    QuerySet,
    RawResponseRecord,
    ScoredRecord,
    load_query_set,
    load_study_config,
)
from oecd_ai_visibility.scoring import (
    cache_path,
    export_scored_responses_csv,
    export_validation_sample_csv,
    score_collection,
)

ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_scoring_creates_valid_scored_records(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path, validation_sample_size=3)
    query_set = _fixture_query_set()
    run_collection(config=config, query_set=query_set, project_root=ROOT, dry_run=True)

    result = score_collection(
        config=config,
        query_set=query_set,
        project_root=ROOT,
        dry_run=True,
    )

    scored_files = sorted((tmp_path / "scored").glob("*.json"))
    assert len(scored_files) == len(query_set.queries)
    assert sorted(result.generated_files) == scored_files
    assert result.missing_raw_files == []
    assert result.validation_sample_path == tmp_path / "validation_sample.csv"

    records = [
        ScoredRecord.model_validate_json(path.read_text(encoding="utf-8")) for path in scored_files
    ]
    assert {record.judge_provider for record in records} == {"dry-run"}
    assert any(record.score.oecd_mentioned for record in records)
    assert any(record.score.oecd_url_referenced for record in records)
    assert any(record.score.competitors_mentioned for record in records)


def test_dry_run_scoring_cache_reuse_skips_rescoring(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    query_set = _fixture_query_set()
    run_collection(config=config, query_set=query_set, project_root=ROOT, dry_run=True)

    first_result = score_collection(
        config=config,
        query_set=query_set,
        project_root=ROOT,
        dry_run=True,
    )
    first_contents = {
        path.name: path.read_text(encoding="utf-8") for path in first_result.generated_files
    }

    second_result = score_collection(
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


def test_validation_sample_csv_is_deterministic_and_respects_size(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path, validation_sample_size=2)
    query_set = _fixture_query_set()
    run_collection(config=config, query_set=query_set, project_root=ROOT, dry_run=True)
    score_collection(
        config=config,
        query_set=query_set,
        project_root=ROOT,
        dry_run=True,
        export_validation_sample=False,
    )

    sample_path = export_validation_sample_csv(config=config, project_root=ROOT)
    first_content = sample_path.read_text(encoding="utf-8")
    second_path = export_validation_sample_csv(config=config, project_root=ROOT)
    second_content = second_path.read_text(encoding="utf-8")

    rows = list(csv.DictReader(first_content.splitlines()))
    assert first_content == second_content
    assert len(rows) == 2
    assert rows[0]["query_id"] <= rows[1]["query_id"]
    assert "response_text" in rows[0]
    assert "competitors_mentioned" in rows[0]


def test_heuristic_live_cache_scores_only_existing_live_raw_records(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    query_set = _fixture_query_set()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    for provider, model in [("openai", "gpt-4o"), ("anthropic", "claude-sonnet-4-6")]:
        raw_path = cache_path(
            output_dir=raw_dir,
            provider=provider,
            model=model,
            query_id="product_pisa",
            run_index=0,
        )
        raw_path.write_text(
            RawResponseRecord(
                provider=provider,
                model=model,
                query_id="product_pisa",
                run_index=0,
                latency_seconds=0.01,
                response_text="PISA is run by the OECD and reported at oecd.org.",
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )

    result = score_collection(
        config=config,
        query_set=query_set,
        project_root=ROOT,
        dry_run=False,
        heuristic_live_cache=True,
        export_validation_sample=False,
        use_cache=False,
    )

    scored_records = [
        ScoredRecord.model_validate_json(path.read_text(encoding="utf-8"))
        for path in result.generated_files
    ]
    assert len(scored_records) == 2
    assert result.missing_raw_files == [
        cache_path(
            output_dir=raw_dir,
            provider=provider,
            model=model,
            query_id=query_id,
            run_index=0,
        )
        for provider, model in [
            ("openai", "gpt-4o"),
            ("anthropic", "claude-sonnet-4-6"),
        ]
        for query_id in [query.id for query in query_set.queries if query.id != "product_pisa"]
    ]
    assert {record.provider for record in scored_records} == {"anthropic", "openai"}
    assert {record.judge_provider for record in scored_records} == {"heuristic-local"}
    assert all(record.score.oecd_mentioned for record in scored_records)


def test_export_scored_responses_csv_writes_power_bi_columns(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    scored_dir = tmp_path / "scored"
    scored_dir.mkdir()
    record = ScoredRecord(
        provider="openai",
        model="gpt-4o",
        query_id="product_pisa",
        category="named_product_recall",
        run_index=0,
        response_text="PISA is run by the OECD.",
        judge_provider="heuristic-local",
        judge_model="deterministic-v1",
        score=JudgeScore(
            oecd_mentioned=True,
            oecd_prominence="primary",
            oecd_url_referenced=False,
            oecd_publications_named=["PISA"],
            competitors_mentioned={"World Bank": "incidental"},
            judge_confidence="high",
        ),
    )
    (scored_dir / "openai__gpt-4o__product_pisa__0.json").write_text(
        record.model_dump_json(indent=2),
        encoding="utf-8",
    )

    csv_path = export_scored_responses_csv(config=config, project_root=ROOT)

    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
    assert csv_path == tmp_path / "scored_responses.csv"
    assert len(rows) == 1
    assert rows[0]["provider"] == "openai"
    assert rows[0]["model"] == "gpt-4o"
    assert rows[0]["query_id"] == "product_pisa"
    assert rows[0]["category"] == "named_product_recall"
    assert rows[0]["oecd_mentioned"] == "True"
    assert rows[0]["oecd_prominence"] == "primary"
    assert rows[0]["oecd_url_referenced"] == "False"
    assert rows[0]["oecd_publications_named"] == '["PISA"]'
    assert rows[0]["competitors_mentioned"] == '{"World Bank": "incidental"}'
    assert rows[0]["judge_confidence"] == "high"
    assert rows[0]["response_text"] == "PISA is run by the OECD."


def test_dry_run_judge_detects_fixture_behaviour(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    query_set = _fixture_query_set()
    query_by_id = {query.id: query for query in query_set.queries}
    judge = DryRunJudge(peer_organisations=config.peer_organisations)

    records = {
        query.id: _raw_record_for_query(config=config, query_set=query_set, query_id=query.id)
        for query in query_set.queries
    }

    primary_score = judge.score(
        raw_record=records["product_pisa"],
        query=query_by_id["product_pisa"],
    )
    peer_score = judge.score(
        raw_record=records["compare_economic_advice"],
        query=query_by_id["compare_economic_advice"],
    )
    citation_score = judge.score(
        raw_record=records["geo_citable_sources_ai_governance"],
        query=query_by_id["geo_citable_sources_ai_governance"],
    )
    no_mention_score = judge.score(
        raw_record=records["policy_sme_digitalisation"],
        query=query_by_id["policy_sme_digitalisation"],
    )

    assert primary_score.oecd_mentioned is True
    assert primary_score.oecd_prominence == "primary"
    assert peer_score.competitors_mentioned == {
        "IMF": "supporting",
        "World Bank": "supporting",
        "ILO": "supporting",
    }
    assert citation_score.oecd_url_referenced is True
    assert no_mention_score.oecd_mentioned is False
    assert no_mention_score.oecd_prominence == "none"


def _config_with_output_paths(tmp_path: Path, validation_sample_size: int = 12):
    config = load_study_config(ROOT / "config" / "study.yaml")
    return config.model_copy(
        update={
            "judge": config.judge.model_copy(
                update={"validation_sample_size": validation_sample_size}
            ),
            "paths": config.paths.model_copy(
                update={
                    "raw_dir": tmp_path / "raw",
                    "scored_dir": tmp_path / "scored",
                    "aggregated_csv": tmp_path / "scored_responses.csv",
                    "validation_sample_csv": tmp_path / "validation_sample.csv",
                }
            ),
        }
    )


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


def _raw_record_for_query(
    *,
    config,
    query_set: QuerySet,
    query_id: str,
) -> RawResponseRecord:
    query = next(query for query in query_set.queries if query.id == query_id)
    result = run_collection(
        config=config,
        query_set=query_set.model_copy(update={"queries": [query]}),
        project_root=ROOT,
        dry_run=True,
        use_cache=False,
    )
    return RawResponseRecord.model_validate_json(
        result.generated_files[0].read_text(encoding="utf-8")
    )
