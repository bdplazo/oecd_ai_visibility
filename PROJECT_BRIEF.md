# PROJECT BRIEF — OECD Visibility in AI-Mediated Information Environments

## 1. Role and mandate for Code Assistant

You are acting as a senior data/ML engineer building a **small, rigorous, fully reproducible
research tool and accompanying analysis**. This is a portfolio piece supporting a job
application for a *Junior AI & Communications Intelligence Officer* role at the OECD's
Directorate for Communications (COM). The audience that will read the repository is composed of
communications-analytics professionals at an evidence-based, transparency-focused international
organisation. **Methodological honesty, clean engineering, and clear writing matter more than
scale or flashiness.** A small study done impeccably beats a large one done sloppily.

Optimise for: reproducibility, transparency, defensible methodology, readable code, and a
deliverable that reads like an internal COM brief — not an academic paper and not a hype demo.

## 2. The analytical question

**How, and how prominently, does the OECD appear when major LLMs and generative-search engines answer questions in the OECD's areas of expertise — and how does that compare to peer organisations?**

This maps directly to the role's first responsibility: *analysing OECD visibility in
AI-mediated environments (LLM referrals, generative search, AI discoverability)* and to its
ask for *"metrics and proxies to assess OECD presence in AI systems"* and *"exploratory work on
Generative Engine Optimisation (GEO)."* We are not applying a settled methodology; we are
proposing one. Treat the design of the measurement as a first-class deliverable, not just the
numbers.

## 3. Success criteria

The project succeeds if it produces:

1. A **config-driven Python tool** that runs a designed set of queries across multiple
   LLM/generative-search providers, records raw responses, and scores them with a transparent
   rubric.
2. A **structured dataset** (one tidy row per scored response) that is clean enough to drop
   straight into Power BI.
3. A small set of **clear visualisations** of the headline findings.
4. A **3–4 page analytical report (Markdown → PDF)** with an executive summary, methodology,
   findings, GEO implications, and an honest limitations section.
5. A **README** good enough that a stranger can reproduce the whole study in one command after
   adding their API keys.

Everything must run end-to-end with a single CLI command and a `--dry-run` mode that needs no
API keys at all.

## 4. Tech stack and environment

- **Python 3.11+**. Use `uv` for env + dependency management if available; otherwise a standard
  `venv` + `pyproject.toml`. Pin versions.
- Provider SDKs: `anthropic`, `openai`, `google-genai`, and `requests`/`httpx` for Perplexity's
  REST API. **Only import a provider's SDK lazily**, inside its adapter, so the tool runs with
  whatever subset of keys I actually have.
- `pydantic` for the data schemas (it gives validation + clean serialisation for free).
- `tenacity` for retries with exponential backoff.
- `pandas` for aggregation; `matplotlib` (and/or `plotly`) for charts.
- `python-dotenv` for secrets; `pyyaml` for config.
- `typer` (or stdlib `argparse`) for the CLI.
- `rich` for readable logging/progress (optional, nice-to-have).
- `pytest` for a light smoke-test suite.
- Format with `ruff` + `ruff format`. Type hints everywhere; docstrings on public functions.

## 5. Repository structure

```
oecd-ai-visibility/
├── README.md                 # methodology, how-to-run, limitations, headline findings
├── PROJECT_BRIEF.md          # this file
├── CLAUDE.md                 # working notes for future Claude Code sessions (see §11)
├── pyproject.toml
├── .env.example              # lists required env vars, NO real values
├── .gitignore                # must ignore .env, __pycache__, and the raw cache if large
├── config/
│   └── study.yaml            # providers enabled, n_runs, judge model, paths, budget cap
├── data/
│   ├── queries.yaml          # the query framework (see §6) — version-controlled
│   ├── raw/                  # raw provider responses as JSON (committed for auditability)
│   └── scored/               # scored + aggregated CSVs (committed)
├── outputs/
│   ├── figures/              # PNG/SVG charts
│   └── report/               # report.md and report.pdf
├── src/
│   ├── schemas.py            # pydantic models: QuerySpec, ResponseRecord, ScoredRecord
│   ├── providers/
│   │   ├── base.py           # Provider ABC: .query(prompt) -> ResponseRecord
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   ├── gemini.py
│   │   └── perplexity.py
│   ├── judge.py              # LLM-as-judge: scores a ResponseRecord -> ScoredRecord
│   ├── run.py                # orchestration: load config+queries, query, cache, score
│   ├── aggregate.py          # build metrics + Power BI-ready tidy CSV
│   ├── visualize.py          # generate the figures
│   ├── report.py             # assemble the Markdown report draft from real numbers
│   └── costs.py              # token/cost estimation + budget guard
└── tests/
    └── test_scoring.py       # fixtures-based smoke tests, no live API calls
```

