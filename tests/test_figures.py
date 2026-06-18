from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from oecd_ai_visibility.figures import (
    build_figures,
    competitor_mention_frequency_figure,
    competitor_mention_totals,
    mention_rate_by_category,
    mention_rate_by_category_figure,
    mention_rate_by_provider_model,
    mention_rate_by_provider_model_figure,
    prominence_distribution_by_provider_model,
    prominence_distribution_figure,
)

# Aggregated CSV columns the figures read; mirrors scoring._aggregated_fields.
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
    competitors: dict[str, str],
) -> dict[str, object]:
    return {
        "provider": provider,
        "model": model,
        "category": category,
        "oecd_mentioned": mentioned,
        "oecd_prominence": prominence,
        "oecd_url_referenced": False,
        "oecd_publications_named": [],
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
                competitors={"IMF": "supporting", "World Bank": "incidental"},
            ),
            _row(
                provider="openai",
                model="gpt-4o",
                category="policy_recommendation",
                mentioned=False,
                prominence="none",
                competitors={},
            ),
            _row(
                provider="anthropic",
                model="claude-sonnet-4-6",
                category="authority_standard_setting",
                mentioned=True,
                prominence="supporting",
                competitors={"IMF": "incidental"},
            ),
            _row(
                provider="anthropic",
                model="claude-sonnet-4-6",
                category="policy_recommendation",
                mentioned=True,
                prominence="supporting",
                competitors={"World Bank": "supporting"},
            ),
        ]
    )


def test_mention_rate_by_provider_model_counts_and_rate() -> None:
    table = mention_rate_by_provider_model(_frame())

    openai = table[table["provider"] == "openai"].iloc[0]
    assert openai["n_responses"] == 2
    assert openai["n_oecd_mentioned"] == 1
    assert openai["oecd_mention_rate"] == 0.5

    anthropic = table[table["provider"] == "anthropic"].iloc[0]
    assert anthropic["n_responses"] == 2
    assert anthropic["oecd_mention_rate"] == 1.0


def test_mention_rate_by_category_aggregates_across_providers() -> None:
    table = mention_rate_by_category(_frame())

    authority = table[table["category"] == "authority_standard_setting"].iloc[0]
    assert authority["n_responses"] == 2
    assert authority["oecd_mention_rate"] == 1.0

    policy = table[table["category"] == "policy_recommendation"].iloc[0]
    assert policy["n_responses"] == 2
    assert policy["n_oecd_mentioned"] == 1
    assert policy["oecd_mention_rate"] == 0.5


def test_prominence_distribution_is_complete_and_shares_sum_to_one() -> None:
    table = prominence_distribution_by_provider_model(_frame())

    # Every (provider, model) group reports one row per prominence level.
    group_sizes = table.groupby(["provider", "model"]).size()
    assert set(group_sizes.unique()) == {4}

    openai = table[table["provider"] == "openai"]
    by_level = dict(zip(openai["oecd_prominence"], openai["n_responses"], strict=True))
    assert by_level == {"none": 1, "incidental": 0, "supporting": 0, "primary": 1}
    assert round(openai["oecd_prominence_share"].sum(), 6) == 1.0


def test_competitor_mention_totals_counts_and_orders() -> None:
    table = competitor_mention_totals(_frame())

    counts = dict(zip(table["competitor"], table["n_mentions"], strict=True))
    assert counts == {"IMF": 2, "World Bank": 2}
    # Descending frequency then alphabetical: IMF before World Bank on the tie.
    assert table["competitor"].tolist() == ["IMF", "World Bank"]
    assert "" not in counts  # empty competitor maps must not leak rows


def test_figure_builders_return_figures_with_axes() -> None:
    frame = _frame()
    for builder in (
        mention_rate_by_provider_model_figure,
        mention_rate_by_category_figure,
        prominence_distribution_figure,
        competitor_mention_frequency_figure,
    ):
        figure = builder(frame)
        assert figure.axes  # at least one axis was drawn
        assert figure.axes[0].get_title()  # title is set


def test_build_figures_writes_all_png_files(tmp_path: Path) -> None:
    csv_path = _write_scored_csv(tmp_path, _frame())
    figures_dir = tmp_path / "figures"

    result = build_figures(aggregated_csv=csv_path, figures_dir=figures_dir)

    expected = {
        "oecd_mention_rate_by_provider_model.png",
        "oecd_mention_rate_by_category.png",
        "oecd_prominence_distribution.png",
        "competitor_mention_frequency.png",
    }
    assert {path.name for path in result.written_files} == expected
    assert all(path.exists() and path.stat().st_size > 0 for path in result.written_files)
    # PNG magic number, so we know real images were written.
    for path in result.written_files:
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


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
