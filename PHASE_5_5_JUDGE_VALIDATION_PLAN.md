# Phase 5.5 — Judge Validation Plan

Planning note. **No code, no live calls, no raw-file changes are part of this phase.** The goal
is to decide *whether the deterministic heuristic scores are good enough to stand as the study's
measurement*, or whether a manual review (and, later, an optional live LLM judge) is needed to
trust them.

## 1. What we are validating

All Phase 5 numbers come from a single **deterministic local heuristic**
(`heuristic-local` / `deterministic-v1`, implemented in
[src/oecd_ai_visibility/judges/dry_run.py](src/oecd_ai_visibility/judges/dry_run.py) and bridged by
[heuristic.py](src/oecd_ai_visibility/judges/heuristic.py)). It is a rule-based pass over the saved
answer text. Reproducible and free, but rule-based pattern matching — not judgement. The fields it
emits and how each is derived:

| Field | How the heuristic decides it | Built-in blind spot |
|-------|------------------------------|---------------------|
| `oecd_mentioned` | regex `\bOECD\b` (case-insensitive) **or** an `oecd.org` citation | Misses the spelled-out name ("Organisation for Economic Co-operation and Development") and `O.E.C.D.` when the acronym is absent → possible **false negatives** |
| `oecd_prominence` | centrality rules: named-product + publication ⇒ `primary`; OECD leads first sentence with no peer in the lead ⇒ `primary`; peers present ⇒ `supporting`; bare `oecd.org`/"strong citable source" ⇒ `supporting`; else `incidental` | First-sentence "lead" detection is brittle to formatting; `incidental` is **never assigned** in the current 60 rows (0 cases) — needs a human check |
| `oecd_url_referenced` | literal `oecd.org` in prose or citation | Known weak proxy (`supports_citations: false` for both models). Treat as a **lower bound**, already documented in METHODOLOGY.md |
| `oecd_publications_named` | substring match against a fixed list of 11 flagships | Undercounts lesser-known / renamed publications |
| `competitors_mentioned` | word-boundary match against the configured `peer_organisations` list | Misses peers not on the list and abbreviations/aliases (e.g. "WB", "U.N.") |
| `factual_issues` | always `""` | The heuristic **cannot** assess factual quality at all — only a live judge could |
| `judge_confidence` | rule of thumb on signal clarity | **All 60 rows are `high`** → currently uninformative as a quality signal |

### Current scored corpus (the population being validated)

- **60 responses** = 2 live providers (`openai/gpt-4o`, `anthropic/claude-sonnet-4-6`) × 30 queries × 1 run.
- 6 categories: `authority_standard_setting`, `policy_recommendation`, `data_statistics`,
  `named_product_recall`, `comparative_peer`, `generative_search_referral`.
- Heuristic distribution: `oecd_mentioned` 46 T / 14 F · `oecd_prominence` supporting 31, primary 15,
  none 14, incidental 0 · `oecd_url_referenced` 4 T · `judge_confidence` 60× high.

## 2. Validation design (three-way comparison)

A single labelled sample is scored three ways and compared cell-by-cell.

```
                       ┌─────────────────────────┐
  raw response  ─────► │ A. heuristic (existing)  │ ── already in data/scored/
                       └─────────────────────────┘
                       ┌─────────────────────────┐
                ─────► │ B. human review (gold)   │ ── this phase, manual, offline
                       └─────────────────────────┘
                       ┌─────────────────────────┐
                ─────► │ C. live LLM judge (later)│ ── design only, NOT run now
                       └─────────────────────────┘
```

- **A — Deterministic heuristic.** Already computed; read straight from `data/scored/*.json` /
  `scored_responses.csv`. No re-run needed.
- **B — Manual review (the gold standard for this phase).** One or two reviewers label the sample
  by reading each answer against the same rubric the heuristic targets. **B is the reference** all
  agreement metrics are measured against.
- **C — Live LLM judge (future, design only).** The interface already exists as a stub
  (`LiveJudgeAdapter` in [base.py](src/oecd_ai_visibility/judges/base.py), config in
  `config/study.yaml` → `judge: openai/gpt-4o-mini`). This plan specifies *how it would be
  evaluated* (same sample, same metrics, compared against B) so it can be slotted in later. **It is
  not implemented or invoked in Phase 5.5.** No provider keys, no spend.

The deliverable of this phase is the answer to: **does A agree with B closely enough to publish A
as the study measurement?** C is only pursued if A fails the thresholds in §5.

## 3. Validation sample strategy

