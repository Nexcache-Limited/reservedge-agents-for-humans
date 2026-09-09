"""COMP-G1-06: unknown fields are rejected on new orchestration documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema.validators import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages/contracts"
SCHEMA_DIR = CONTRACTS / "schemas/v1"
VALID = CONTRACTS / "fixtures/valid"

NEW_DOCUMENTS = (
    ("orchestration-intent", "OrchestrationIntent", "orchestration_intent"),
    ("conversation", "Conversation", "conversation"),
    ("intent-plan", "IntentPlan", "intent_plan"),
    ("booking-task", "BookingTask", "booking_task"),
    ("cost-ledger", "CostLedger", "cost_ledger"),
    ("buyer-offer", "BuyerOffer", "buyer_offer"),
)

UNKNOWN = "unknownCompG106Field"


def _schema_path(stem: str) -> Path:
    path = SCHEMA_DIR / f"{stem}.schema.json"
    assert path.is_file(), f"missing Phase 1 schema {path.relative_to(ROOT)}"
    return path


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


def _generated_model(module_name: str, export: str) -> Any:
    module = __import__(f"itaa_contracts_generated.{module_name}", fromlist=[export])
    return getattr(module, export)


def _object_nodes(node: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            found.append(node)
        for child in node.values():
            found.extend(_object_nodes(child))
    elif isinstance(node, list):
        for child in node:
            found.extend(_object_nodes(child))
    return found


def test_new_comp_g1_06_documents_declare_additional_properties_false() -> None:
    for stem, _export, _module in NEW_DOCUMENTS:
        schema = json.loads(_schema_path(stem).read_text(encoding="utf-8"))
        assert schema.get("additionalProperties") is False


def test_unknown_fields_rejected_on_new_comp_g1_06_documents() -> None:
    for stem, export, module_name in NEW_DOCUMENTS:
        schema = json.loads(_schema_path(stem).read_text(encoding="utf-8"))
        document = _valid_fixture(stem)
        tainted = {**document, UNKNOWN: "must-not-round-trip"}
        errors = [
            error
            for error in _validator(schema).iter_errors(tainted)
            if error.validator == "additionalProperties"
        ]
        assert errors, f"{stem} must reject unknown field {UNKNOWN}"
        assert any(UNKNOWN in error.message for error in errors)
        model = _generated_model(module_name, export)
        try:
            model.model_validate(tainted)
        except ValidationError as exc:
            assert UNKNOWN in str(exc)
        else:
            raise AssertionError(f"{export} accepted unknown field {UNKNOWN}")


def _resolve_object(schema: dict[str, object], node: object) -> dict[str, object]:
    assert isinstance(node, dict)
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        defs = schema["$defs"]
        assert isinstance(defs, dict)
        resolved = defs[ref.rsplit("/", 1)[-1]]
        assert isinstance(resolved, dict)
        return resolved
    return node


def test_conversation_event_and_fact_objects_forbid_unknown_fields() -> None:
    schema = json.loads(_schema_path("conversation").read_text(encoding="utf-8"))
    properties = schema["properties"]
    assert isinstance(properties, dict)
    for name in ("events", "facts"):
        items_holder = properties[name]
        assert isinstance(items_holder, dict)
        items = _resolve_object(schema, items_holder["items"])
        assert items.get("additionalProperties") is False

    document = _valid_fixture("conversation")
    events = document["events"]
    facts = document["facts"]
    assert isinstance(events, list) and events
    assert isinstance(facts, list) and facts
    assert isinstance(events[0], dict)
    assert isinstance(facts[0], dict)

    event_tainted = {**document, "events": [{**events[0], UNKNOWN: True}]}
    fact_tainted = {**document, "facts": [{**facts[0], UNKNOWN: True}]}
    for tainted in (event_tainted, fact_tainted):
        errors = [
            error
            for error in _validator(schema).iter_errors(tainted)
            if error.validator == "additionalProperties"
        ]
        assert errors
        assert any(UNKNOWN in error.message for error in errors)


def test_nested_signed_objects_on_new_documents_forbid_additional_properties() -> None:
    for stem, _export, _module in NEW_DOCUMENTS:
        schema = json.loads(_schema_path(stem).read_text(encoding="utf-8"))
        for node in _object_nodes(schema):
            if node.get("type") != "object":
                continue
            extra = node.get("additionalProperties")
            if extra is False:
                continue
            if isinstance(extra, dict):
                continue
            raise AssertionError(f"{stem} object node must set additionalProperties false")