## 6. The query framework (the methodological core)

Store the queries in `data/queries.yaml` so they are transparent and editable. Design **~24–30
prompts** grouped into categories that mirror what COM cares about. Each query has an `id`, a
`category`, the `text`, and an optional `expected_topic` note. Proposed categories (refine with
me before finalising):

- **Authority / standard-setting** — e.g. *"Which international organisations set standards for
  corporate taxation?"*, *"Who produces the most authoritative cross-country education data?"*
  (Tests whether the OECD surfaces as a trusted source unprompted.)
- **Policy recommendation** — e.g. *"What are evidence-based policies to reduce youth
  unemployment?"*, *"How can governments improve productivity growth?"* (Tests policy footprint.)
- **Data / statistics** — e.g. *"Which OECD countries spend the most on R&D as a share of
  GDP?"*, *"What are the latest trends in income inequality across advanced economies?"*
- **Named-product recall** — e.g. *"What is PISA and who runs it?"*, *"Tell me about the OECD
  Economic Outlook."* (Tests recognition of flagship publications.)
- **Comparative / peer** — e.g. *"Compare the OECD, IMF and World Bank as sources of economic
  policy advice."* (Directly surfaces share-of-voice vs peers.)

Define a fixed **peer set** to benchmark against and detect in responses: IMF, World Bank, ILO,
UN/UNDP, World Economic Forum, Eurostat, IMF. Keep this list in config so it is explicit.

**Design principle to document in the report:** these prompts are a *designed, illustrative
sample of plausible user intents*, not a representative sample of all queries. State this
plainly — it is a strength (intentional, transparent) not a weakness to hide.

## 7. Providers

Implement a `Provider` abstract base class with a single `query(query_spec) -> ResponseRecord`
method. Each concrete provider:

- Reads its key from the environment; if the key is absent, it is **skipped gracefully** with a
  logged warning (the study runs on whatever subset is configured + keyed).
- Sets **temperature 0** where the provider allows it, for maximum determinism.
- Records the exact **model version string**, request **timestamp (UTC)**, **latency**, and
  **token usage**.

Required adapters: **Anthropic (Claude)**, **OpenAI (GPT-4o or current)**, **Google (Gemini)**,
**Perplexity (Sonar)**.

**Treat Perplexity as the most important provider for the "referrals/discoverability" angle:**
it is a generative *search* engine and returns source citations with URLs. Capture those
citations explicitly so we can measure whether `oecd.org` is actually *referred to* — that is
the closest real proxy for the "AI referrals / bot-driven traffic" concern in the job. Make the
citation/URL field first-class in the schema.

## 8. LLM-as-judge scoring

For each `ResponseRecord`, run a separate **judge** LLM call (temperature 0, strict JSON output,
one model held fixed for the whole study) that reads the raw response text and returns a
`ScoredRecord` validated by pydantic with these fields:

- `oecd_mentioned: bool`
- `oecd_prominence: Literal["none","incidental","supporting","primary"]`
- `oecd_publications_named: list[str]`  (PISA, Economic Outlook, Going for Growth, etc.)
- `oecd_url_referenced: bool`  (true if an oecd.org link appears in citations/text)
- `competitors_mentioned: dict[str, str]`  (org → same prominence scale)
- `factual_issues: str`  (note any clear errors or out-of-date claims about the OECD; "" if none)
- `judge_confidence: Literal["low","medium","high"]`

Make the rubric explicit in the judge's system prompt and **mirror that exact rubric in the
README**, so the scoring is auditable. Using an LLM to analyse LLM outputs is on-theme for the
role — but flag the obvious risk (the judge has its own biases). Mitigate it two ways:
(1) temperature 0 + a fixed judge model + a precise rubric; (2) a **human-validation step** —
export a random sample of ~10–15 scored responses to `data/scored/validation_sample.csv` for me
to hand-check, and report the agreement rate as a reliability indicator in the report.

## 9. Engineering best practices (non-negotiable)

- **Secrets:** never hard-code or print keys. Read from `.env`. Ship `.env.example` with the var
  names only. Add `.env` to `.gitignore` and double-check it before any commit.
- **Caching:** key each call on `(provider, model, query_id, run_index)` and write results to
  `data/raw/` as JSON. On re-run, **skip anything already cached** unless `--no-cache` is passed.
  API calls are the expensive, non-deterministic step — never repeat them needlessly.
- **Idempotent, resumable runs:** a crash mid-run must be recoverable from the cache.
- **Retries:** wrap provider calls in `tenacity` with exponential backoff for transient/rate-limit
  errors; fail loudly on auth errors.
