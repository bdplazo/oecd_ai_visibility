"""Agreement metrics for the Phase 5.5 blind human validation sample.

The functions in this module compare the existing deterministic heuristic output
against the manually labelled gold-standard sample. They read local CSV artifacts
only and make no provider or judge calls.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

JOIN_KEY_FIELDS = ("provider", "model", "query_id", "run_index")
PROMINENCE_LEVELS = ("none", "incidental", "supporting", "primary")
T = TypeVar("T")

REVIEWED_VALIDATION_SAMPLE_CSV_NAME = "validation_sample_stratified_reviewed.csv"
VALIDATION_AGREEMENT_REPORT_NAME = "validation_agreement_report.md"
VALIDATION_AGREEMENT_ROWS_NAME = "validation_agreement_rows.csv"

_REQUIRED_REVIEW_COLUMNS = {
    *JOIN_KEY_FIELDS,
    "category",
    "human_oecd_mentioned",
    "human_oecd_prominence",
    "human_oecd_url_referenced",
    "human_oecd_publications_named",
    "human_competitors_mentioned",
}
_REQUIRED_HEURISTIC_COLUMNS = {
    *JOIN_KEY_FIELDS,
    "category",
    "oecd_mentioned",
    "oecd_prominence",
    "oecd_url_referenced",
    "oecd_publications_named",
    "competitors_mentioned",
    "judge_confidence",
}


@dataclass(frozen=True)
class AgreementBlock:
    """Agreement metrics for one group of reviewed rows."""

    name: str
    row_count: int
    mention_agreement: float
    mention_kappa: float
    missed_mentions: int
    false_positive_mentions: int
    prominence_exact_agreement: float
    prominence_adjacent_agreement: float
    prominence_weighted_kappa: float
    competitor_precision: float
    competitor_recall: float
    competitor_f1: float
    configured_competitor_recall: float
    publication_recall: float | None
    judge_confidence_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationAgreementResult:
    """Summary of one Phase 5.5 agreement-report export."""

    reviewed_path: Path
    heuristic_key_path: Path
    report_path: Path
    row_level_path: Path
    row_count: int
    overall: AgreementBlock
    provider_blocks: list[AgreementBlock]
    category_blocks: list[AgreementBlock]
    decision: str


@dataclass(frozen=True)
class _AgreementRow:
    provider: str
    model: str
    query_id: str
    run_index: str
    category: str
    heuristic_oecd_mentioned: bool
    human_oecd_mentioned: bool
    heuristic_oecd_prominence: str
    human_oecd_prominence: str
    heuristic_oecd_url_referenced: bool
    human_oecd_url_referenced: bool
    heuristic_publications: set[str]
    human_publications: set[str]
    heuristic_competitors: set[str]
    human_competitors: set[str]
    configured_human_competitors: set[str]
    judge_confidence: str


def export_validation_agreement_report(
    *,
    reviewed_path: Path,
    heuristic_key_path: Path,
    report_path: Path,
    row_level_path: Path,
    peer_organisations: Iterable[str],
) -> ValidationAgreementResult:
    """Compare the filled human-review CSV against the heuristic key.

    ``reviewed_path`` should be the blind review file after the reviewer has filled the
    ``human_*`` columns. ``heuristic_key_path`` is the separate key generated with the
    stratified sample. Outputs are a compact Markdown report and a row-level diagnostic CSV.
    """

    rows = _load_agreement_rows(
        reviewed_path=reviewed_path,
        heuristic_key_path=heuristic_key_path,
        peer_organisations=tuple(peer_organisations),
    )
    if not rows:
        raise ValueError("No reviewed rows found.")

    row_level_path.parent.mkdir(parents=True, exist_ok=True)
    _write_row_level_csv(row_level_path, rows)

    overall = _agreement_block("overall", rows)
    provider_blocks = _split_blocks(rows, "provider")
    category_blocks = _split_blocks(rows, "category")
    decision = _decision_label(overall)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _render_report(
            reviewed_path=reviewed_path,
            heuristic_key_path=heuristic_key_path,
            row_level_path=row_level_path,
            overall=overall,
            provider_blocks=provider_blocks,
            category_blocks=category_blocks,
            decision=decision,
            rows=rows,
            configured_peers=set(peer_organisations),
        ),
        encoding="utf-8",
    )

    return ValidationAgreementResult(
        reviewed_path=reviewed_path,
        heuristic_key_path=heuristic_key_path,
        report_path=report_path,
        row_level_path=row_level_path,
        row_count=len(rows),
        overall=overall,
        provider_blocks=provider_blocks,
        category_blocks=category_blocks,
        decision=decision,
    )


def _load_agreement_rows(
    *,
    reviewed_path: Path,
    heuristic_key_path: Path,
    peer_organisations: tuple[str, ...],
) -> list[_AgreementRow]:
    review_rows = _read_csv(reviewed_path, required_columns=_REQUIRED_REVIEW_COLUMNS)
    heuristic_rows = _read_csv(heuristic_key_path, required_columns=_REQUIRED_HEURISTIC_COLUMNS)
    review_by_key = _index_by_key(review_rows, reviewed_path)
    heuristic_by_key = _index_by_key(heuristic_rows, heuristic_key_path)

    review_keys = set(review_by_key)
    heuristic_keys = set(heuristic_by_key)
    if review_keys != heuristic_keys:
        missing_key = sorted(heuristic_keys - review_keys)[:3]
        extra_key = sorted(review_keys - heuristic_keys)[:3]
        raise ValueError(
            "Reviewed sample and heuristic key do not contain the same rows. "
            f"Missing from review: {missing_key}; missing from key: {extra_key}"
        )

    rows: list[_AgreementRow] = []
    for key in sorted(review_keys):
        review = review_by_key[key]
        heuristic = heuristic_by_key[key]
        human_competitors = _human_organisation_set(review["human_competitors_mentioned"])
        configured_human_competitors = {
            competitor for competitor in human_competitors if competitor in peer_organisations
        }
        rows.append(
            _AgreementRow(
                provider=review["provider"],
                model=review["model"],
                query_id=review["query_id"],
                run_index=review["run_index"],
                category=review["category"],
                heuristic_oecd_mentioned=_parse_bool(
                    heuristic["oecd_mentioned"],
                    field_name="oecd_mentioned",
                    key=key,
                ),
                human_oecd_mentioned=_parse_bool(
                    review["human_oecd_mentioned"],
                    field_name="human_oecd_mentioned",
                    key=key,
                ),
                heuristic_oecd_prominence=_parse_prominence(
                    heuristic["oecd_prominence"],
                    field_name="oecd_prominence",
                    key=key,
                ),
                human_oecd_prominence=_parse_prominence(
                    review["human_oecd_prominence"],
                    field_name="human_oecd_prominence",
                    key=key,
                ),
                heuristic_oecd_url_referenced=_parse_bool(
                    heuristic["oecd_url_referenced"],
                    field_name="oecd_url_referenced",
                    key=key,
                ),
                human_oecd_url_referenced=_parse_bool(
                    review["human_oecd_url_referenced"],
                    field_name="human_oecd_url_referenced",
                    key=key,
                ),
                heuristic_publications=_json_list_set(heuristic["oecd_publications_named"]),
                human_publications=_human_publication_set(review["human_oecd_publications_named"]),
                heuristic_competitors=set(_json_dict(heuristic["competitors_mentioned"])),
                human_competitors=human_competitors,
                configured_human_competitors=configured_human_competitors,
                judge_confidence=heuristic["judge_confidence"],
            )
        )
    return rows


def _agreement_block(name: str, rows: list[_AgreementRow]) -> AgreementBlock:
    mention_pairs = [(row.heuristic_oecd_mentioned, row.human_oecd_mentioned) for row in rows]
    prominence_pairs = [(row.heuristic_oecd_prominence, row.human_oecd_prominence) for row in rows]
    competitor_scores = [
        _set_scores(row.heuristic_competitors, row.human_competitors) for row in rows
    ]
    configured_competitor_scores = [
        _set_scores(row.heuristic_competitors, row.configured_human_competitors) for row in rows
    ]
    publication_scores = [
        _set_scores(row.heuristic_publications, row.human_publications)
        for row in rows
        if row.human_publications
    ]

    return AgreementBlock(
        name=name,
        row_count=len(rows),
        mention_agreement=_agreement(mention_pairs),
        mention_kappa=_cohens_kappa(mention_pairs, labels=(False, True)),
        missed_mentions=sum(
            not row.heuristic_oecd_mentioned and row.human_oecd_mentioned for row in rows
        ),
        false_positive_mentions=sum(
            row.heuristic_oecd_mentioned and not row.human_oecd_mentioned for row in rows
        ),
        prominence_exact_agreement=_agreement(prominence_pairs),
        prominence_adjacent_agreement=_adjacent_agreement(prominence_pairs),
        prominence_weighted_kappa=_weighted_kappa(
            prominence_pairs,
            labels=PROMINENCE_LEVELS,
        ),
        competitor_precision=_mean(score[0] for score in competitor_scores),
        competitor_recall=_mean(score[1] for score in competitor_scores),
        competitor_f1=_mean(score[2] for score in competitor_scores),
        configured_competitor_recall=_mean(score[1] for score in configured_competitor_scores),
        publication_recall=(
            _mean(score[1] for score in publication_scores) if publication_scores else None
        ),
        judge_confidence_counts=dict(sorted(Counter(row.judge_confidence for row in rows).items())),
    )


def _split_blocks(rows: list[_AgreementRow], field_name: str) -> list[AgreementBlock]:
    grouped: dict[str, list[_AgreementRow]] = defaultdict(list)
    for row in rows:
        grouped[getattr(row, field_name)].append(row)
    return [_agreement_block(name, grouped[name]) for name in sorted(grouped)]


def _decision_label(overall: AgreementBlock) -> str:
    mentions_pass = (
        overall.mention_agreement >= 0.95
        and overall.mention_kappa >= 0.85
        and overall.missed_mentions <= 1
    )
    prominence_pass = (
        overall.prominence_exact_agreement >= 0.80
        and overall.prominence_adjacent_agreement >= 0.95
        and overall.prominence_weighted_kappa >= 0.70
    )
    competitors_pass = overall.competitor_recall >= 0.85
    configured_competitors_pass = overall.configured_competitor_recall >= 0.85

    if mentions_pass and prominence_pass and competitors_pass:
        return "accepted"
    if mentions_pass and prominence_pass and configured_competitors_pass:
        return "accepted_with_competitor_caveat"
    if mentions_pass and overall.prominence_exact_agreement >= 0.65:
        return "accepted_with_caveats"
    return "escalate_live_judge"


def _render_report(
    *,
    reviewed_path: Path,
    heuristic_key_path: Path,
    row_level_path: Path,
    overall: AgreementBlock,
    provider_blocks: list[AgreementBlock],
    category_blocks: list[AgreementBlock],
    decision: str,
    rows: list[_AgreementRow],
    configured_peers: set[str],
) -> str:
    missed_rows = [
        row for row in rows if not row.heuristic_oecd_mentioned and row.human_oecd_mentioned
    ]
    false_positive_rows = [
        row for row in rows if row.heuristic_oecd_mentioned and not row.human_oecd_mentioned
    ]
    absent_peers = Counter(
        competitor
        for row in rows
        for competitor in row.human_competitors
        if competitor not in configured_peers
    )

    lines = [
        "# Phase 5.5 heuristic validation report",
        "",
        "Offline A-vs-B comparison: deterministic heuristic (A) vs blind human review (B).",
        "",
        "## Inputs",
        "",
        f"- Reviewed sample: `{_display_path(reviewed_path)}`",
        f"- Heuristic key: `{_display_path(heuristic_key_path)}`",
        f"- Row-level diagnostics: `{_display_path(row_level_path)}`",
        f"- Reviewed rows: {overall.row_count}",
        "",
        "## Decision",
        "",
        f"**{decision}**",
        "",
        _decision_explanation(decision),
        "",
        "## Overall metrics",
        "",
        "| Target | Metric | Value | Threshold | Result |",
        "|---|---:|---:|---:|---|",
        _metric_row("OECD mentioned", "agreement", overall.mention_agreement, ">= 95%", 0.95),
        _metric_row("OECD mentioned", "Cohen's kappa", overall.mention_kappa, ">= 0.85", 0.85),
        _count_row(
            "Missed OECD mentions",
            overall.missed_mentions,
            "<= 1",
            overall.missed_mentions <= 1,
        ),
        _count_row(
            "False positive OECD mentions",
            overall.false_positive_mentions,
            "context",
            True,
        ),
        _metric_row(
            "OECD prominence",
            "exact agreement",
            overall.prominence_exact_agreement,
            ">= 80%",
            0.80,
        ),
        _metric_row(
            "OECD prominence",
            "+/-1 adjacent agreement",
            overall.prominence_adjacent_agreement,
            ">= 95%",
            0.95,
        ),
        _metric_row(
            "OECD prominence",
            "weighted kappa",
            overall.prominence_weighted_kappa,
            ">= 0.70",
            0.70,
        ),
        _metric_row(
            "Competitors",
            "macro precision",
            overall.competitor_precision,
            "context",
            None,
        ),
        _metric_row("Competitors", "macro recall", overall.competitor_recall, ">= 85%", 0.85),
        _metric_row("Competitors", "macro F1", overall.competitor_f1, "context", None),
        _metric_row(
            "Competitors",
            "configured-peer recall",
            overall.configured_competitor_recall,
            ">= 85%",
            0.85,
        ),
        _metric_row(
            "OECD publications",
            "human-set recall",
            overall.publication_recall,
            "context",
            None,
        ),
        "",
        "## Splits by provider",
        "",
        _block_table(provider_blocks),
        "",
        "## Splits by category",
        "",
        _block_table(category_blocks),
        "",
        "## OECD mention errors",
        "",
        _row_list("False negatives (human true, heuristic false)", missed_rows),
        "",
        _row_list("False positives (heuristic true, human false)", false_positive_rows),
        "",
        "## Competitor list coverage gaps",
        "",
        _counter_table(absent_peers),
        "",
        "## Judge confidence",
        "",
        ", ".join(f"{name}: {count}" for name, count in overall.judge_confidence_counts.items())
        or "No confidence values.",
        "",
    ]
    return "\n".join(lines)


def _decision_explanation(decision: str) -> str:
    if decision == "accepted":
        return "All pre-committed thresholds pass. No live LLM judge is needed for Phase 5.5."
    if decision == "accepted_with_competitor_caveat":
        return (
            "OECD mention and prominence thresholds pass. Strict competitor recall is below the "
            "threshold because the human review found organisations outside the configured peer "
            "list; configured-peer recall passes. Use competitor counts as directional unless the "
            "peer list is expanded and re-scored."
        )
    if decision == "accepted_with_caveats":
        return (
            "Core OECD mention detection passes, but one or more secondary thresholds need caveats "
            "before publication."
        )
    return (
        "One or more core thresholds failed. Escalate to the live LLM judge design on this sample."
    )


def _write_row_level_csv(path: Path, rows: list[_AgreementRow]) -> None:
    fieldnames = [
        *JOIN_KEY_FIELDS,
        "category",
        "heuristic_oecd_mentioned",
        "human_oecd_mentioned",
        "mention_match",
        "heuristic_oecd_prominence",
        "human_oecd_prominence",
        "prominence_distance",
        "heuristic_oecd_url_referenced",
        "human_oecd_url_referenced",
        "url_match",
        "heuristic_competitors",
        "human_competitors",
        "competitor_true_positives",
        "competitor_false_positives",
        "competitor_false_negatives",
        "competitor_precision",
        "competitor_recall",
        "competitor_f1",
        "human_competitors_outside_config",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            true_positives = row.heuristic_competitors & row.human_competitors
            false_positives = row.heuristic_competitors - row.human_competitors
            false_negatives = row.human_competitors - row.heuristic_competitors
            precision, recall, f1 = _set_scores(row.heuristic_competitors, row.human_competitors)
            writer.writerow(
                {
                    "provider": row.provider,
                    "model": row.model,
                    "query_id": row.query_id,
                    "run_index": row.run_index,
                    "category": row.category,
                    "heuristic_oecd_mentioned": row.heuristic_oecd_mentioned,
                    "human_oecd_mentioned": row.human_oecd_mentioned,
                    "mention_match": row.heuristic_oecd_mentioned == row.human_oecd_mentioned,
                    "heuristic_oecd_prominence": row.heuristic_oecd_prominence,
                    "human_oecd_prominence": row.human_oecd_prominence,
                    "prominence_distance": abs(
                        PROMINENCE_LEVELS.index(row.heuristic_oecd_prominence)
                        - PROMINENCE_LEVELS.index(row.human_oecd_prominence)
                    ),
                    "heuristic_oecd_url_referenced": row.heuristic_oecd_url_referenced,
                    "human_oecd_url_referenced": row.human_oecd_url_referenced,
                    "url_match": (
                        row.heuristic_oecd_url_referenced == row.human_oecd_url_referenced
                    ),
                    "heuristic_competitors": _json_sorted(row.heuristic_competitors),
                    "human_competitors": _json_sorted(row.human_competitors),
                    "competitor_true_positives": _json_sorted(true_positives),
                    "competitor_false_positives": _json_sorted(false_positives),
                    "competitor_false_negatives": _json_sorted(false_negatives),
                    "competitor_precision": f"{precision:.6f}",
                    "competitor_recall": f"{recall:.6f}",
                    "competitor_f1": f"{f1:.6f}",
                    "human_competitors_outside_config": _json_sorted(
                        row.human_competitors - row.configured_human_competitors
                    ),
                }
            )


def _read_csv(path: Path, *, required_columns: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header.")
        missing = sorted(required_columns - set(reader.fieldnames))
        if missing:
            raise ValueError(f"{path} is missing required columns: {missing}")
        return list(reader)


def _index_by_key(rows: list[dict[str, str]], path: Path) -> dict[tuple[str, ...], dict[str, str]]:
    indexed: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(str(row[field]).strip() for field in JOIN_KEY_FIELDS)
        if key in indexed:
            raise ValueError(f"{path} contains duplicate join key: {key}")
        indexed[key] = row
    return indexed


def _parse_bool(value: str, *, field_name: str, key: tuple[str, ...]) -> bool:
    normalized = str(value).strip().casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Invalid boolean in {field_name} for {key}: {value!r}")


def _parse_prominence(value: str, *, field_name: str, key: tuple[str, ...]) -> str:
    normalized = str(value).strip().casefold()
    if normalized in PROMINENCE_LEVELS:
        return normalized
    raise ValueError(f"Invalid prominence in {field_name} for {key}: {value!r}")


def _json_list_set(value: str) -> set[str]:
    if not str(value).strip():
        return set()
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON list, got: {value!r}")
    return {str(item).strip() for item in parsed if str(item).strip()}


def _json_dict(value: str) -> dict[str, str]:
    if not str(value).strip():
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got: {value!r}")
    return {str(key).strip(): str(val).strip() for key, val in parsed.items() if str(key).strip()}


def _human_organisation_set(value: str) -> set[str]:
    aliases = {
        "au": "AU",
        "eu": "European Union",
        "european comission": "European Union",
        "european commission": "European Union",
        "european parliament": "European Union",
        "eur lex": "European Union",
        "eur-lex": "European Union",
        "euroestat": "Eurostat",
        "g7": "G7",
        "g20": "G20",
        "gpai": "Global Partnership on AI",
        "iea": "IEA",
        "ilo": "ILO",
        "imf": "IMF",
        "itu": "ITU",
        "un": "United Nations",
        "un data": "United Nations",
        "un fts": "United Nations",
        "undp": "UNDP",
        "unesco": "UNESCO",
        "wef": "World Economic Forum",
        "wolrd bank": "World Bank",
        "world bank": "World Bank",
        "world bank data": "World Bank",
        "world bank health data": "World Bank",
    }
    organisations: set[str] = set()
    for part in _split_free_text_list(value):
        normalized = part.casefold()
        if normalized in aliases:
            organisations.add(aliases[normalized])
        elif normalized.startswith("world bank "):
            organisations.add("World Bank")
        else:
            organisations.add(part)
    return organisations


def _human_publication_set(value: str) -> set[str]:
    known_patterns = {
        "anti-bribery convention": "OECD Anti-Bribery Convention",
        "beps": "BEPS",
        "better life index": "Better Life Index",
        "creditor reporting system": "Creditor Reporting System",
        "economic outlook": "OECD Economic Outlook",
        "going for growth": "Going for Growth",
        "health statistics": "OECD Health Statistics",
        "oecd ai policy observatory": "OECD AI Policy Observatory",
        "oecd.ai policy observatory": "OECD AI Policy Observatory",
        "oecd ai principles": "OECD AI Principles",
        "pisa": "PISA",
        "programme for international student assessment": "PISA",
        "revenue statistics": "Revenue Statistics",
    }
    publications: set[str] = set()
    text = str(value or "")
    normalized_text = text.casefold()
    for pattern, canonical in known_patterns.items():
        if pattern in normalized_text:
            publications.add(canonical)
    if publications:
        return publications
    return set(_split_free_text_list(value))


def _split_free_text_list(value: str) -> list[str]:
    text = str(value or "").replace("\r", "\n")
    pieces = re.split(r",|;|\n| - ", text)
    cleaned: list[str] = []
    for piece in pieces:
        cleaned_piece = re.sub(r"[*`]", "", piece)
        cleaned_piece = re.sub(r"^\s*[-•]\s*", "", cleaned_piece)
        cleaned_piece = re.sub(r"\s+", " ", cleaned_piece).strip(" .;:()")
        if cleaned_piece:
            cleaned.append(cleaned_piece)
    return cleaned


def _agreement(pairs: Iterable[tuple[object, object]]) -> float:
    pairs = list(pairs)
    return _mean(1.0 if left == right else 0.0 for left, right in pairs)


def _adjacent_agreement(pairs: Iterable[tuple[str, str]]) -> float:
    pairs = list(pairs)
    return _mean(
        1.0 if abs(PROMINENCE_LEVELS.index(left) - PROMINENCE_LEVELS.index(right)) <= 1 else 0.0
        for left, right in pairs
    )


def _cohens_kappa(pairs: Iterable[tuple[T, T]], *, labels: tuple[T, ...]) -> float:
    pairs = list(pairs)
    if not pairs:
        return 0.0
    observed = _agreement(pairs)
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    total = len(pairs)
    expected = sum((left_counts[label] / total) * (right_counts[label] / total) for label in labels)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _weighted_kappa(pairs: Iterable[tuple[str, str]], *, labels: tuple[str, ...]) -> float:
    pairs = list(pairs)
    if not pairs:
        return 0.0
    index = {label: position for position, label in enumerate(labels)}
    max_distance = len(labels) - 1
    observed = _mean(
        ((index[left] - index[right]) ** 2) / (max_distance**2) for left, right in pairs
    )
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    total = len(pairs)
    expected = sum(
        left_counts[left]
        * right_counts[right]
        * (((index[left] - index[right]) ** 2) / (max_distance**2))
        for left in labels
        for right in labels
    ) / (total**2)
    if expected == 0.0:
        return 1.0 if observed == 0.0 else 0.0
    return 1.0 - (observed / expected)


def _set_scores(predicted: set[str], actual: set[str]) -> tuple[float, float, float]:
    true_positives = len(predicted & actual)
    precision = true_positives / len(predicted) if predicted else (1.0 if not actual else 0.0)
    recall = true_positives / len(actual) if actual else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _json_sorted(values: Iterable[str]) -> str:
    return json.dumps(sorted(values), ensure_ascii=False)


def _metric_row(
    target: str,
    metric: str,
    value: float | None,
    threshold: str,
    pass_threshold: float | None,
) -> str:
    if value is None:
        return f"| {target} | {metric} | n/a | {threshold} | context |"
    status = "pass" if pass_threshold is None or value >= pass_threshold else "fail"
    return f"| {target} | {metric} | {_format_metric(metric, value)} | {threshold} | {status} |"


def _count_row(target: str, value: int, threshold: str, passed: bool) -> str:
    return f"| {target} | count | {value} | {threshold} | {'pass' if passed else 'fail'} |"


def _pct_or_float(value: float) -> str:
    if 0.0 <= value <= 1.0:
        return f"{value:.1%}"
    return f"{value:.3f}"


def _format_metric(metric: str, value: float) -> str:
    if "kappa" in metric.casefold():
        return f"{value:.3f}"
    return _pct_or_float(value)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _block_table(blocks: list[AgreementBlock]) -> str:
    lines = [
        "| Group | n | mention agreement | prominence exact | competitor recall | "
        "configured-peer recall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for block in blocks:
        lines.append(
            "| "
            f"{block.name} | {block.row_count} | {_pct_or_float(block.mention_agreement)} | "
            f"{_pct_or_float(block.prominence_exact_agreement)} | "
            f"{_pct_or_float(block.competitor_recall)} | "
            f"{_pct_or_float(block.configured_competitor_recall)} |"
        )
    return "\n".join(lines)


def _row_list(title: str, rows: list[_AgreementRow]) -> str:
    if not rows:
        return f"**{title}:** none."
    lines = [f"**{title}:**"]
    lines.extend(f"- {row.provider}/{row.model} `{row.query_id}` ({row.category})" for row in rows)
    return "\n".join(lines)


def _counter_table(counter: Counter[str]) -> str:
    if not counter:
        return "No human-labelled competitors fell outside the configured peer list."
    lines = ["| Organisation | Human rows |", "|---|---:|"]
    for organisation, count in counter.most_common():
        lines.append(f"| {organisation} | {count} |")
    return "\n".join(lines)
