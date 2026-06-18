# Analytical Report: OECD Visibility in AI-Mediated Answers

## Executive Reading

The current scored corpus shows a clear communications-intelligence pattern: OECD visibility is strong when the user intent already resembles an authority, product, peer-comparison, data-source, or citable-source task. It disappears when the user asks broad policy-advice questions without asking for institutions or evidence sources.

In the 60 live scored responses, the OECD is mentioned in 46 responses, or 76.7%. OpenAI `gpt-4o` and Anthropic `claude-sonnet-4-6` produce the same overall OECD mention rate: 23 of 30 responses each. The important finding is therefore not a simple provider winner. It is an intent pattern: the OECD is visible in source-seeking and institution-seeking prompts, but not in generic policy recommendation prompts.

The deterministic scorer is strong enough for this interpretation. In the 46-row blind human validation sample, OECD mention agreement is 100.0%, OECD prominence exact agreement is 91.3%, and adjacent prominence agreement is 100.0%. Competitor metrics should be read directionally because strict competitor recall is 79.9%, while recall for configured peers is 92.8%.

## Where Visibility Is Strongest And Weakest

| Query category | Responses | OECD mentions | Mention rate | Interpretation |
|---|---:|---:|---:|---|
| Authority and standard-setting | 10 | 10 | 100.0% | Strong authority visibility. |
| Comparative peer positioning | 10 | 10 | 100.0% | Strong peer-comparison visibility. |
| Named-product recall | 10 | 10 | 100.0% | Strong product recall. |
| Generative-search referral | 6 | 6 | 100.0% | Strong source-list visibility, but weak literal URL evidence. |
| Data and statistics | 12 | 10 | 83.3% | Generally strong, with one repeated topic gap. |
| Policy recommendation | 12 | 0 | 0.0% | Clear visibility gap in broad policy advice. |

OECD prominence is also substantive when the OECD appears. Across all 60 responses, the distribution is 15 primary, 31 supporting, and 14 none. There are no incidental-only OECD mentions in the current scored corpus.

The strongest category is named-product recall: all 10 responses are scored as primary. Authority prompts are consistently visible, with 2 primary and 8 supporting scores. Comparative peer and generative-search referral prompts are consistently supporting: the OECD appears, but as one institution among others. Data and statistics prompts are mixed: 3 primary, 7 supporting, and 2 none. The two data misses are both `data_income_inequality_trends`, one from each provider.

The weakest category is policy recommendation. Every broad policy recommendation prompt is scored as no OECD mention for both providers. This is not evidence that OECD analysis is irrelevant to those topics. It shows that when the prompt asks for general advice rather than sources, standards, datasets, or institutional comparisons, the models can answer without naming the OECD.

## What Each Query Category Creates

Authority and standard-setting prompts create authority visibility. The OECD appears in all 10 authority responses, usually as a supporting authority in a wider institutional field. The authority prompts also surface recognizable OECD assets: OECD AI Principles, Anti-Bribery Convention, PISA, and BEPS are each named by both providers in the relevant authority context.

Named-product prompts create product recall. They are the cleanest route to primary OECD visibility: all 10 named-product responses are primary. Across providers, the most frequently surfaced products are PISA with 8 mentions, BEPS with 6, Going for Growth with 5, OECD Economic Outlook with 3, and Revenue Statistics with 3. Anti-Bribery Convention, Better Life Index, and OECD AI Principles each appear twice.

Comparative peer prompts create peer-positioning visibility. The OECD appears in all 10 comparative responses, always as supporting rather than primary. That is appropriate for the prompt design: users are explicitly asking how the OECD compares with organizations such as the IMF, World Bank, ILO, Eurostat, UNDP, or World Economic Forum.

Generative-search referral prompts create source-list visibility, but not strong URL visibility in this setup. The OECD is mentioned in all 6 referral-style responses, all as supporting. However, none of those 6 referral-style responses includes a literal `oecd.org` reference. The current URL metric only detects literal `oecd.org` strings, so it should be treated as a lower-bound proxy rather than a true citation or referral metric.

Data and statistics prompts create source and dataset visibility with one notable blind spot. OECD appears in 10 of 12 data responses. The repeated miss is the income inequality trends prompt, where both providers answered without naming the OECD. Anthropic includes 4 literal `oecd.org` references in data/statistics answers; OpenAI includes none.

Policy recommendation prompts create topic visibility but not institutional visibility. The models can generate plausible policy advice on youth unemployment, productivity growth, green transition, inequality, SME digitalisation, and public trust without attributing that advice to OECD evidence or naming OECD products.

## Provider-Level Similarities And Differences

The provider-level similarity is more important than the provider-level difference. Both providers mention OECD in 23 of 30 responses, both mention OECD in every authority, comparison, product, and referral prompt, both mention OECD in 5 of 6 data prompts, and both omit OECD in all 6 policy recommendation prompts.

This suggests that, in this snapshot, user intent drives OECD visibility more than provider choice. Communications teams should therefore focus measurement on query classes and audience intents, not only on provider rankings.

The differences are still useful:

