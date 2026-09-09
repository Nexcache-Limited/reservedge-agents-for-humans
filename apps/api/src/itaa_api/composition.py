"""Local in-memory composition. Restart discards all session state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

from itaa_application.approval_service import ApprovalService
from itaa_application.audit_service import AuditService
from itaa_application.dispatch_service import DispatchService
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import FaultInjector, GoldenPathFacade, GoldenPathServices
from itaa_application.idempotency_service import IdempotencyService
from itaa_application.local_memory import LocalMemoryUnitOfWork
from itaa_application.local_progress import InMemoryProgressBus
from itaa_application.market_evidence import SyntheticMarketEvidence
from itaa_application.policy_evaluation import TrustedPolicyEvaluation
from itaa_application.progress_events import ProgressSink
from itaa_application.session_models import GoldenPathSession
from itaa_application.session_ports import PolicyEvaluationPort
from itaa_application.solicitation_service import SolicitationCollector
from itaa_application.supplier_port import Clock, FrozenClock, SupplierPort
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import BuyerToken, IntentId, SupplierToken
from itaa_domain.value_objects import AddOn, CoveredPreference, EvidenceRef, parse_utc
from itaa_policy.envelopes import RecipientAssignment
from itaa_policy.isolation import SupplierCapability, SupplierInvitationToken
from itaa_ranking.inputs import RankingNeed, ReliabilityFact
from itaa_supplier_simulator.canonical import (
    canonical_golden_ports,
    canonical_trusted_specs,
    trusted_canonical_evaluation,
)
from itaa_supplier_simulator.economics import billable_days
from itaa_supplier_simulator.policy import (
    PARKDIRECT,
    SEEDED,
    SKYSHIELD,
    TERMINALFLEX,
    trusted_evaluation,
)

LOCAL_OCCURRED = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
LOCAL_CREATED = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
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

_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"


class SequentialIdFactory:
    def __init__(self) -> None:
        self._n = 0
        self._lock = Lock()

    def _next(self, prefix: str) -> str:
        with self._lock:
            self._n += 1
            n = self._n
        return prefix + _encode(n)

    def requirement_id(self) -> str:
        return self._next("rq_")

    def offer_id(self, supplier_token: SupplierToken) -> str:
        del supplier_token
        return self._next("of_")

    def signature(self, supplier_token: SupplierToken) -> str:
        del supplier_token
        return self._next("sg_")

    def correlation_id(self, supplier_token: SupplierToken | None = None) -> str:
        del supplier_token
        return self._next("cr_")

    def acceptance_id(self) -> str:
        return self._next("ac_")

    def authorization_id(self) -> str:
        return self._next("ta_")

    def receipt_signature(self) -> str:
        return self._next("sg_")

    def audit_event_id(self) -> str:
        return self._next("ae_")

    def result_ref(self) -> str:
        return self._next("rr_")


class SeededRoster:
    """Default local-demo roster.

    When no ports are injected, each ``ports()`` call returns a fresh
    canonical golden-path trio so sequential demonstrations cannot share
    mutable supplier capacity. Injected ports remain shared for tests.
    """

    def __init__(self, ports: dict[SupplierToken, SupplierPort] | None = None) -> None:
        self._injected = ports

    def recipients(
        self, clock: object, expires_at: datetime | None = None
    ) -> tuple[RecipientAssignment, ...]:
        tokens = (PARKDIRECT.supplier_token, SKYSHIELD.supplier_token, TERMINALFLEX.supplier_token)
        instant = clock.now() if hasattr(clock, "now") else LOCAL_CREATED
        until = expires_at if expires_at is not None else instant + timedelta(hours=48)
        valid_from = until - timedelta(hours=48)
        valid_until = until
        return tuple(
            RecipientAssignment(
                supplier_token=tokens[index],
                invitation=INVITATIONS[index],
                scoped_intent_id=SCOPED_INTENTS[index],
                scoped_buyer_token=SCOPED_BUYERS[index],
                valid_from=valid_from,
                valid_until=valid_until,
                capabilities=frozenset(
                    {
                        SupplierCapability.INVITATION_READ,
                        SupplierCapability.OFFER_WRITE,
                        SupplierCapability.COUNTEROFFER_WRITE,
                    }
                )
                if index == 0
                else frozenset(
                    {SupplierCapability.INVITATION_READ, SupplierCapability.OFFER_WRITE}
                ),
            )
            for index in range(3)
        )

    def ports(self) -> dict[SupplierToken, SupplierPort]:
        if self._injected is not None:
            return dict(self._injected)
        return canonical_golden_ports()


class GoldenPathPolicyPort:
    """Buyer-trusted policy from the import-time canonical table.

    ``offer_payload`` is an untrusted candidate and is not read. Trusted
    identity, lot, add-ons, availability, evidence, fees, tax, floors, and
    cancellation/refund sets come from ``canonical_trusted_specs()``.
    ``scoped_intent_id`` is the solicitation binding from the call.
    """

    def evaluate(
        self,
        supplier_token: SupplierToken,
        *,
        scoped_intent_id: object,
        offer_payload: object,
    ) -> TrustedPolicyEvaluation:
        del offer_payload
        spec = canonical_trusted_specs().get(supplier_token)
        if spec is None:
            raise ApplicationError("supplierToken", "unknown")
        if isinstance(scoped_intent_id, IntentId):
            intent = scoped_intent_id
        else:
            try:
                intent = IntentId(str(getattr(scoped_intent_id, "value", scoped_intent_id)))
            except DomainInvariantError as exc:
                raise ApplicationError(exc.field, exc.code) from None
        return trusted_canonical_evaluation(spec, intent)


class SimulatorPolicyPort:
    def evaluate(
        self,
        supplier_token: SupplierToken,
        *,
        scoped_intent_id: object,
        offer_payload: object,
    ) -> TrustedPolicyEvaluation:
        policy = next(item for item in SEEDED if item.supplier_token == supplier_token)
        payload = offer_payload if isinstance(offer_payload, dict) else {}
        window = payload.get("serviceWindow")
        days = 6
        if isinstance(window, dict):
            days = billable_days(
                parse_utc(window.get("start"), "service_start"),
                parse_utc(window.get("end"), "service_end"),
            )
        intent = (
            scoped_intent_id
            if isinstance(scoped_intent_id, IntentId)
            else IntentId(str(getattr(scoped_intent_id, "value", scoped_intent_id)))
        )
        return trusted_evaluation(policy, days, intent)


class LocalReliability:
    def facts(self) -> tuple[ReliabilityFact, ...]:
        return (
            ReliabilityFact(
                PARKDIRECT.supplier_token,
                700_000,
                EvidenceRef("registry.parkdirect.reliability.v1"),
                "synthetic.v1",
            ),
            ReliabilityFact(
                SKYSHIELD.supplier_token,
                950_000,
                EvidenceRef("registry.skyshield.reliability.v1"),
                "synthetic.v1",
            ),
            ReliabilityFact(
                TERMINALFLEX.supplier_token,
                850_000,
                EvidenceRef("registry.terminalflex.reliability.v1"),
                "synthetic.v1",
            ),
        )

    def need(self, session: GoldenPathSession) -> RankingNeed:
        requirement = session.requirement
        representable = frozenset(
            item
            for item in AddOn
            if item.value in {need.value for need in requirement.accessibility}
        )
        return RankingNeed(
            covered=requirement.covered
            if type(requirement.covered) is CoveredPreference
            else CoveredPreference.PREFERRED,
            representable_add_ons=representable,
            shuttle_max_minutes=requirement.shuttle_max_minutes,
        )


def build_facade(
    *,
    roster: SeededRoster | None = None,
    clock: Clock | None = None,
    faults: FaultInjector | None = None,
    policies: PolicyEvaluationPort | None = None,
    progress: ProgressSink | None = None,
) -> GoldenPathFacade:
    chosen_roster = roster or SeededRoster()
    unit_of_work = LocalMemoryUnitOfWork()
    services = GoldenPathServices(
        approvals=ApprovalService(unit_of_work.approvals),
        dispatch=DispatchService(unit_of_work.approvals),
        collector=SolicitationCollector(DispatchService(unit_of_work.approvals)),
        idempotency=IdempotencyService(unit_of_work.idempotency),
        audit=AuditService(unit_of_work.audit),
    )
    return GoldenPathFacade(
        sessions=unit_of_work.sessions,
        clock=clock or FrozenClock(LOCAL_OCCURRED),
        ids=SequentialIdFactory(),
        roster=chosen_roster,
        policies=policies or GoldenPathPolicyPort(),
        reliability=LocalReliability(),
        market=SyntheticMarketEvidence(),
        services=services,
        unit_of_work=unit_of_work,
        faults=faults,
        progress=progress or InMemoryProgressBus(),
    )


def _encode(value: int) -> str:
    body = ["0"] * 26
    n = value
    for index in range(25, -1, -1):
        body[index] = _CROCKFORD[n % 32]
        n //= 32
    return "".join(body)
