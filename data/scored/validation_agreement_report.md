# Phase 5.5 heuristic validation report

Offline A-vs-B comparison: deterministic heuristic (A) vs blind human review (B).

## Inputs

- Reviewed sample: `data/scored/validation_sample_stratified_reviewed.csv`
- Heuristic key: `data/scored/validation_sample_heuristic_key.csv`
- Row-level diagnostics: `data/scored/validation_agreement_rows.csv`
- Reviewed rows: 46

## Decision

**accepted_with_competitor_caveat**

OECD mention and prominence thresholds pass. Strict competitor recall is below the threshold because the human review found organisations outside the configured peer list; configured-peer recall passes. Use competitor counts as directional unless the peer list is expanded and re-scored.

## Overall metrics

| Target | Metric | Value | Threshold | Result |
|---|---:|---:|---:|---|
| OECD mentioned | agreement | 100.0% | >= 95% | pass |
| OECD mentioned | Cohen's kappa | 1.000 | >= 0.85 | pass |
| Missed OECD mentions | count | 0 | <= 1 | pass |
| False positive OECD mentions | count | 0 | context | pass |
| OECD prominence | exact agreement | 91.3% | >= 80% | pass |
| OECD prominence | +/-1 adjacent agreement | 100.0% | >= 95% | pass |
| OECD prominence | weighted kappa | 0.971 | >= 0.70 | pass |
| Competitors | macro precision | 92.5% | context | pass |
| Competitors | macro recall | 79.9% | >= 85% | fail |
| Competitors | macro F1 | 83.0% | context | pass |
| Competitors | configured-peer recall | 92.8% | >= 85% | pass |
| OECD publications | human-set recall | 63.5% | context | pass |

## Splits by provider

| Group | n | mention agreement | prominence exact | competitor recall | configured-peer recall |
|---|---:|---:|---:|---:|---:|
| anthropic | 24 | 100.0% | 83.3% | 73.2% | 91.7% |
| openai | 22 | 100.0% | 100.0% | 87.1% | 93.9% |

## Splits by category

| Group | n | mention agreement | prominence exact | competitor recall | configured-peer recall |
|---|---:|---:|---:|---:|---:|
| authority_standard_setting | 6 | 100.0% | 83.3% | 68.6% | 91.7% |
| comparative_peer | 4 | 100.0% | 100.0% | 87.5% | 100.0% |
| data_statistics | 10 | 100.0% | 90.0% | 70.3% | 95.0% |
| generative_search_referral | 4 | 100.0% | 50.0% | 52.1% | 91.7% |
| named_product_recall | 10 | 100.0% | 100.0% | 80.0% | 80.0% |
| policy_recommendation | 12 | 100.0% | 100.0% | 100.0% | 100.0% |

## OECD mention errors

**False negatives (human true, heuristic false):** none.

**False positives (heuristic true, human false):** none.

## Competitor list coverage gaps

| Organisation | Human rows |
|---|---:|
| FATF | 2 |
| AidData | 2 |
| IEA | 2 |
| Our World in Data | 2 |
| AU | 1 |
| Council of Europe | 1 |
| UNCTAD | 1 |
| China | 1 |
| gulf states | 1 |
| Commonwealth Fund | 1 |
| WHO | 1 |
| Lancet/NEJM studies | 1 |
| Oxford Internet Institute | 1 |
| OSTP | 1 |
| Federal Register | 1 |
| Georgetown CSET | 1 |
| Congressional Research Service | 1 |
| Standford HAI | 1 |
| NIST | 1 |
| MIT | 1 |
| Review of Economics and Statistics | 1 |
| Journal of Economic Perspectives (accessible synthesis articles | 1 |
| Journal of Economic Growth | 1 |
| Penn World Tables | 1 |
| American Economic Review | 1 |
| BIS | 1 |
| Conference Board Total Economy Database | 1 |
| EU KLEMS | 1 |
| ICC | 1 |
| Transparency International | 1 |
| IATI | 1 |
| AID Data | 1 |
| IEEE | 1 |

## Judge confidence

high: 46
