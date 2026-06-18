from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from oecd_ai_visibility.analysis import (
    PROMINENCE_LEVELS,
    AnalysisInputError,
    build_summary_tables,
    competitor_mention_frequency_table,
    load_scored_frame,
    mention_rate_table,
    prominence_distribution_table,
    publications_named_frequency_table,
    url_referenced_rate_table,
)

# Aggregated CSV columns that the summary tables read; mirrors scoring._aggregated_fields.
_CSV_FIELDS = [
    "provider",
    "model",
    "category",
    "oecd_mentioned",
    "oecd_prominence",
    "oecd_url_referenced",
    "oecd_publications_named",
    "competitors_mentioned",
]


def _row(
    *,
    provider: str,
    model: str,
    category: str,
    mentioned: bool,
    prominence: str,
    url: bool,
    publications: list[str],
    competitors: dict[str, str],
) -> dict[str, object]:
    return {
        "provider": provider,
        "model": model,
        "category": category,
        "oecd_mentioned": mentioned,
        "oecd_prominence": prominence,
        "oecd_url_referenced": url,
        "oecd_publications_named": publications,
        "competitors_mentioned": competitors,
    }


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row(
                provider="openai",
                model="gpt-4o",
                category="authority_standard_setting",
                mentioned=True,
                prominence="primary",
                url=True,
                publications=["PISA", "OECD AI Principles"],
                competitors={"IMF": "supporting", "World Bank": "incidental"},
            ),
            _row(
                provider="openai",
                model="gpt-4o",
                category="authority_standard_setting",
                mentioned=False,
                prominence="none",
                url=False,
                publications=[],
                competitors={},
            ),
            _row(
                provider="anthropic",
                model="claude-sonnet-4-6",
                category="authority_standard_setting",
                mentioned=True,
                prominence="supporting",
                url=False,
                publications=["PISA"],
                competitors={"IMF": "incidental"},
            ),
        ]
    )


def test_mention_rate_table_counts_and_rate() -> None:
    table = mention_rate_table(_frame())

    openai = table[table["provider"] == "openai"].iloc[0]
    assert openai["n_responses"] == 2
    assert openai["n_oecd_mentioned"] == 1
    assert openai["oecd_mention_rate"] == 0.5

    anthropic = table[table["provider"] == "anthropic"].iloc[0]
    assert anthropic["n_responses"] == 1
    assert anthropic["oecd_mention_rate"] == 1.0


def test_url_referenced_rate_table_counts_and_rate() -> None:
    table = url_referenced_rate_table(_frame())

    openai = table[table["provider"] == "openai"].iloc[0]
    assert openai["n_oecd_url_referenced"] == 1
    assert openai["oecd_url_referenced_rate"] == 0.5

    anthropic = table[table["provider"] == "anthropic"].iloc[0]
    assert anthropic["n_oecd_url_referenced"] == 0
    assert anthropic["oecd_url_referenced_rate"] == 0.0


def test_prominence_distribution_is_complete_and_shares_sum_to_one() -> None:
    table = prominence_distribution_table(_frame())

    # Every (provider, model, category) group reports one row per prominence level.
    group_sizes = table.groupby(["provider", "model", "category"]).size()
    assert set(group_sizes.unique()) == {len(PROMINENCE_LEVELS)}

    openai = table[table["provider"] == "openai"]
    by_level = dict(zip(openai["oecd_prominence"], openai["n_responses"], strict=True))
    assert by_level == {"none": 1, "incidental": 0, "supporting": 0, "primary": 1}
    assert openai["group_total"].unique().tolist() == [2]
    assert round(openai["oecd_prominence_share"].sum(), 6) == 1.0

    # Levels are ordered none -> incidental -> supporting -> primary.
    assert openai["oecd_prominence"].tolist() == PROMINENCE_LEVELS


def test_publications_named_frequency_counts_per_provider_model() -> None:
    table = publications_named_frequency_table(_frame())

    pisa = table[table["publication"] == "PISA"]
    assert set(zip(pisa["provider"], pisa["n_mentions"], strict=True)) == {
        ("openai", 1),
        ("anthropic", 1),
    }
    principles = table[table["publication"] == "OECD AI Principles"]
    assert principles.iloc[0]["n_mentions"] == 1
    # Sorted by descending frequency.
    assert table["n_mentions"].tolist() == sorted(table["n_mentions"], reverse=True)


