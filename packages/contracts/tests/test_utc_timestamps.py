from __future__ import annotations

import pytest

from itaa_validate_contracts.errors import ContractViolation
from itaa_validate_contracts.fixtures import validate_invalid_fixture_case
from itaa_validate_contracts.paths import contracts_root
from itaa_validate_contracts.schema import load_json, validate_instance

CONTRACTS = contracts_root()
VALID_INTENT = CONTRACTS / "fixtures" / "valid" / "purchase-intent-jfk.json"


def _created_at_errors(value: str) -> list[ContractViolation]:
    payload = load_json(VALID_INTENT)
    payload["createdAt"] = value
    return validate_instance(payload, schema_key="purchase-intent", source="utc-table/createdAt")


@pytest.mark.contract
@pytest.mark.parametrize(
    ("value", "expected_keyword"),
    [
        ("2026-13-01T00:00:00Z", "format"),
        ("2026-01-32T00:00:00Z", "format"),
        ("2026-01-01T24:00:00Z", "format"),
        ("2026-99-99T99:99:99Z", "format"),
        ("2025-02-29T00:00:00Z", "format"),
        ("2026-08-20T15:00:00+00:00", "pattern"),
    ],
)
def test_invalid_rfc3339_timestamps_are_rejected(value: str, expected_keyword: str) -> None:
    errors = _created_at_errors(value)
    assert any(item.path == "/createdAt" and item.keyword == expected_keyword for item in errors), [
        item.render() for item in errors
    ]


@pytest.mark.contract
@pytest.mark.parametrize(
    "value",
    [
        "2026-08-20T15:00:00Z",
        "2026-08-20T15:00:00.123Z",
        "2026-08-20T15:00:00.123456789Z",
        "2024-02-29T00:00:00Z",
    ],
)
def test_valid_canonical_z_timestamps_are_accepted(value: str) -> None:
    assert _created_at_errors(value) == []


@pytest.mark.contract
def test_counter_offer_impossible_proposed_valid_until_is_rejected() -> None:
    leftover = validate_invalid_fixture_case(
        {
            "file": "counter-offer-impossible-valid-until.json",
            "schema": "counter-offer",
            "expectedPath": "/proposedChanges/0/value",
            "expectedKeyword": "format",
        }
    )
    assert leftover == []
