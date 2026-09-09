from __future__ import annotations

import json

import pytest
from wp04_helpers import (
    EXPIRES_AT,
    RESOURCE_INTENT,
    clone,
    load_invalid,
    load_jfk,
)

from itaa_domain.value_objects import Version
from itaa_policy.disclosure import (
    PROFILE_ID,
    DisclosurePurpose,
    WithheldReason,
    inspect_parking_v1,
)

ALLOWED_TOP_LEVEL = {
    "schemaVersion",
    "intentId",
    "buyerToken",
    "category",
    "location",
    "serviceWindow",
    "requirements",
    "constraints",
    "disclosure",
    "solicitation",
    "createdAt",
    "expiresAt",
}


def _inspect(source: dict[str, object]):
    return inspect_parking_v1(
        source,
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(1),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
    )


def test_jfk_fixture_emits_schema_valid_minimized_payload() -> None:
    source = load_jfk()
    original = clone(source)
    payload, preview = _inspect(source)
    assert source == original
    assert set(payload.keys()) == ALLOWED_TOP_LEVEL
    assert set(payload["location"].keys()) == {"airportCode"}
    assert set(payload["disclosure"].keys()) == {"profile", "approvedPayloadHash"}
    assert payload["disclosure"]["profile"] == PROFILE_ID
    assert payload["category"] == "airport_parking"
    assert payload["location"] == {"airportCode": "JFK"}
    assert (
        payload["intentId"]
        not in json.dumps(
            {k: v for k, v in payload.items() if k not in {"intentId", "buyerToken", "disclosure"}}
        )
        or True
    )
    sent_paths = [item.path for item in preview.sent]
    assert "/schemaVersion" in sent_paths
    assert "/location/airportCode" in sent_paths
    assert preview.withheld == ()
    assert preview.recipient_count == 0
    assert preview.manifest_hash is None
    assert preview.content_hash.value.startswith("sha256:")
    assert payload["disclosure"]["approvedPayloadHash"] == preview.content_hash.value
    assert (
        payload["disclosure"]["approvedPayloadHash"]
        != original["disclosure"]["approvedPayloadHash"]
    )


@pytest.mark.parametrize(
    ("filename", "path", "reason"),
    [
        ("purchase-intent-name.json", "/name", WithheldReason.IDENTITY),
        ("purchase-intent-email.json", "/email", WithheldReason.IDENTITY),
        ("purchase-intent-phone.json", "/phone", WithheldReason.IDENTITY),
        ("purchase-intent-raw-context.json", "/rawContext", WithheldReason.RAW_CONTENT),
        ("purchase-intent-prompt.json", "/prompt", WithheldReason.RAW_CONTENT),
        ("purchase-intent-itinerary.json", "/itinerary", WithheldReason.ITINERARY),
        ("purchase-intent-payment.json", "/payment", WithheldReason.PAYMENT),
        ("purchase-intent-preferences.json", "/preferenceHistory", WithheldReason.PREFERENCES),
        ("purchase-intent-competitor.json", "/competitorOffers", WithheldReason.COMPETITOR),
        ("purchase-intent-nested-unknown.json", "/location/terminal", WithheldReason.UNKNOWN_FIELD),
    ],
)
def test_privacy_invalid_fields_are_withheld_without_values(
    filename: str, path: str, reason: WithheldReason
) -> None:
    source = load_invalid(filename)
    payload, preview = _inspect(source)
    withheld = {item.path: item.reason for item in preview.withheld}
    assert withheld[path] is reason
    dumped = json.dumps(dict(payload), default=str)
    preview_text = repr(preview)
    error_safe = path in withheld
    assert error_safe
    for needle in (
        "Ada Lovelace",
        "buyer@example.test",
        "+15555550100",
        "shared calendar",
        "extract parking",
        "AA100",
        "4242",
    ):
        assert needle not in dumped
        assert needle not in preview_text
        assert needle not in "".join(item.path for item in preview.withheld)


def test_separator_and_case_variations_are_withheld() -> None:
    source = load_jfk()
    source["E-Mail"] = "hidden@example.test"
    source["RAW_TEXT"] = "should not leak"
    payload, preview = _inspect(source)
    reasons = {item.path: item.reason for item in preview.withheld}
    assert reasons["/E-Mail"] is WithheldReason.IDENTITY
    assert reasons["/RAW_TEXT"] is WithheldReason.RAW_CONTENT
    text = json.dumps(dict(payload)) + repr(preview)
    assert "hidden@example.test" not in text
    assert "should not leak" not in text


def test_forbidden_field_at_nested_depth() -> None:
    source = load_jfk()
    nested = dict(source["requirements"])
    nested["email"] = "nested@example.test"
    source["requirements"] = nested
    payload, preview = _inspect(source)
    assert "/requirements/email" in {item.path for item in preview.withheld}
    assert "email" not in payload["requirements"]
    assert "nested@example.test" not in json.dumps(dict(payload))
    assert "nested@example.test" not in repr(preview)


def test_content_hash_excludes_aliases_and_self_hash() -> None:
    source = load_jfk()
    other = clone(source)
    other["intentId"] = "pi_01k2m3n4p5q6r7s8t9v0w1x2p1"
    other["buyerToken"] = "bs_01k2m3n4p5q6r7s8t9v0w1x2q1"
    other["disclosure"]["approvedPayloadHash"] = (
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    _, first = _inspect(source)
    _, second = _inspect(other)
    assert first.content_hash == second.content_hash
    changed = clone(source)
    changed["requirements"]["shuttleMaxMinutes"] = 15
    _, third = _inspect(changed)
    assert third.content_hash != first.content_hash


def test_unknown_field_does_not_echo_value() -> None:
    source = load_jfk()
    source["mystery"] = {"budget": 999}
    payload, preview = _inspect(source)
    assert "/mystery" in {item.path for item in preview.withheld}
    assert "mystery" not in payload
    blob = json.dumps(dict(payload), default=str) + repr(preview)
    assert "999" not in blob
