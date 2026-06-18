# Measuring OECD Visibility in AI-Mediated Information Environments

This repository is a reproducible portfolio case study on how the OECD appears in AI-mediated information environments such as LLM answers, generative-search style responses, and AI-assisted source discovery.

## Executive Summary

The project asks a practical communications-intelligence question:

> When users ask AI systems questions in OECD-relevant policy domains, does the OECD appear, how prominently, and alongside which peer organisations?

This matters because discovery is increasingly mediated by AI systems. Communications teams need transparent ways to monitor whether authoritative institutional work surfaces in generated answers, not only in traditional web search, media coverage, or social analytics.

The project demonstrates a compact, auditable workflow for the OECD role: query design, provider response collection, deterministic scoring, Power BI-ready exports, visual checks, and a completed human validation step that tests whether the core OECD visibility metrics are reliable enough to use.

## Why This Matters

AI-mediated information environments create new visibility questions for public institutions:

- **LLM answers:** users may receive synthesized answers without visiting source websites.
- **Generative search:** source recommendations and citations can shape institutional discoverability.
- **AI discoverability:** visibility depends on whether models surface the OECD as an authority, peer, data source, or product owner.
- **Communications impact measurement:** AI visibility can complement web analytics, publication analytics, media intelligence, and referral monitoring.

This project treats AI visibility as a measurable, exploratory signal rather than a black box.

## Methodology

The study uses a designed query set across OECD-relevant use cases:

- **30 queries** across **6 categories**: authority and standard-setting, policy recommendation, data and statistics, named-product recall, comparative peer positioning, and generative-search referral.
- **2 live provider/model combinations already scored:** OpenAI `gpt-4o` and Anthropic `claude-sonnet-4-6`.
- **1 run per provider per query**, producing 60 scored live responses.
- **Deterministic local heuristic judge** for OECD mention, OECD prominence, OECD URL reference, named OECD publications, and configured peer mentions.
- **Stratified blind human validation sample** covering both providers and all query categories, with edge cases included.

No live LLM judge is needed for the core OECD visibility measurement after validation. The deterministic heuristic is retained for OECD mention and prominence; competitor metrics are interpreted directionally unless the peer organisation list is expanded and re-scored.

See [METHODOLOGY.md](METHODOLOGY.md) for caveats and field definitions.

## Validation Result

Phase 5.5 compared the deterministic heuristic against a blind human review of 46 sampled rows.

| Target | Result |
|---|---:|
| OECD mention agreement | 100.0% |
| OECD mention Cohen's kappa | 1.000 |
| Missed OECD mentions | 0 |
| OECD prominence exact agreement | 91.3% |
| OECD prominence adjacent agreement | 100.0% |
| OECD prominence weighted kappa | 0.971 |
| Competitor strict macro recall | 79.9% |
| Competitor configured-peer recall | 92.8% |
| Decision | accepted with competitor caveat |

Interpretation: the core OECD visibility metrics pass the pre-defined validation thresholds. Competitor recall is strong for the configured peer list, but strict recall falls below threshold because the human review found relevant organisations outside that list.

## Key Findings

From the current scored live corpus:

- OECD was mentioned in **46 of 60 responses (76.7%)**. OpenAI and Anthropic each mentioned the OECD in **23 of 30 responses (76.7%)**.
- OECD visibility was strongest in authority, comparative, named-product, and generative-search referral prompts, where mention rate was **100%** in the current sample.
- Data/statistics queries mentioned the OECD in **10 of 12 responses (83.3%)**.
- Broad policy-recommendation prompts did **not** mention the OECD in this run (**0 of 12 responses**), suggesting that general advice prompts may surface policy content without naming institutional sources.
- OECD prominence was usually substantive when the OECD appeared: **15 primary**, **31 supporting**, and **14 none** across 60 responses. Named-product recall prompts were all scored as primary.
- The URL/referral proxy is weak by design: only **4 of 60 responses** included a literal `oecd.org` reference, all in Anthropic data/statistics responses. Because structured citations were unavailable for the included models, this should be treated as a lower-bound signal only.
- The most frequently configured peer organisation was the **World Bank** (13 mentions for each provider). PISA, BEPS, Going for Growth, and the OECD Economic Outlook were among the named OECD products surfaced in responses.

## What This Demonstrates

This repository maps directly to the OECD communications intelligence role by showing:

- **AI visibility analytics:** a measurable approach to institutional presence in generated answers.
- **Communications intelligence:** query categories that reflect authority, referral, products, peers, and policy discoverability.
- **Metric and proxy design:** explicit flags for mention, prominence, URL reference, peer visibility, and publication recall.
- **Data quality and validation:** a blind human validation step with agreement metrics and a documented decision rule.
- **Power BI-ready outputs:** tidy CSV tables suitable for dashboards and repeated reporting.
- **Clear synthesis for decision-makers:** concise outputs that separate findings from caveats.

## Repository Structure

```text
config/                 Study configuration, provider settings, paths, and peer list
data/queries.yaml       Designed OECD-relevant query set
data/raw/               Cached raw provider responses and dry-run fixtures
data/scored/            Deterministic scores, aggregated CSVs, validation artifacts
outputs/tables/         Power BI-ready summary tables
outputs/figures/        Sanity-check PNG figures
src/oecd_ai_visibility/ Collection, scoring, analysis, figures, and validation code
tests/                  Unit tests for schemas, runner, scoring, analysis, figures, validation
METHODOLOGY.md          Field definitions, interpretation rules, and validation note
PORTFOLIO_CASE_STUDY.md Standalone 1-2 page portfolio narrative
APPLICATION_SNIPPETS.md CV, LinkedIn, cover-letter, and interview-ready text
```

## Reproduce Locally

Install dependencies with `uv`, then run the non-live checks and outputs:

```powershell
uv run --extra dev pytest tests -p no:cacheprovider
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
uv run oecd-ai-visibility status
uv run oecd-ai-visibility validation-report
uv run oecd-ai-visibility analyse
uv run oecd-ai-visibility figures
```

These commands use existing local scored data and validation files. They do not collect new provider responses and do not call a live LLM judge.

The live collection path exists for controlled future runs, but should only be used with explicit budget approval:

```powershell
uv run oecd-ai-visibility run --config config/study.yaml --live --confirm-live LIVE_PROVIDER_CALLS_APPROVED
```

Without the confirmation token, `--live` fails before any provider adapter is built. Local scoring of existing live raw caches remains offline:

```powershell
uv run oecd-ai-visibility score --heuristic-live-cache --aggregate
```

## Limitations and Caveats

- The query set is designed and illustrative, not representative of all OECD-relevant user needs.
- The live corpus covers two providers, one model per provider, and one run per query.
- The URL/reference metric is a weak proxy because the included model APIs did not provide structured citations.
- Competitor metrics are directional unless the peer organisation taxonomy is expanded and existing responses are re-scored.
- No live LLM judge was used after the human validation step confirmed the core OECD mention and prominence metrics.

## Possible Next Steps

- Expand provider and model coverage, including generative search systems with structured citations.
- Add AI referral logs or search-console style referral indicators where available.
- Connect the tidy outputs to Power BI dashboards for monitoring by provider, category, and topic.
- Expand the peer organisation taxonomy and alias list, then re-score competitor visibility.
- Repeat measurement over time to monitor changes in OECD discoverability and prominence.

## Secrets and Safety

API keys belong only in `.env`, which is ignored by git. Use `.env.example` as the template. No live provider or judge calls should be run without explicit approval.
