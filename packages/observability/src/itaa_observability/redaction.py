"""Redaction helpers that never echo rejected values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

FORBIDDEN_NAME_STEMS = (
    "name",
    "email",
    "phone",
    "address",
    "rawcontext",
    "rawtext",
    "itinerary",
    "flight",
    "confirmation",
    "companion",
    "payment",
    "card",
    "bank",
    "prompt",
    "preferencehistory",
    "preferenceevidence",
    "competitor",
    "otheroffer",
    "credential",
    "secret",
    "accesstoken",
)

_EXACT_ONLY = frozenset({"name", "card", "bank"})


def normalize_field_name(name: str) -> str:
    return "".join(char for char in name.lower() if char.isalnum())


def is_forbidden_field_name(name: str) -> bool:
    token = normalize_field_name(name)
    if token in _EXACT_ONLY or token in {"email", "phone", "prompt"}:
        return True
    return any(stem in token for stem in FORBIDDEN_NAME_STEMS if stem not in _EXACT_ONLY)


def collect_forbidden_keys(value: object) -> tuple[str, ...]:
    found: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, Mapping):
            for key, item in node.items():
                child = f"{path}/{key}" if path else str(key)
                if isinstance(key, str) and is_forbidden_field_name(key):
                    found.append(child)
                walk(item, child)
            return
        if isinstance(node, Sequence) and not isinstance(node, str | bytes):
            for index, item in enumerate(node):
                walk(item, f"{path}/{index}")

    walk(value, "")
    return tuple(found)
