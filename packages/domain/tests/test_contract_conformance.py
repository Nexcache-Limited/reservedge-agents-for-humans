from __future__ import annotations

import json
from pathlib import Path

import pytest

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import (
    AcceptanceId,
    ApprovalId,
    AuthorizationId,
    BuyerToken,
    CounterOfferId,
    IdempotencyKey,
    IntentId,
    OfferId,
    SignatureHandle,
    SupplierToken,
)
from itaa_domain.offer import OfferEvidence, OfferPrice, OfferTerms
from itaa_domain.value_objects import (
    AddOn,
    AirportCode,
    CancellationTerm,
    EvidenceRef,
    EvidenceType,
    LotType,
    Money,
    PayloadHash,
    RefundTerm,
    SimulatedAvailability,
    TimeWindow,
    Version,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures"
VALID = CONTRACTS / "valid"
INVALID = CONTRACTS / "invalid"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_fixture_identifiers_and_values_enter_domain() -> None:
    intent = _load(VALID / "purchase-intent-jfk.json")
    assert IntentId(str(intent["intentId"])).to_primitive() == intent["intentId"]
    assert BuyerToken(str(intent["buyerToken"])).to_primitive() == intent["buyerToken"]
    assert AirportCode(str(intent["location"]["airportCode"])).to_primitive() == "JFK"  # type: ignore[index]
    window = TimeWindow.from_primitives(
        intent["serviceWindow"]["start"],  # type: ignore[index]
        intent["serviceWindow"]["end"],  # type: ignore[index]
    )
    assert window.to_primitive()["start"] == "2026-09-03T13:00:00Z"
    disclosure = intent["disclosure"]["approvedPayloadHash"]  # type: ignore[index]
    assert PayloadHash(str(disclosure)).to_primitive() == disclosure

    offer = _load(VALID / "offer-parkdirect.json")
    price = offer["price"]  # type: ignore[assignment]
    domain_price = OfferPrice(
        Money(int(price["subtotalMinor"]), str(price["currency"])),  # type: ignore[index]
        Money(int(price["feesMinor"]), str(price["currency"])),  # type: ignore[index]
        Money(int(price["taxMinor"]), str(price["currency"])),  # type: ignore[index]
        Money(int(price["totalMinor"]), str(price["currency"])),  # type: ignore[index]
    )
    assert domain_price.to_primitive()["totalMinor"] == 11900
    terms = OfferTerms(
        price=domain_price,
        lot_type=LotType(str(offer["service"]["lotType"])),  # type: ignore[index]
        shuttle_minutes=int(offer["service"]["shuttleMinutes"]),  # type: ignore[index]
        distance_metres=int(offer["service"]["distanceMeters"]),  # type: ignore[index]
        availability=SimulatedAvailability(str(offer["service"]["availability"])),  # type: ignore[index]
        add_ons=tuple(AddOn(item) for item in offer["service"]["addOns"]),  # type: ignore[index]
        cancellation=CancellationTerm(str(offer["terms"]["cancellation"])),  # type: ignore[index]
        refund=RefundTerm(str(offer["terms"]["refund"])),  # type: ignore[index]
        validity=TimeWindow.from_primitives(offer["validFrom"], offer["validUntil"]),
        evidence=tuple(
            OfferEvidence(EvidenceType(str(item["type"])), EvidenceRef(str(item["ref"])))  # type: ignore[index]
            for item in offer["evidence"]  # type: ignore[union-attr]
        ),
        signature=SignatureHandle(str(offer["signature"])),
        simulation=bool(offer["simulation"]),
    )
    assert terms.simulation is True
    assert OfferId(str(offer["offerId"]))
    assert SupplierToken(str(offer["supplierToken"]))
    assert Version(int(offer["version"])).value == 1

    sky = _load(VALID / "offer-skyshield.json")
    flex = _load(VALID / "offer-terminalflex.json")
    assert OfferId(str(sky["offerId"]))
    assert OfferId(str(flex["offerId"]))
    AddOn(str(sky["service"]["addOns"][0]))  # type: ignore[index]
    SimulatedAvailability(str(flex["service"]["availability"]))  # type: ignore[index]

    counter = _load(VALID / "counter-offer.json")
    assert CounterOfferId(str(counter["counterOfferId"]))
    assert Version(int(counter["parentOfferVersion"])).value == 1
    assert bool(counter["simulation"]) is True

    acceptance = _load(VALID / "acceptance.json")
    assert AcceptanceId(str(acceptance["acceptanceId"]))
    assert PayloadHash(str(acceptance["acceptedTermsHash"]))
    assert ApprovalId(str(acceptance["buyerApprovalId"]))
    assert Version(int(acceptance["offerVersion"])).value == 1

    auth = _load(VALID / "transaction-authorization.json")
    assert AuthorizationId(str(auth["authorizationId"]))
    assert IdempotencyKey(str(auth["idempotencyKey"]))
    assert ApprovalId(str(auth["userApprovalId"]))
    assert SignatureHandle(str(auth["receiptSignature"]))
    amount = Money(int(auth["amountMinor"]), str(auth["currency"]))
    assert amount.to_primitive()["amountMinor"] == 14800
    assert auth["mode"] == "SIMULATED"
    assert auth["action"] == "reserve_parking"


def test_invalid_fixture_values_are_rejected_by_domain_types() -> None:
    with pytest.raises(DomainInvariantError):
        OfferId("bad")
    with pytest.raises(DomainInvariantError):
        Money(-1, "USD")
    with pytest.raises(DomainInvariantError):
        Money(9800, "usd")
    with pytest.raises(DomainInvariantError):
        PayloadHash("not-a-hash")
    with pytest.raises(DomainInvariantError):
        TimeWindow.from_primitives("2026-08-21T16:00:00Z", "2026-08-20T16:00:00Z")
    false_sim = _load(INVALID / "offer-false-simulation.json")
    assert false_sim["simulation"] is False
    with pytest.raises(DomainInvariantError):
        OfferTerms(
            price=OfferPrice(
                Money(9800, "USD"),
                Money(1200, "USD"),
                Money(900, "USD"),
                Money(11900, "USD"),
            ),
            lot_type=LotType.UNCOVERED,
            shuttle_minutes=15,
            distance_metres=2400,
            availability=SimulatedAvailability.CONFIRMED_SIMULATED,
            add_ons=(),
            cancellation=CancellationTerm.FREE_UNTIL_24H,
            refund=RefundTerm.ORIGINAL_METHOD,
            validity=TimeWindow.from_primitives("2026-08-20T16:00:00Z", "2026-08-21T16:00:00Z"),
            evidence=(
                OfferEvidence(EvidenceType.SUPPLIER_POLICY, EvidenceRef("policy.parkdirect.v1")),
            ),
            signature=SignatureHandle("sg_01k2m3n4p5q6r7s8t9v0w1x2h1"),
            simulation=False,
        )
    live = _load(INVALID / "authorization-live-mode.json")
    assert live["mode"] != "SIMULATED"
    real = _load(INVALID / "authorization-real-mode.json")
    assert real["mode"] != "SIMULATED"
    wrong_action = _load(INVALID / "authorization-wrong-action.json")
    assert wrong_action["action"] != "reserve_parking"
    overflow = _load(INVALID / "offer-overflow-money.json")
    with pytest.raises(DomainInvariantError):
        Money(int(overflow["price"]["taxMinor"]), "USD")  # type: ignore[index]
    float_money = _load(INVALID / "offer-float-money.json")
    with pytest.raises(DomainInvariantError):
        Money(float_money["price"]["subtotalMinor"], "USD")  # type: ignore[index, arg-type]
    incorrect = _load(INVALID / "offer-incorrect-total.json")
    with pytest.raises(DomainInvariantError):
        OfferPrice(
            Money(int(incorrect["price"]["subtotalMinor"]), "USD"),  # type: ignore[index]
            Money(int(incorrect["price"]["feesMinor"]), "USD"),  # type: ignore[index]
            Money(int(incorrect["price"]["taxMinor"]), "USD"),  # type: ignore[index]
            Money(int(incorrect["price"]["totalMinor"]), "USD"),  # type: ignore[index]
        )
