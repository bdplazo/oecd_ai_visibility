# OECD AI Visibility

Small, reproducible research tool for measuring how prominently the OECD appears in AI-mediated information environments across selected LLM and generative-search providers.

This project is designed as an exploratory communications-intelligence study: transparent methodology, defensible data handling, and reproducible outputs matter more than scale.

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

## Methodological Principle

The prompt set will be a designed, illustrative sample of plausible user intents in OECD-relevant policy domains. It will not be presented as representative of all possible queries. That caveat is part of the methodology, not a footnote.

## Secrets

API keys must live in `.env`, which is ignored by git. Use `.env.example` as the template.

No live API calls should be run without explicit approval.
