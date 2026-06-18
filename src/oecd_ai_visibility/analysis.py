"""Phase 5 summary tables built from the aggregated scored CSV.

These functions read the tidy ``scored_responses.csv`` produced by the scoring
pipeline and derive small, Power BI friendly summary tables. They do no live
provider or judge calls; they only reshape already-scored data.

Read ``METHODOLOGY.md`` before interpreting the numbers: this is an exploratory
snapshot of two providers on a designed question set, scored by a deterministic
local heuristic. The tables describe what was measured; they draw no conclusions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger(__name__)

#: OECD prominence levels, from absent to most central. Used to keep the
#: distribution table complete (every group reports a row per level) and ordered.
PROMINENCE_LEVELS = ["none", "incidental", "supporting", "primary"]

#: Grain shared by the rate/distribution tables.
_GROUP_KEYS = ["provider", "model", "category"]

#: Decimal places used when rounding shares and rates for tidy output.
_RATE_DECIMALS = 4
_REQUIRED_AGGREGATED_COLUMNS = {
    *_GROUP_KEYS,
    "oecd_mentioned",
    "oecd_prominence",
    "oecd_url_referenced",
    "oecd_publications_named",
    "competitors_mentioned",
}


class AnalysisInputError(ValueError):
    """Raised when the aggregated scored CSV cannot be safely analysed."""


@dataclass(frozen=True)
class SummaryTablesResult:
    """Paths written by :func:`build_summary_tables`."""

    tables_dir: Path
    written_files: list[Path] = field(default_factory=list)


def build_summary_tables(
    *,
    aggregated_csv: Path,
    tables_dir: Path,
    logger: logging.Logger | None = None,
) -> SummaryTablesResult:
    """Read the aggregated scored CSV and write all summary tables.

    Parameters are explicit paths so callers can resolve them from config.
    """

    log = logger or LOGGER
    frame = load_scored_frame(aggregated_csv)
    tables_dir.mkdir(parents=True, exist_ok=True)

    tables = {
        "oecd_mention_rate_by_provider_model_category.csv": mention_rate_table(frame),
        "oecd_prominence_distribution_by_provider_model_category.csv": (
            prominence_distribution_table(frame)
        ),
        "oecd_url_referenced_rate_by_provider_model_category.csv": (
            url_referenced_rate_table(frame)
        ),
        "oecd_publications_named_frequency.csv": publications_named_frequency_table(frame),
        "competitor_mention_frequency.csv": competitor_mention_frequency_table(frame),
    }

    written_files: list[Path] = []
    for filename, table in tables.items():
        path = tables_dir / filename
        table.to_csv(path, index=False, encoding="utf-8")
        log.info("Wrote summary table: %s", path)
        written_files.append(path)

    return SummaryTablesResult(tables_dir=tables_dir, written_files=written_files)


def load_scored_frame(aggregated_csv: Path) -> pd.DataFrame:
    """Load the aggregated scored CSV with typed analysis columns.

    Booleans are parsed from their stringified form and the JSON list/dict columns
    (``oecd_publications_named``, ``competitors_mentioned``) are decoded into Python
    objects so downstream tables can group and explode them directly.
    """

    frame = pd.read_csv(aggregated_csv, dtype=str, keep_default_na=False)
    missing = sorted(_REQUIRED_AGGREGATED_COLUMNS - set(frame.columns))
    if missing:
        raise AnalysisInputError(f"{aggregated_csv} is missing required columns: {missing}")

    frame["oecd_mentioned"] = [
        _to_bool(value, field_name="oecd_mentioned", row_number=index + 2)
        for index, value in enumerate(frame["oecd_mentioned"])
    ]
    frame["oecd_url_referenced"] = [
        _to_bool(value, field_name="oecd_url_referenced", row_number=index + 2)
        for index, value in enumerate(frame["oecd_url_referenced"])
    ]
    frame["oecd_publications_named"] = [
        _parse_json_list(value, field_name="oecd_publications_named", row_number=index + 2)
        for index, value in enumerate(frame["oecd_publications_named"])
    ]
    frame["competitors_mentioned"] = [
        _parse_json_dict(value, field_name="competitors_mentioned", row_number=index + 2)
        for index, value in enumerate(frame["competitors_mentioned"])
    ]
    return frame


def mention_rate_table(frame: pd.DataFrame) -> pd.DataFrame:
    """OECD mention rate per provider/model/category."""

    table = frame.groupby(_GROUP_KEYS, as_index=False).agg(
        n_responses=("oecd_mentioned", "size"),
        n_oecd_mentioned=("oecd_mentioned", "sum"),
    )
    table["n_oecd_mentioned"] = table["n_oecd_mentioned"].astype(int)
    table["oecd_mention_rate"] = _safe_rate(table["n_oecd_mentioned"], table["n_responses"])
    return table.sort_values(_GROUP_KEYS).reset_index(drop=True)


def url_referenced_rate_table(frame: pd.DataFrame) -> pd.DataFrame:
    """OECD URL (``oecd.org``) referenced rate per provider/model/category.

    See ``METHODOLOGY.md``: this is a lower-bound proxy, not a citation measure.
    """

    table = frame.groupby(_GROUP_KEYS, as_index=False).agg(
        n_responses=("oecd_url_referenced", "size"),
        n_oecd_url_referenced=("oecd_url_referenced", "sum"),
    )
    table["n_oecd_url_referenced"] = table["n_oecd_url_referenced"].astype(int)
    table["oecd_url_referenced_rate"] = _safe_rate(
        table["n_oecd_url_referenced"], table["n_responses"]
    )
    return table.sort_values(_GROUP_KEYS).reset_index(drop=True)


def prominence_distribution_table(frame: pd.DataFrame) -> pd.DataFrame:
    """OECD prominence distribution per provider/model/category.

    Every group reports one row per prominence level (zero-filled where a level
    does not occur) so stacked charts and shares stay complete and comparable.
    """

    counts = (
        frame.groupby([*_GROUP_KEYS, "oecd_prominence"], as_index=False)
        .size()
        .rename(columns={"size": "n_responses"})
    )

    groups = frame[_GROUP_KEYS].drop_duplicates()
    levels = pd.DataFrame({"oecd_prominence": PROMINENCE_LEVELS})
    full = groups.merge(levels, how="cross")

    table = full.merge(counts, on=[*_GROUP_KEYS, "oecd_prominence"], how="left")
    table["n_responses"] = table["n_responses"].fillna(0).astype(int)

    group_totals = table.groupby(_GROUP_KEYS)["n_responses"].transform("sum")
    table["group_total"] = group_totals.astype(int)
    table["oecd_prominence_share"] = _safe_rate(table["n_responses"], table["group_total"])

    table["oecd_prominence"] = pd.Categorical(
        table["oecd_prominence"], categories=PROMINENCE_LEVELS, ordered=True
    )
    table = table.sort_values([*_GROUP_KEYS, "oecd_prominence"]).reset_index(drop=True)
    table["oecd_prominence"] = table["oecd_prominence"].astype(str)
    return table


def publications_named_frequency_table(frame: pd.DataFrame) -> pd.DataFrame:
    """How often each named OECD publication appears, per provider/model.

    One response names a publication at most once, so ``n_mentions`` is the number
    of responses naming it. Rows are ordered by descending frequency.
    """

    exploded = (
        frame[["provider", "model", "oecd_publications_named"]]
        .explode("oecd_publications_named")
        .dropna(subset=["oecd_publications_named"])
        .rename(columns={"oecd_publications_named": "publication"})
    )
    table = (
        exploded.groupby(["provider", "model", "publication"], as_index=False)
        .size()
        .rename(columns={"size": "n_mentions"})
    )
    return table.sort_values(
        ["n_mentions", "provider", "model", "publication"],
        ascending=[False, True, True, True],
    ).reset_index(drop=True)


def competitor_mention_frequency_table(frame: pd.DataFrame) -> pd.DataFrame:
    """How often each peer organisation is mentioned, per provider/model.

    ``n_mentions`` counts responses naming the competitor at any prominence level.
    Rows are ordered by descending frequency.
    """

    competitors = frame[["provider", "model", "competitors_mentioned"]].copy()
    competitors["competitor"] = competitors["competitors_mentioned"].map(
        lambda mapping: sorted(mapping)
    )
    exploded = competitors.explode("competitor").dropna(subset=["competitor"])
    table = (
        exploded.groupby(["provider", "model", "competitor"], as_index=False)
        .size()
        .rename(columns={"size": "n_mentions"})
    )
    return table.sort_values(
        ["n_mentions", "provider", "model", "competitor"],
        ascending=[False, True, True, True],
    ).reset_index(drop=True)


def _safe_rate(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Element-wise ``numerator / denominator``, yielding 0.0 where denominator is 0."""

    rate = numerator.div(denominator).where(denominator != 0, 0.0)
    return rate.round(_RATE_DECIMALS)


def _to_bool(value: object, *, field_name: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise AnalysisInputError(f"Invalid boolean in {field_name} at CSV row {row_number}: {value!r}")


def _parse_json_list(value: object, *, field_name: str, row_number: int) -> list[str]:
    if not str(value).strip():
        return []
    parsed = _parse_json(value, field_name=field_name, row_number=row_number)
    if not isinstance(parsed, list):
        raise AnalysisInputError(
            f"Expected JSON list in {field_name} at CSV row {row_number}: {value!r}"
        )
    return [str(item) for item in parsed]


def _parse_json_dict(value: object, *, field_name: str, row_number: int) -> dict[str, str]:
    if not str(value).strip():
        return {}
    parsed = _parse_json(value, field_name=field_name, row_number=row_number)
    if not isinstance(parsed, dict):
        raise AnalysisInputError(
            f"Expected JSON object in {field_name} at CSV row {row_number}: {value!r}"
        )
    return {str(key): str(value) for key, value in parsed.items()}


def _parse_json(value: object, *, field_name: str, row_number: int) -> object:
    text = str(value).strip()
    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise AnalysisInputError(
            f"Invalid JSON in {field_name} at CSV row {row_number}: {value!r}"
        ) from exc
