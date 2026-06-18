# OECD AI Visibility

Small, reproducible research tool for measuring how prominently the OECD appears in AI-mediated information environments across selected LLM and generative-search providers.

This project is designed as an exploratory communications-intelligence study: transparent methodology, defensible data handling, and reproducible outputs matter more than scale.

## Current Status

Phase 1 is in place: schemas, study configuration, and the first transparent query framework.
The remaining implementation will proceed in reviewed phases:

1. Provider adapters and dry-run pipeline.
2. LLM-as-judge scoring.
3. Live run, after explicit budget approval.
4. Aggregation, Power BI export, and visualisations.
5. Markdown report drafted from real computed numbers.

## Intended Command

The final tool will run end to end with:

```powershell
uv run oecd-ai-visibility run --config config/study.yaml --dry-run
```

If `uv` is unavailable, the fallback will be a standard Python 3.11+ virtual environment using the same `pyproject.toml`.

## Methodological Principle

The prompt set will be a designed, illustrative sample of plausible user intents in OECD-relevant policy domains. It will not be presented as representative of all possible queries. That caveat is part of the methodology, not a footnote.

## Secrets

API keys must live in `.env`, which is ignored by git. Use `.env.example` as the template.

No live API calls should be run without explicit approval.
