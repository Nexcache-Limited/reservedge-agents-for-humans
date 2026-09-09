from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import parkdirect_price, parkdirect_terms, usd
from pydantic import ValidationError
from wp04_helpers import A1_ID, A2_ID, A3_ID, BUYER, CORRELATION, CREATED_AT, EXPIRES_AT, OWNER
from wp06_fakes import (
    accept_command,
    authorize_command,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_api.app import create_app
from itaa_api.export_openapi import openapi_document
from itaa_api.schemas import BuyerOffer
from itaa_application.errors import ApplicationError
from itaa_application.offer_terms_hash import offer_terms_hash
from itaa_application.session_models import RankedOfferView, fit_for_rank
from itaa_domain.identifiers import SignatureHandle
from itaa_domain.offer import OfferEvidence, OfferPrice
from itaa_domain.value_objects import (
    AddOn,
    CancellationTerm,
    EvidenceRef,
    EvidenceType,
    LotType,
    Money,
    RefundTerm,
    SimulatedAvailability,
    TimeWindow,
    format_utc,
)
from itaa_policy.canonical import SEPARATOR_OFFER_TERMS, hash_canonical

_TERMS_HASH = "sha256:" + ("a" * 64)
_PREFIX = "/v1/simulations/airport-parking"
_REQUIRED = {
    "schemaVersion",
    "offerId",
    "supplierToken",
    "version",
    "sourceType",
    "offerClass",
    "issuedAt",
    "validFrom",
    "validUntil",
    "termsHash",
    "price",
    "fit",
    "simulation",
    "validity",
    "inventory",
    "transactionResult",
    "completeness",
    "evidence",
}


def _gov(approval_id: object) -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": approval_id.to_primitive(),
        "correlationId": CORRELATION.to_primitive(),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def _buyer_offer_schema(document: dict[str, object]) -> dict[str, object]:
    components = document["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    schema = schemas["BuyerOffer"]
    assert isinstance(schema, dict)
    return schema


def _ranked_view(
    *, rank: int = 1, score_micros: int = 671_000, recommended: bool = True
) -> RankedOfferView:
    return RankedOfferView(
        offer_id="of_01k2m3n4p5q6r7s8t9v0w1x2a2",
        supplier_token="sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
        version=1,
        rank=rank,
        score_micros=score_micros,
        total_minor=14800,
        currency="USD",
        recommended=recommended,
        simulation=True,
        issued_at="2026-06-01T12:00:00Z",
        valid_from="2026-06-01T12:00:00Z",
        valid_until="2026-06-02T12:00:00Z",
        terms_hash=_TERMS_HASH,
        tax_minor=800,
        fees_minor=400,
        fit=fit_for_rank(rank),
        evidence=(("rate_card", "rate.jfk.skyshield"),),
    )


def test_openapi_names_buyer_offer_without_score_micros() -> None:
    document = openapi_document()
    schema = _buyer_offer_schema(document)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert "scoreMicros" not in properties
    assert "scoreMicros" not in json.dumps(schema)
    for name in _REQUIRED:
        assert name in properties
    assert set(schema["required"]) >= _REQUIRED
    assert "termsHash" in schema["required"]
    terms_schema = properties["termsHash"]
    assert isinstance(terms_schema, dict)
    assert terms_schema.get("type") == "string"
    assert "anyOf" not in terms_schema
    assert properties["sourceType"]["enum"] == [
        "aggregator_rate",
        "public_market_reference",
        "supplier_private_quote",
    ]
    assert properties["offerClass"]["enum"] == ["standard", "curated"]
    assert properties["fit"]["enum"] == ["strong", "good", "fair"]
    assert properties["inventory"]["enum"] == [
        "not_held",
        "subject_to_availability",
        "held_until",
    ]
    assert properties["simulation"]["const"] is True
    assert "inventoryHeldUntil" not in schema["required"]
    snapshot = document["paths"]["/v1/simulations/airport-parking/intents/{intent_id}"]["get"]
    ref = snapshot["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("BuyerSessionSnapshot")
    dumped = json.dumps(document)
    assert dumped.count("scoreMicros") == 0


def test_buyer_offer_model_rejects_score_micros_and_simulated_hold() -> None:
    valid = {
        "schemaVersion": "1.0",
        "offerId": "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
        "supplierToken": "sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
        "version": 1,
        "sourceType": "supplier_private_quote",
        "offerClass": "curated",
        "issuedAt": "2026-06-01T12:00:00Z",
        "validFrom": "2026-06-01T12:00:00Z",
        "validUntil": "2026-06-02T12:00:00Z",
        "termsHash": _TERMS_HASH,
        "price": {"totalMinor": 14800, "taxMinor": 800, "feesMinor": 400, "currency": "USD"},
        "fit": "strong",
        "simulation": True,
        "validity": "valid",
        "inventory": "not_held",
        "transactionResult": "simulated",
        "completeness": "complete",
        "evidence": [{"type": "rate_card", "ref": "rate.jfk.skyshield"}],
        "recommended": False,
    }
    offer = BuyerOffer.model_validate(valid)
    assert offer.offerClass == "curated"
    assert offer.sourceType == "supplier_private_quote"
    assert offer.recommended is False
    assert offer.termsHash == _TERMS_HASH
    missing = dict(valid)
    missing.pop("termsHash")
    with pytest.raises(ValidationError):
        BuyerOffer.model_validate(missing)
    with pytest.raises(ValidationError):
        BuyerOffer.model_validate({**valid, "scoreMicros": 671000})
    with pytest.raises(ValidationError):
        BuyerOffer.model_validate({**valid, "inventoryHeldUntil": "2026-06-01T18:00:00Z"})


def test_buyer_projection_keeps_score_micros_off_serialized_json() -> None:
    view = _ranked_view()
    assert view.score_micros == 671_000
    primitive = view.to_buyer_offer()
    assert "scoreMicros" not in primitive
    assert primitive["termsHash"] == _TERMS_HASH
    assert "inventoryHeldUntil" not in primitive
    assert primitive["inventory"] == "not_held"
    assert primitive["sourceType"] == "supplier_private_quote"
    assert primitive["offerClass"] == "standard"
    assert primitive["fit"] == "strong"
    assert primitive["recommended"] is True
    BuyerOffer.model_validate(primitive)
    curated_private = dict(primitive)
    curated_private["offerClass"] = "curated"
    curated_private["sourceType"] = "supplier_private_quote"
    curated_private["recommended"] = False
    BuyerOffer.model_validate(curated_private)
    assert fit_for_rank(2) == "good"
    assert fit_for_rank(3) == "fair"


def test_identical_offer_terms_produce_the_same_hash() -> None:
    first = parkdirect_terms()
    second = parkdirect_terms()
    assert offer_terms_hash(first) == offer_terms_hash(second)
    assert offer_terms_hash(first).to_primitive() == offer_terms_hash(second).to_primitive()


def test_price_change_changes_terms_hash() -> None:
    base = parkdirect_terms()
    original = offer_terms_hash(base)
    price = parkdirect_price()
    total_changed = replace(base, price=OfferPrice(usd(9801), price.fees, price.tax, usd(11901)))
    assert offer_terms_hash(total_changed) != original
    currency_changed = replace(
        base,
        price=OfferPrice(
            Money(9800, "GBP"),
            Money(1200, "GBP"),
            Money(900, "GBP"),
            Money(11900, "GBP"),
        ),
    )
    assert offer_terms_hash(currency_changed) != original
    assert offer_terms_hash(total_changed) != offer_terms_hash(currency_changed)


def test_non_price_term_changes_each_change_the_hash() -> None:
    base = parkdirect_terms()
    original = offer_terms_hash(base)
    window = base.validity
    mutations = (
        replace(base, cancellation=CancellationTerm.NON_REFUNDABLE),
        replace(base, refund=RefundTerm.NONE),
        replace(base, validity=TimeWindow(window.start, window.end + timedelta(hours=1))),
        replace(base, lot_type=LotType.COVERED, shuttle_minutes=10, distance_metres=1800),
        replace(base, availability=SimulatedAvailability.LIMITED_SIMULATED),
        replace(base, add_ons=(AddOn.EV_CHARGING,)),
        replace(
            base,
            evidence=(OfferEvidence(EvidenceType.RATE_CARD, EvidenceRef("rate.parkdirect.v2")),),
        ),
        replace(base, signature=SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h9")),
    )
    seen = {original.to_primitive()}
    for mutated in mutations:
        digest = offer_terms_hash(mutated)
        assert digest != original
        assert digest.to_primitive() not in seen
        seen.add(digest.to_primitive())
    material = base.to_primitive()
    assert material["simulation"] is True
    assert "signature" in material


def test_ranking_recommendation_and_score_micros_do_not_change_terms_hash() -> None:
    terms = parkdirect_terms()
    digest = offer_terms_hash(terms).to_primitive()
    material = json.dumps(terms.to_primitive())
    assert "scoreMicros" not in material
    assert "score_micros" not in material
    primitive = terms.to_primitive()
    assert "rank" not in primitive
    assert "recommended" not in primitive
    first = replace(_ranked_view(rank=1, score_micros=671_000, recommended=True), terms_hash=digest)
    second = replace(
        _ranked_view(rank=3, score_micros=535_000, recommended=False), terms_hash=digest
    )
    assert first.to_buyer_offer()["termsHash"] == digest
    assert second.to_buyer_offer()["termsHash"] == digest
    legacy = hash_canonical(
        SEPARATOR_OFFER_TERMS,
        {"totalMinor": terms.price.total.amount_minor, "currency": terms.price.total.currency},
    )
    assert offer_terms_hash(terms) != legacy


def test_a3_a4_and_buyer_projection_use_the_identical_terms_hash() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    winner = next(item for item in dispatched.offers if item.recommended)
    session = facade._sessions.get(intent_id())
    assert session is not None
    mapped = next(
        item
        for item in session.mapped_offers
        if item.offer.offer_id.to_primitive() == winner.offer_id
    )
    assert mapped.offer.terms is not None
    expected = offer_terms_hash(mapped.offer.terms).to_primitive()
    assert winner.terms_hash == expected
    buyer = winner.to_buyer_offer()
    assert buyer["termsHash"] == expected
    assert "scoreMicros" not in buyer
    BuyerOffer.model_validate(buyer)
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(winner.offer_id)
    )
    assert accepted.acceptance is not None
    session = facade._sessions.get(intent_id())
    assert session is not None
    assert session.acceptance is not None
    assert session.acceptance.accepted_terms_hash.to_primitive() == expected
    accepted_winner = next(item for item in accepted.offers if item.offer_id == winner.offer_id)
    assert accepted_winner.terms_hash == expected
    authorized = facade.authorize_simulated_transaction(
        intent_id(),
        authorize_command(
            acceptance_id=accepted.acceptance.acceptance_id,
            amount_minor=winner.total_minor,
            supplier_token=winner.supplier_token,
        ),
    )
    authorized_winner = next(item for item in authorized.offers if item.offer_id == winner.offer_id)
    assert authorized_winner.terms_hash == expected


def test_stale_or_changed_terms_cannot_reuse_authorization_binding() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    winner = next(item for item in dispatched.offers if item.recommended)
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(winner.offer_id)
    )
    assert accepted.acceptance is not None
    session = facade._sessions.get(intent_id())
    assert session is not None
    mutated_mapped = []
    for item in session.mapped_offers:
        terms = item.offer.terms
        if item.offer.offer_id.to_primitive() != winner.offer_id or terms is None:
            mutated_mapped.append(item)
            continue
        changed = replace(terms, cancellation=CancellationTerm.NON_REFUNDABLE)
        mutated_mapped.append(replace(item, offer=replace(item.offer, terms=changed)))
    facade._sessions.save(replace(session, mapped_offers=tuple(mutated_mapped)))
    with pytest.raises(ApplicationError) as caught:
        facade.authorize_simulated_transaction(
            intent_id(),
            authorize_command(
                acceptance_id=accepted.acceptance.acceptance_id,
                amount_minor=winner.total_minor,
                supplier_token=winner.supplier_token,
            ),
        )
    assert caught.value.field == "termsHash"
    assert caught.value.code == "mismatch"


def test_http_buyer_json_contains_required_terms_hash_never_score_micros() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post(f"{_PREFIX}/intents", json=jfk_payload())
    assert created.status_code == 200
    intent = created.json()["intentId"]
    confirmed = client.post(f"{_PREFIX}/intents/{intent}/confirm", json=_gov(A1_ID))
    assert confirmed.status_code == 200
    dispatched = client.post(f"{_PREFIX}/intents/{intent}/dispatch", json=_gov(A2_ID))
    assert dispatched.status_code == 200
    body = dispatched.json()
    assert body["offers"]
    for item in body["offers"]:
        assert isinstance(item, dict)
        assert "scoreMicros" not in item
        assert "termsHash" in item
        BuyerOffer.model_validate(item)
    winner = next(item for item in body["offers"] if item["recommended"])
    accepted = client.post(
        f"{_PREFIX}/intents/{intent}/acceptances",
        json={**_gov(A3_ID), "offerId": body["recommendedOfferId"], "offerVersion": 1},
    )
    assert accepted.status_code == 200
    accepted_winner = next(
        item for item in accepted.json()["offers"] if item["offerId"] == winner["offerId"]
    )
    assert accepted_winner["termsHash"] == winner["termsHash"]
    snapshot = client.get(f"{_PREFIX}/intents/{intent}")
    assert snapshot.status_code == 200
    snapshot_winner = next(
        item for item in snapshot.json()["offers"] if item["offerId"] == winner["offerId"]
    )
    assert snapshot_winner["termsHash"] == winner["termsHash"]
    assert "scoreMicros" not in snapshot.text
