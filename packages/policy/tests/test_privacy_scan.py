from __future__ import annotations

from collections.abc import Mapping, Sequence

from wp04_helpers import (
    CREATED_AT,
    EXPIRES_AT,
    INVITATIONS,
    READ_WRITE,
    RESOURCE_INTENT,
    SCOPED_BUYERS,
    SCOPED_INTENTS,
    SUPPLIERS,
    load_invalid,
    load_jfk,
)

from itaa_domain.value_objects import Version
from itaa_observability.redaction import collect_forbidden_keys
from itaa_policy.disclosure import DisclosurePurpose, inspect_parking_v1
from itaa_policy.envelopes import RecipientAssignment, bind_solicitation

FORBIDDEN_VALUES = (
    "Ada Lovelace",
    "buyer@example.test",
    "+15555550100",
    "shared calendar screenshot text",
    "extract parking from this email",
    "AA100",
    "4242",
)


def _walk_strings(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.extend(_walk_strings(key))
            found.extend(_walk_strings(item))
        return found
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            found.extend(_walk_strings(item))
        return found
    if isinstance(value, str):
        found.append(value)
    return found


def test_recursive_forbidden_scan_on_previews_and_envelopes() -> None:
    payload, preview = inspect_parking_v1(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(1),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
    )
    assert collect_forbidden_keys(dict(payload)) == ()
    texts = _walk_strings(payload) + _walk_strings(preview)
    for needle in FORBIDDEN_VALUES:
        assert all(needle not in item for item in texts)
    for filename in (
        "purchase-intent-name.json",
        "purchase-intent-email.json",
        "purchase-intent-phone.json",
        "purchase-intent-raw-context.json",
        "purchase-intent-prompt.json",
        "purchase-intent-itinerary.json",
        "purchase-intent-payment.json",
        "purchase-intent-preferences.json",
        "purchase-intent-competitor.json",
    ):
        filtered, previewed = inspect_parking_v1(
            load_invalid(filename),
            intent_resource_id=RESOURCE_INTENT,
            intent_resource_version=Version(1),
            purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
            expires_at=EXPIRES_AT,
        )
        blob = " ".join(_walk_strings(filtered) + _walk_strings(previewed) + [repr(previewed)])
        for needle in FORBIDDEN_VALUES:
            assert needle not in blob
        assert collect_forbidden_keys(dict(filtered)) == ()
    binding = bind_solicitation(
        load_jfk(),
        intent_resource_id=RESOURCE_INTENT,
        intent_resource_version=Version(1),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=EXPIRES_AT,
        recipients=tuple(
            RecipientAssignment(
                supplier_token=SUPPLIERS[index],
                invitation=INVITATIONS[index],
                scoped_intent_id=SCOPED_INTENTS[index],
                scoped_buyer_token=SCOPED_BUYERS[index],
                valid_from=CREATED_AT,
                valid_until=EXPIRES_AT,
                capabilities=READ_WRITE,
            )
            for index in range(3)
        ),
    )
    for envelope in binding.envelopes:
        assert collect_forbidden_keys(envelope.payload_dict()) == ()
