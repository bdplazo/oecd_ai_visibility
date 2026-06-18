from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from oecd_ai_visibility.validation import export_validation_agreement_report


def test_export_validation_agreement_report_writes_metrics_and_diagnostics(
    tmp_path: Path,
) -> None:
    reviewed_path = tmp_path / "reviewed.csv"
    heuristic_path = tmp_path / "heuristic_key.csv"
    report_path = tmp_path / "report.md"
    row_level_path = tmp_path / "rows.csv"
    _write_reviewed_csv(reviewed_path)
    _write_heuristic_key_csv(heuristic_path)

    result = export_validation_agreement_report(
        reviewed_path=reviewed_path,
        heuristic_key_path=heuristic_path,
        report_path=report_path,
        row_level_path=row_level_path,
        peer_organisations=["IMF", "World Bank", "European Union"],
    )

    assert result.row_count == 3
    assert result.overall.mention_agreement == pytest.approx(1 / 3)
    assert result.overall.missed_mentions == 1
    assert result.overall.false_positive_mentions == 1
    assert result.overall.prominence_exact_agreement == pytest.approx(1 / 3)
    assert result.overall.prominence_adjacent_agreement == pytest.approx(1.0)
    assert result.overall.competitor_recall == pytest.approx((2 / 3 + 1 + 1) / 3)
    assert result.overall.configured_competitor_recall == pytest.approx(1.0)
    assert result.overall.publication_recall == pytest.approx(1.0)
    assert result.decision == "escalate_live_judge"

    report = report_path.read_text(encoding="utf-8")
    assert "False negatives" in report
    assert "FATF" in report

    diagnostic_rows = list(csv.DictReader(row_level_path.read_text(encoding="utf-8").splitlines()))
    diagnostics_by_query = {row["query_id"]: row for row in diagnostic_rows}
    assert diagnostics_by_query["q1"]["competitor_false_negatives"] == '["FATF"]'
    assert diagnostics_by_query["q3"]["human_competitors"] == '["European Union"]'


def test_export_validation_agreement_report_rejects_mismatched_keys(tmp_path: Path) -> None:
    reviewed_path = tmp_path / "reviewed.csv"
    heuristic_path = tmp_path / "heuristic_key.csv"
    _write_reviewed_csv(reviewed_path)
    _write_heuristic_key_csv(heuristic_path, omit_last=True)

    with pytest.raises(ValueError, match="same rows"):
        export_validation_agreement_report(
            reviewed_path=reviewed_path,
            heuristic_key_path=heuristic_path,
            report_path=tmp_path / "report.md",
            row_level_path=tmp_path / "rows.csv",
            peer_organisations=["IMF", "World Bank", "European Union"],
        )


def _write_reviewed_csv(path: Path) -> None:
    rows = [
        {
            "provider": "openai",
            "model": "gpt-4o",
            "query_id": "q1",
            "run_index": "0",
            "category": "cat_a",
            "human_oecd_mentioned": "True",
            "human_oecd_prominence": "primary",
            "human_oecd_url_referenced": "False",
            "human_oecd_publications_named": "PISA",
            "human_competitors_mentioned": "IMF, World Bank, FATF",
        },
        {
            "provider": "openai",
            "model": "gpt-4o",
            "query_id": "q2",
            "run_index": "0",
            "category": "cat_a",
            "human_oecd_mentioned": "True",
            "human_oecd_prominence": "incidental",
            "human_oecd_url_referenced": "False",
            "human_oecd_publications_named": "",
            "human_competitors_mentioned": "",
        },
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "query_id": "q3",
            "run_index": "0",
            "category": "cat_b",
            "human_oecd_mentioned": "False",
            "human_oecd_prominence": "incidental",
            "human_oecd_url_referenced": "False",
            "human_oecd_publications_named": "",
            "human_competitors_mentioned": "EU",
        },
    ]
    _write_csv(path, rows)


def _write_heuristic_key_csv(path: Path, *, omit_last: bool = False) -> None:
    rows = [
        {
            "provider": "openai",
            "model": "gpt-4o",
            "query_id": "q1",
            "run_index": "0",
            "category": "cat_a",
            "oecd_mentioned": "True",
            "oecd_prominence": "primary",
            "oecd_url_referenced": "False",
            "oecd_publications_named": json.dumps(["PISA"]),
            "competitors_mentioned": json.dumps({"IMF": "supporting", "World Bank": "incidental"}),
            "factual_issues": "",
            "judge_confidence": "high",
            "selection_reason": "stratum",
        },
        {
            "provider": "openai",
            "model": "gpt-4o",
            "query_id": "q2",
            "run_index": "0",
            "category": "cat_a",
            "oecd_mentioned": "False",
            "oecd_prominence": "none",
            "oecd_url_referenced": "False",
            "oecd_publications_named": json.dumps([]),
            "competitors_mentioned": json.dumps({}),
            "factual_issues": "",
            "judge_confidence": "high",
            "selection_reason": "edge",
        },
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "query_id": "q3",
            "run_index": "0",
            "category": "cat_b",
            "oecd_mentioned": "True",
            "oecd_prominence": "supporting",
            "oecd_url_referenced": "False",
            "oecd_publications_named": json.dumps([]),
            "competitors_mentioned": json.dumps({"European Union": "supporting"}),
            "factual_issues": "",
            "judge_confidence": "high",
            "selection_reason": "stratum",
        },
    ]
    if omit_last:
        rows = rows[:-1]
    _write_csv(path, rows)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
