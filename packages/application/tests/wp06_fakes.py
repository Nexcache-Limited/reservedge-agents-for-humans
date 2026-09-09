"""Test helpers for the WP-06 golden-path facade. Not production adapters."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from wp04_helpers import (
    A3_ID,
    A4_ID,
    BUYER,
    CORRELATION,
    CREATED_AT,
    EXPIRES_AT,
    INVITATIONS,
    OCCURRED_AT,
    OWNER,
    READ_OFFER,
    READ_WRITE,
    SCOPED_BUYERS,
    SCOPED_INTENTS,
    SUPPLIERS,
)
from wp05_helpers import RELIABILITY, fixture_policy, load_offer

from itaa_application.approval_service import ApprovalService
from itaa_application.audit_service import AuditService
from itaa_application.dispatch_service import DispatchService
from itaa_application.golden_path import (
    FaultInjector,
    GoldenPathFacade,
    GoldenPathServices,
)
from itaa_application.idempotency_service import IdempotencyService
from itaa_application.local_memory import LocalMemoryUnitOfWork
from itaa_application.market_evidence import SyntheticMarketEvidence
from itaa_application.session_models import AcceptCommand, AuthorizeCommand, GovernanceCommand
from itaa_application.solicitation_service import SolicitationCollector
from itaa_application.supplier_port import (
    ClosedReason,
    FrozenClock,
    SupplierAttempt,
    SupplierTerminal,
    TerminalKind,
)
from itaa_domain.identifiers import IntentId, SupplierToken
from itaa_domain.value_objects import AddOn, CoveredPreference
from itaa_policy.envelopes import RecipientAssignment
from itaa_ranking.inputs import RankingNeed

REPO = Path(__file__).resolve().parents[3]
JFK = json.loads(
    (REPO / "packages" / "contracts" / "fixtures" / "valid" / "purchase-intent-jfk.json").read_text(
        encoding="utf-8"
    )
)
OFFER_FILES = {
    SUPPLIERS[0]: "offer-parkdirect.json",
    SUPPLIERS[1]: "offer-skyshield.json",
    SUPPLIERS[2]: "offer-terminalflex.json",
}
OFFER_IDS = {
    SUPPLIERS[0]: "of_01k2m3n4p5q6r7s8t9v0w1x2a1",
    SUPPLIERS[1]: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
    SUPPLIERS[2]: "of_01k2m3n4p5q6r7s8t9v0w1x2a3",
}
SIGNATURES = {
    SUPPLIERS[0]: "sg_01k2m3n4p5q6r7s8t9v0w1x2h1",
    SUPPLIERS[1]: "sg_01k2m3n4p5q6r7s8t9v0w1x2h2",
    SUPPLIERS[2]: "sg_01k2m3n4p5q6r7s8t9v0w1x2h3",
}
SLOT_CORRELATIONS = {
    SUPPLIERS[0]: "cr_01k2m3n4p5q6r7s8t9v0w1x2m1",
    SUPPLIERS[1]: "cr_01k2m3n4p5q6r7s8t9v0w1x2m2",
    SUPPLIERS[2]: "cr_01k2m3n4p5q6r7s8t9v0w1x2m3",
}


class ScriptedIdFactory:
    def __init__(self) -> None:
        self._audit = 0

    def requirement_id(self) -> str:
        return "rq_01k2m3n4p5q6r7s8t9v0w1x2z1"

    def offer_id(self, supplier_token: SupplierToken) -> str:
        return OFFER_IDS[supplier_token]

    def signature(self, supplier_token: SupplierToken) -> str:
        return SIGNATURES[supplier_token]

    def correlation_id(self, supplier_token: SupplierToken | None = None) -> str:
        if supplier_token is None:
            return CORRELATION.to_primitive()
        return SLOT_CORRELATIONS[supplier_token]

    def acceptance_id(self) -> str:
        return "ac_01k2m3n4p5q6r7s8t9v0w1x2d1"

    def authorization_id(self) -> str:
        return "ta_01k2m3n4p5q6r7s8t9v0w1x2e1"

    def receipt_signature(self) -> str:
        return "sg_01k2m3n4p5q6r7s8t9v0w1x2h9"

    def audit_event_id(self) -> str:
        self._audit += 1
        return "ae_" + f"{self._audit:026d}"

    def result_ref(self) -> str:
        return "rr_01k2m3n4p5q6r7s8t9v0w1x2n1"


class FixtureOfferPort:
    def __init__(self, payload: dict[str, object], *, remaining_capacity: int = 8) -> None:
        self._payload = payload
        self.seen_envelopes: list[dict[str, object]] = []
        self._remaining = remaining_capacity

    @property
    def remaining_capacity(self) -> int:
        return self._remaining

    def restore_capacity(self, remaining: int) -> None:
        self._remaining = remaining

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        envelope = request.envelope.payload_dict()
        self.seen_envelopes.append(envelope)
        payload = deepcopy(self._payload)
        payload["intentId"] = request.envelope.assignment.scoped_intent_id.to_primitive()
        payload["offerId"] = request.offer_id.to_primitive()
        payload["signature"] = request.signature.to_primitive()
        payload["supplierToken"] = request.envelope.assignment.supplier_token.to_primitive()
        if self._remaining < 1:
            return SupplierTerminal(
                TerminalKind.DECLINED,
                request.envelope.assignment.supplier_token,
                request.correlation_id,
                request.invitation,
                request.occurred_at,
                ClosedReason.INSUFFICIENT_CAPACITY,
            )
        self._remaining -= 1
        return SupplierTerminal(
            TerminalKind.OFFER,
            request.envelope.assignment.supplier_token,
            request.correlation_id,
            request.invitation,
            request.occurred_at,
            payload=payload,
        )


class FailingOfferPort:
    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        raise RuntimeError("supplier_internal")


class DecliningOfferPort:
    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        return SupplierTerminal(
            TerminalKind.DECLINED,
            request.envelope.assignment.supplier_token,
            request.correlation_id,
            request.invitation,
            request.occurred_at,
            ClosedReason.INSUFFICIENT_CAPACITY,
        )


class FixtureRoster:
    def __init__(self, ports: dict[SupplierToken, object] | None = None) -> None:
        self._ports = ports or {
            token: FixtureOfferPort(load_offer(OFFER_FILES[token])) for token in SUPPLIERS
        }

    def recipients(
        self, clock: object, expires_at: object = None
    ) -> tuple[RecipientAssignment, ...]:
        del clock, expires_at
        return tuple(
            RecipientAssignment(
                supplier_token=SUPPLIERS[index],
                invitation=INVITATIONS[index],
                scoped_intent_id=SCOPED_INTENTS[index],
                scoped_buyer_token=SCOPED_BUYERS[index],
                valid_from=CREATED_AT,
                valid_until=EXPIRES_AT,
                capabilities=READ_WRITE if index == 0 else READ_OFFER,
            )
            for index in range(3)
        )

    def ports(self) -> dict[SupplierToken, object]:
        return self._ports


class FixturePolicyPort:
    def evaluate(
        self,
        supplier_token: SupplierToken,
        *,
        scoped_intent_id: object,
        offer_payload: object,
    ) -> object:
        payload = offer_payload if isinstance(offer_payload, dict) else {}
        binding = _BindingShim(supplier_token, scoped_intent_id, payload)
        return fixture_policy(binding, payload)  # type: ignore[arg-type]


class _BindingShim:
    def __init__(
        self, token: SupplierToken, scoped_intent_id: object, payload: dict[str, object]
    ) -> None:
        self.supplier_token = token
        self.scoped_intent_id = scoped_intent_id
        self.airport = "JFK"
        self.vehicle_class = "standard"
        _ = payload


class FixtureReliability:
    def facts(self):
        return RELIABILITY

    def need(self, session: object) -> RankingNeed:
        return RankingNeed(
            covered=CoveredPreference.PREFERRED,
            representable_add_ons=frozenset({AddOn.EV_CHARGING}),
            shuttle_max_minutes=20,
        )


def governance(
    approval_id: object,
    *,
    issued_at: datetime = CREATED_AT,
    expires_at: datetime = EXPIRES_AT,
) -> GovernanceCommand:
    return GovernanceCommand(
        actor_id=BUYER.actor_id.to_primitive(),
        owner_id=OWNER.to_primitive(),
        approval_id=approval_id.to_primitive()
        if hasattr(approval_id, "to_primitive")
        else str(approval_id),
        correlation_id=CORRELATION.to_primitive(),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def accept_command(offer_id: str, version: int = 1) -> AcceptCommand:
    base = governance(A3_ID)
    return AcceptCommand(
        actor_id=base.actor_id,
        owner_id=base.owner_id,
        approval_id=base.approval_id,
        correlation_id=base.correlation_id,
        issued_at=base.issued_at,
        expires_at=base.expires_at,
        offer_id=offer_id,
        offer_version=version,
    )


def authorize_command(
    *,
    acceptance_id: str,
    amount_minor: int,
    supplier_token: str,
    mode: str = "SIMULATED",
    action: str = "reserve_parking",
    idempotency_key: str = "ik_01k2m3n4p5q6r7s8t9v0w1x2c1",
) -> AuthorizeCommand:
    base = governance(A4_ID)
    return AuthorizeCommand(
        actor_id=base.actor_id,
        owner_id=base.owner_id,
        approval_id=base.approval_id,
        correlation_id=base.correlation_id,
        issued_at=base.issued_at,
        expires_at=base.expires_at,
        acceptance_id=acceptance_id,
        amount_minor=amount_minor,
        currency="USD",
        supplier_token=supplier_token,
        action=action,
        mode=mode,
        idempotency_key=idempotency_key,
    )


def build_memory(
    *,
    roster: FixtureRoster | None = None,
    clock: FrozenClock | None = None,
    faults: FaultInjector | None = None,
) -> tuple[GoldenPathFacade, LocalMemoryUnitOfWork, FaultInjector]:
    chosen_roster = roster or FixtureRoster()
    unit_of_work = LocalMemoryUnitOfWork()
    unit_of_work.attach_capacity_ports(chosen_roster.ports())
    injector = faults or FaultInjector()
    services = GoldenPathServices(
        approvals=ApprovalService(unit_of_work.approvals),
        dispatch=DispatchService(unit_of_work.approvals),
        collector=SolicitationCollector(DispatchService(unit_of_work.approvals)),
        idempotency=IdempotencyService(unit_of_work.idempotency),
        audit=AuditService(unit_of_work.audit),
    )
    facade = GoldenPathFacade(
        sessions=unit_of_work.sessions,
        clock=clock or FrozenClock(OCCURRED_AT),
        ids=ScriptedIdFactory(),
        roster=chosen_roster,
        policies=FixturePolicyPort(),  # type: ignore[arg-type]
        reliability=FixtureReliability(),
        market=SyntheticMarketEvidence(),
        services=services,
        unit_of_work=unit_of_work,
        faults=injector,
    )
    return facade, unit_of_work, injector


def build_facade(
    *,
    roster: FixtureRoster | None = None,
    clock: FrozenClock | None = None,
    faults: FaultInjector | None = None,
) -> GoldenPathFacade:
    facade, _unit_of_work, _injector = build_memory(roster=roster, clock=clock, faults=faults)
    return facade


def jfk_payload() -> dict[str, object]:
    return deepcopy(JFK)


def intent_id() -> IntentId:
    return IntentId(str(JFK["intentId"]))