def test_competitor_mention_frequency_counts_responses() -> None:
    table = competitor_mention_frequency_table(_frame())

    imf = table[table["competitor"] == "IMF"]
    assert set(zip(imf["provider"], imf["n_mentions"], strict=True)) == {
        ("openai", 1),
        ("anthropic", 1),
    }
    world_bank = table[table["competitor"] == "World Bank"]
    assert world_bank.iloc[0]["n_mentions"] == 1
    assert "" not in set(table["competitor"])  # empty competitor maps must not leak rows


def test_load_scored_frame_parses_typed_columns(tmp_path: Path) -> None:
    csv_path = _write_scored_csv(tmp_path, _frame())

    frame = load_scored_frame(csv_path)

    assert frame["oecd_mentioned"].tolist() == [True, False, True]
    assert frame["oecd_url_referenced"].tolist() == [True, False, False]
    assert frame.loc[0, "oecd_publications_named"] == ["PISA", "OECD AI Principles"]
    assert frame.loc[0, "competitors_mentioned"] == {
        "IMF": "supporting",
        "World Bank": "incidental",
    }
    assert frame.loc[1, "oecd_publications_named"] == []
    assert frame.loc[1, "competitors_mentioned"] == {}


def test_load_scored_frame_rejects_missing_required_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "scored_responses.csv"
    csv_path.write_text("provider,model,category\nopenai,gpt-4o,cat\n", encoding="utf-8")

    with pytest.raises(AnalysisInputError, match="missing required columns"):
        load_scored_frame(csv_path)


def test_load_scored_frame_rejects_invalid_boolean(tmp_path: Path) -> None:
    csv_path = _write_scored_csv(tmp_path, _frame())
    content = csv_path.read_text(encoding="utf-8").replace("True", "perhaps", 1)
    csv_path.write_text(content, encoding="utf-8")

    with pytest.raises(AnalysisInputError, match="Invalid boolean"):
        load_scored_frame(csv_path)


def test_load_scored_frame_rejects_invalid_json_shape(tmp_path: Path) -> None:
    frame = _frame()
    frame.at[0, "oecd_publications_named"] = {}
    csv_path = _write_scored_csv(tmp_path, frame)

    with pytest.raises(AnalysisInputError, match="Expected JSON list"):
        load_scored_frame(csv_path)


def test_build_summary_tables_writes_all_tables_deterministically(tmp_path: Path) -> None:
    csv_path = _write_scored_csv(tmp_path, _frame())
    tables_dir = tmp_path / "tables"

    result = build_summary_tables(aggregated_csv=csv_path, tables_dir=tables_dir)

    expected = {
        "oecd_mention_rate_by_provider_model_category.csv",
        "oecd_prominence_distribution_by_provider_model_category.csv",
        "oecd_url_referenced_rate_by_provider_model_category.csv",
        "oecd_publications_named_frequency.csv",
        "competitor_mention_frequency.csv",
    }
    assert {path.name for path in result.written_files} == expected
    assert all(path.exists() for path in result.written_files)

    first = {path.name: path.read_text(encoding="utf-8") for path in result.written_files}
    rerun = build_summary_tables(aggregated_csv=csv_path, tables_dir=tables_dir)
    second = {path.name: path.read_text(encoding="utf-8") for path in rerun.written_files}
    assert first == second  # rebuilding yields identical bytes


def _write_scored_csv(tmp_path: Path, frame: pd.DataFrame) -> Path:
    """Write a frame back to the on-disk aggregated CSV format (strings + JSON)."""

    csv_path = tmp_path / "scored_responses.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for record in frame.to_dict(orient="records"):
            writer.writerow(
                {
                    "provider": record["provider"],
                    "model": record["model"],
                    "category": record["category"],
                    "oecd_mentioned": record["oecd_mentioned"],
                    "oecd_prominence": record["oecd_prominence"],
                    "oecd_url_referenced": record["oecd_url_referenced"],
                    "oecd_publications_named": json.dumps(
                        record["oecd_publications_named"], sort_keys=True
                    ),
                    "competitors_mentioned": json.dumps(
                        record["competitors_mentioned"], sort_keys=True
                    ),
                }
            )
    return csv_path
