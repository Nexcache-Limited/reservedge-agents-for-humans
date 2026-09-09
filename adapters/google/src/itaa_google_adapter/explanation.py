"""Buyer-facing explanation grounded in ranking facts. Never writes scores."""

from __future__ import annotations

import re
from collections.abc import Mapping

from itaa_google_adapter.ports import ExplanationResponse, RankingFacts

_NUMBER_RE = re.compile(r"\b\d+\b")


def deterministic_explanation(facts: RankingFacts) -> str:
    return (
        f"{facts.winner_display_name} is the recommended simulated airport-parking option. "
        "The ranking scores, offer totals, and downside remain those already shown "
        "on the buyer snapshot."
    )


def _recommended_names(facts: RankingFacts) -> set[str]:
    names = {facts.winner_display_name.lower()}
    for offer in facts.offers:
        if offer.recommended:
            names.add(offer.display_name.lower())
    return names


def _other_names(facts: RankingFacts) -> set[str]:
    winner = facts.winner_display_name.lower()
    return {
        offer.display_name.lower() for offer in facts.offers if offer.display_name.lower() != winner
    }


def _allowed_numbers(facts: RankingFacts) -> set[int]:
    allowed = {facts.downside_delta}
    for offer in facts.offers:
        allowed.add(offer.score_micros)
        allowed.add(offer.total_minor)
        allowed.add(offer.rank)
    return allowed


def contradicts_facts(text: str, facts: RankingFacts) -> bool:
    lowered = text.lower()
    others = _other_names(facts)
    for name in others:
        pattern_before = rf"\b{re.escape(name)}\b.{{0,40}}recommend"
        pattern_after = rf"recommend.{{0,40}}\b{re.escape(name)}\b"
        if re.search(pattern_before, lowered) or re.search(pattern_after, lowered):
            return True
    recommended = _recommended_names(facts)
    if not any(name in lowered for name in recommended):
        return True
    for match in _NUMBER_RE.finditer(text):
        value = int(match.group(0))
        if value >= 100 and value not in _allowed_numbers(facts):
            return True
    return False


def ground_explanation(model_text: object, facts: RankingFacts) -> ExplanationResponse:
    if not isinstance(model_text, str) or not model_text.strip():
        return ExplanationResponse(
            explanation=deterministic_explanation(facts),
            grounded=True,
            fallback="deterministic_facts",
        )
    if contradicts_facts(model_text, facts):
        return ExplanationResponse(
            explanation=deterministic_explanation(facts),
            grounded=True,
            fallback="deterministic_facts",
        )
    return ExplanationResponse(explanation=model_text.strip(), grounded=True)


def explanation_from_mapping(
    mapping: Mapping[str, object], facts: RankingFacts
) -> ExplanationResponse:
    return ground_explanation(mapping.get("explanation"), facts)
