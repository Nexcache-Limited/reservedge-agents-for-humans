"""COMP-G1-06: scoreMicros is forbidden on buyer surfaces; retained internally."""

from __future__ import annotations

import json
from pathlib import Path

from itaa_application.session_models import BuyerSessionState, BuyerSnapshot, RankedOfferView

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages/contracts"
RANKING = ROOT / "packages/ranking"
OPENAPI = ROOT / "apps/api/openapi/itaa-v1.json"
API_SCHEMAS = ROOT / "apps/api/src/itaa_api/schemas.py"
BUYER_OFFER_SCHEMA = CONTRACTS / "schemas/v1/buyer-offer.schema.json"
GENERATED_PY = CONTRACTS / "generated/python/itaa_contracts_generated/buyer_offer.py"
GENERATED_TS = CONTRACTS / "generated/typescript/index.ts"
SCORE = "scoreMicros"


def _load(path: Path) -> object:
    assert path.is_file(), f"missing Phase 1 artifact {path.relative_to(ROOT)}"
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def _valid_buyer_offer_fixtures() -> list[Path]:
    found = sorted((CONTRACTS / "fixtures/valid").glob("buyer-offer*.json"))
    assert found, "missing valid BuyerOffer fixture"
    return found


def _buyer_offer_ts_block(source: str) -> str:
    for marker in ("export interface BuyerOffer", "export type BuyerOffer"):
        if marker not in source:
            continue
        start = source.index(marker)
        nxt = source.find("\nexport ", start + len(marker))
        return source[start:] if nxt == -1 else source[start:nxt]
    raise AssertionError("generated TypeScript must export BuyerOffer")


def _serialized_buyer_offers() -> dict[str, object]:
    snapshot = BuyerSnapshot(
        environment="local_simulation",
        simulation=True,
        intent_id="pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
        state=BuyerSessionState.OFFERS_RANKED,
        airport="JFK",
        category="airport_parking",
        created_at="2026-08-20T15:00:00Z",
        updated_at="2026-08-20T16:00:00Z",
        expires_at="2026-08-22T15:00:00Z",
        market_evidence=(),
        supplier_outcomes=(),
        offers=(
            RankedOfferView(
                offer_id="of_01k2m3n4p5q6r7s8t9v0w1x2a2",
                supplier_token="sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
                version=1,
                rank=1,
                score_micros=671000,
                total_minor=14800,
                currency="USD",
                recommended=True,
                simulation=True,
                issued_at="2026-08-20T15:00:00Z",
                valid_from="2026-08-20T16:00:00Z",
                valid_until="2026-08-21T16:00:00Z",
                terms_hash="sha256:" + ("a" * 64),
                evidence=(("rate_card", "rate.jfk.skyshield"),),
            ),
        ),
        recommended_offer_id="of_01k2m3n4p5q6r7s8t9v0w1x2a2",
        downside=None,
        acceptance=None,
        transaction=None,
    )
    return snapshot.to_primitive()


def test_buyer_offer_schema_contains_no_score_micros() -> None:
    schema = _load(BUYER_OFFER_SCHEMA)
    blob = json.dumps(schema)
    assert SCORE not in blob
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert SCORE not in properties
    assert "score_micros" not in properties


def test_generated_buyer_offer_types_contain_no_score_micros() -> None:
    from itaa_contracts_generated.buyer_offer import BuyerOffer

    python_source = _load(GENERATED_PY)
    assert isinstance(python_source, str)
    assert SCORE not in python_source
    assert SCORE not in BuyerOffer.model_fields
    assert SCORE not in json.dumps(BuyerOffer.model_json_schema())

    ts = _load(GENERATED_TS)
    assert isinstance(ts, str)
    assert SCORE not in _buyer_offer_ts_block(ts)


def test_buyer_offer_fixtures_contain_no_score_micros() -> None:
    for path in _valid_buyer_offer_fixtures():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert SCORE not in json.dumps(payload)
        assert SCORE not in payload


def test_serialized_buyer_json_contains_no_score_micros() -> None:
    primitive = _serialized_buyer_offers()
    blob = json.dumps(primitive)
    assert SCORE not in blob
    offers = primitive["offers"]
    assert isinstance(offers, list)
    assert offers
    for item in offers:
        assert isinstance(item, dict)
        assert SCORE not in item
        assert "termsHash" in item
        assert item["termsHash"].startswith("sha256:")


def test_openapi_and_api_buyer_offer_contain_no_score_micros() -> None:
    openapi = _load(OPENAPI)
    assert isinstance(openapi, dict)
    components = openapi["components"]["schemas"]
    buyer_keys = [name for name in components if name.replace("_", "").lower() == "buyeroffer"]
    assert buyer_keys, "OpenAPI must export a named BuyerOffer component"
    for name in buyer_keys:
        assert SCORE not in json.dumps(components[name])
    assert SCORE not in json.dumps(openapi)

    api_schemas = _load(API_SCHEMAS)
    assert isinstance(api_schemas, str)
    assert "class BuyerOffer" in api_schemas
    assert SCORE not in api_schemas


def test_existing_supplier_offer_surfaces_still_omit_score_micros() -> None:
    offer_schema = json.loads(
        (CONTRACTS / "schemas/v1/offer.schema.json").read_text(encoding="utf-8")
    )
    assert SCORE not in json.dumps(offer_schema)
    from itaa_contracts_generated.offer import Offer

    assert SCORE not in Offer.model_fields
    for path in (CONTRACTS / "fixtures/valid").glob("offer-*.json"):
        assert SCORE not in path.read_text(encoding="utf-8")


def test_internal_ranker_tests_and_files_retain_score_micros_and_locked_vector() -> None:
    texts: list[str] = []
    for path in RANKING.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix not in {".py", ".md"}:
            continue
        texts.append(path.read_text(encoding="utf-8"))
    blob = "\n".join(texts)
    assert SCORE in blob
    assert "score_micros" in blob
    collapsed = blob.replace("_", "").replace(",", "")
    assert "671000" in collapsed
    assert "660000" in collapsed
    assert "535000" in collapsed

    tests_blob = "\n".join(
        path.read_text(encoding="utf-8") for path in (RANKING / "tests").glob("test_*.py")
    )
    assert "671_000" in tests_blob or "671000" in tests_blob
    assert "660_000" in tests_blob or "660000" in tests_blob
    assert "535_000" in tests_blob or "535000" in tests_blob
    assert "score_micros" in tests_blob
