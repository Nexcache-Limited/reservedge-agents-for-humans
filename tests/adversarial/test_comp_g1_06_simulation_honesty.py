"""COMP-G1-06: simulation BuyerOffer never claims an inventory hold."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from itaa_validate_contracts.invariants import check_invariants

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages/contracts"
SCHEMA_PATH = CONTRACTS / "schemas/v1/buyer-offer.schema.json"
VALID = CONTRACTS / "fixtures/valid"


def _schema() -> dict[str, object]:
    assert SCHEMA_PATH.is_file(), f"missing Phase 1 schema {SCHEMA_PATH.relative_to(ROOT)}"
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _valid_buyer_offers() -> list[dict[str, object]]:
    matches = sorted(VALID.glob("buyer-offer*.json"))
    assert matches, "missing valid BuyerOffer fixture"
    payloads: list[dict[str, object]] = []
    for path in matches:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        payloads.append(payload)
    return payloads


def _referencing_registry() -> Registry:
    resources: list[tuple[str, Resource[object]]] = []
    for path in sorted((CONTRACTS / "schemas/v1").glob("*.schema.json")):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append(
            (contents["$id"], Resource.from_contents(contents, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def _validator(schema: dict[str, object]) -> Draft202012Validator:
    return Draft202012Validator(schema, registry=_referencing_registry())


def _required(schema: dict[str, object]) -> set[str]:
    raw = schema.get("required", [])
    assert isinstance(raw, list)
    return {str(item) for item in raw}


def _properties(schema: dict[str, object]) -> dict[str, object]:
    raw = schema["properties"]
    assert isinstance(raw, dict)
    return raw


def _rejected(document: dict[str, object], schema: dict[str, object]) -> bool:
    schema_errors = list(_validator(schema).iter_errors(document))
    invariant_errors = check_invariants(document, schema_key="buyer-offer", source="adversarial")
    model_rejected = False
    try:
        from itaa_contracts_generated.buyer_offer import BuyerOffer

        BuyerOffer.model_validate(document)
    except Exception:
        model_rejected = True
    return bool(schema_errors or invariant_errors or model_rejected)


def test_simulation_buyer_offer_inventory_is_not_held() -> None:
    schema = _schema()
    properties = _properties(schema)
    assert "inventory" in properties
    for payload in _valid_buyer_offers():
        assert payload["simulation"] is True
        assert payload["inventory"] == "not_held"
        assert payload.get("transactionResult") in {"simulated", "authorized_simulated"}


def test_simulation_buyer_offer_omits_inventory_held_until() -> None:
    schema = _schema()
    required = _required(schema)
    assert "inventoryHeldUntil" not in required
    for payload in _valid_buyer_offers():
        assert "inventoryHeldUntil" not in payload


def test_valid_until_does_not_require_inventory_held_until() -> None:
    schema = _schema()
    required = _required(schema)
    assert "validUntil" in required
    assert "inventoryHeldUntil" not in required
    properties = _properties(schema)
    assert "validUntil" in properties
    for payload in _valid_buyer_offers():
        assert payload["validUntil"]
        assert "inventoryHeldUntil" not in payload
        errors = list(_validator(schema).iter_errors(payload))
        assert errors == []


def test_inventory_held_until_rejected_when_simulation_true() -> None:
    schema = _schema()
    for payload in _valid_buyer_offers():
        tainted = {
            **payload,
            "simulation": True,
            "inventory": "not_held",
            "inventoryHeldUntil": "2026-08-21T16:00:00Z",
        }
        assert _rejected(tainted, schema), (
            "simulation BuyerOffer must reject inventoryHeldUntil even when validUntil is present"
        )


def test_held_until_inventory_rejected_when_simulation_true() -> None:
    schema = _schema()
    for payload in _valid_buyer_offers():
        tainted = {**payload, "simulation": True, "inventory": "held_until"}
        assert _rejected(tainted, schema), (
            "simulation BuyerOffer inventory must stay not_held; held_until is dishonest"
        )
