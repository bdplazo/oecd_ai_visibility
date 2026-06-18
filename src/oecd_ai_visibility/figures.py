"""Phase 5 sanity figures built from the aggregated scored CSV.

These functions read the same tidy ``scored_responses.csv`` used by
:mod:`oecd_ai_visibility.analysis` and render small, plainly labelled matplotlib
charts for a quick visual check of the measured data. They do no live provider or
judge calls; they only reshape and plot already-scored data.

The charts are deliberately minimal sanity checks, not report graphics. Read
``METHODOLOGY.md`` before interpreting them: this is an exploratory snapshot of a
small provider/model set on a designed question set, scored by a deterministic
local heuristic. The figures describe what was measured; they draw no conclusions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend: render to files, never to a display.

import matplotlib.pyplot as plt  # noqa: E402  (must follow backend selection)
import pandas as pd  # noqa: E402

from oecd_ai_visibility.analysis import (  # noqa: E402
    PROMINENCE_LEVELS,
    _safe_rate,
    load_scored_frame,
)

LOGGER = logging.getLogger(__name__)

#: Grain for the per-model summaries that do not split by category.
_MODEL_KEYS = ["provider", "model"]

#: Largest number of competitors to show in the frequency chart, to keep it readable.
_MAX_COMPETITORS = 15

#: Shared figure resolution for the saved PNGs.
_DPI = 150


@dataclass(frozen=True)
class FiguresResult:
    """Paths written by :func:`build_figures`."""

    figures_dir: Path
    written_files: list[Path] = field(default_factory=list)


def build_figures(
    *,
    aggregated_csv: Path,
    figures_dir: Path,
    logger: logging.Logger | None = None,
) -> FiguresResult:
    """Read the aggregated scored CSV and write all sanity figures as PNGs.

    Parameters are explicit paths so callers can resolve them from config.
    """

    log = logger or LOGGER
    frame = load_scored_frame(aggregated_csv)
    figures_dir.mkdir(parents=True, exist_ok=True)

    builders = {
        "oecd_mention_rate_by_provider_model.png": mention_rate_by_provider_model_figure,
        "oecd_mention_rate_by_category.png": mention_rate_by_category_figure,
        "oecd_prominence_distribution.png": prominence_distribution_figure,
        "competitor_mention_frequency.png": competitor_mention_frequency_figure,
    }

    written_files: list[Path] = []
    for filename, builder in builders.items():
        path = figures_dir / filename
        figure = builder(frame)
        figure.savefig(path, dpi=_DPI, bbox_inches="tight")
        plt.close(figure)
        log.info("Wrote figure: %s", path)
        written_files.append(path)

    return FiguresResult(figures_dir=figures_dir, written_files=written_files)


def mention_rate_by_provider_model(frame: pd.DataFrame) -> pd.DataFrame:
    """OECD mention rate per provider/model (across all categories)."""

    table = frame.groupby(_MODEL_KEYS, as_index=False).agg(
        n_responses=("oecd_mentioned", "size"),
        n_oecd_mentioned=("oecd_mentioned", "sum"),
    )
    table["n_oecd_mentioned"] = table["n_oecd_mentioned"].astype(int)
    table["oecd_mention_rate"] = _safe_rate(table["n_oecd_mentioned"], table["n_responses"])
    return table.sort_values(_MODEL_KEYS).reset_index(drop=True)


def mention_rate_by_category(frame: pd.DataFrame) -> pd.DataFrame:
    """OECD mention rate per category (across all providers/models)."""

    table = frame.groupby("category", as_index=False).agg(
        n_responses=("oecd_mentioned", "size"),
        n_oecd_mentioned=("oecd_mentioned", "sum"),
    )
    table["n_oecd_mentioned"] = table["n_oecd_mentioned"].astype(int)
    table["oecd_mention_rate"] = _safe_rate(table["n_oecd_mentioned"], table["n_responses"])
    return table.sort_values("category").reset_index(drop=True)


def prominence_distribution_by_provider_model(frame: pd.DataFrame) -> pd.DataFrame:
    """OECD prominence shares per provider/model, one row per level.

    Every (provider, model) group reports one row per prominence level (zero-filled
    where a level does not occur) so the stacked bars stay complete and comparable.
    """

    counts = (
        frame.groupby([*_MODEL_KEYS, "oecd_prominence"], as_index=False)
        .size()
        .rename(columns={"size": "n_responses"})
    )

    groups = frame[_MODEL_KEYS].drop_duplicates()
    levels = pd.DataFrame({"oecd_prominence": PROMINENCE_LEVELS})
    full = groups.merge(levels, how="cross")

    table = full.merge(counts, on=[*_MODEL_KEYS, "oecd_prominence"], how="left")
    table["n_responses"] = table["n_responses"].fillna(0).astype(int)

    group_totals = table.groupby(_MODEL_KEYS)["n_responses"].transform("sum")
    table["oecd_prominence_share"] = _safe_rate(table["n_responses"], group_totals)

    table["oecd_prominence"] = pd.Categorical(
        table["oecd_prominence"], categories=PROMINENCE_LEVELS, ordered=True
    )
    table = table.sort_values([*_MODEL_KEYS, "oecd_prominence"]).reset_index(drop=True)
    table["oecd_prominence"] = table["oecd_prominence"].astype(str)
    return table


def competitor_mention_totals(frame: pd.DataFrame) -> pd.DataFrame:
    """Total responses mentioning each peer organisation (across providers/models).

    ``n_mentions`` counts responses naming the competitor at any prominence level.
    Rows are ordered by descending frequency, then competitor name.
    """

    competitor_lists = frame["competitors_mentioned"].map(lambda mapping: sorted(mapping))
    exploded = competitor_lists.explode().dropna()
    exploded = exploded[exploded != ""]
    table = exploded.value_counts().rename_axis("competitor").reset_index(name="n_mentions")
    return table.sort_values(["n_mentions", "competitor"], ascending=[False, True]).reset_index(
        drop=True
    )


def _model_label(provider: str, model: str) -> str:
    """Compact two-line axis label for a provider/model pair."""

    return f"{provider}\n{model}"


def mention_rate_by_provider_model_figure(frame: pd.DataFrame) -> plt.Figure:
    """Bar chart of OECD mention rate per provider/model."""

    table = mention_rate_by_provider_model(frame)
    labels = [_model_label(p, m) for p, m in zip(table["provider"], table["model"], strict=True)]

    figure, axis = plt.subplots(figsize=(max(6, 1.6 * len(labels)), 4.5))
    axis.bar(labels, table["oecd_mention_rate"], color="#1f77b4")
    axis.set_ylim(0, 1)
    axis.set_ylabel("OECD mention rate")
    axis.set_xlabel("Provider / model")
    axis.set_title("OECD mention rate by provider/model")
    for index, rate in enumerate(table["oecd_mention_rate"]):
        axis.text(index, rate + 0.02, f"{rate:.0%}", ha="center", va="bottom", fontsize=9)
    axis.grid(axis="y", linestyle=":", alpha=0.5)
    figure.tight_layout()
    return figure


def mention_rate_by_category_figure(frame: pd.DataFrame) -> plt.Figure:
    """Horizontal bar chart of OECD mention rate per category."""

    table = mention_rate_by_category(frame)

    figure, axis = plt.subplots(figsize=(8, max(4, 0.55 * len(table))))
    axis.barh(table["category"], table["oecd_mention_rate"], color="#2ca02c")
    axis.set_xlim(0, 1)
    axis.set_xlabel("OECD mention rate")
    axis.set_ylabel("Query category")
    axis.set_title("OECD mention rate by category")
    axis.invert_yaxis()  # highest category alphabetically at the top
    for index, rate in enumerate(table["oecd_mention_rate"]):
        axis.text(rate + 0.01, index, f"{rate:.0%}", va="center", fontsize=9)
    axis.grid(axis="x", linestyle=":", alpha=0.5)
    figure.tight_layout()
    return figure


def prominence_distribution_figure(frame: pd.DataFrame) -> plt.Figure:
    """Stacked bar chart of OECD prominence shares per provider/model."""

    table = prominence_distribution_by_provider_model(frame)
    pivot = table.pivot(
        index=_MODEL_KEYS, columns="oecd_prominence", values="oecd_prominence_share"
    ).reindex(columns=PROMINENCE_LEVELS, fill_value=0.0)

    labels = [_model_label(p, m) for p, m in pivot.index]
    colors = {
        "none": "#d3d3d3",
        "incidental": "#fdae6b",
        "supporting": "#6baed6",
        "primary": "#08519c",
    }

    figure, axis = plt.subplots(figsize=(max(6, 1.6 * len(labels)), 4.5))
    bottom = [0.0] * len(labels)
    for level in PROMINENCE_LEVELS:
        values = pivot[level].tolist()
        axis.bar(labels, values, bottom=bottom, label=level, color=colors[level])
        bottom = [b + v for b, v in zip(bottom, values, strict=True)]

    axis.set_ylim(0, 1)
    axis.set_ylabel("Share of responses")
    axis.set_xlabel("Provider / model")
    axis.set_title("OECD prominence distribution by provider/model")
    axis.legend(title="OECD prominence", bbox_to_anchor=(1.02, 1), loc="upper left")
    figure.tight_layout()
    return figure


def competitor_mention_frequency_figure(frame: pd.DataFrame) -> plt.Figure:
    """Horizontal bar chart of the most frequently mentioned peer organisations."""

    table = competitor_mention_totals(frame).head(_MAX_COMPETITORS)
    # Plot most frequent at the top.
    table = table.iloc[::-1].reset_index(drop=True)

    figure, axis = plt.subplots(figsize=(8, max(4, 0.45 * len(table))))
    axis.barh(table["competitor"], table["n_mentions"], color="#9467bd")
    axis.set_xlabel("Responses mentioning organisation")
    axis.set_ylabel("Peer organisation")
    axis.set_title("Competitor mention frequency")
    for index, count in enumerate(table["n_mentions"]):
        axis.text(count, index, f" {count}", va="center", fontsize=9)
    axis.grid(axis="x", linestyle=":", alpha=0.5)
    figure.tight_layout()
    return figure
