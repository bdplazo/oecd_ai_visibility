from pathlib import Path

import pytest
from pydantic import ValidationError

from oecd_ai_visibility.schemas import (
    JudgeScore,
    QuerySet,
    RawResponseRecord,
    StudyConfig,
    load_query_set,
    load_study_config,
)

ROOT = Path(__file__).resolve().parents[1]


def test_study_config_loads() -> None:
    config = load_study_config(ROOT / "config" / "study.yaml")

    assert config.n_runs == 1
    assert config.budget_eur > 0
    assert {provider.name for provider in config.providers} == {
        "anthropic",
        "gemini",
        "openai",
        "perplexity",
    }
    assert "World Bank" in config.peer_organisations


def test_query_set_loads_with_unique_ids_and_expected_size() -> None:
    query_set = load_query_set(ROOT / "data" / "queries.yaml")
    query_ids = [query.id for query in query_set.queries]
    categories = {query.category for query in query_set.queries}

    assert 24 <= len(query_set.queries) <= 30
    assert len(query_ids) == len(set(query_ids))
    assert {
        "authority_standard_setting",
        "policy_recommendation",
        "data_statistics",
        "named_product_recall",
        "comparative_peer",
        "generative_search_referral",
    }.issubset(categories)


def test_query_set_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="Query ids must be unique"):
        QuerySet.model_validate(
            {
                "version": "test",
                "design_note": "Synthetic duplicate-id test.",
                "queries": [
                    {
                        "id": "duplicate_id",
                        "category": "cat",
                        "text": "A long enough prompt for validation.",
                    },
                    {
                        "id": "duplicate_id",
                        "category": "cat",
                        "text": "Another long enough prompt for validation.",
                    },
                ],
            }
        )


def test_study_config_rejects_overlapping_raw_and_scored_paths() -> None:
    config = load_study_config(ROOT / "config" / "study.yaml")
    payload = config.model_dump(mode="python")
    payload["paths"]["scored_dir"] = payload["paths"]["raw_dir"]

    with pytest.raises(ValidationError, match="raw_dir and paths.scored_dir"):
        StudyConfig.model_validate(payload)


def test_study_config_rejects_generated_outputs_under_raw_dir() -> None:
    config = load_study_config(ROOT / "config" / "study.yaml")
    payload = config.model_dump(mode="python")
    payload["paths"]["aggregated_csv"] = Path("data/raw/scored_responses.csv")

    with pytest.raises(ValidationError, match="Generated outputs"):
        StudyConfig.model_validate(payload)


def test_judge_score_rejects_invalid_prominence() -> None:
    with pytest.raises(ValidationError):
        JudgeScore.model_validate(
            {
                "oecd_mentioned": True,
                "oecd_prominence": "dominant",
                "oecd_publications_named": [],
                "oecd_url_referenced": False,
                "competitors_mentioned": {},
                "factual_issues": "",
                "judge_confidence": "high",
            }
        )


def test_raw_response_record_requires_response_text() -> None:
    with pytest.raises(ValidationError):
        RawResponseRecord.model_validate(
            {
                "provider": "fixture",
                "model": "fixture-v1",
                "query_id": "product_pisa",
                "run_index": 0,
                "latency_seconds": 0.0,
                "response_text": "",
            }
        )
