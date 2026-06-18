# Measuring OECD Visibility in AI-Mediated Information Environments

## Role relevance

This project was built as a compact communications-intelligence case study for monitoring how the OECD appears in AI-mediated information environments. It connects directly to work on AI visibility, generative search, AI discoverability, publication analytics, dashboard-ready data products, and validated metrics for communications teams.

## Problem

As users increasingly ask LLMs and generative search systems for policy evidence, institutional visibility is no longer limited to web search rankings, media mentions, publication downloads, or social analytics. A user may receive a synthesized answer that names the OECD, treats it as one authority among many, recommends an OECD product, links to `oecd.org`, or omits the institution entirely.

The project asks:

> Across a designed set of OECD-relevant user questions, when and how does the OECD surface in generated answers?

The aim is not to claim web-scale representativeness. The aim is to design a transparent pilot that communications teams could inspect, reproduce, validate, and extend.

## Approach

I designed a 30-query sample across six communications-relevant categories:

- authority and standard-setting
- policy recommendation
- data and statistics
- named-product recall
- comparative peer positioning
- generative-search referral

The current live scored corpus covers two provider/model combinations: OpenAI `gpt-4o` and Anthropic `claude-sonnet-4-6`, with one run per provider per query. Existing raw responses are cached and scored locally; the current analysis does not require additional provider calls.

The scoring pipeline uses a deterministic local heuristic to produce auditable metrics:

- OECD mentioned
- OECD prominence: `none`, `incidental`, `supporting`, `primary`
- literal `oecd.org` reference
- named OECD publications and products
- configured peer organisation mentions

The outputs are structured for analysis and reporting: response-level scored CSVs, tidy helper tables for publications/peers/citations, Power BI-ready summary tables, and sanity-check figures.

## Validation

Because the scoring heuristic is rule-based, I added a Phase 5.5 validation step before treating the metrics as portfolio-ready evidence.

The validation used a stratified blind human review sample covering both providers and all six query categories, with edge cases included. Human labels were compared against the heuristic labels after review.

Validation results:

- OECD mention agreement: 100.0%
- Cohen's kappa for OECD mention: 1.000
- Missed OECD mentions: 0
- OECD prominence exact agreement: 91.3%
- OECD prominence adjacent agreement: 100.0%
- OECD prominence weighted kappa: 0.971
- Competitor strict macro recall: 79.9%
- Configured-peer recall: 92.8%
- Decision: accepted with competitor caveat

Interpretation: the deterministic heuristic is retained for OECD mention and prominence measurement. Competitor metrics are interpreted directionally because the human review identified relevant organisations outside the configured peer list.

No live LLM judge was used after validation passed for the core OECD metrics.

## Findings

In the current 60-response live scored corpus:

- OECD was mentioned in 46 responses, a 76.7% overall mention rate.
- Both included providers had the same overall OECD mention rate: 23 of 30 responses.
- Authority, comparative peer, named-product recall, and generative-search referral prompts all produced 100% OECD mention rates in this sample.
- Data/statistics prompts produced 10 OECD mentions in 12 responses.
- Broad policy-recommendation prompts produced no OECD mentions in this run, suggesting that general advice questions can surface policy recommendations without naming institutional evidence sources.
- OECD prominence was substantive when present: 15 primary and 31 supporting scores across the 60 responses.
- URL/reference visibility was limited: only 4 responses contained a literal `oecd.org` string, and the project treats this as a weak lower-bound proxy because structured citations were not available from the included model APIs.
- World Bank was the most frequently mentioned configured peer organisation. PISA, BEPS, Going for Growth, and the OECD Economic Outlook were among the OECD products surfaced.

## Limitations

This is a validated exploratory pilot, not a complete measurement system.

- The query set is designed, not statistically representative.
- The current live corpus covers two providers, one model per provider, and one run per query.
- Generative search and referral behavior are only approximated because the included model APIs did not return structured citations.
- Competitor metrics depend on the configured peer list and should be treated as directional until the taxonomy is expanded.
- The pipeline measures visibility and prominence, not factual accuracy, sentiment, or policy quality.

## Tools used

- Python
- Typer CLI
- Pydantic schemas
- pandas
- matplotlib
- pytest
- ruff
- uv
- Markdown documentation
- Power BI-ready CSV outputs

## How this could extend inside OECD COM/CISC

At OECD scale, this pilot could become a recurring communications-intelligence monitor:

- expand provider coverage to LLMs, AI search products, and citation-capable generative systems
- connect AI referral logs and web analytics where available
- build Power BI dashboards by topic, provider, model, query intent, and peer organisation
- extend peer and publication taxonomies with aliases, abbreviations, and multilingual variants
- repeat runs over time to track whether OECD visibility improves after publications, campaigns, standards work, or media activity
- add human-in-the-loop review for high-impact outputs and factual quality checks

The core contribution is the measurement design: transparent proxies, reproducible data preparation, validation before interpretation, and concise synthesis for communications decision-making.
