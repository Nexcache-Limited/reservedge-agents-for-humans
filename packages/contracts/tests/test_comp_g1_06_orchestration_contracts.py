from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from itaa_validate_contracts.invariants import check_invariants
from itaa_validate_contracts.paths import contracts_root
from itaa_validate_contracts.schema import load_json, validate_instance

CONTRACTS = contracts_root()
VALID = CONTRACTS / "fixtures" / "valid"

ORCHESTRATION_FIXTURES: tuple[tuple[str, str], ...] = (
    ("orchestration-intent", "orchestration-intent.json"),
    ("conversation", "conversation.json"),
    ("intent-plan", "intent-plan.json"),
    ("booking-task", "booking-task.json"),
    ("cost-ledger", "cost-ledger.json"),
    ("buyer-offer", "buyer-offer.json"),
)

ID_PREFIXES = {
    "intentId": "oi_",
    "taskId": "bt_",
    "eventId": "ce_",
    "factId": "cf_",
    "planId": "pl_",
    "ledgerId": "ld_",
}


def _assert_valid(document: dict[str, Any], *, schema_key: str, source: str) -> None:
    assert validate_instance(document, schema_key=schema_key, source=source) == []
    assert check_invariants(document, schema_key=schema_key, source=source) == []


def _assert_additional_property(
    document: dict[str, Any], *, schema_key: str, source: str, field: str
) -> None:
    violations = validate_instance(document, schema_key=schema_key, source=source)
    assert any(
        item.keyword == "additionalProperties" and f"/{field}" in item.path for item in violations
    ), [item.render() for item in violations]


@pytest.mark.contract
def test_six_new_valid_fixtures_validate() -> None:
    for schema_key, name in ORCHESTRATION_FIXTURES:
        payload = load_json(VALID / name)
        assert isinstance(payload, dict)
        _assert_valid(payload, schema_key=schema_key, source=name)


@pytest.mark.contract
def test_new_id_prefixes_are_present() -> None:
    intent = load_json(VALID / "orchestration-intent.json")
    conversation = load_json(VALID / "conversation.json")
    plan = load_json(VALID / "intent-plan.json")
    task = load_json(VALID / "booking-task.json")
    ledger = load_json(VALID / "cost-ledger.json")
    assert intent["intentId"].startswith(ID_PREFIXES["intentId"])
    assert intent["planId"].startswith(ID_PREFIXES["planId"])
    assert intent["ledgerId"].startswith(ID_PREFIXES["ledgerId"])
    assert conversation["intentId"].startswith(ID_PREFIXES["intentId"])
    assert conversation["events"][0]["eventId"].startswith(ID_PREFIXES["eventId"])
    assert conversation["facts"][0]["factId"].startswith(ID_PREFIXES["factId"])
    assert plan["planId"].startswith(ID_PREFIXES["planId"])
    assert all(task_id.startswith(ID_PREFIXES["taskId"]) for task_id in plan["taskIds"])
    assert task["taskId"].startswith(ID_PREFIXES["taskId"])
    assert ledger["ledgerId"].startswith(ID_PREFIXES["ledgerId"])


@pytest.mark.contract
def test_orchestration_intent_rejects_preferences() -> None:
    payload = deepcopy(load_json(VALID / "orchestration-intent.json"))
    payload["preferences"] = {"covered": "preferred"}
    _assert_additional_property(
        payload,
        schema_key="orchestration-intent",
        source="orchestration-intent-preferences",
        field="preferences",
    )


@pytest.mark.contract
def test_booking_task_rejects_sibling_tasks() -> None:
    payload = deepcopy(load_json(VALID / "booking-task.json"))
    payload["siblingTasks"] = ["bt_01k2m3n4p5q6r7s8t9v0w1x2p5"]
    _assert_additional_property(
        payload,
        schema_key="booking-task",
        source="booking-task-sibling-tasks",
        field="siblingTasks",
    )


@pytest.mark.contract
def test_conversation_rejects_preference_history() -> None:
    payload = deepcopy(load_json(VALID / "conversation.json"))
    payload["preferenceHistory"] = [{"key": "covered"}]
    _assert_additional_property(
        payload,
        schema_key="conversation",
        source="conversation-preference-history",
        field="preferenceHistory",
    )
