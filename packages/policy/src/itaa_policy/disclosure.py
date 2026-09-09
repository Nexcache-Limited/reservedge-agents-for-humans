"""Parking v1 disclosure firewall, sent/withheld preview, and content hashing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import BuyerToken, IntentId
from itaa_domain.value_objects import (
    AirportCode,
    PayloadHash,
    Version,
    format_utc,
    parse_utc,
    require_exact_enum,
    require_shuttle_minutes,
    require_utc,
)
from itaa_policy.canonical import (
    SEPARATOR_DISCLOSURE_CONTENT,
    content_hash_material,
    hash_canonical,
)
from itaa_policy.errors import PolicyError

PROFILE_ID: Final[str] = "parking_v1"
PROFILE_VERSION: Final[str] = "1.0"
SCHEMA_VERSION: Final[str] = "1.0"
MAX_RECIPIENTS: Final[int] = 3

VEHICLE_CLASSES: Final[frozenset[str]] = frozenset({"standard", "compact", "suv", "oversized"})
COVERED_VALUES: Final[frozenset[str]] = frozenset({"none", "preferred", "required"})
ACCESSIBILITY_VALUES: Final[frozenset[str]] = frozenset({"step_free", "wheelchair", "ev_charging"})


class DisclosurePurpose(StrEnum):
    PURCHASE_INTENT_DISPATCH = "purchase_intent_dispatch"


class WithheldReason(StrEnum):
    IDENTITY = "withheld_identity"
    RAW_CONTENT = "withheld_raw_content"
    ITINERARY = "withheld_itinerary"
    PAYMENT = "withheld_payment"
    PREFERENCES = "withheld_preferences"
    BUDGET = "withheld_budget"
    COMPETITOR = "withheld_competitor"
    CREDENTIALS = "withheld_credentials"
    UNKNOWN_FIELD = "denied_unknown_field"


_EXACT_FORBIDDEN: Final[dict[str, WithheldReason]] = {
    "name": WithheldReason.IDENTITY,
    "fullname": WithheldReason.IDENTITY,
    "firstname": WithheldReason.IDENTITY,
    "lastname": WithheldReason.IDENTITY,
    "email": WithheldReason.IDENTITY,
    "phone": WithheldReason.IDENTITY,
    "address": WithheldReason.IDENTITY,
    "postal": WithheldReason.IDENTITY,
    "street": WithheldReason.IDENTITY,
    "prompt": WithheldReason.RAW_CONTENT,
    "notes": WithheldReason.RAW_CONTENT,
    "message": WithheldReason.RAW_CONTENT,
    "messages": WithheldReason.RAW_CONTENT,
    "freetext": WithheldReason.RAW_CONTENT,
    "card": WithheldReason.PAYMENT,
    "bank": WithheldReason.PAYMENT,
    "secret": WithheldReason.CREDENTIALS,
}

_SUBSTRING_FORBIDDEN: Final[tuple[tuple[str, WithheldReason], ...]] = (
    ("rawcontext", WithheldReason.RAW_CONTENT),
    ("rawtext", WithheldReason.RAW_CONTENT),
    ("rawsource", WithheldReason.RAW_CONTENT),
    ("sharepayload", WithheldReason.RAW_CONTENT),
    ("itinerary", WithheldReason.ITINERARY),
    ("flight", WithheldReason.ITINERARY),
    ("confirmation", WithheldReason.ITINERARY),
    ("companion", WithheldReason.ITINERARY),
    ("booking", WithheldReason.ITINERARY),
    ("payment", WithheldReason.PAYMENT),
    ("wallet", WithheldReason.PAYMENT),
    ("billing", WithheldReason.PAYMENT),
    ("preferencehistory", WithheldReason.PREFERENCES),
    ("preferenceevidence", WithheldReason.PREFERENCES),
    ("buyerprofile", WithheldReason.PREFERENCES),
    ("willingnesstopay", WithheldReason.BUDGET),
    ("budget", WithheldReason.BUDGET),
    ("competitor", WithheldReason.COMPETITOR),
    ("otheroffer", WithheldReason.COMPETITOR),
    ("supplierpolicy", WithheldReason.COMPETITOR),
    ("credential", WithheldReason.CREDENTIALS),
    ("accesstoken", WithheldReason.CREDENTIALS),
    ("postaladdress", WithheldReason.IDENTITY),
    ("streetaddress", WithheldReason.IDENTITY),
)

_ALLOWED_TREE: Final[dict[str, object]] = {
    "schemaVersion": "leaf",
    "intentId": "leaf",
    "buyerToken": "leaf",
    "category": "leaf",
    "location": {"airportCode": "leaf"},
    "serviceWindow": {"start": "leaf", "end": "leaf"},
    "requirements": {
        "vehicleClass": "leaf",
        "covered": "leaf",
        "shuttleMaxMinutes": "leaf",
    },
    "constraints": {"currency": "leaf", "accessibility": "leaf"},
    "disclosure": {"profile": "leaf", "approvedPayloadHash": "leaf"},
    "solicitation": {"responseDeadline": "leaf", "counteroffersAllowed": "leaf"},
    "createdAt": "leaf",
    "expiresAt": "leaf",
}


def _normalize_name(name: str) -> str:
    return "".join(char for char in name.lower() if char.isalnum())


def classify_field_name(name: str) -> WithheldReason | None:
    token = _normalize_name(name)
    if not token:
        return WithheldReason.UNKNOWN_FIELD
    if token in _EXACT_FORBIDDEN:
        return _EXACT_FORBIDDEN[token]
    for stem, reason in _SUBSTRING_FORBIDDEN:
        if stem in token:
            return reason
    return None


@dataclass(frozen=True, slots=True)
class WithheldEntry:
    path: str
    reason: WithheldReason


@dataclass(frozen=True, slots=True)
class SentField:
    path: str
    value: object


@dataclass(frozen=True, slots=True)
class DisclosurePreview:
    profile_id: str
    profile_version: str
    sent: tuple[SentField, ...]
    withheld: tuple[WithheldEntry, ...]
    content_hash: PayloadHash
    intent_resource_id: IntentId
    intent_resource_version: Version
    purpose: DisclosurePurpose
    expires_at: str
    recipient_count: int
    manifest_hash: PayloadHash | None

    def __post_init__(self) -> None:
        require_exact_enum(self.purpose, DisclosurePurpose, "purpose")
        object.__setattr__(self, "sent", tuple(sorted(self.sent, key=lambda item: item.path)))
        object.__setattr__(
            self, "withheld", tuple(sorted(self.withheld, key=lambda item: item.path))
        )


def inspect_parking_v1(
    source: Mapping[str, object],
    *,
    intent_resource_id: IntentId,
    intent_resource_version: Version,
    purpose: DisclosurePurpose,
    expires_at: datetime,
    recipient_count: int = 0,
    manifest_hash: PayloadHash | None = None,
) -> tuple[MappingProxyType[str, object], DisclosurePreview]:
    require_exact_enum(purpose, DisclosurePurpose, "purpose")
    if purpose is not DisclosurePurpose.PURCHASE_INTENT_DISPATCH:
        raise PolicyError("purpose", "unsupported")
    if not isinstance(source, Mapping):
        raise PolicyError("source", "must_be_object")
    if not isinstance(intent_resource_id, IntentId):
        raise PolicyError("intent_resource_id", "invalid_opaque_syntax")
    expiry = require_utc(expires_at, "expires_at")
    if recipient_count < 0 or recipient_count > MAX_RECIPIENTS:
        raise PolicyError("recipient_count", "out_of_range")
    if recipient_count and manifest_hash is None:
        raise PolicyError("manifest_hash", "required")
    if recipient_count == 0 and manifest_hash is not None:
        raise PolicyError("manifest_hash", "must_be_absent")

    extracted: dict[str, object] = {}
    withheld: list[WithheldEntry] = []
    _walk(source, "", _ALLOWED_TREE, extracted, withheld)
    payload = _validate_minimized(extracted)
    material = content_hash_material(payload)
    digest = hash_canonical(SEPARATOR_DISCLOSURE_CONTENT, material)
    disclosure = payload["disclosure"]
    if not isinstance(disclosure, dict):
        raise PolicyError("/disclosure", "must_be_object")
    disclosure["approvedPayloadHash"] = digest.to_primitive()
    payload_expiry = payload["expiresAt"]
    if not isinstance(payload_expiry, str):
        raise PolicyError("/expiresAt", "invalid_value")
    try:
        supplied = format_utc(expiry)
    except DomainInvariantError as exc:
        raise PolicyError("expires_at", exc.code) from exc
    if supplied != payload_expiry:
        raise PolicyError("expires_at", "mismatch")
    sent = _sent_fields(payload)
    preview = DisclosurePreview(
        profile_id=PROFILE_ID,
        profile_version=PROFILE_VERSION,
        sent=sent,
        withheld=tuple(withheld),
        content_hash=digest,
        intent_resource_id=intent_resource_id,
        intent_resource_version=intent_resource_version,
        purpose=purpose,
        expires_at=payload_expiry,
        recipient_count=recipient_count,
        manifest_hash=manifest_hash,
    )
    return MappingProxyType(_copy_mapping(payload)), preview


def _walk(
    value: object,
    path: str,
    allowed: object,
    output: dict[str, object],
    withheld: list[WithheldEntry],
) -> None:
    if not isinstance(value, Mapping):
        if path:
            raise PolicyError(path, "must_be_object")
        raise PolicyError("source", "must_be_object")
    for key, item in value.items():
        if not isinstance(key, str) or isinstance(key, bool):
            raise PolicyError(path or "source", "non_string_key")
        child = f"{path}/{key}"
        forbidden = classify_field_name(key)
        if forbidden is not None:
            withheld.append(WithheldEntry(child, forbidden))
            continue
        if not isinstance(allowed, Mapping) or key not in allowed:
            withheld.append(WithheldEntry(child, WithheldReason.UNKNOWN_FIELD))
            continue
        next_allowed = allowed[key]
        if next_allowed == "leaf":
            output[key] = item
            continue
        nested: dict[str, object] = {}
        output[key] = nested
        _walk(item, child, next_allowed, nested, withheld)


def _validate_minimized(payload: dict[str, object]) -> dict[str, object]:
    schema_version = payload.get("schemaVersion")
    if schema_version != SCHEMA_VERSION:
        raise PolicyError("/schemaVersion", "invalid_value")
    category = payload.get("category")
    if category != "airport_parking":
        raise PolicyError("/category", "invalid_value")
    intent_id = _require_id(payload.get("intentId"), IntentId, "/intentId")
    buyer_token = _require_id(payload.get("buyerToken"), BuyerToken, "/buyerToken")
    location = _require_object(payload.get("location"), "/location")
    airport = location.get("airportCode")
    if not isinstance(airport, str):
        raise PolicyError("/location/airportCode", "invalid_value")
    AirportCode(airport)
    window = _require_object(payload.get("serviceWindow"), "/serviceWindow")
    start = _require_utc_string(window.get("start"), "/serviceWindow/start")
    end = _require_utc_string(window.get("end"), "/serviceWindow/end")
    if parse_utc(end, "/serviceWindow/end") <= parse_utc(start, "/serviceWindow/start"):
        raise PolicyError("/serviceWindow", "end_must_follow_start")
    requirements = _require_object(payload.get("requirements"), "/requirements")
    vehicle = requirements.get("vehicleClass")
    if vehicle not in VEHICLE_CLASSES:
        raise PolicyError("/requirements/vehicleClass", "invalid_value")
    covered = requirements.get("covered")
    if covered not in COVERED_VALUES:
        raise PolicyError("/requirements/covered", "invalid_value")
    shuttle = requirements.get("shuttleMaxMinutes")
    require_shuttle_minutes(shuttle, "/requirements/shuttleMaxMinutes")
    constraints = _require_object(payload.get("constraints"), "/constraints")
    currency = constraints.get("currency")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise PolicyError("/constraints/currency", "invalid_value")
    if currency != currency.upper():
        raise PolicyError("/constraints/currency", "invalid_value")
    accessibility = constraints.get("accessibility")
    if not isinstance(accessibility, Sequence) or isinstance(accessibility, str | bytes):
        raise PolicyError("/constraints/accessibility", "invalid_value")
    values = list(accessibility)
    if any(item not in ACCESSIBILITY_VALUES for item in values):
        raise PolicyError("/constraints/accessibility", "invalid_value")
    if len(set(values)) != len(values):
        raise PolicyError("/constraints/accessibility", "duplicate_values")
    disclosure = _require_object(payload.get("disclosure"), "/disclosure")
    if disclosure.get("profile") != PROFILE_ID:
        raise PolicyError("/disclosure/profile", "invalid_value")
    solicitation = _require_object(payload.get("solicitation"), "/solicitation")
    deadline = _require_utc_string(
        solicitation.get("responseDeadline"),
        "/solicitation/responseDeadline",
    )
    allowed = solicitation.get("counteroffersAllowed")
    if type(allowed) is not bool:
        raise PolicyError("/solicitation/counteroffersAllowed", "invalid_value")
    created = _require_utc_string(payload.get("createdAt"), "/createdAt")
    expires = _require_utc_string(payload.get("expiresAt"), "/expiresAt")
    if parse_utc(expires, "/expiresAt") <= parse_utc(created, "/createdAt"):
        raise PolicyError("/expiresAt", "must_follow_created")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "intentId": intent_id,
        "buyerToken": buyer_token,
        "category": "airport_parking",
        "location": {"airportCode": airport},
        "serviceWindow": {"start": start, "end": end},
        "requirements": {
            "vehicleClass": vehicle,
            "covered": covered,
            "shuttleMaxMinutes": shuttle,
        },
        "constraints": {"currency": currency, "accessibility": list(values)},
        "disclosure": {
            "profile": PROFILE_ID,
            "approvedPayloadHash": disclosure.get("approvedPayloadHash"),
        },
        "solicitation": {
            "responseDeadline": deadline,
            "counteroffersAllowed": allowed,
        },
        "createdAt": created,
        "expiresAt": expires,
    }


def _require_object(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PolicyError(path, "required")
    return value


def _require_id(value: object, constructor: type[object], path: str) -> str:
    if not isinstance(value, str):
        raise PolicyError(path, "invalid_value")
    try:
        parsed = constructor(value)  # type: ignore[call-arg]
    except Exception as exc:
        raise PolicyError(path, "invalid_value") from exc
    to_primitive = getattr(parsed, "to_primitive", None)
    if callable(to_primitive):
        result = to_primitive()
        if isinstance(result, str):
            return result
    raise PolicyError(path, "invalid_value")


def _require_utc_string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise PolicyError(path, "invalid_value")
    parse_utc(value, path)
    return value


def _sent_fields(payload: Mapping[str, object]) -> tuple[SentField, ...]:
    sent: list[SentField] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, Mapping):
            for key, item in node.items():
                walk(item, f"{path}/{key}")
            return
        sent.append(SentField(path, node))

    walk(payload, "")
    return tuple(sent)


def _copy_mapping(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or isinstance(key, bool):
            raise PolicyError("payload", "non_string_key")
        if isinstance(item, Mapping):
            result[key] = _copy_mapping(item)
        elif isinstance(item, list):
            copied_list: list[object] = []
            for entry in item:
                if isinstance(entry, Mapping):
                    copied_list.append(_copy_mapping(entry))
                else:
                    copied_list.append(entry)
            result[key] = copied_list
        else:
            result[key] = item
    return result
