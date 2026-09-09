"""Deep-freeze nested JSON-like mappings. No I/O and no key coercion."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from itaa_application.errors import ApplicationError

_ATOMS = (type(None), bool, int, float, str)


def freeze_payload(value: object) -> object:
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key in value:
            if type(key) is not str:
                raise ApplicationError("payload", "invalid_key")
            if key in frozen:
                raise ApplicationError("payload", "duplicate_key")
            frozen[key] = freeze_payload(value[key])
        return MappingProxyType(frozen)
    if type(value) is list or type(value) is tuple:
        return tuple(freeze_payload(item) for item in value)
    if type(value) is set or type(value) is frozenset:
        raise ApplicationError("payload", "unsupported_container")
    if type(value) in _ATOMS:
        return value
    raise ApplicationError("payload", "unsupported_type")


def thaw_payload(value: object) -> object:
    if isinstance(value, Mapping):
        thawed: dict[str, object] = {}
        for key in value:
            if type(key) is not str:
                raise ApplicationError("payload", "invalid_key")
            thawed[key] = thaw_payload(value[key])
        return thawed
    if type(value) is tuple:
        return [thaw_payload(item) for item in value]
    return value
