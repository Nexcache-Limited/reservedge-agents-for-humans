"""ITAA Canonical JSON v1 and context-separated SHA-256 bindings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Final

from itaa_domain.value_objects import JS_SAFE_MAX, PayloadHash
from itaa_policy.errors import PolicyError

JS_SAFE_MIN: Final[int] = -JS_SAFE_MAX

SEPARATOR_REQUIREMENT_CONFIRMATION: Final[str] = "itaa.requirement.confirmation.v1"
SEPARATOR_DISCLOSURE_CONTENT: Final[str] = "itaa.disclosure.content.v1"
SEPARATOR_SUPPLIER_ENVELOPE: Final[str] = "itaa.supplier.envelope.v1"
SEPARATOR_DISCLOSURE_MANIFEST: Final[str] = "itaa.disclosure.manifest.v1"
SEPARATOR_OFFER_TERMS: Final[str] = "itaa.offer.terms.v1"
SEPARATOR_TRANSACTION_AUTHORIZATION: Final[str] = "itaa.transaction.authorization.v1"
SEPARATOR_IDEMPOTENCY_REQUEST: Final[str] = "itaa.idempotency.request.v1"
SEPARATOR_AUDIT_EVENT: Final[str] = "itaa.audit.event.v1"
SEPARATOR_RANKING_DECISION: Final[str] = "itaa.ranking.decision.v1"

LOCKED_SEPARATORS: Final[tuple[str, ...]] = (
    SEPARATOR_REQUIREMENT_CONFIRMATION,
    SEPARATOR_DISCLOSURE_CONTENT,
    SEPARATOR_SUPPLIER_ENVELOPE,
    SEPARATOR_DISCLOSURE_MANIFEST,
    SEPARATOR_OFFER_TERMS,
    SEPARATOR_TRANSACTION_AUTHORIZATION,
    SEPARATOR_IDEMPOTENCY_REQUEST,
    SEPARATOR_AUDIT_EVENT,
    SEPARATOR_RANKING_DECISION,
)

CONTENT_HASH_EXCLUDED_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/intentId",
        "/buyerToken",
        "/disclosure/approvedPayloadHash",
    }
)


def canonicalize(value: object) -> bytes:
    """Return UTF-8 canonical JSON bytes with no BOM and no insignificant whitespace."""

    normalized = _normalize(value, "value")
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return text.encode("utf-8")


def bind_hash(separator: str, canonical_bytes: bytes) -> PayloadHash:
    if not isinstance(separator, str) or not separator.isascii() or not separator:
        raise PolicyError("domain_separator", "must_be_ascii")
    if separator not in LOCKED_SEPARATORS:
        raise PolicyError("domain_separator", "unsupported")
    if not isinstance(canonical_bytes, bytes) or isinstance(canonical_bytes, bytearray):
        raise PolicyError("canonical_bytes", "must_be_bytes")
    digest = hashlib.sha256(separator.encode("ascii") + b"\x00" + canonical_bytes).hexdigest()
    return PayloadHash(f"sha256:{digest}")


def hash_canonical(separator: str, value: object) -> PayloadHash:
    return bind_hash(separator, canonicalize(value))


def content_hash_material(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a new mapping with scoped aliases and the self-hash field removed."""

    if not isinstance(payload, Mapping):
        raise PolicyError("payload", "must_be_object")
    omitted = _omit_paths(payload, CONTENT_HASH_EXCLUDED_PATHS, "")
    if not isinstance(omitted, dict):
        raise PolicyError("payload", "must_be_object")
    return omitted


def _omit_paths(
    value: object,
    excluded: frozenset[str],
    path: str,
) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or isinstance(key, bool):
                raise PolicyError("payload", "non_string_key")
            child = f"{path}/{key}"
            if child in excluded:
                continue
            omitted = _omit_paths(item, excluded, child)
            if omitted is _EMPTY_OBJECT:
                continue
            result[key] = omitted
        if path == "/disclosure" and not result:
            return _EMPTY_OBJECT
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_omit_paths(item, excluded, path) for item in value]
    return value


class _Empty:
    pass


_EMPTY_OBJECT = _Empty()


def _normalize(value: object, field: str) -> object:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        raise PolicyError(field, "enum_forbidden")
    if isinstance(value, int) and not isinstance(value, bool):
        if value < JS_SAFE_MIN or value > JS_SAFE_MAX:
            raise PolicyError(field, "integer_out_of_range")
        return value
    if isinstance(value, str):
        _reject_surrogates(value, field)
        return value
    if isinstance(value, float):
        raise PolicyError(field, "float_forbidden")
    if isinstance(value, bytes | bytearray | memoryview):
        raise PolicyError(field, "bytes_forbidden")
    if isinstance(value, set | frozenset):
        raise PolicyError(field, "set_forbidden")
    if isinstance(value, datetime | date | time):
        raise PolicyError(field, "datetime_forbidden")
    if is_dataclass(value) and not isinstance(value, type):
        raise PolicyError(field, "dataclass_forbidden")
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or isinstance(key, bool):
                raise PolicyError(field, "non_string_key")
            _reject_surrogates(key, field)
            normalized[key] = _normalize(item, field)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_normalize(item, field) for item in value]
    raise PolicyError(field, "unsupported_type")


def _reject_surrogates(value: str, field: str) -> None:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise PolicyError(field, "unpaired_surrogate")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PolicyError(field, "unpaired_surrogate") from exc
