"""Synthetic fixtures for WP-04 policy tests. No real personal data."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from itaa_domain.identifiers import (
    AcceptanceId,
    ActorId,
    ApprovalId,
    BuyerToken,
    CorrelationId,
    IntentId,
    OfferId,
    RequirementId,
    SupplierToken,
)
from itaa_domain.value_objects import ActorRef, ActorType, PayloadHash
from itaa_policy.isolation import SupplierCapability, SupplierInvitationToken

REPO = Path(__file__).resolve().parents[3]
JFK_PATH = REPO / "packages" / "contracts" / "fixtures" / "valid" / "purchase-intent-jfk.json"
INVALID_DIR = REPO / "packages" / "contracts" / "fixtures" / "invalid"

RESOURCE_INTENT = IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2y3")
BUYER = ActorRef(ActorType.BUYER, ActorId("ar_01k2m3n4p5q6r7s8t9v0w1x2k1"))
OWNER = BUYER.actor_id
CORRELATION = CorrelationId("cr_01k2m3n4p5q6r7s8t9v0w1x2k2")
REQUIREMENT_ID = RequirementId("rq_01k2m3n4p5q6r7s8t9v0w1x2z1")
OFFER_ID = OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a1")
ACCEPTANCE_ID = AcceptanceId("ac_01k2m3n4p5q6r7s8t9v0w1x2d1")
A1_ID = ApprovalId("ap_01k2m3n4p5q6r7s8t9v0w1x2f0")
A2_ID = ApprovalId("ap_01k2m3n4p5q6r7s8t9v0w1x2f1")
A3_ID = ApprovalId("ap_01k2m3n4p5q6r7s8t9v0w1x2f2")
A4_ID = ApprovalId("ap_01k2m3n4p5q6r7s8t9v0w1x2f3")
REVOKE_ID = ApprovalId("ap_01k2m3n4p5q6r7s8t9v0w1x2f9")

SUPPLIERS = (
    SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b1"),
    SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b2"),
    SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b3"),
)
INVITATIONS = (
    SupplierInvitationToken("iv_01k2m3n4p5q6r7s8t9v0w1x2j1"),
    SupplierInvitationToken("iv_01k2m3n4p5q6r7s8t9v0w1x2j2"),
    SupplierInvitationToken("iv_01k2m3n4p5q6r7s8t9v0w1x2j3"),
)
SCOPED_INTENTS = (
    IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2p1"),
    IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2p2"),
    IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2p3"),
)
SCOPED_BUYERS = (
    BuyerToken("bs_01k2m3n4p5q6r7s8t9v0w1x2q1"),
    BuyerToken("bs_01k2m3n4p5q6r7s8t9v0w1x2q2"),
    BuyerToken("bs_01k2m3n4p5q6r7s8t9v0w1x2q3"),
)

CREATED_AT = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)

PLACEHOLDER_HASH = PayloadHash(
    "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)
OTHER_HASH = PayloadHash("sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210")

READ_WRITE = frozenset(
    {
        SupplierCapability.INVITATION_READ,
        SupplierCapability.OFFER_WRITE,
        SupplierCapability.COUNTEROFFER_WRITE,
    }
)
READ_OFFER = frozenset({SupplierCapability.INVITATION_READ, SupplierCapability.OFFER_WRITE})


def load_jfk() -> dict[str, Any]:
    return json.loads(JFK_PATH.read_text(encoding="utf-8"))


def load_invalid(name: str) -> dict[str, Any]:
    return json.loads((INVALID_DIR / name).read_text(encoding="utf-8"))


def clone(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)


def at_minutes(offset: int) -> datetime:
    return CREATED_AT + timedelta(minutes=offset)


def audit_id(index: int) -> str:
    return "ae_" + f"{index:026d}"