- Anthropic has 8 primary OECD responses, 15 supporting, and 7 none.
- OpenAI has 7 primary OECD responses, 16 supporting, and 7 none.
- Anthropic is the only provider with literal `oecd.org` references: 4 responses, all in data/statistics.
- OpenAI more often surfaces some configured peers, including United Nations, European Union, Eurostat, and World Economic Forum.
- Anthropic more often surfaces G20 and has slightly higher counts for several configured peers such as UNDP, ITU, and G7.
- World Bank is the dominant configured peer for both providers, with 13 mentions from Anthropic and 13 from OpenAI.

The practical reading is that providers differ in packaging and peer mix more than in the main OECD visibility pattern. A dashboard should therefore allow side-by-side provider comparison, but the strategic interpretation should start from category and query intent.

## What To Do With The Policy Recommendation Gap

The policy recommendation gap is the most actionable communications finding in the study. It shows a disconnect between OECD relevance and model attribution. The questions are OECD-relevant, but the models answer them as general policy advice and do not name the OECD.

Communications teams should treat this as a discoverability and attribution problem, not as a simple content-volume problem. Useful actions include:

- Map priority policy topics to the OECD products, datasets, explainers, and country notes that should be associated with those topics.
- Create source-forward pages and summaries that connect broad user questions to named OECD evidence, for example by making the institutional source, flagship product, data table, and policy takeaway explicit.
- Strengthen metadata, headings, schema, cross-links, and snippets around evidence-based policy questions so that "what should governments do" queries can resolve to OECD evidence rather than generic advice.
- Track whether future responses move from `none` to `supporting` or `primary` after publication launches, campaigns, content refreshes, or structured citation improvements.
- Use human review for high-priority policy topics where visibility alone is not enough and factual quality, framing, or policy nuance matters.

The goal is not to force every answer to name the OECD. It is to ensure that when OECD evidence is genuinely authoritative for a policy topic, AI-mediated answers have a clear, citable route to it.

## How To Interpret The Competitor Caveat

The competitor caveat is about taxonomy coverage, not about the reliability of the core OECD visibility result. The human validation found that the scorer performs well for OECD mention and prominence. It also found that competitor detection is limited by the configured peer list.

The validation distinction matters:

- Strict competitor macro recall is 79.9%, below the threshold.
- Configured-peer recall is 92.8%, above the threshold.
- The gap exists because human reviewers identified relevant organizations that were not in the configured peer taxonomy, such as FATF, AidData, IEA, Our World in Data, WHO, NIST, BIS, and others.

Therefore, competitor counts can answer "which configured peers appeared in the current scoring system?" They should not be used to answer "which competitors or alternative authorities appeared overall?" until the peer taxonomy is expanded and the existing responses are re-scored.

For communications use, the current competitor table is still valuable as a directional co-visibility signal. World Bank is the most frequent configured peer, with 26 mentions across both providers. IMF and United Nations each appear 10 times, European Union 8 times, UNESCO 7 times, and Eurostat, G20, and World Economic Forum each 5 times. These figures help identify the institutional neighborhoods in which OECD visibility is being framed, but absence from the table should not be interpreted as absence from the answers.

## Recommended Power BI Indicators

The most useful dashboard should focus on validated OECD visibility first, then layer in caveated peer and referral indicators.

| Indicator | Why it matters | Suggested grain |
|---|---|---|
| OECD mention rate | Core discoverability signal. | Provider, model, category, query_id |
| OECD prominence distribution | Shows whether OECD is primary, supporting, incidental, or absent. | Provider, model, category |
| Primary/supporting visibility count | Easier executive signal than a full distribution. | Provider, model, category |
| Policy recommendation gap count | Tracks broad policy topics where OECD evidence is absent from generated advice. | Topic, query_id, provider |
| Named OECD publication frequency | Measures product recall for flagships and known assets. | Publication, provider, category |
| OECD URL reference rate | Lower-bound referral proxy; useful only with caveat. | Provider, model, category |
| Configured peer mention frequency | Directional co-visibility and positioning signal. | Peer, provider, category |
| Provider comparison table | Separates shared patterns from provider-specific packaging. | Provider, model |
| Validation status and caveat banner | Keeps users from over-reading competitor and URL proxies. | Dashboard-level metadata |
| Query inventory coverage | Shows which intents and topics are represented in the designed sample. | Category, query_id, expected_topic |

Recommended dashboard views:

- Executive overview: total responses, OECD mention rate, prominence distribution, policy recommendation gap, and validation status.
- Category view: mention rate and prominence by query category.
- Provider view: side-by-side OpenAI and Anthropic metrics, including URL lower-bound references.
- Product view: named OECD publications and products surfaced in responses.
- Peer view: configured peer frequencies with the competitor caveat visible.
- Query diagnostics: response-level table for drill-through, including query text, category, OECD flags, named publications, peers, and judge confidence.

## Bottom Line

This study shows that OECD visibility in AI-mediated answers is already strong when users ask for authorities, products, comparisons, datasets, or citable sources. The main strategic gap is broad policy recommendation visibility: models answer OECD-relevant policy questions without naming OECD evidence. For communications teams, the next step is to convert that gap into an operational dashboard and a content strategy that makes OECD evidence easier for AI systems to surface, cite, and distinguish from generic policy advice.
