from __future__ import annotations

import pytest

from itaa_contracts_generated import (
    Acceptance,
    CounterOffer,
    Offer,
    PurchaseIntent,
    TransactionAuthorization,
)
from itaa_validate_contracts.fixtures import (
    VALID_FILES,
    load_invalid_cases,
    validate_invalid_fixture_case,
    validate_valid_fixtures,
)
from itaa_validate_contracts.paths import contracts_root
from itaa_validate_contracts.schema import check_registry, load_json, validate_schema_documents

CONTRACTS = contracts_root()


@pytest.mark.contract
def test_registry_and_meta_schema() -> None:
    assert check_registry() == []
    assert validate_schema_documents() == []


@pytest.mark.contract
def test_valid_fixtures_pass() -> None:
    assert validate_valid_fixtures() == []


@pytest.mark.contract
def test_generated_models_import_and_parse_valid_fixtures() -> None:
    mapping = {
        "purchase-intent": PurchaseIntent,
        "offer": Offer,
        "counter-offer": CounterOffer,
        "acceptance": Acceptance,
        "transaction-authorization": TransactionAuthorization,
    }
    valid = CONTRACTS / "fixtures" / "valid"
    for schema_key, names in VALID_FILES.items():
        model = mapping[schema_key]
        for name in names:
            payload = load_json(valid / name)
            model.model_validate(payload)


@pytest.mark.contract
def test_invalid_cases_fail_at_expected_path() -> None:
    failures = []
    for case in load_invalid_cases():
        leftover = validate_invalid_fixture_case(case)
        if leftover:
            failures.extend(item.render() for item in leftover)
    assert failures == []


@pytest.mark.contract
def test_jfk_airport_code_is_accepted() -> None:
    payload = load_json(CONTRACTS / "fixtures" / "valid" / "purchase-intent-jfk.json")
    assert payload["location"]["airportCode"] == "JFK"
    PurchaseIntent.model_validate(payload)


@pytest.mark.contract
def test_privacy_invalid_fixtures_cover_required_identifiers() -> None:
    names = {case["file"] for case in load_invalid_cases()}
    required = {
        "purchase-intent-email.json",
        "purchase-intent-name.json",
        "purchase-intent-phone.json",
        "purchase-intent-raw-context.json",
        "purchase-intent-itinerary.json",
        "purchase-intent-payment.json",
        "purchase-intent-preferences.json",
        "purchase-intent-prompt.json",
        "purchase-intent-competitor.json",
        "purchase-intent-nested-unknown.json",
    }
    assert required <= names


@pytest.mark.contract
def test_canonical_schemas_declare_draft_2020_12() -> None:
    schema_dir = CONTRACTS / "schemas" / "v1"
    for path in sorted(schema_dir.glob("*.schema.json")):
        payload = load_json(path)
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["$id"].startswith("https://contracts.itaa.invalid/v1/")


@pytest.mark.contract
def test_invalid_catalog_files_exist() -> None:
    invalid = CONTRACTS / "fixtures" / "invalid"
    for case in load_invalid_cases():
        assert (invalid / case["file"]).is_file()


@pytest.mark.contract
def test_three_simulated_offers_are_independent() -> None:
    offers = [
        load_json(CONTRACTS / "fixtures" / "valid" / name)
        for name in (
            "offer-parkdirect.json",
            "offer-skyshield.json",
            "offer-terminalflex.json",
        )
    ]
    tokens = {offer["supplierToken"] for offer in offers}
    ids = {offer["offerId"] for offer in offers}
    assert len(tokens) == 3
    assert len(ids) == 3
    assert all(offer["simulation"] is True for offer in offers)
