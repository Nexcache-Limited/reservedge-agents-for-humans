from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from itaa_validate_contracts.invariants import check_invariants
from itaa_validate_contracts.paths import contracts_root
from itaa_validate_contracts.schema import load_json, validate_instance

CONTRACTS = contracts_root()
BUYER_OFFER = CONTRACTS / "fixtures" / "valid" / "buyer-offer.json"

COMMERCIAL_FIELDS = (
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
)

PRICE_FIELDS = ("totalMinor", "taxMinor", "feesMinor", "currency")


def _assert_valid(document: dict[str, Any], *, source: str) -> None:
    assert validate_instance(document, schema_key="buyer-offer", source=source) == []
    assert check_invariants(document, schema_key="buyer-offer", source=source) == []


@pytest.mark.contract
def test_valid_buyer_offer_projection_validates() -> None:
    payload = load_json(BUYER_OFFER)
    assert isinstance(payload, dict)
    _assert_valid(payload, source="buyer-offer.json")


@pytest.mark.contract
def test_buyer_offer_commercial_fields_are_present() -> None:
    payload = load_json(BUYER_OFFER)
    for field in COMMERCIAL_FIELDS:
        assert field in payload
    for field in PRICE_FIELDS:
        assert field in payload["price"]
    assert payload["simulation"] is True
    assert payload["inventory"] == "not_held"
    assert "inventoryHeldUntil" not in payload
    assert payload["transactionResult"] in {"simulated", "authorized_simulated"}
    assert "depositMinor" in payload["price"]
    assert "payLaterMinor" in payload["price"]


@pytest.mark.contract
def test_buyer_offer_rejects_score_micros() -> None:
    payload = deepcopy(load_json(BUYER_OFFER))
    payload["scoreMicros"] = 671000
    violations = validate_instance(
        payload, schema_key="buyer-offer", source="buyer-offer-score-micros"
    )
    assert any(
        item.keyword == "additionalProperties" and "/scoreMicros" in item.path
        for item in violations
    ), [item.render() for item in violations]


@pytest.mark.contract
def test_buyer_offer_rejects_held_until_in_simulation() -> None:
    payload = deepcopy(load_json(BUYER_OFFER))
    payload["inventoryHeldUntil"] = "2026-08-20T18:00:00Z"
    violations = validate_instance(
        payload, schema_key="buyer-offer", source="buyer-offer-held-until-simulation"
    )
    assert any(
        item.keyword in {"not", "invariant"}
        and (
            "inventoryHeldUntil" in item.path
            or "inventoryHeldUntil" in item.message
            or item.path == "/"
        )
        for item in violations
    ), [item.render() for item in violations]


@pytest.mark.contract
def test_buyer_offer_rejects_unknown_field() -> None:
    payload = deepcopy(load_json(BUYER_OFFER))
    payload["competitorRate"] = 12000
    violations = validate_instance(payload, schema_key="buyer-offer", source="buyer-offer-unknown")
    assert any(
        item.keyword == "additionalProperties" and "/competitorRate" in item.path
        for item in violations
    ), [item.render() for item in violations]
