from __future__ import annotations

import csv
from pathlib import Path

from oecd_ai_visibility.judges.dry_run import DryRunJudge
from oecd_ai_visibility.runner import run_collection
from oecd_ai_visibility.schemas import (
    Citation,
    JudgeScore,
    QuerySet,
    QuerySpec,
    RawResponseRecord,
    ScoredRecord,
    load_query_set,
    load_study_config,
)
from oecd_ai_visibility.scoring import (
    CITATIONS_CSV_NAME,
    COMPETITORS_CSV_NAME,
    PUBLICATIONS_CSV_NAME,
    STRATIFIED_VALIDATION_SAMPLE_CSV_NAME,
    VALIDATION_SAMPLE_HEURISTIC_KEY_CSV_NAME,
    cache_path,
    export_helper_tables,
    export_scored_responses_csv,
    export_stratified_validation_sample_csv,
    export_validation_sample_csv,
    score_collection,
    select_stratified_validation_sample,
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


def _stratified_record(
    *,
    provider: str,
    category: str,
    query_id: str,
    oecd_mentioned: bool = True,
    oecd_prominence: str = "supporting",
    oecd_url_referenced: bool = False,
) -> ScoredRecord:
    model = "gpt-4o" if provider == "openai" else "claude-sonnet-4-6"
    return ScoredRecord(
        provider=provider,
        model=model,
        query_id=query_id,
        category=category,
        run_index=0,
        response_text=f"Answer for {provider}/{query_id}.",
        citations=[],
        judge_provider="heuristic-local",
        judge_model="deterministic-v1",
        score=JudgeScore(
            oecd_mentioned=oecd_mentioned,
            oecd_prominence=oecd_prominence,
            oecd_url_referenced=oecd_url_referenced,
            oecd_publications_named=[],
            competitors_mentioned={},
            judge_confidence="high",
        ),
    )


def _stratified_fixture_records() -> list[ScoredRecord]:
    """Two providers x two categories x three queries, with three forced edge cases.

    Stratification (per_cell=2) takes a1/a2 and b1/b2 from each cell (8 rows). The forced
    edge cases push in two extra rows: openai/cat_a/a3 (a missed mention) and
    anthropic/cat_b/b3 (a primary). openai/cat_b/b1 carries a URL but is already a stratum
    pick, so it adds no new row. Expected unique total: 10.
    """

    records: list[ScoredRecord] = []
    for provider in ("openai", "anthropic"):
        for category, prefix in (("cat_a", "a"), ("cat_b", "b")):
            for index in (1, 2, 3):
                records.append(
                    _stratified_record(
                        provider=provider,
                        category=category,
                        query_id=f"{prefix}{index}",
                    )
                )

    by_key = {(r.provider, r.query_id): r for r in records}
    by_key[("openai", "a3")] = _stratified_record(
        provider="openai",
        category="cat_a",
        query_id="a3",
        oecd_mentioned=False,
        oecd_prominence="none",
    )
    by_key[("anthropic", "b3")] = _stratified_record(
        provider="anthropic",
        category="cat_b",
        query_id="b3",
        oecd_prominence="primary",
    )
    by_key[("openai", "b1")] = _stratified_record(
        provider="openai",
        category="cat_b",
        query_id="b1",
        oecd_url_referenced=True,
    )
    return list(by_key.values())


def _write_stratified_fixture(scored_dir: Path) -> None:
    scored_dir.mkdir(parents=True, exist_ok=True)
    for record in _stratified_fixture_records():
        _write_scored_record(scored_dir, record)


def test_select_stratified_validation_sample_covers_strata_and_forced_edges() -> None:
    selected = select_stratified_validation_sample(_stratified_fixture_records(), per_cell=2)
    keys = {(r.provider, r.query_id) for r in selected}

    # 4 cells x 2 stratum picks + 2 extra forced rows, deduped.
    assert len(selected) == 10
    # Every provider x category cell contributes its first two queries.
    for provider in ("openai", "anthropic"):
        for prefix in ("a", "b"):
            assert (provider, f"{prefix}1") in keys
            assert (provider, f"{prefix}2") in keys
    # Forced edge cases pulled in beyond the per-cell slice.
    assert ("openai", "a3") in keys  # missed mention (oecd_mentioned=False)
    assert ("anthropic", "b3") in keys  # primary prominence
    # Deterministic, stable-sorted output.
    assert [_sample_key(r) for r in selected] == sorted(_sample_key(r) for r in selected)


def test_export_stratified_validation_sample_blind_layout_and_separate_key(
    tmp_path: Path,
) -> None:
    config = _config_with_output_paths(tmp_path)
    scored_dir = tmp_path / "scored"
    _write_stratified_fixture(scored_dir)

    result = export_stratified_validation_sample_csv(config=config, project_root=ROOT, per_cell=2)

    assert result.sample_path == scored_dir / STRATIFIED_VALIDATION_SAMPLE_CSV_NAME
    assert result.heuristic_key_path == scored_dir / VALIDATION_SAMPLE_HEURISTIC_KEY_CSV_NAME
    assert result.row_count == 10
    # All four strata represented with two rows each.
    assert result.stratum_counts == {
        ("openai", "cat_a"): 2,
        ("openai", "cat_b"): 2,
        ("anthropic", "cat_a"): 2,
        ("anthropic", "cat_b"): 2,
    }
    assert result.edge_case_counts == {
        "edge_oecd_not_mentioned": 1,
        "edge_prominence_primary": 1,
        "edge_url_referenced": 1,
    }

    sample_rows = list(csv.DictReader(result.sample_path.read_text(encoding="utf-8").splitlines()))
    key_rows = list(
        csv.DictReader(result.heuristic_key_path.read_text(encoding="utf-8").splitlines())
    )
    assert len(sample_rows) == 10
    assert len(key_rows) == 10

    # Blind layout: no heuristic score leaks into the review file; human columns are empty.
    header = _csv_header(result.sample_path)
    assert "oecd_mentioned" not in header
    assert "oecd_prominence" not in header
    assert "judge_confidence" not in header
    human_columns = [name for name in header if name.startswith("human_")] + ["reviewer_notes"]
    assert "human_oecd_mentioned" in human_columns
    for row in sample_rows:
        assert all(row[name] == "" for name in human_columns)

    # The key file carries the heuristic scores and joins back on the four keys.
    assert "oecd_mentioned" in _csv_header(result.heuristic_key_path)

    def join_keys(rows: list[dict[str, str]]) -> set[tuple[str, str, str, str]]:
        return {(r["provider"], r["model"], r["query_id"], r["run_index"]) for r in rows}

    assert join_keys(sample_rows) == join_keys(key_rows)


def test_export_stratified_validation_sample_is_deterministic(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    _write_stratified_fixture(tmp_path / "scored")

    first = export_stratified_validation_sample_csv(config=config, project_root=ROOT)
    first_sample = first.sample_path.read_text(encoding="utf-8")
    first_key = first.heuristic_key_path.read_text(encoding="utf-8")

    second = export_stratified_validation_sample_csv(config=config, project_root=ROOT)

    assert second.sample_path.read_text(encoding="utf-8") == first_sample
    assert second.heuristic_key_path.read_text(encoding="utf-8") == first_key


def test_export_stratified_validation_sample_leaves_existing_files_untouched(
    tmp_path: Path,
) -> None:
    config = _config_with_output_paths(tmp_path)
    scored_dir = tmp_path / "scored"
    _write_stratified_fixture(scored_dir)

    # Sentinels for the default validation sample and a raw response record.
    default_sample = tmp_path / "validation_sample.csv"
    default_sample.write_text("DO NOT TOUCH\n", encoding="utf-8")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_file = raw_dir / "openai__gpt-4o__a1__0.json"
    raw_file.write_text('{"raw": true}\n', encoding="utf-8")

    before = {path: path.read_text(encoding="utf-8") for path in (default_sample, raw_file)}
    # Also snapshot the source scored JSON files.
    scored_before = {path: path.read_text(encoding="utf-8") for path in scored_dir.glob("*.json")}

    export_stratified_validation_sample_csv(config=config, project_root=ROOT)

    for path, content in before.items():
        assert path.read_text(encoding="utf-8") == content
    for path, content in scored_before.items():
        assert path.read_text(encoding="utf-8") == content


def _sample_key(record: ScoredRecord) -> tuple[str, str, str, int]:
    return (record.provider, record.model, record.query_id, record.run_index)


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


def _write_scored_record(scored_dir: Path, record: ScoredRecord) -> None:
    filename = f"{record.provider}__{record.model}__{record.query_id}__{record.run_index}.json"
    (scored_dir / filename).write_text(record.model_dump_json(indent=2), encoding="utf-8")


def _helper_fixture_records() -> list[ScoredRecord]:
    return [
        ScoredRecord(
            provider="openai",
            model="gpt-4o",
            query_id="product_pisa",
            category="named_product_recall",
            run_index=0,
            response_text="PISA is run by the OECD; see oecd.org.",
            citations=[
                Citation(url="https://www.oecd.org/pisa", title="PISA", source="oecd.org"),
                Citation(url="https://example.org/imf", title=None, source=None),
            ],
            judge_provider="heuristic-local",
            judge_model="deterministic-v1",
            score=JudgeScore(
                oecd_mentioned=True,
                oecd_prominence="primary",
                oecd_url_referenced=True,
                oecd_publications_named=["PISA", "OECD AI Principles"],
                competitors_mentioned={"IMF": "supporting", "World Bank": "incidental"},
                judge_confidence="high",
            ),
        ),
        ScoredRecord(
            provider="anthropic",
            model="claude-sonnet-4-6",
            query_id="policy_sme_digitalisation",
            category="policy_recommendation",
            run_index=0,
            response_text="Several bodies advise on this topic.",
            citations=[],
            judge_provider="heuristic-local",
            judge_model="deterministic-v1",
            score=JudgeScore(
                oecd_mentioned=False,
                oecd_prominence="none",
                oecd_url_referenced=False,
                oecd_publications_named=[],
                competitors_mentioned={},
                judge_confidence="low",
            ),
        ),
    ]


def test_export_helper_tables_shape_and_row_counts(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    scored_dir = tmp_path / "scored"
    scored_dir.mkdir()
    for record in _helper_fixture_records():
        _write_scored_record(scored_dir, record)

    paths = export_helper_tables(config=config, project_root=ROOT)

    assert [path.name for path in paths] == [
        PUBLICATIONS_CSV_NAME,
        COMPETITORS_CSV_NAME,
        CITATIONS_CSV_NAME,
    ]
    assert all(path.parent == tmp_path for path in paths)

    publications, competitors, citations = (
        list(csv.DictReader(path.read_text(encoding="utf-8").splitlines())) for path in paths
    )

    # One publication per row, joined and sorted; the no-mention record adds no rows.
    assert [row["oecd_publication"] for row in publications] == ["OECD AI Principles", "PISA"]
    assert all(
        (row["provider"], row["model"], row["query_id"], row["run_index"])
        == ("openai", "gpt-4o", "product_pisa", "0")
        for row in publications
    )

    # One competitor per row with its prominence, sorted by name.
    assert [(row["competitor"], row["prominence"]) for row in competitors] == [
        ("IMF", "supporting"),
        ("World Bank", "incidental"),
    ]

    # One citation per row, preserving order; missing title/source become empty strings.
    assert [
        (row["citation_url"], row["citation_title"], row["citation_source"]) for row in citations
    ] == [
        ("https://www.oecd.org/pisa", "PISA", "oecd.org"),
        ("https://example.org/imf", "", ""),
    ]


def test_export_helper_tables_headers_are_stable(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    scored_dir = tmp_path / "scored"
    scored_dir.mkdir()
    for record in _helper_fixture_records():
        _write_scored_record(scored_dir, record)

    publications_path, competitors_path, citations_path = export_helper_tables(
        config=config, project_root=ROOT
    )

    join_keys = ["provider", "model", "query_id", "run_index"]
    assert _csv_header(publications_path) == [*join_keys, "oecd_publication"]
    assert _csv_header(competitors_path) == [*join_keys, "competitor", "prominence"]
    assert _csv_header(citations_path) == [
        *join_keys,
        "citation_url",
        "citation_title",
        "citation_source",
    ]


def test_export_helper_tables_respects_provider_model_filter(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    scored_dir = tmp_path / "scored"
    scored_dir.mkdir()
    for record in _helper_fixture_records():
        _write_scored_record(scored_dir, record)

    publications_path, competitors_path, _ = export_helper_tables(
        config=config,
        project_root=ROOT,
        provider_models=[("anthropic", "claude-sonnet-4-6")],
    )

    # The anthropic record names no publication or competitor, so both tables are empty.
    assert list(csv.DictReader(publications_path.read_text(encoding="utf-8").splitlines())) == []
    assert list(csv.DictReader(competitors_path.read_text(encoding="utf-8").splitlines())) == []


def test_score_collection_writes_helper_tables_with_aggregate(tmp_path: Path) -> None:
    config = _config_with_output_paths(tmp_path)
    query_set = _fixture_query_set()
    run_collection(config=config, query_set=query_set, project_root=ROOT, dry_run=True)

    result = score_collection(
        config=config,
        query_set=query_set,
        project_root=ROOT,
        dry_run=True,
        export_aggregated_csv=True,
    )

    assert [path.name for path in result.helper_csv_paths] == [
        PUBLICATIONS_CSV_NAME,
        COMPETITORS_CSV_NAME,
        CITATIONS_CSV_NAME,
    ]
    assert all(path.exists() for path in result.helper_csv_paths)


def _csv_header(path: Path) -> list[str]:
    reader = csv.reader(path.read_text(encoding="utf-8").splitlines())
    return next(reader)


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


def _judge() -> DryRunJudge:
    config = load_study_config(ROOT / "config" / "study.yaml")
    return DryRunJudge(peer_organisations=config.peer_organisations)


def _raw(text: str, query_id: str = "q_test") -> RawResponseRecord:
    return RawResponseRecord(
        provider="openai",
        model="gpt-4o",
        query_id=query_id,
        run_index=0,
        latency_seconds=0.01,
        response_text=text,
    )


def _query(category: str, query_id: str = "q_test") -> QuerySpec:
    return QuerySpec(id=query_id, category=category, text="A transparent test prompt.")


def test_named_product_recall_floors_terse_answer_to_primary() -> None:
    # A terse answer that names an OECD product but mentions "OECD" only once must not
    # be demoted to incidental purely for being short (the earlier verbosity artifact).
    judge = _judge()
    score = judge.score(
        raw_record=_raw("PISA is run by the OECD.", query_id="product_pisa"),
        query=_query("named_product_recall", query_id="product_pisa"),
    )
    assert score.oecd_publications_named == ["PISA"]
    assert score.oecd_prominence == "primary"


def test_repeating_oecd_is_not_enough_for_primary() -> None:
    # Two OECD mentions without OECD leading the answer or any product floor must not
    # reach primary; raw mention count is deliberately ignored.
    judge = _judge()
    text = "Many bodies study this. The OECD has data here, and the OECD also publishes reports."
    score = judge.score(
        raw_record=_raw(text),
        query=_query("policy_recommendation"),
    )
    assert score.oecd_mentioned is True
    assert score.oecd_prominence == "incidental"


def test_oecd_leading_the_answer_is_primary() -> None:
    judge = _judge()
    text = "The OECD is the leading authority here, providing comparable cross-country indicators."
    score = judge.score(
        raw_record=_raw(text),
        query=_query("authority_standard_setting"),
    )
    assert score.oecd_prominence == "primary"


def test_peer_co_listing_in_lead_is_supporting_not_primary() -> None:
    judge = _judge()
    text = "The OECD, IMF, and World Bank all publish relevant economic analysis."
    score = judge.score(
        raw_record=_raw(text),
        query=_query("comparative_peer"),
    )
    assert score.oecd_prominence == "supporting"
    assert set(score.competitors_mentioned) == {"IMF", "World Bank"}


def test_markdown_table_does_not_inflate_prominence_to_primary() -> None:
    # An OECD reference buried in a comparison table (alongside a peer) is supporting,
    # not primary: the markdown table must not be read as the answer's lead.
    judge = _judge()
    text = (
        "# Comparison of data sources\n\n"
        "| Source | Coverage |\n"
        "|--------|----------|\n"
        "| World Bank | global |\n"
        "| OECD | member countries |\n\n"
        "Both provide useful statistics."
    )
    score = judge.score(
        raw_record=_raw(text),
        query=_query("data_statistics"),
    )
    assert score.oecd_mentioned is True
    assert score.oecd_prominence == "supporting"


def test_expanded_peer_list_detects_new_peers() -> None:
    judge = _judge()
    text = "Guidance comes from the OECD, UNESCO, the ITU, and the G20."
    score = judge.score(
        raw_record=_raw(text),
        query=_query("authority_standard_setting"),
    )
    assert {"UNESCO", "ITU", "G20"} <= set(score.competitors_mentioned)


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
