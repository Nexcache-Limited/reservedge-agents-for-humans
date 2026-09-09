from __future__ import annotations

from enum import StrEnum

from wp04_helpers import (
    CREATED_AT,
    EXPIRES_AT,
    INVITATIONS,
    OCCURRED_AT,
    READ_OFFER,
    READ_WRITE,
    SCOPED_INTENTS,
    SUPPLIERS,
    at_minutes,
)

from itaa_policy.isolation import (
    IsolationReason,
    SupplierCapability,
    SupplierPrincipal,
    SupplierResourceScope,
    authorize_supplier,
    deny_unrepresentable,
)


def _scope(
    index: int, capabilities: frozenset[SupplierCapability] | None = None
) -> SupplierResourceScope:
    caps = capabilities
    if caps is None:
        caps = READ_WRITE if index == 0 else READ_OFFER
    return SupplierResourceScope(
        principal=SupplierPrincipal(SUPPLIERS[index]),
        invitation=INVITATIONS[index],
        intent_id=SCOPED_INTENTS[index],
        capabilities=caps,
        valid_from=CREATED_AT,
        valid_until=EXPIRES_AT,
    )


def test_three_supplier_isolation_matrix() -> None:
    scopes = [_scope(index) for index in range(3)]
    allows = 0
    denials = 0
    for owner_index, granted in enumerate(scopes):
        for actor_index in range(3):
            for cap in SupplierCapability:
                decision = authorize_supplier(
                    granted=granted,
                    principal=SupplierPrincipal(SUPPLIERS[actor_index]),
                    invitation=INVITATIONS[actor_index],
                    intent_id=SCOPED_INTENTS[actor_index],
                    capability=cap,
                    occurred_at=OCCURRED_AT,
                )
                own = owner_index == actor_index
                permitted = cap in granted.capabilities
                if own and permitted:
                    assert decision.allowed is True
                    assert decision.reason is IsolationReason.ALLOWED
                    allows += 1
                else:
                    assert decision.allowed is False
                    denials += 1
    assert allows == 7
    assert denials == 20
    assert allows + denials == 27


def test_expired_and_not_yet_valid_tokens_deny() -> None:
    granted = _scope(0)
    expired = authorize_supplier(
        granted=granted,
        principal=granted.principal,
        invitation=granted.invitation,
        intent_id=granted.intent_id,
        capability=SupplierCapability.INVITATION_READ,
        occurred_at=EXPIRES_AT,
    )
    assert expired.reason is IsolationReason.EXPIRED
    early = authorize_supplier(
        granted=granted,
        principal=granted.principal,
        invitation=granted.invitation,
        intent_id=granted.intent_id,
        capability=SupplierCapability.INVITATION_READ,
        occurred_at=at_minutes(-1),
    )
    assert early.reason is IsolationReason.NOT_YET_VALID


def test_raw_string_capability_and_list_all_deny() -> None:
    granted = _scope(0)

    class Fake(StrEnum):
        INVITATION_READ = "invitation.read"

    raw = authorize_supplier(
        granted=granted,
        principal=granted.principal,
        invitation=granted.invitation,
        intent_id=granted.intent_id,
        capability="invitation.read",
        occurred_at=OCCURRED_AT,
    )
    assert raw.reason is IsolationReason.UNKNOWN_CAPABILITY
    forged = authorize_supplier(
        granted=granted,
        principal=granted.principal,
        invitation=granted.invitation,
        intent_id=granted.intent_id,
        capability=Fake.INVITATION_READ,
        occurred_at=OCCURRED_AT,
    )
    assert forged.reason is IsolationReason.UNKNOWN_CAPABILITY
    listed = deny_unrepresentable(granted)
    assert listed.reason is IsolationReason.UNREPRESENTABLE
    assert listed.allowed is False


def test_counteroffer_write_only_when_granted() -> None:
    granted = _scope(1)
    decision = authorize_supplier(
        granted=granted,
        principal=granted.principal,
        invitation=granted.invitation,
        intent_id=granted.intent_id,
        capability=SupplierCapability.COUNTEROFFER_WRITE,
        occurred_at=OCCURRED_AT,
    )
    assert decision.reason is IsolationReason.CAPABILITY_DENIED
    own = authorize_supplier(
        granted=_scope(0),
        principal=SupplierPrincipal(SUPPLIERS[0]),
        invitation=INVITATIONS[0],
        intent_id=SCOPED_INTENTS[0],
        capability=SupplierCapability.COUNTEROFFER_WRITE,
        occurred_at=OCCURRED_AT,
    )
    assert own.allowed is True
