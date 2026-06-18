# OECD AI Visibility

Small, reproducible research tool for measuring how prominently the OECD appears in AI-mediated information environments across selected LLM and generative-search providers.

This project is designed as an exploratory communications-intelligence study: transparent methodology, defensible data handling, and reproducible outputs matter more than scale.

> **Before analysing Phase 5 outputs**, read [METHODOLOGY.md](METHODOLOGY.md). It explains —
> in plain, non-engineering terms — which providers were included, how the data was scored, and
> exactly what each field means and does not mean. This context should travel with the numbers
> into any analysis table, Power BI dashboard, or report.

## Current Status

Phase 3 is in place: schemas, study configuration, query framework, provider adapters, a fixture-backed dry-run raw pipeline, deterministic dry-run scoring, and validation sample export.
The remaining implementation will proceed in reviewed phases:

1. Live run, after explicit budget approval.
2. Aggregation, Power BI export, and visualisations.
3. Markdown report drafted from real computed numbers.

## Dry-Run Command

The current raw-response pipeline can be exercised without API keys or network calls:

```powershell
uv run oecd-ai-visibility run --config config/study.yaml --dry-run
```

Dry-run mode uses committed fixtures in `data/fixtures/`, writes validated `RawResponseRecord` JSON files to `data/raw/`, and reuses cached raw responses unless `--no-cache` is passed.

Dry-run scoring uses a deterministic local judge, reads `data/raw/`, writes validated `ScoredRecord` JSON files to `data/scored/`, and exports a stable manual-review CSV sample to the path configured as `paths.validation_sample_csv`:

```powershell
uv run oecd-ai-visibility score --config config/study.yaml --dry-run
```

Live provider mode is available only by explicit opt-in:

```powershell
uv run oecd-ai-visibility run --config config/study.yaml --live
```

Providers with missing API-key environment variables are skipped with a warning.

## Deterministic Scoring Notes

The deterministic local judge (`DryRunJudge` / `HeuristicJudge`) is a transparent,
network-free stand-in for the LLM judge. Two limitations are worth stating plainly:

- **`oecd_url_referenced` is a weak proxy.** All configured providers run with
  `supports_citations: false`, so structured citations are almost always empty. The flag
  therefore detects a literal `oecd.org` string in the answer text, not genuine
  citation/referral behaviour. Treat it as a lower bound on OECD referral visibility.
- **`oecd_prominence` measures centrality, not repetition.** `primary` requires that the
  OECD leads the answer (it appears in the opening segment with no peer sharing that
  opening), or — for `named_product_recall` queries — that an OECD publication is named.
  Raw OECD mention counts are deliberately not used, to avoid rewarding verbose answers.
  Markdown tables are stripped before the opening segment is read.

Existing live raw caches can be re-scored with the deterministic heuristic (no judge API
calls) and exported for analysis:

```powershell
uv run oecd-ai-visibility score --config config/study.yaml --heuristic-live-cache --aggregate --no-cache
```

`--aggregate` writes the response-level `data/scored/scored_responses.csv` plus three tidy
relational helper tables next to it, which split that file's nested columns so Power BI can
join them directly instead of parsing JSON:

- `scored_publications.csv` — one named OECD publication per row.
- `scored_competitors.csv` — one competitor mention per row, with its prominence.
- `scored_citations.csv` — one citation per row (empty while providers run with
  `supports_citations: false`).

Each helper table carries the `provider`, `model`, `query_id`, and `run_index` join keys
that link back to `scored_responses.csv`.

## Methodological Principle

The prompt set will be a designed, illustrative sample of plausible user intents in OECD-relevant policy domains. It will not be presented as representative of all possible queries. That caveat is part of the methodology, not a footnote.

## Secrets

API keys must live in `.env`, which is ignored by git. Use `.env.example` as the template.

No live API calls should be run without explicit approval.
