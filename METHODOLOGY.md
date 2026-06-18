# Methodology Note — Phase 5 Outputs

Read this before building analysis tables, Power BI dashboards, or report text from the
Phase 5 data. It explains, in plain terms, what was measured, how, and what the numbers can
and cannot support.

## What this study is

An **exploratory snapshot** of how visibly the OECD appears in answers from general-purpose
AI assistants, across a designed set of OECD-relevant questions. It is a directional
indicator of AI-mediated visibility — not a measurement of the general population of possible
questions or users.

## Query design

The questions are a **designed, illustrative sample** of plausible user intents in
OECD-relevant policy domains (authority, comparison, data lookup, citable-source / "GEO",
general policy, and named-product recall). They were hand-built to probe visibility, **not**
drawn by representative or random sampling. Results describe how the models answered *these*
questions, and should not be read as estimates for all questions a real user might ask.

## Providers and models included

| Provider  | Model               | Included? |
|-----------|---------------------|-----------|
| OpenAI    | gpt-4o              | ✅ Yes    |
| Anthropic | claude-sonnet-4-6   | ✅ Yes    |
| Google    | Gemini              | ❌ Skipped |
| Perplexity| Perplexity (Sonar)  | ❌ Skipped |

**Gemini and Perplexity were skipped because their API credentials were not available.**
Their absence is a coverage gap, not a finding — do not interpret it as those providers
performing differently. Any cross-provider comparison in Phase 5 covers OpenAI and Anthropic
only.

## Run structure

**One run per provider per query.** Each model answered each question once. With a single run,
the data shows what a model said on that occasion; it does not capture run-to-run variation, so
treat per-question results as single observations rather than averages.

## How the data was produced

- The **raw model answers were captured and cached** earlier and preserved unchanged. Phase 5.1
  re-scored those existing cached responses; it did **not** re-query the providers.
- Scoring was done by a **deterministic local heuristic** — a transparent, rule-based pass over
  the saved answer text. Running it again on the same answers yields the same scores.
- **No live LLM judge was used.** The optional "LLM-as-judge" scoring path was not run, so no
  judgement calls to any model were made. The `judge_provider` / `judge_model` fields therefore
  record the local heuristic (`heuristic-local` / `deterministic-v1`), not a live judge.
- **No live provider calls** were made in this phase.

## What each key field means (and its limits)

- **`oecd_mentioned`** — `true` if the OECD is named anywhere in the answer (or in a structured
  citation, when present). A simple presence flag; it says nothing about how central or positive
  the mention is.

- **`oecd_prominence`** — how central the OECD is to the answer, on a four-level scale:
  `none` → `incidental` → `supporting` → `primary`. It rewards *centrality*, not repetition:
  `primary` means the OECD leads the answer (or, for named-product questions, an OECD
  publication is named), `supporting` means the OECD appears alongside peer organisations, and
  `incidental` is a passing mention. Repeating "OECD" many times does **not** raise the score.

- **`oecd_url_referenced`** — ⚠️ **Read this carefully.** This flag only detects a literal
  `oecd.org` string in the answer text. Because citations are disabled/unavailable for the
  included models (`supports_citations: false`), the models do not return structured source
  links, so this is **not** a measure of genuine citation or referral behaviour. Treat it as a
  **lower bound** on OECD referral visibility — many answers can draw on OECD material without
  ever typing `oecd.org`.

- **`oecd_publications_named`** — list of recognised OECD products/flagships found in the answer
  (e.g. PISA, OECD Economic Outlook, BEPS, Better Life Index, OECD AI Principles). It only
  matches names on a fixed known list, so it can undercount lesser-known publications.

- **`competitors_mentioned`** — peer organisations named in the answer (IMF, World Bank, ILO,
  UN, WEF, Eurostat, etc.), each with its own prominence level. Useful for "who else shows up
  alongside the OECD", but limited to the configured peer list.

- **`judge_confidence`** — the heuristic's confidence in its own scoring (`low` / `medium` /
  `high`), based on how clear the signal in the text was. It reflects the **rule-based scorer's**
  certainty, not a human or LLM judgement of answer quality.

## How to interpret the results

Read the Phase 5 numbers as **exploratory visibility indicators** for two assistants on a
designed question set. They are directionally useful for spotting patterns and shaping
communications questions. They are **not** definitive, general-population estimates of OECD
visibility, and any caveat above (designed sample, two providers only, single run, weak URL
proxy) should travel with the figures into tables, dashboards, and the written report.
