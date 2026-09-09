"""Validate committed contract fixtures against schemas and invariants."""

from __future__ import annotations

import json
from pathlib import Path

from itaa_validate_contracts.errors import ContractViolation
from itaa_validate_contracts.invariants import check_invariants
from itaa_validate_contracts.paths import contracts_root
from itaa_validate_contracts.schema import load_json, validate_instance

VALID_FILES = {
    "purchase-intent": ("purchase-intent-jfk.json",),
    "offer": (
        "offer-parkdirect.json",
        "offer-skyshield.json",
        "offer-terminalflex.json",
    ),
    "counter-offer": ("counter-offer.json",),
    "acceptance": ("acceptance.json",),
    "transaction-authorization": ("transaction-authorization.json",),
}


def validate_valid_fixtures(root: Path | None = None) -> list[ContractViolation]:
    contracts = contracts_root(root)
    valid_dir = contracts / "fixtures" / "valid"
    found: list[ContractViolation] = []
    for schema_key, names in VALID_FILES.items():
        for name in names:
            path = valid_dir / name
            document = load_json(path)
            source = path.relative_to(contracts).as_posix()
            found.extend(
                validate_instance(document, schema_key=schema_key, source=source, root=root)
            )
            if isinstance(document, dict):
                found.extend(check_invariants(document, schema_key=schema_key, source=source))
    return found


def load_invalid_cases(root: Path | None = None) -> list[dict[str, str]]:
    catalog = contracts_root(root) / "fixtures" / "invalid" / "cases.json"
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    return [dict(item) for item in payload]


def validate_invalid_fixture_case(
    case: dict[str, str], *, root: Path | None = None
) -> list[ContractViolation]:
    contracts = contracts_root(root)
    path = contracts / "fixtures" / "invalid" / case["file"]
    document = load_json(path)
    source = path.relative_to(contracts).as_posix()
    schema_key = case["schema"]
    schema_violations = validate_instance(document, schema_key=schema_key, source=source, root=root)
    invariant_violations = (
        check_invariants(document, schema_key=schema_key, source=source)
        if isinstance(document, dict)
        else []
    )
    combined = schema_violations + invariant_violations
    expected_path = case["expectedPath"]
    expected_keyword = case["expectedKeyword"]
    matched = [
        item
        for item in combined
        if expected_keyword == item.keyword
        and (expected_path in item.path or expected_path in item.message)
    ]
    if matched:
        return []
    if not combined:
        return [
            ContractViolation(
                schema_key=schema_key,
                source=source,
                path=expected_path,
                keyword="fixture",
                message=(
                    f"expected rejection {expected_keyword} at {expected_path}; document was valid"
                ),
            )
        ]
    detail = "; ".join(item.render() for item in combined)
    return [
        ContractViolation(
            schema_key=schema_key,
            source=source,
            path=expected_path,
            keyword="fixture",
            message=f"expected {expected_keyword} at {expected_path}; got: {detail}",
        )
    ]


def validate_invalid_fixtures(root: Path | None = None) -> list[ContractViolation]:
    found: list[ContractViolation] = []
    for case in load_invalid_cases(root):
        found.extend(validate_invalid_fixture_case(case, root=root))
    return found
