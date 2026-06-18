# OECD AI Visibility

Small, reproducible research tool for measuring how prominently the OECD appears in AI-mediated information environments across selected LLM and generative-search providers.

This project is designed as an exploratory communications-intelligence study: transparent methodology, defensible data handling, and reproducible outputs matter more than scale.

## Current Status

Phase 2 is in place: schemas, study configuration, query framework, provider adapters, and a fixture-backed dry-run pipeline.
The remaining implementation will proceed in reviewed phases:

1. LLM-as-judge scoring.
2. Live run, after explicit budget approval.
3. Aggregation, Power BI export, and visualisations.
4. Markdown report drafted from real computed numbers.

## Dry-Run Command

The current raw-response pipeline can be exercised without API keys or network calls:

```powershell
uv run oecd-ai-visibility run --config config/study.yaml --dry-run
```

Dry-run mode uses committed fixtures in `data/fixtures/`, writes validated `RawResponseRecord` JSON files to `data/raw/`, and reuses cached raw responses unless `--no-cache` is passed.

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
