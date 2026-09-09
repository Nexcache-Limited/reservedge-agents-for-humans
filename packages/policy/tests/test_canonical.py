from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import pytest

from itaa_policy.canonical import (
    LOCKED_SEPARATORS,
    canonicalize,
    hash_canonical,
)
from itaa_policy.errors import PolicyError

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
KNOWN_VECTOR = b'{"a":1}'
KNOWN_HASHES = {
    "itaa.requirement.confirmation.v1": (
        "sha256:d911ae9926bc3785faf0d22f5009884c2f7bb3ab79a0546c0bb4d5ccc20335bd"
    ),
    "itaa.disclosure.content.v1": (
        "sha256:929433496f15040c85cda03b51292d90190b2964706fcd50bdd51f086c6d134d"
    ),
    "itaa.supplier.envelope.v1": (
        "sha256:d8a33489b8bc9d5f617a4749649d8206a1222d33f512c0d1c38dfea3b1ad631a"
    ),
    "itaa.disclosure.manifest.v1": (
        "sha256:fb8e31ed4ec19cfc79a5c78b31119272a56ebdda50e84f18b99ba96d9090b159"
    ),
    "itaa.offer.terms.v1": (
        "sha256:b31c1fcca2a71e6a62156264f41205528be30ebeb6598aa04f283b6838a2f62a"
    ),
    "itaa.transaction.authorization.v1": (
        "sha256:5c89cf35a6972a5de32f117b593840c74d3065e1e687f3c5e4108a48d261cb96"
    ),
    "itaa.idempotency.request.v1": (
        "sha256:5277fbd39ab21891f2c4bec9f70743bf6a350dd034d6978e0829dec4249d2d80"
    ),
    "itaa.audit.event.v1": (
        "sha256:b6fc73dc4efdafe665ad5f7b664f1432f1875311e0cdf19fd7b9967ee4a4d202"
    ),
    "itaa.ranking.decision.v1": (
        "sha256:9ec771fc4d73904052d5f49aec4b652913fc5480167813e8b9afd2e511879648"
    ),
}


def test_reordered_object_keys_are_identical() -> None:
    left = canonicalize({"b": 1, "a": 2})
    right = canonicalize({"a": 2, "b": 1})
    assert left == right == GOLDEN_DIR.joinpath("reordered.json").read_bytes()


def test_nested_arrays_preserve_order() -> None:
    value = {"z": {"b": 1, "a": [3, 1]}, "m": True, "n": None}
    assert canonicalize(value) == GOLDEN_DIR.joinpath("nested.json").read_bytes()
    changed = {"z": {"b": 1, "a": [1, 3]}, "m": True, "n": None}
    assert canonicalize(changed) != canonicalize(value)


def test_control_characters_and_unicode() -> None:
    assert canonicalize({"x": "a\nb\t"}) == GOLDEN_DIR.joinpath("controls.json").read_bytes()
    assert (
        canonicalize({"city": "München", "ok": True})
        == GOLDEN_DIR.joinpath("unicode.json").read_bytes()
    )
    assert canonicalize({"emoji": "😀"}) == GOLDEN_DIR.joinpath("supplementary.json").read_bytes()


def test_locked_separators_have_stable_known_digests() -> None:
    assert set(LOCKED_SEPARATORS) == set(KNOWN_HASHES)
    hashes = {
        separator: hash_canonical(separator, {"a": 1}).value for separator in LOCKED_SEPARATORS
    }
    assert hashes == KNOWN_HASHES
    assert len(set(hashes.values())) == len(hashes)


def test_material_change_alters_digest() -> None:
    first = hash_canonical("itaa.disclosure.content.v1", {"a": 1})
    second = hash_canonical("itaa.disclosure.content.v1", {"a": 2})
    assert first != second


@pytest.mark.parametrize(
    "value",
    [1.5, float("nan"), float("inf"), b"x", {1}, datetime(2026, 1, 1, tzinfo=UTC), object()],
)
def test_unsupported_json_values_fail(value: object) -> None:
    with pytest.raises(PolicyError) as captured:
        canonicalize(value)
    assert "Ada" not in str(captured.value)
    assert "@" not in str(captured.value)


def test_enum_dataclass_and_non_string_keys_fail() -> None:
    class Kind(StrEnum):
        A = "A"

    @dataclass
    class Box:
        value: int

    with pytest.raises(PolicyError, match="enum_forbidden"):
        canonicalize(Kind.A)
    with pytest.raises(PolicyError, match="dataclass_forbidden"):
        canonicalize(Box(1))
    with pytest.raises(PolicyError, match="non_string_key"):
        canonicalize({1: "x"})
    from itaa_policy.canonical import content_hash_material

    with pytest.raises(PolicyError, match="non_string_key"):
        content_hash_material({1: "x"})
    with pytest.raises(PolicyError, match="non_string_key"):
        content_hash_material({"disclosure": {True: "x"}})


def test_unpaired_surrogate_and_out_of_range_integer_fail() -> None:
    with pytest.raises(PolicyError, match="unpaired_surrogate"):
        canonicalize({"x": "\ud800"})
    with pytest.raises(PolicyError, match="integer_out_of_range"):
        canonicalize(9007199254740992)


def test_tuple_array_is_accepted() -> None:
    assert canonicalize(("a", 1, False)) == canonicalize(["a", 1, False]) == b'["a",1,false]'
