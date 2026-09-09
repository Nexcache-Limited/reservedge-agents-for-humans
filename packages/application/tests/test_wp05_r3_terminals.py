from __future__ import annotations

from enum import StrEnum

import pytest
from test_wp05_solicitation import SpyPort, _collect, _collector, fake_ports
from wp04_helpers import INVITATIONS, OCCURRED_AT, SUPPLIERS
from wp05_helpers import CORRELATIONS

from itaa_application.errors import ApplicationError
from itaa_application.solicitation_service import IsolatedMailbox
from itaa_application.supplier_port import ClosedReason, SupplierTerminal, TerminalKind


class ForeignKind(StrEnum):
    OFFER = "OFFER"


def test_string_and_foreign_kind_fail_closed_without_echo() -> None:
    with pytest.raises(ApplicationError, match="kind: invalid_enum") as captured:
        SupplierTerminal(
            "OFFER",  # type: ignore[arg-type]
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            payload={"simulation": True},
        )
    assert "OFFER" not in str(captured.value)
    assert "alice@" not in str(captured.value)
    with pytest.raises(ApplicationError, match="kind: invalid_enum") as captured:
        SupplierTerminal(
            ForeignKind.OFFER,  # type: ignore[arg-type]
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            payload={"simulation": True},
        )
    assert "OFFER" not in str(captured.value)


def test_free_text_and_wrong_type_reason_fail_closed() -> None:
    with pytest.raises(ApplicationError, match="reason: invalid_enum") as captured:
        SupplierTerminal(
            TerminalKind.DECLINED,
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            "malformed",  # type: ignore[arg-type]
        )
    assert "malformed" not in str(captured.value)
    assert "alice@" not in str(captured.value)
    with pytest.raises(ApplicationError, match="reason: invalid_enum"):
        SupplierTerminal(
            TerminalKind.DECLINED,
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            1,  # type: ignore[arg-type]
        )


def test_wrong_type_identity_fields_fail_closed() -> None:
    with pytest.raises(ApplicationError, match="supplier_token: invalid_opaque_syntax") as captured:
        SupplierTerminal(
            TerminalKind.DECLINED,
            "sp_01k2m3n4p5q6r7s8t9v0w1x2b1",  # type: ignore[arg-type]
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            ClosedReason.INSUFFICIENT_CAPACITY,
        )
    assert "sp_" not in str(captured.value)
    with pytest.raises(ApplicationError, match="correlation_id: invalid_opaque_syntax"):
        SupplierTerminal(
            TerminalKind.DECLINED,
            SUPPLIERS[0],
            "cr_01k2m3n4p5q6r7s8t9v0w1x2m1",  # type: ignore[arg-type]
            INVITATIONS[0],
            OCCURRED_AT,
            ClosedReason.INSUFFICIENT_CAPACITY,
        )
    with pytest.raises(ApplicationError, match="invitation: required"):
        SupplierTerminal(
            TerminalKind.DECLINED,
            SUPPLIERS[0],
            CORRELATIONS[0],
            "iv_01k2m3n4p5q6r7s8t9v0w1x2j1",  # type: ignore[arg-type]
            OCCURRED_AT,
            ClosedReason.INSUFFICIENT_CAPACITY,
        )


def test_malformed_terminal_from_one_supplier_does_not_stop_others() -> None:
    collector, binding, _repo = _collector()

    class DuckTerminal:
        kind = "OFFER"
        supplier_token = SUPPLIERS[0]
        correlation_id = CORRELATIONS[0]
        invitation = INVITATIONS[0]
        completed_at = OCCURRED_AT
        reason = None
        payload = {"simulation": True, "email": "alice@example.com"}

        def attempt(self, request):
            return self

    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    spies[SUPPLIERS[0]] = SpyPort(DuckTerminal())  # type: ignore[arg-type]
    result = _collect(collector, binding, spies)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.INVALID
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER
    assert spies[SUPPLIERS[1]].calls == 1
    assert spies[SUPPLIERS[2]].calls == 1
    assert all(
        item.payload is None for item in result.terminals if item.kind is TerminalKind.INVALID
    )
    assert "alice@" not in str(result)


