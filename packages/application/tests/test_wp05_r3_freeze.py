from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType

import pytest
from wp04_helpers import OCCURRED_AT
from wp05_helpers import collected_offer, fixture_policy, scoped_fixture

from itaa_application.errors import ApplicationError
from itaa_application.freeze import freeze_payload, thaw_payload
from itaa_application.offer_boundary import CollectedSupplierResponse
from itaa_application.supplier_port import ClosedReason, TerminalKind


def test_non_string_and_colliding_keys_are_rejected() -> None:
    with pytest.raises(ApplicationError, match="payload: invalid_key") as captured:
        freeze_payload({1: "a", "1": "b"})
    assert "1" not in str(captured.value)
    assert "alice@" not in str(captured.value)
    with pytest.raises(ApplicationError, match="payload: invalid_key"):
        freeze_payload({"nested": {True: "x"}})
    with pytest.raises(ApplicationError, match="payload: invalid_key"):
        freeze_payload({"nested": {(1, 2): "x"}})
    with pytest.raises(ApplicationError, match="payload: invalid_key"):
        freeze_payload({"nested": {b"k": "x"}})


def test_sets_and_frozensets_are_rejected() -> None:
    with pytest.raises(ApplicationError, match="payload: unsupported_container"):
        freeze_payload({"tags": {"a", "b"}})
    with pytest.raises(ApplicationError, match="payload: unsupported_container"):
        freeze_payload({"tags": frozenset({"a"})})


def test_unsupported_types_and_list_order_are_canonical() -> None:
    with pytest.raises(ApplicationError, match="payload: unsupported_type"):
        freeze_payload({"blob": b"secret"})
    frozen = freeze_payload({"items": ["c", "a", "b"], "ok": True, "n": 1, "z": None})
    assert isinstance(frozen, MappingProxyType)
    assert frozen["items"] == ("c", "a", "b")
    thawed = thaw_payload(frozen)
    assert thawed == {"items": ["c", "a", "b"], "ok": True, "n": 1, "z": None}
    thawed["items"].append("x")
    thawed["ok"] = False
    assert frozen["items"] == ("c", "a", "b")
    assert frozen["ok"] is True
    again = thaw_payload(frozen)
    assert again["items"] == ["c", "a", "b"]
    assert again is not thawed


def test_valid_contract_payload_is_deeply_immutable() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    payload["service"]["addOns"] = ["ev_charging"]
    frozen = freeze_payload(payload)
    assert isinstance(frozen, MappingProxyType)
    with pytest.raises(TypeError):
        frozen["simulation"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        frozen["price"]["feesMinor"] = 0  # type: ignore[index]
    original_fees = payload["price"]["feesMinor"]
    payload["price"]["feesMinor"] = 999
    assert frozen["price"]["feesMinor"] == original_fees
    copy = thaw_payload(frozen)
    copy["price"]["feesMinor"] = 1
    assert frozen["price"]["feesMinor"] == original_fees


def test_repeating_mapping_keys_fail_closed() -> None:
    class Repeating(Mapping[str, int]):
        def __iter__(self) -> Iterator[str]:
            yield "a"
            yield "a"

        def __len__(self) -> int:
            return 2

        def __getitem__(self, key: str) -> int:
            return 1

    with pytest.raises(ApplicationError, match="payload: duplicate_key"):
        freeze_payload(Repeating())
    with pytest.raises(ApplicationError, match="payload: invalid_key"):
        thaw_payload(MappingProxyType({1: "a"}))  # type: ignore[dict-item]


def test_collected_response_rejects_integer_keys() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    with pytest.raises(ApplicationError, match="payload: invalid_key"):
        CollectedSupplierResponse.seal(
            supplier_token=binding.supplier_token,
            invitation=binding.invitation,
            correlation_id=binding.correlation_id,
            kind=TerminalKind.OFFER,
            received_at=OCCURRED_AT,
            payload={1: "a", "1": "b"},
            binding=binding,
        )
    declined = CollectedSupplierResponse.seal(
        supplier_token=binding.supplier_token,
        invitation=binding.invitation,
        correlation_id=binding.correlation_id,
        kind=TerminalKind.DECLINED,
        received_at=OCCURRED_AT,
        reason=ClosedReason.INSUFFICIENT_CAPACITY,
        binding=binding,
    )
    assert declined.payload is None
    _ = fixture_policy(binding, payload)
    _ = collected_offer(payload, binding)
