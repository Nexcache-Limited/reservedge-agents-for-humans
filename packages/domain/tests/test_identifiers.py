from __future__ import annotations

import pytest

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import (
    AcceptanceId,
    ActorId,
    ApprovalId,
    AuthorizationId,
    BuyerToken,
    CorrelationId,
    CounterOfferId,
    IdempotencyKey,
    IntentId,
    OfferId,
    RequirementId,
    SignatureHandle,
    SupplierToken,
)

CANONICAL_IDS = {
    IntentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
    BuyerToken: "bs_01k2m3n4p5q6r7s8t9v0w1x2y4",
    OfferId: "of_01k2m3n4p5q6r7s8t9v0w1x2a1",
    SupplierToken: "sp_01k2m3n4p5q6r7s8t9v0w1x2b1",
    CounterOfferId: "co_01k2m3n4p5q6r7s8t9v0w1x2c1",
    AcceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
    AuthorizationId: "ta_01k2m3n4p5q6r7s8t9v0w1x2e1",
    ApprovalId: "ap_01k2m3n4p5q6r7s8t9v0w1x2f1",
    IdempotencyKey: "ik_01k2m3n4p5q6r7s8t9v0w1x2g1",
    SignatureHandle: "sg_01k2m3n4p5q6r7s8t9v0w1x2h1",
    RequirementId: "rq_01k2m3n4p5q6r7s8t9v0w1x2z1",
    ActorId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
    CorrelationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
}


@pytest.mark.parametrize(("cls", "value"), list(CANONICAL_IDS.items()))
def test_canonical_fixture_ids_are_accepted(cls: type[object], value: str) -> None:
    typed = cls(value)  # type: ignore[operator]
    assert typed.to_primitive() == value  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "value",
    [
        "pi_01k2m3n4p5q6r7s8t9v0w1x2y",
        "PI_01k2m3n4p5q6r7s8t9v0w1x2y3",
        "pi_01k2m3n4p5q6r7s8t9v0w1x2y3extra",
        "pi_01k2m3n4p5q6r7s8t9v0w1x2yI",
        "pi_01k2m3n4p5q6r7s8t9v0w1x2yl",
        "pi_01k2m3n4p5q6r7s8t9v0w1x2yo",
        "pi_01k2m3n4p5q6r7s8t9v0w1x2yu",
    ],
)
def test_invalid_crockford_ids_are_rejected(value: str) -> None:
    with pytest.raises(DomainInvariantError) as exc:
        IntentId(value)
    assert "pi_" not in str(exc.value) or exc.value.field == "intent_id"
    assert value not in str(exc.value)