def test_normalization_exception_is_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    collector, binding, _repo = _collector()

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("alice@example.com")

    monkeypatch.setattr("itaa_application.solicitation_service._normalize", boom)
    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    result = _collect(collector, binding, spies)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert set(kinds.values()) == {TerminalKind.INVALID}
    assert all(spy.calls == 1 for spy in spies.values())
    assert all(item.payload is None for item in result.terminals)
    assert "alice@" not in str(result)


def test_mailbox_get_and_invitation_mismatch() -> None:
    box = IsolatedMailbox((INVITATIONS[0],))
    declined = SupplierTerminal(
        TerminalKind.DECLINED,
        SUPPLIERS[0],
        CORRELATIONS[0],
        INVITATIONS[0],
        OCCURRED_AT,
        ClosedReason.INSUFFICIENT_CAPACITY,
    )
    box.submit(INVITATIONS[0], declined)
    assert box.get(INVITATIONS[0]) is declined
    assert box.get(INVITATIONS[1]) is None
    mismatched = SupplierTerminal(
        TerminalKind.DECLINED,
        SUPPLIERS[0],
        CORRELATIONS[0],
        INVITATIONS[1],
        OCCURRED_AT,
        ClosedReason.INSUFFICIENT_CAPACITY,
    )
    with pytest.raises(ApplicationError, match="invitation: wrong_channel"):
        IsolatedMailbox((INVITATIONS[0],)).submit(INVITATIONS[0], mismatched)


def test_offer_payload_invariants() -> None:
    with pytest.raises(ApplicationError, match="payload: offer_required"):
        SupplierTerminal(
            TerminalKind.OFFER,
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
        )
    with pytest.raises(ApplicationError, match="payload: offer_required"):
        SupplierTerminal(
            TerminalKind.OFFER,
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            ClosedReason.INSUFFICIENT_CAPACITY,
            payload={"simulation": True},
        )
    with pytest.raises(ApplicationError, match="payload: must_be_absent"):
        SupplierTerminal(
            TerminalKind.DECLINED,
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
            ClosedReason.INSUFFICIENT_CAPACITY,
            payload={"simulation": True},
        )
    with pytest.raises(ApplicationError, match="reason: required"):
        SupplierTerminal(
            TerminalKind.DECLINED,
            SUPPLIERS[0],
            CORRELATIONS[0],
            INVITATIONS[0],
            OCCURRED_AT,
        )


def test_bypassed_terminal_types_are_invalid_not_fatal() -> None:
    collector, binding, _repo = _collector()

    class Bypass:
        def attempt(self, request):
            terminal = object.__new__(SupplierTerminal)
            object.__setattr__(terminal, "kind", "OFFER")
            object.__setattr__(
                terminal, "supplier_token", request.envelope.assignment.supplier_token
            )
            object.__setattr__(terminal, "correlation_id", request.correlation_id)
            object.__setattr__(terminal, "invitation", request.invitation)
            object.__setattr__(terminal, "completed_at", request.occurred_at)
            object.__setattr__(terminal, "reason", None)
            object.__setattr__(terminal, "payload", {"simulation": True})
            return terminal

    spies = {token: SpyPort(port) for token, port in fake_ports().items()}
    spies[SUPPLIERS[0]] = SpyPort(Bypass())  # type: ignore[arg-type]
    result = _collect(collector, binding, spies)
    kinds = {item.supplier_token: item.kind for item in result.terminals}
    assert kinds[SUPPLIERS[0]] is TerminalKind.INVALID
    assert kinds[SUPPLIERS[1]] is TerminalKind.OFFER
    assert kinds[SUPPLIERS[2]] is TerminalKind.OFFER
    assert spies[SUPPLIERS[1]].calls == 1