**Problem with the current sample.** `export_validation_sample_csv` takes the first
`validation_sample_size` (12) records after sorting by `(provider, model, query_id, run_index)`. The
result is **all Anthropic and only 3 of 6 categories** — not representative. Do not use it as-is for
validation conclusions.

**Proposed sample.** A **stratified ~24-response sample** (40% of the 60-row corpus), drawn offline
into a *new* file (e.g. `data/scored/validation_sample_stratified.csv`) so the existing artifact and
all raw files stay untouched:

1. **Stratify by provider × category** — 2 providers × 6 categories = 12 cells; take **2 per cell**
   where available, so both models and every category are represented.
2. **Force-include the edge cases** the heuristic is most likely to get wrong (these are where A vs
   B is most informative):
   - all `oecd_mentioned = False` rows (the 14 negatives — checks **missed mentions**);
   - all `oecd_prominence = primary` rows (15 — checks the brittle first-sentence lead rule);
   - the 4 `oecd_url_referenced = True` rows;
   - a few `comparative_peer` / `generative_search_referral` rows (richest competitor content).
3. **Deterministic selection** — sort within each stratum by the existing stable key and take the
   first *k*, so the sample is reproducible and reviewer-independent.

Reviewers label **blind to the heuristic output** (the heuristic columns are hidden during review,
then joined back for comparison) to avoid anchoring. ~24 rows is small enough for one careful
reviewer in a sitting and large enough to expose systematic errors, while leaving the remaining 36
rows as an untouched hold-out.

## 4. Metrics (A vs B; reused unchanged for C vs B later)

| Target | Metric | Pass intuition |
|--------|--------|----------------|
| **`oecd_mentioned` agreement** | raw agreement %, **Cohen's κ**, and a 2×2 confusion table | binary flag should be near-perfect |
| **`oecd_prominence` agreement** | exact-match %, **±1 adjacent-level agreement** %, **weighted κ** (ordinal: none<incidental<supporting<primary) | exact match can be lenient; adjacent + weighted κ capture ordinal closeness |
| **Missed OECD mentions** | false-negative rate = human-`true` but heuristic-`false`, over human positives; list each miss with the likely cause (e.g. spelled-out name) | this is the heuristic's most plausible failure |
| **False positives** | false-positive rate = heuristic-`true` but human-`false`, over human negatives | expected low; confirm no spurious `OECD` matches |
| **Competitor detection quality** | per-response **precision / recall / F1** of the heuristic's competitor set vs the human-found set; tally peers the human found that are absent from the configured `peer_organisations` list | reveals undercounting from the fixed list and aliases |
| (context) `oecd_publications_named` | recall of named flagships the human spotted | sanity check on the fixed-list approach |
| (context) `judge_confidence` | does `high` actually track agreement? | currently constant — flag if it adds no value |

Report each metric **overall and split by provider and by category**, so a failure concentrated in
one category (e.g. brittle `primary` calls in `comparative_peer`) is visible rather than averaged
away.

## 5. Decision rule — is the heuristic sufficient?

Pre-commit to thresholds *before* reviewing, to keep the decision honest:

- **Heuristic accepted as the study measurement (no live judge needed) if all hold:**
  - `oecd_mentioned`: agreement ≥ 95% and κ ≥ 0.85, with **0–1 missed mentions** in the sample;
  - `oecd_prominence`: exact-match ≥ 80% **and** ±1 adjacent ≥ 95% (weighted κ ≥ 0.70);
  - competitor detection: recall ≥ 0.85 against the human set (after noting any list-coverage gaps).
- **Heuristic accepted *with documented caveats*** if mentions pass but prominence sits in a middle
  band (exact 65–80%): keep using it, but widen the METHODOLOGY caveats and treat `prominence` as
  coarse/directional only.
- **Escalate to the live LLM judge (Phase 6+)** if mentions miss the bar, prominence exact-match
  < 65%, or `factual_issues` turns out to matter for the report — none of which the heuristic can
  ever produce. In that case run C on the *same* sample, compare C-vs-B with the §4 metrics, and
  only adopt C if it beats B-vs-A materially and stays within budget.

Whatever the outcome, the existing METHODOLOGY.md caveats (designed sample, two providers, single
run, weak URL proxy) continue to travel with the numbers.

## 6. Scope guardrails for Phase 5.5

- ✅ Inspect heuristic logic and existing scores; design the comparison, sample, and metrics.
- ✅ Produce this note; optionally, later, generate a *stratified* sample CSV into a new file.
- ❌ Do **not** implement or call the live LLM judge.
- ❌ Do **not** make any live provider/judge API calls (no spend).
- ❌ Do **not** modify files in `data/raw/` or existing scored artifacts.
