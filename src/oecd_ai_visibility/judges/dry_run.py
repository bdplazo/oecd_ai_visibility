"""Deterministic local judge used for dry-run scoring."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from oecd_ai_visibility.judges.base import Judge
from oecd_ai_visibility.schemas import (
    Citation,
    JudgeScore,
    Prominence,
    QuerySpec,
    RawResponseRecord,
)

OECD_PUBLICATIONS = (
    "PISA",
    "OECD Economic Outlook",
    "Going for Growth",
    "Better Life Index",
    "BEPS",
    "Revenue Statistics",
    "Health at a Glance",
    "Main Science and Technology Indicators",
    "Income Distribution Database",
    "OECD AI Principles",
    "Anti-Bribery Convention",
)


class DryRunJudge(Judge):
    """Transparent, conservative heuristic judge requiring no keys or network."""

    def __init__(
        self,
        *,
        peer_organisations: list[str],
        provider: str = "dry-run",
        model: str = "deterministic-v1",
    ) -> None:
        super().__init__(provider=provider, model=model)
        self.peer_organisations = peer_organisations

    def score(self, *, raw_record: RawResponseRecord, query: QuerySpec) -> JudgeScore:
        response_text = raw_record.response_text
        oecd_mentioned = _mentions_oecd(response_text, raw_record.citations)
        competitors = _competitors_mentioned(
            response_text=response_text,
            query=query,
            peer_organisations=self.peer_organisations,
        )
        # NOTE: ``oecd_url_referenced`` is a weak proxy. The configured providers run with
        # ``supports_citations: false``, so structured ``citations`` are almost always empty.
        # In practice this flag therefore detects a literal ``oecd.org`` string typed in the
        # answer prose, not genuine citation/referral behaviour. Treat it as a lower bound on
        # OECD referral visibility, not a measure of it.
        oecd_url_referenced = any(_is_oecd_citation(citation) for citation in raw_record.citations)
        if not oecd_url_referenced:
            oecd_url_referenced = "oecd.org" in response_text.casefold()

        publications = _oecd_publications_named(response_text)
        return JudgeScore(
            oecd_mentioned=oecd_mentioned,
            oecd_prominence=_oecd_prominence(
                response_text=response_text,
                category=query.category,
                oecd_mentioned=oecd_mentioned,
                competitors_mentioned=competitors,
                publications_named=publications,
            ),
            oecd_publications_named=publications,
            oecd_url_referenced=oecd_url_referenced,
            competitors_mentioned=competitors,
            factual_issues="",
            judge_confidence=_judge_confidence(
                response_text=response_text,
                oecd_mentioned=oecd_mentioned,
                oecd_url_referenced=oecd_url_referenced,
            ),
        )


def _mentions_oecd(response_text: str, citations: list[Citation]) -> bool:
    if re.search(r"\bOECD\b", response_text, flags=re.IGNORECASE):
        return True
    return any(_is_oecd_citation(citation) for citation in citations)


def _oecd_prominence(
    *,
    response_text: str,
    category: str,
    oecd_mentioned: bool,
    competitors_mentioned: dict[str, Prominence],
    publications_named: list[str],
) -> Prominence:
    """Classify how central the OECD is to the answer.

    Designed to avoid the earlier verbosity bias, where simply repeating "OECD"
    twice was enough to earn ``primary``. Repetition count is deliberately not used.
    The signals are instead about *centrality*:

    * ``named_product_recall`` queries ask directly about an OECD product (PISA,
      BEPS, ...). If OECD is mentioned and an OECD publication is named, the answer
      is squarely about the OECD, so prominence is floored at ``primary``.
    * Otherwise the OECD is ``primary`` only when it *leads* the answer: it appears
      in the opening segment and no peer organisation shares that opening. This
      captures "the answer is about the OECD" while excluding comparative lead-ins
      that merely list the OECD among peers.
    * If peers are present (and OECD does not lead) the OECD is ``supporting``.
    * A bare ``oecd.org``/"strong citable source" signal also counts as ``supporting``.
    * Anything else with a mention is ``incidental``.
    """

    if not oecd_mentioned:
        return "none"

    if category == "named_product_recall" and publications_named:
        return "primary"

    lead = _lead_segment(response_text)
    oecd_leads = "oecd" in lead and not any(
        peer.casefold() in lead for peer in competitors_mentioned
    )
    if oecd_leads:
        return "primary"

    if competitors_mentioned:
        return "supporting"

    normalized = " ".join(response_text.split()).casefold()
    if "strong citable source" in normalized or "oecd.org" in normalized:
        return "supporting"
    return "incidental"


def _lead_segment(response_text: str) -> str:
    """Return the casefolded opening sentence, robust to markdown structure.

    Markdown table rows and separators are dropped and header/emphasis markers are
    stripped before taking the first sentence. Without this, a leading markdown
    table would be collapsed into one giant "sentence", letting an OECD reference
    buried deep inside a comparison table masquerade as the lead of the answer.
    """

    cleaned: list[str] = []
    for line in response_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("|"):  # markdown table data row
            continue
        if set(stripped) <= set("|-: "):  # markdown table separator row
            continue
        stripped = stripped.lstrip("#").strip().replace("*", "").replace("`", "")
        if stripped:
            cleaned.append(stripped)

    joined = " ".join(cleaned)
    first_sentence = re.split(r"(?<=[.!?])\s+", joined, maxsplit=1)[0]
    return first_sentence.casefold()


def _oecd_publications_named(response_text: str) -> list[str]:
    normalized = response_text.casefold()
    return [
        publication for publication in OECD_PUBLICATIONS if publication.casefold() in normalized
    ]


def _competitors_mentioned(
    *,
    response_text: str,
    query: QuerySpec,
    peer_organisations: list[str],
) -> dict[str, Prominence]:
    competitors: dict[str, Prominence] = {}
    for organisation in peer_organisations:
        if not _contains_term(response_text, organisation):
            continue
        count = len(re.findall(_term_pattern(organisation), response_text, flags=re.IGNORECASE))
        competitors[organisation] = (
            "supporting" if query.category == "comparative_peer" or count > 1 else "incidental"
        )
    return competitors


def _is_oecd_citation(citation: Citation) -> bool:
    values = [str(citation.url), citation.source or "", citation.title or ""]
    for value in values:
        normalized = value.casefold()
        parsed = urlparse(value)
        host = parsed.netloc.casefold()
        if host == "oecd.org" or host.endswith(".oecd.org") or "oecd.org" in normalized:
            return True
    return False


def _judge_confidence(
    *,
    response_text: str,
    oecd_mentioned: bool,
    oecd_url_referenced: bool,
) -> str:
    if oecd_url_referenced or re.search(r"\bOECD\b", response_text, flags=re.IGNORECASE):
        return "high"
    if not oecd_mentioned:
        return "high"
    return "medium"


def _contains_term(text: str, term: str) -> bool:
    return re.search(_term_pattern(term), text, flags=re.IGNORECASE) is not None


def _term_pattern(term: str) -> str:
    escaped = re.escape(term)
    return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
