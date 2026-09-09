from __future__ import annotations

import json
from pathlib import Path

import pytest
from wp04_helpers import OCCURRED_AT, SUPPLIERS
from wp05_helpers import (
    DEADLINE,
    INTENT,
    RELIABILITY,
    authorized_binding_for,
    clone,
    collected_offer,
    fixture_policy,
    load_invalid_offer,
    scoped_fixture,
)

from itaa_application.errors import ApplicationError
from itaa_application.offer_boundary import accept_offer
from itaa_application.ranking_decision import decide
from itaa_domain.offer import OfferState
from itaa_domain.value_objects import SimulatedAvailability

INVALID_DIR = (
    Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures" / "invalid"
)


def _accept(name: str, **overrides: object):
    payload, binding = scoped_fixture(name)
    received = overrides.pop("received_at", OCCURRED_AT)
    evaluated = overrides.pop("evaluated_at", OCCURRED_AT)
    seen = overrides.pop("seen_versions", frozenset())
    if overrides:
        payload = clone(payload)
        payload.update(overrides)  # type: ignore[arg-type]
    return accept_offer(
        collected_offer(payload, binding, received),  # type: ignore[arg-type]
        fixture_policy(binding, payload),
        evaluated_at=evaluated,  # type: ignore[arg-type]
        seen_versions=seen,  # type: ignore[arg-type]
    )


def test_canonical_offers_map_to_eligible_and_golden_ranking() -> None:
    mapped = [
        _accept("offer-parkdirect.json"),
        _accept("offer-skyshield.json"),
        _accept("offer-terminalflex.json"),
    ]
    assert all(item.offer.state is OfferState.ELIGIBLE for item in mapped)
    decision = decide(
        tuple(item.ranking_input for item in mapped),
        mapped[0].need,
        evaluated_at=OCCURRED_AT,
        reliability=RELIABILITY,
    )
    scores = {item.offer_id.to_primitive(): item.score_micros for item in decision.result.ranked}
    assert scores["of_01k2m3n4p5q6r7s8t9v0w1x2a2"] == 671_000
    assert scores["of_01k2m3n4p5q6r7s8t9v0w1x2a1"] == 660_000
    assert scores["of_01k2m3n4p5q6r7s8t9v0w1x2a3"] == 535_000
    assert decision.result.recommended_offer_id is not None
    assert decision.result.recommended_offer_id.to_primitive() == "of_01k2m3n4p5q6r7s8t9v0w1x2a2"
    assert decision.fingerprint.value.startswith("sha256:")


@pytest.mark.parametrize("path", sorted(INVALID_DIR.glob("offer-*.json")))
def test_invalid_contract_offers_are_rejected(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    binding = authorized_binding_for(SUPPLIERS[0])
    park, _unused = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, park),
            evaluated_at=OCCURRED_AT,
        )


def test_wrong_supplier_and_intent_are_rejected() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    payload["supplierToken"] = "sp_01k2m3n4p5q6r7s8t9v0w1x2b2"
    with pytest.raises(ApplicationError, match="supplierToken: mismatch"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
        )
    payload, binding = scoped_fixture("offer-parkdirect.json")
    payload["intentId"] = "pi_01k2m3n4p5q6r7s8t9v0w1x2y3"
    with pytest.raises(ApplicationError, match="intentId: mismatch"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
        )
    assert INTENT.to_primitive() == "pi_01k2m3n4p5q6r7s8t9v0w1x2y3"


def test_expired_unavailable_and_stale_are_rejected() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError, match="version: duplicate"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
            seen_versions=frozenset({1}),
        )
    payload["version"] = 2
    with pytest.raises(ApplicationError, match="version: stale"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
            seen_versions=frozenset({3}),
        )
    payload, binding = scoped_fixture("offer-parkdirect.json")
    payload["service"]["availability"] = SimulatedAvailability.UNAVAILABLE_SIMULATED.value
    with pytest.raises(ApplicationError, match="availability: unavailable"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
        )
    payload, binding = scoped_fixture("offer-parkdirect.json")
    payload["validFrom"] = "2026-08-20T15:00:00Z"
    payload["validUntil"] = "2026-08-20T16:00:00Z"
    with pytest.raises(ApplicationError, match="validUntil: expired"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
        )


def test_after_deadline_and_invalid_evidence_are_rejected() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError, match="responseDeadline: after_deadline"):
        accept_offer(
            collected_offer(payload, binding, DEADLINE),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
        )
    payload, binding = scoped_fixture("offer-parkdirect.json")
    payload["evidence"] = [{"type": "supplier_policy", "ref": "buyer.raw.context"}]
    with pytest.raises(ApplicationError, match="evidence: mismatch"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, scoped_fixture("offer-parkdirect.json")[0]),
            evaluated_at=OCCURRED_AT,
        )
    payload, binding = scoped_fixture("offer-parkdirect.json")
    payload["price"]["currency"] = "EUR"
    with pytest.raises(ApplicationError, match="currency: mismatch"):
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, payload),
            evaluated_at=OCCURRED_AT,
        )


def test_errors_do_not_echo_adversarial_values() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    original = clone(payload)
    payload["supplierToken"] = "sp_01k2m3n4p5q6r7s8t9v0w1x2b2"
    with pytest.raises(ApplicationError) as captured:
        accept_offer(
            collected_offer(payload, binding),
            fixture_policy(binding, original),
            evaluated_at=OCCURRED_AT,
        )
    text = str(captured.value)
    assert "alice@" not in text
    assert "sp_" not in text
    assert "sha256:" not in text
    invalid = load_invalid_offer("offer-forbidden-buyer-field.json")
    binding = authorized_binding_for(SUPPLIERS[0])
    park, _unused = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError) as captured:
        accept_offer(
            collected_offer(invalid, binding),
            fixture_policy(binding, park),
            evaluated_at=OCCURRED_AT,
        )
    assert "email" not in str(captured.value).lower() or "schema_invalid" in str(captured.value)
