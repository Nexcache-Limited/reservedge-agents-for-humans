"""COMP-G1-06: preferences never appear on orchestration or buyer documents."""

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

PREFERENCE_KEYS = ("preferences", "preferenceHistory")

DOCUMENTS = (
    ("orchestration-intent", "OrchestrationIntent", "orchestration_intent"),
    ("conversation", "Conversation", "conversation"),
    ("booking-task", "BookingTask", "booking_task"),
    ("buyer-offer", "BuyerOffer", "buyer_offer"),
    ("purchase-intent", "PurchaseIntent", "purchase_intent"),
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


def _additional_property_errors(
    schema: dict[str, object], document: dict[str, object]
) -> list[str]:
    found: list[str] = []
    for error in _validator(schema).iter_errors(document):
        if error.validator == "additionalProperties":
            found.append(error.message)
    return found


def _generated_model(module_name: str, export: str) -> Any:
    module = __import__(f"itaa_contracts_generated.{module_name}", fromlist=[export])
    return getattr(module, export)


def _model_for(stem: str, export: str, module_name: str) -> Any:
    if stem == "purchase-intent":
        return PurchaseIntent
    return _generated_model(module_name, export)


def test_preference_keys_are_not_declared_on_phase1_documents() -> None:
    missing: list[str] = []
    for stem, _export, _module in DOCUMENTS:
        path = SCHEMA_DIR / f"{stem}.schema.json"
        if not path.is_file():
            missing.append(stem)
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        declared = set(_walk_property_names(schema))
        for key in PREFERENCE_KEYS:
            assert key not in declared
    assert not missing, f"missing Phase 1 schemas: {missing}"


def test_preferences_rejected_as_additional_properties() -> None:
    missing: list[str] = []
    for stem, export, module_name in DOCUMENTS:
        path = SCHEMA_DIR / f"{stem}.schema.json"
        if not path.is_file():
            missing.append(stem)
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        document = _valid_fixture(stem)
        tainted = {**document, "preferences": {"covered": "preferred"}}
        errors = _additional_property_errors(schema, tainted)
        assert errors, f"{stem} must reject preferences via additionalProperties"
        assert any("preferences" in message for message in errors)

        model = _model_for(stem, export, module_name)
        try:
            model.model_validate(tainted)
        except ValidationError as exc:
            assert "preferences" in str(exc)
        else:
            raise AssertionError(f"{export} accepted preferences")
    assert not missing, f"missing Phase 1 schemas: {missing}"


def test_preference_history_rejected_as_additional_properties() -> None:
    missing: list[str] = []
    for stem, export, module_name in DOCUMENTS:
        path = SCHEMA_DIR / f"{stem}.schema.json"
        if not path.is_file():
            missing.append(stem)
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        document = _valid_fixture(stem)
        tainted = {**document, "preferenceHistory": [{"key": "covered"}]}
        errors = _additional_property_errors(schema, tainted)
        assert errors, f"{stem} must reject preferenceHistory via additionalProperties"
        assert any("preferenceHistory" in message for message in errors)

        model = _model_for(stem, export, module_name)
        try:
            model.model_validate(tainted)
        except ValidationError as exc:
            assert "preferenceHistory" in str(exc)
        else:
            raise AssertionError(f"{export} accepted preferenceHistory")
    assert not missing, f"missing Phase 1 schemas: {missing}"


def test_existing_purchase_intent_preference_invalid_fixture_still_rejects() -> None:
    leftover = validate_invalid_fixture_case(
        {
            "file": "purchase-intent-preferences.json",
            "schema": "purchase-intent",
            "expectedPath": "/preferenceHistory",
            "expectedKeyword": "additionalProperties",
        }
    )
    assert leftover == []
    payload = load_json(CONTRACTS / "fixtures/invalid/purchase-intent-preferences.json")
    violations = validate_instance(
        payload, schema_key="purchase-intent", source="purchase-intent-preferences.json"
    )
    assert any(item.keyword == "additionalProperties" for item in violations)
