"""COMP-G1-06: parent Intent, conversation, and sibling fields stay off supplier/buyer docs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from jsonschema.validators import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from itaa_contracts_generated.purchase_intent import PurchaseIntent
from itaa_validate_contracts.fixtures import validate_invalid_fixture_case
from itaa_validate_contracts.schema import load_json, validate_instance

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages/contracts"
SCHEMA_DIR = CONTRACTS / "schemas/v1"
VALID = CONTRACTS / "fixtures/valid"

PARENT_OR_SIBLING_FIELDS = (
    "conversation",
    "conversationId",
    "conversationEvents",
    "parentIntent",
    "parentIntentId",
    "orchestrationIntent",
    "orchestrationIntentId",
    "siblingTasks",
    "siblingTaskIds",
    "plan",
    "planId",
    "competitorOffers",
    "competitorOfferIds",
)

TARGETS = (
    ("purchase-intent", "PurchaseIntent", "purchase_intent"),
    ("buyer-offer", "BuyerOffer", "buyer_offer"),
)


def _valid_fixture(stem: str) -> dict[str, object]:
    matches = sorted(VALID.glob(f"{stem}*.json"))
    assert matches, f"missing valid fixture for {stem}"
    payload = json.loads(matches[0].read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _referencing_registry() -> Registry:
    resources: list[tuple[str, Resource[object]]] = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append(
            (contents["$id"], Resource.from_contents(contents, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def _validator(schema: dict[str, object]) -> Draft202012Validator:
    return Draft202012Validator(schema, registry=_referencing_registry())


def _walk_property_names(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            yield from properties
            for child in properties.values():
                yield from _walk_property_names(child)
        for key, child in node.items():
            if key != "properties":
                yield from _walk_property_names(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk_property_names(child)


def _generated_model(module_name: str, export: str) -> Any:
    if export == "PurchaseIntent":
        return PurchaseIntent
    module = __import__(f"itaa_contracts_generated.{module_name}", fromlist=[export])
    return getattr(module, export)


def test_parent_conversation_sibling_fields_are_not_declared() -> None:
    missing: list[str] = []
    for stem, _export, _module in TARGETS:
        path = SCHEMA_DIR / f"{stem}.schema.json"
        if not path.is_file():
            missing.append(stem)
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        declared = set(_walk_property_names(schema))
        for field in PARENT_OR_SIBLING_FIELDS:
            assert field not in declared
    assert not missing, f"missing Phase 1 schemas: {missing}"


def test_parent_conversation_sibling_fields_rejected_on_purchase_intent_and_buyer_offer() -> None:
    missing: list[str] = []
    for stem, export, module_name in TARGETS:
        path = SCHEMA_DIR / f"{stem}.schema.json"
        if not path.is_file():
            missing.append(stem)
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        base = _valid_fixture(stem)
        model = _generated_model(module_name, export)
        for field in PARENT_OR_SIBLING_FIELDS:
            tainted = {**base, field: "leak"}
            errors = [
                error
                for error in _validator(schema).iter_errors(tainted)
                if error.validator == "additionalProperties"
            ]
            assert errors, f"{stem} must reject {field} via additionalProperties"
            assert any(field in error.message for error in errors)
            try:
                model.model_validate(tainted)
            except ValidationError as exc:
                assert field in str(exc)
            else:
                raise AssertionError(f"{export} accepted parent/sibling field {field}")
    assert not missing, f"missing Phase 1 schemas: {missing}"


def test_existing_purchase_intent_competitor_invalid_fixture_still_rejects() -> None:
    leftover = validate_invalid_fixture_case(
        {
            "file": "purchase-intent-competitor.json",
            "schema": "purchase-intent",
            "expectedPath": "/competitorOffers",
            "expectedKeyword": "additionalProperties",
        }
    )
    assert leftover == []
    payload = load_json(CONTRACTS / "fixtures/invalid/purchase-intent-competitor.json")
    violations = validate_instance(
        payload, schema_key="purchase-intent", source="purchase-intent-competitor.json"
    )
    assert any(item.keyword == "additionalProperties" for item in violations)
