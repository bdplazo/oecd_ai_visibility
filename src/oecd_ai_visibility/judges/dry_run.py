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

    def __init__(self, *, peer_organisations: list[str]) -> None:
        super().__init__(provider="dry-run", model="deterministic-v1")
        self.peer_organisations = peer_organisations

    def score(self, *, raw_record: RawResponseRecord, query: QuerySpec) -> JudgeScore:
        response_text = raw_record.response_text
        oecd_mentioned = _mentions_oecd(response_text, raw_record.citations)
        competitors = _competitors_mentioned(
            response_text=response_text,
            query=query,
            peer_organisations=self.peer_organisations,
        )
        oecd_url_referenced = any(_is_oecd_citation(citation) for citation in raw_record.citations)
        if not oecd_url_referenced:
            oecd_url_referenced = "oecd.org" in response_text.casefold()

        return JudgeScore(
            oecd_mentioned=oecd_mentioned,
            oecd_prominence=_oecd_prominence(
                response_text=response_text,
                oecd_mentioned=oecd_mentioned,
                competitors_mentioned=competitors,
            ),
            oecd_publications_named=_oecd_publications_named(response_text),
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
    oecd_mentioned: bool,
    competitors_mentioned: dict[str, Prominence],
) -> Prominence:
    if not oecd_mentioned:
        return "none"

    normalized = " ".join(response_text.split()).casefold()
    first_sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    if first_sentence.startswith("the oecd is the primary") or (
        "oecd" in first_sentence and "primary international reference point" in first_sentence
    ):
        return "primary"

    if competitors_mentioned:
        return "supporting"
    if "strong citable source" in normalized or "oecd.org" in normalized:
        return "supporting"
    if normalized.count("oecd") >= 2:
        return "primary"
    return "incidental"


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
