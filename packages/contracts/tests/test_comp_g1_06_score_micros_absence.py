from __future__ import annotations

import json
from pathlib import Path

import pytest

from itaa_validate_contracts.paths import contracts_root
from itaa_validate_contracts.schema import load_json

CONTRACTS = contracts_root()
SCHEMA = CONTRACTS / "schemas" / "v1" / "buyer-offer.schema.json"
FIXTURE = CONTRACTS / "fixtures" / "valid" / "buyer-offer.json"
GENERATED_PYTHON = (
    CONTRACTS / "generated" / "python" / "itaa_contracts_generated" / "buyer_offer.py"
)
GENERATED_TYPESCRIPT = CONTRACTS / "generated" / "typescript" / "index.ts"


def _text_contains_score_micros(path: Path) -> bool:
    return "scoreMicros" in path.read_text(encoding="utf-8")


@pytest.mark.contract
def test_buyer_offer_schema_has_no_score_micros() -> None:
    schema = load_json(SCHEMA)
    dumped = json.dumps(schema)
    assert "scoreMicros" not in dumped
    assert "scoreMicros" not in schema.get("properties", {})
    assert "scoreMicros" not in schema.get("required", [])


@pytest.mark.contract
def test_buyer_offer_fixture_has_no_score_micros() -> None:
    payload = load_json(FIXTURE)
    assert "scoreMicros" not in payload
    assert not _text_contains_score_micros(FIXTURE)


@pytest.mark.contract
def test_generated_buyer_offer_has_no_score_micros_if_present() -> None:
    if GENERATED_PYTHON.is_file():
        assert not _text_contains_score_micros(GENERATED_PYTHON)
    if GENERATED_TYPESCRIPT.is_file():
        assert "scoreMicros" not in GENERATED_TYPESCRIPT.read_text(encoding="utf-8")