- **Cost control:** `src/costs.py` estimates total cost before a live run, prints it, and a
  `budget_eur` cap in config aborts if the estimate exceeds it. Track actual token usage too.
- **Dry-run / mock mode:** `--dry-run` exercises the entire pipeline using canned fixture
  responses and **zero API calls**, so the plumbing can be validated before keys or budget are
  spent. Build and test this first.
- **Determinism + provenance:** temperature 0, recorded model versions + UTC timestamps, and a
  configurable `n_runs` (default 1) so I can optionally run each query 2–3× to **measure
  response variability** — itself a finding worth reporting, since AI-mediated visibility is
  inherently unstable.
- **Logging:** structured, leveled logging; a one-line progress indication per call. No `print`.
- **Typing + docstrings:** type-hint everything; docstring every public function/class.
- **Tests:** `tests/` covers the parsing/scoring logic against committed fixtures — no live
  calls in tests.
- **Git hygiene:** initialise a repo, sensible `.gitignore`, and commit at each phase boundary
  with clear messages. Commit the raw responses and scored CSVs (they are small and make the
  whole study auditable) — but verify no secrets leak in.

## 10. Build phases — check in with me after each

- **Phase 0 — Plan & scaffold.** Restate the plan in your own words, list assumptions/open
  questions, propose the repo skeleton and `pyproject.toml`, write `CLAUDE.md` and `.env.example`.
  *Wait for my go-ahead.*
- **Phase 1 — Schemas + config + query framework.** `schemas.py`, `config/study.yaml`,
  `data/queries.yaml` with a first full draft of the ~24–30 prompts and the peer list. Show me the
  prompts for review.
- **Phase 2 — Providers + dry-run.** Base class, all four adapters, mock/fixtures, working
  `--dry-run` end-to-end. Smoke-test it.
- **Phase 3 — Judge + scoring.** `judge.py`, scoring schema, validation-sample export. Verify on
  fixtures.
- **Phase 4 — Live run.** **Ask me before spending any budget.** Run on whatever providers I have
  keys for, with caching on. Report cost actually spent.
- **Phase 5 — Aggregate + visualise + Power BI export.** Metrics in §12, tidy long-format CSV,
  figures.
- **Phase 6 — Report draft.** Assemble `report.md` from the *real* numbers (see §13), then offer
  to convert to PDF.

## 11. AGENTS.md contents

Create a `AGENTS.md` capturing: the project's purpose, the run commands, the config knobs, the
data-flow (queries → raw → scored → aggregated → figures → report), where secrets live, and the
key conventions (temperature 0, caching, no secrets in commits). This keeps future sessions
consistent.

## 12. Metrics to compute in aggregation

- OECD **mention rate** overall and **by provider** and **by category** (a provider × category
  heatmap is ideal).
- OECD **prominence distribution** (share of responses at each prominence level).
- **Share-of-voice**: OECD mention rate vs each peer organisation, overall and by category.
- **Referral signal**: rate of `oecd_url_referenced = true`, primarily from Perplexity.
- **Flagship recall**: which OECD publications get named, and how often.
- If `n_runs > 1`: **stability** — how often OECD's presence flips across identical re-runs.
- **Factual-issue log**: any recurring errors/staleness in how models describe the OECD (very
  relevant to COM's mis/disinformation mandate).

## 13. Report (`outputs/report/report.md`)

Draft it from the actual computed numbers — never invent figures. Structure:

1. **Executive summary** (≤200 words) — the 3–4 headline findings and the single most actionable
   GEO implication.
2. **Why this matters** — framed in COM's language (visibility in AI-mediated environments,
   discoverability, referrals).
3. **Methodology** — query framework, providers, scoring rubric, judge + its validation, the
   honest sampling caveat.
4. **Findings** — with the figures, plain-language reading of each.
5. **GEO implications** — what content patterns/structures appear more "citable" by LLMs; where
   the OECD's gaps and strengths are vs peers; concrete, modest next steps.
6. **Limitations** — snapshot in time, non-determinism, designed (not representative) sample,
   judge bias, model-version sensitivity. Be candid; candour reads as competence here.

> Mark the narrative/interpretation passages clearly as **DRAFT FOR HUMAN REVIEW** — I will
> curate the final prose so it carries my voice and judgement. Your job is an excellent,
> numerically faithful first draft, not the final published text.

## 14. Guardrails (read before acting)

- **Never** commit a real API key or print one to logs.
- **Ask before any live API run** that spends budget (Phase 4).
- Keep total scope to roughly a focused **2–3 day** build — resist gold-plating; a clean small
  study is the goal.
- When in doubt about a methodological choice, **surface the trade-off to me and ask** rather
  than silently deciding.
- Do not overstate findings. This study is **illustrative and exploratory**, and the writing
  must say so.
