from pathlib import Path

import pytest
from pydantic import ValidationError

from oecd_ai_visibility.schemas import (
    JudgeScore,
    RawResponseRecord,
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
