# AGENTS.md

## Purpose

This repository supports an exploratory study of OECD visibility in AI-mediated information environments. It should read as a small, rigorous internal communications-intelligence tool: reproducible, transparent, and candid about limitations.

## Expected Workflow

The intended data flow is:

```text
queries -> raw provider responses -> scored responses -> aggregated CSVs -> figures -> report
```

The final CLI should support:

```powershell
uv run oecd-ai-visibility run --config config/study.yaml --dry-run
uv run oecd-ai-visibility run --config config/study.yaml
```

Dry-run mode must require zero API keys and make zero external calls.

## Secrets

Secrets live only in `.env`. Never commit `.env`, print API keys, or include real keys in logs, fixtures, reports, or notebooks.

Expected environment variables are listed in `.env.example`.

## Conventions

- Python 3.11+.
- Use `uv` when available.
- Keep dependencies pinned in `pyproject.toml`.
- Provider SDKs must be imported lazily inside provider adapters.
- Temperature should be `0` whenever the provider allows it.
- Cache raw calls by provider, model, query id, and run index.
- Re-runs should skip cached raw responses unless explicitly told not to.
- Live runs that may spend money require explicit human approval first.
- Raw and scored outputs are committed when small enough to support auditability.
- Reports must distinguish measured results from draft interpretation.

## Project Phases

1. Phase 0: scaffold and planning.
2. Phase 1: schemas, config, query framework, and prompt review.
3. Phase 2: providers and dry-run pipeline.
4. Phase 3: judge scoring and validation sample export.
5. Phase 4: live run after budget approval.
6. Phase 5: aggregation, Power BI export, and figures.
7. Phase 6: report draft and optional PDF export.
