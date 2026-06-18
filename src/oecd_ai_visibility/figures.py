"""Publication-ready figures built from the aggregated scored CSV.

These functions read the same tidy ``scored_responses.csv`` used by
:mod:`oecd_ai_visibility.analysis` and render plainly labelled matplotlib charts
for portfolio, PDF, and internal communications-intelligence use. They do no
live provider or judge calls; they only reshape and plot already-scored data.

Read ``METHODOLOGY.md`` before interpreting them: this is an exploratory snapshot
of a small provider/model set on a designed question set, scored by a
deterministic local heuristic. The figures describe what was measured and avoid
claims beyond the sample.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend: render to files, never to a display.

import matplotlib.pyplot as plt  # noqa: E402  (must follow backend selection)
import pandas as pd  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

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
_DPI = 220

_OECD_BLUE = "#0B4EA2"
_OECD_TEAL = "#007C89"
_OECD_AMBER = "#D9A441"
_OECD_CORAL = "#C65D3A"
_DARK_TEXT = "#25313B"
_MID_TEXT = "#52606D"
_GRID = "#D5DBE0"
_BAR_GREY = "#B8C2CC"
_PAGE_BG = "#FFFFFF"

_CATEGORY_LABELS = {
    "authority_standard_setting": "Authority / standards",
    "comparative_peer": "Comparative peer",
    "data_statistics": "Data / statistics",
    "generative_search_referral": "Citable-source referral",
    "named_product_recall": "Named OECD products",
    "policy_recommendation": "Generic policy advice",
}
_CATEGORY_STORY_ORDER = {
    "authority_standard_setting": 0,
    "comparative_peer": 1,
    "named_product_recall": 2,
    "generative_search_referral": 3,
    "data_statistics": 4,
    "policy_recommendation": 5,
}

_PROMINENCE_LABELS = {
    "none": "Not mentioned",
    "incidental": "Incidental",
    "supporting": "Supporting",
    "primary": "Primary",
}
_PROMINENCE_COLORS = {
    "none": "#D8DEE3",
    "incidental": _OECD_AMBER,
    "supporting": "#5DA7C9",
    "primary": _OECD_BLUE,
}


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
        "oecd_visibility_summary.png": visibility_summary_figure,
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
    return table.sort_values(
        ["oecd_mention_rate", "n_oecd_mentioned", *_MODEL_KEYS],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)


def mention_rate_by_category(frame: pd.DataFrame) -> pd.DataFrame:
    """OECD mention rate per category (across all providers/models)."""

    table = frame.groupby("category", as_index=False).agg(
        n_responses=("oecd_mentioned", "size"),
        n_oecd_mentioned=("oecd_mentioned", "sum"),
    )
    table["n_oecd_mentioned"] = table["n_oecd_mentioned"].astype(int)
    table["oecd_mention_rate"] = _safe_rate(table["n_oecd_mentioned"], table["n_responses"])
    table["_story_order"] = table["category"].map(_CATEGORY_STORY_ORDER).fillna(999)
    return (
        table.sort_values(
            ["oecd_mention_rate", "_story_order", "category"],
            ascending=[False, True, True],
        )
        .drop(columns="_story_order")
        .reset_index(drop=True)
    )


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

    provider_label = {
        "anthropic": "Anthropic",
        "openai": "OpenAI",
    }.get(provider, provider.title())
    return f"{provider_label}\n{model}"


def _category_label(category: str) -> str:
    """Reader-facing label for a query category."""

    return _CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def _compact_peer_label(peer: str) -> str:
    """Shorten long peer names in compact dashboard panels."""

    return {"World Economic Forum": "WEF"}.get(peer, peer)


def _style_figure(figure: plt.Figure) -> None:
    figure.patch.set_facecolor(_PAGE_BG)
    for axis in figure.axes:
        axis.set_facecolor(_PAGE_BG)
        axis.tick_params(colors=_DARK_TEXT, labelsize=9)
        axis.xaxis.label.set_color(_DARK_TEXT)
        axis.yaxis.label.set_color(_DARK_TEXT)
        axis.title.set_color(_DARK_TEXT)
        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)
        axis.spines["left"].set_color(_GRID)
        axis.spines["bottom"].set_color(_GRID)


def _apply_percent_axis(axis: plt.Axes, *, orientation: str) -> None:
    formatter = PercentFormatter(xmax=1.0, decimals=0)
    if orientation == "x":
        axis.xaxis.set_major_formatter(formatter)
    else:
        axis.yaxis.set_major_formatter(formatter)


def _add_source_note(figure: plt.Figure) -> None:
    figure.text(
        0.01,
        0.01,
        (
            "Source: local scored responses only. Exploratory sample; "
            "competitor counts use configured peers."
        ),
        ha="left",
        va="bottom",
        fontsize=8,
        color=_MID_TEXT,
    )


def _set_title_with_subtitle(axis: plt.Axes, *, title: str, subtitle: str) -> None:
    axis.set_title(title, loc="left", fontsize=12, weight="bold", pad=26)
    axis.text(
        0,
        1.015,
        subtitle,
        transform=axis.transAxes,
        fontsize=9,
        color=_MID_TEXT,
        va="bottom",
    )


def _write_rate_labels(
    axis: plt.Axes,
    *,
    rates: pd.Series,
    counts: pd.Series,
    totals: pd.Series,
    orientation: str,
) -> None:
    for index, (rate, count, total) in enumerate(zip(rates, counts, totals, strict=True)):
        label = f"{rate:.0%} ({int(count)}/{int(total)})"
        if orientation == "vertical":
            axis.text(
                index,
                min(float(rate) + 0.025, 1.045),
                label,
                ha="center",
                va="bottom",
                fontsize=9,
            )
        else:
            if rate >= 0.92:
                axis.text(
                    float(rate) - 0.025,
                    index,
                    label,
                    ha="right",
                    va="center",
                    fontsize=9,
                    color="white",
                )
            else:
                axis.text(
                    min(float(rate) + 0.025, 1.045),
                    index,
                    label,
                    va="center",
                    fontsize=9,
                )


def mention_rate_by_provider_model_figure(frame: pd.DataFrame) -> plt.Figure:
    """Bar chart of OECD mention rate per provider/model."""

    table = mention_rate_by_provider_model(frame)
    labels = [_model_label(p, m) for p, m in zip(table["provider"], table["model"], strict=True)]

    figure, axis = plt.subplots(figsize=(6.8, 4.2))
    axis.bar(labels, table["oecd_mention_rate"], color=[_OECD_TEAL, _OECD_BLUE][: len(labels)])
    axis.set_ylim(0, 1.08)
    _apply_percent_axis(axis, orientation="y")
    axis.set_ylabel("Share of responses mentioning OECD")
    axis.set_xlabel("Provider / model")
    _set_title_with_subtitle(
        axis,
        title="Provider-level OECD visibility is even in this sample",
        subtitle="Both measured providers mention OECD in 23 of 30 responses.",
    )
    _write_rate_labels(
        axis,
        rates=table["oecd_mention_rate"],
        counts=table["n_oecd_mentioned"],
        totals=table["n_responses"],
        orientation="vertical",
    )
    axis.grid(axis="y", color=_GRID, linestyle="-", linewidth=0.8, alpha=0.8)
    _style_figure(figure)
    _add_source_note(figure)
    figure.tight_layout(rect=(0, 0.04, 1, 0.92))
    return figure


def mention_rate_by_category_figure(frame: pd.DataFrame) -> plt.Figure:
    """Horizontal bar chart of OECD mention rate per category."""

    table = mention_rate_by_category(frame)
    labels = [_category_label(category) for category in table["category"]]
    colors = [
        _OECD_CORAL if category == "policy_recommendation" else _OECD_BLUE
        for category in table["category"]
    ]

    figure, axis = plt.subplots(figsize=(9, 4.8))
    axis.barh(labels, table["oecd_mention_rate"], color=colors)
    axis.set_xlim(0, 1.08)
    _apply_percent_axis(axis, orientation="x")
    axis.set_xlabel("Share of responses mentioning OECD")
    axis.set_ylabel("Query category")
    _set_title_with_subtitle(
        axis,
        title="OECD visibility depends more on query intent than provider",
        subtitle=(
            "Source-seeking and named-product prompts surface OECD; generic policy advice does not."
        ),
    )
    axis.invert_yaxis()
    _write_rate_labels(
        axis,
        rates=table["oecd_mention_rate"],
        counts=table["n_oecd_mentioned"],
        totals=table["n_responses"],
        orientation="horizontal",
    )
    axis.grid(axis="x", color=_GRID, linestyle="-", linewidth=0.8, alpha=0.8)
    _style_figure(figure)
    _add_source_note(figure)
    figure.tight_layout(rect=(0, 0.04, 1, 0.92))
    return figure


def prominence_distribution_figure(frame: pd.DataFrame) -> plt.Figure:
    """Stacked bar chart of OECD prominence shares per provider/model."""

    table = prominence_distribution_by_provider_model(frame)
    pivot = table.pivot(
        index=_MODEL_KEYS, columns="oecd_prominence", values="oecd_prominence_share"
    ).reindex(columns=PROMINENCE_LEVELS, fill_value=0.0)

    labels = [_model_label(p, m) for p, m in pivot.index]
    colors = {level: _PROMINENCE_COLORS[level] for level in PROMINENCE_LEVELS}

    figure, axis = plt.subplots(figsize=(7.2, 4.5))
    bottom = [0.0] * len(labels)
    for level in PROMINENCE_LEVELS:
        values = pivot[level].tolist()
        axis.bar(
            labels,
            values,
            bottom=bottom,
            label=_PROMINENCE_LABELS[level],
            color=colors[level],
        )
        for index, value in enumerate(values):
            if value >= 0.12:
                axis.text(
                    index,
                    bottom[index] + value / 2,
                    f"{value:.0%}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=_DARK_TEXT if level in {"none", "incidental"} else "white",
                )
        bottom = [b + v for b, v in zip(bottom, values, strict=True)]

    axis.set_ylim(0, 1)
    _apply_percent_axis(axis, orientation="y")
    axis.set_ylabel("Share of responses")
    axis.set_xlabel("Provider / model")
    _set_title_with_subtitle(
        axis,
        title="When OECD appears, it is usually substantive",
        subtitle="No incidental-only OECD mentions appear in the current scored corpus.",
    )
    axis.legend(title="OECD prominence", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
    axis.grid(axis="y", color=_GRID, linestyle="-", linewidth=0.8, alpha=0.8)
    _style_figure(figure)
    _add_source_note(figure)
    figure.tight_layout(rect=(0, 0.04, 0.84, 0.92))
    return figure


def competitor_mention_frequency_figure(frame: pd.DataFrame) -> plt.Figure:
    """Horizontal bar chart of the most frequently mentioned peer organisations."""

    table = competitor_mention_totals(frame).head(_MAX_COMPETITORS)
    # Plot most frequent at the top.
    table = table.iloc[::-1].reset_index(drop=True)

    figure, axis = plt.subplots(figsize=(8.8, max(4.8, 0.45 * len(table))))
    bars = axis.barh(table["competitor"], table["n_mentions"], color=_BAR_GREY)
    if bars:
        bars[-1].set_color(_OECD_TEAL)
    axis.set_xlabel("Responses mentioning organisation")
    axis.set_ylabel("Configured peer organisation")
    _set_title_with_subtitle(
        axis,
        title="Configured peers most often co-visible with OECD topics",
        subtitle=(
            "Directional only: human validation found relevant organisations "
            "outside the configured list."
        ),
    )
    for index, count in enumerate(table["n_mentions"]):
        axis.text(count, index, f" {count}", va="center", fontsize=9)
    axis.grid(axis="x", color=_GRID, linestyle="-", linewidth=0.8, alpha=0.8)
    _style_figure(figure)
    _add_source_note(figure)
    figure.tight_layout(rect=(0, 0.04, 1, 0.92))
    return figure


def visibility_summary_figure(frame: pd.DataFrame) -> plt.Figure:
    """One-page visual summary for portfolio/PDF use."""

    total_responses = len(frame)
    total_mentions = int(frame["oecd_mentioned"].sum())
    overall_rate = total_mentions / total_responses if total_responses else 0.0

    category_table = mention_rate_by_category(frame)
    provider_table = mention_rate_by_provider_model(frame)
    prominence_counts = (
        frame["oecd_prominence"].value_counts().reindex(PROMINENCE_LEVELS, fill_value=0)
    )
    competitor_table = competitor_mention_totals(frame).head(8).iloc[::-1].reset_index(drop=True)

    figure = plt.figure(figsize=(11, 8.5))
    grid = figure.add_gridspec(
        3,
        2,
        height_ratios=[0.72, 1.7, 1.45],
        width_ratios=[1.18, 1],
        hspace=0.55,
        wspace=0.33,
    )

    header = figure.add_subplot(grid[0, :])
    header.axis("off")
    header.text(
        0,
        0.86,
        "OECD AI Visibility: category intent drives discoverability",
        fontsize=18,
        weight="bold",
        color=_DARK_TEXT,
        ha="left",
        va="top",
    )
    header.text(
        0,
        0.46,
        (
            f"{total_mentions}/{total_responses} responses mention OECD "
            f"({overall_rate:.0%}). Both measured providers are 23/30; "
            "the gap is in generic policy-advice prompts."
        ),
        fontsize=10,
        color=_MID_TEXT,
        ha="left",
        va="top",
    )
    header.text(
        0,
        0.12,
        (
            "Exploratory local scored sample. Core OECD mention/prominence metrics passed "
            "human validation; configured-peer counts remain directional."
        ),
        fontsize=9,
        color=_MID_TEXT,
        ha="left",
        va="top",
    )

    category_axis = figure.add_subplot(grid[1, 0])
    category_labels = [_category_label(category) for category in category_table["category"]]
    category_colors = [
        _OECD_CORAL if category == "policy_recommendation" else _OECD_BLUE
        for category in category_table["category"]
    ]
    category_axis.barh(category_labels, category_table["oecd_mention_rate"], color=category_colors)
    category_axis.set_xlim(0, 1.08)
    _apply_percent_axis(category_axis, orientation="x")
    category_axis.set_title(
        "Mention rate by query category",
        loc="left",
        fontsize=11,
        weight="bold",
    )
    category_axis.set_xlabel("Responses mentioning OECD")
    category_axis.invert_yaxis()
    _write_rate_labels(
        category_axis,
        rates=category_table["oecd_mention_rate"],
        counts=category_table["n_oecd_mentioned"],
        totals=category_table["n_responses"],
        orientation="horizontal",
    )
    category_axis.grid(axis="x", color=_GRID, linestyle="-", linewidth=0.8, alpha=0.8)

    provider_axis = figure.add_subplot(grid[1, 1])
    provider_labels = [
        _model_label(p, m)
        for p, m in zip(provider_table["provider"], provider_table["model"], strict=True)
    ]
    provider_axis.bar(
        provider_labels,
        provider_table["oecd_mention_rate"],
        color=[_OECD_TEAL, _OECD_BLUE],
    )
    provider_axis.set_ylim(0, 1.08)
    _apply_percent_axis(provider_axis, orientation="y")
    provider_axis.set_title("Provider/model comparison", loc="left", fontsize=11, weight="bold")
    _write_rate_labels(
        provider_axis,
        rates=provider_table["oecd_mention_rate"],
        counts=provider_table["n_oecd_mentioned"],
        totals=provider_table["n_responses"],
        orientation="vertical",
    )
    provider_axis.grid(axis="y", color=_GRID, linestyle="-", linewidth=0.8, alpha=0.8)

    prominence_axis = figure.add_subplot(grid[2, 0])
    prominence_labels = [_PROMINENCE_LABELS[level] for level in PROMINENCE_LEVELS]
    prominence_axis.bar(
        prominence_labels,
        prominence_counts.tolist(),
        color=[_PROMINENCE_COLORS[level] for level in PROMINENCE_LEVELS],
    )
    prominence_axis.set_title(
        "OECD prominence across responses",
        loc="left",
        fontsize=11,
        weight="bold",
    )
    prominence_axis.set_ylabel("Responses")
    for index, count in enumerate(prominence_counts.tolist()):
        prominence_axis.text(
            index,
            count + 0.6,
            str(int(count)),
            ha="center",
            va="bottom",
            fontsize=9,
        )
    prominence_axis.set_ylim(0, max(prominence_counts.max() + 6, 10))
    prominence_axis.tick_params(axis="x", labelrotation=0)
    prominence_axis.grid(axis="y", color=_GRID, linestyle="-", linewidth=0.8, alpha=0.8)

    peers_axis = figure.add_subplot(grid[2, 1])
    peer_labels = [_compact_peer_label(peer) for peer in competitor_table["competitor"]]
    peers_axis.barh(peer_labels, competitor_table["n_mentions"], color=_BAR_GREY)
    peers_axis.set_title("Top configured peers", loc="left", fontsize=11, weight="bold")
    peers_axis.set_xlabel("Mentions")
    for index, count in enumerate(competitor_table["n_mentions"]):
        peers_axis.text(count, index, f" {count}", va="center", fontsize=9)
    peers_axis.grid(axis="x", color=_GRID, linestyle="-", linewidth=0.8, alpha=0.8)

    _style_figure(figure)
    _add_source_note(figure)
    figure.subplots_adjust(left=0.16, right=0.97, top=0.96, bottom=0.10)
    return figure
