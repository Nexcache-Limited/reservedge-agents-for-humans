from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from itaa_validate_contracts.invariants import check_invariants
from itaa_validate_contracts.paths import contracts_root
from itaa_validate_contracts.schema import load_json, validate_instance

CONTRACTS = contracts_root()
LEDGER = CONTRACTS / "fixtures" / "valid" / "cost-ledger.json"

LEDGER_BUCKETS = (
    "authorizedSimulatedMinor",
    "authorizedLiveMinor",
    "bookingPendingMinor",
    "confirmedBookingMinor",
    "selectedNotAuthorizedMinor",
    "estimatedMinor",
    "expiredExcludedMinor",
    "taxesFeesMinor",
    "depositsHoldsMinor",
    "payableNowMinor",
    "payableLaterMinor",
)

SIMULATION_ZERO_BUCKETS = (
    "confirmedBookingMinor",
    "authorizedLiveMinor",
    "bookingPendingMinor",
    "depositsHoldsMinor",
    "payableNowMinor",
)


def _assert_valid(document: dict[str, Any], *, source: str) -> None:
    assert validate_instance(document, schema_key="cost-ledger", source=source) == []
    assert check_invariants(document, schema_key="cost-ledger", source=source) == []


@pytest.mark.contract
def test_valid_mixed_currency_ledger_without_fx_validates() -> None:
    payload = load_json(LEDGER)
    assert isinstance(payload, dict)
    currencies = {row["currency"] for row in payload["rows"]}
    assert currencies == {"USD", "GBP"}
    assert "fx" not in payload
    assert "totalMinor" not in payload
    _assert_valid(payload, source="cost-ledger.json")


@pytest.mark.contract
def test_ledger_rows_declare_required_buckets() -> None:
    payload = load_json(LEDGER)
    assert payload["rows"]
    for row in payload["rows"]:
        for bucket in LEDGER_BUCKETS:
            assert bucket in row
            assert isinstance(row[bucket], int)


@pytest.mark.contract
def test_simulation_zeros_live_and_confirmed_buckets() -> None:
    payload = load_json(LEDGER)
    assert payload["simulation"] is True
    for row in payload["rows"]:
        for bucket in SIMULATION_ZERO_BUCKETS:
            assert row[bucket] == 0


@pytest.mark.contract
def test_ledger_rejects_silent_combined_total() -> None:
    payload = deepcopy(load_json(LEDGER))
    payload["totalMinor"] = 25800
    violations = validate_instance(
        payload, schema_key="cost-ledger", source="cost-ledger-silent-sum"
    )
    assert any(
        item.keyword == "additionalProperties" and "/totalMinor" in item.path for item in violations
    ), [item.render() for item in violations]


@pytest.mark.contract
def test_ledger_rejects_confirmed_booking_in_simulation() -> None:
    payload = deepcopy(load_json(LEDGER))
    payload["rows"][0]["confirmedBookingMinor"] = 16900
    violations = validate_instance(
        payload, schema_key="cost-ledger", source="cost-ledger-confirmed-booking-simulation"
    )
    assert any(
        item.keyword in {"const", "invariant"} and "confirmedBookingMinor" in item.path
        for item in violations
    ), [item.render() for item in violations]


@pytest.mark.contract
def test_ledger_rejects_unknown_field() -> None:
    payload = deepcopy(load_json(LEDGER))
    payload["grandTotalMinor"] = 1
    violations = validate_instance(payload, schema_key="cost-ledger", source="cost-ledger-unknown")
    assert any(
        item.keyword == "additionalProperties" and "/grandTotalMinor" in item.path
        for item in violations
    ), [item.render() for item in violations]
