"""FastAPI-free ports for the local golden-path facade."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from itaa_application.policy_evaluation import TrustedPolicyEvaluation
from itaa_application.session_models import GoldenPathSession
from itaa_application.supplier_port import Clock, SupplierPort
from itaa_domain.identifiers import IntentId, SupplierToken
from itaa_policy.envelopes import RecipientAssignment
from itaa_ranking.inputs import RankingNeed, ReliabilityFact


class SessionRepository(Protocol):
    def get(self, intent_id: IntentId) -> GoldenPathSession | None: ...

    def save(self, session: GoldenPathSession) -> None: ...

    def delete(self, intent_id: IntentId) -> None: ...

    def list_all(self) -> tuple[GoldenPathSession, ...]: ...


class IdFactory(Protocol):
    def requirement_id(self) -> str: ...

    def offer_id(self, supplier_token: SupplierToken) -> str: ...

    def signature(self, supplier_token: SupplierToken) -> str: ...

    def correlation_id(self, supplier_token: SupplierToken | None = None) -> str: ...

    def acceptance_id(self) -> str: ...

    def authorization_id(self) -> str: ...

    def receipt_signature(self) -> str: ...

    def audit_event_id(self) -> str: ...

    def result_ref(self) -> str: ...


class SupplierRosterPort(Protocol):
    def recipients(
        self, clock: Clock, expires_at: datetime | None = None
    ) -> tuple[RecipientAssignment, ...]: ...

    def ports(self) -> dict[SupplierToken, SupplierPort]: ...


class PolicyEvaluationPort(Protocol):
    def evaluate(
        self,
        supplier_token: SupplierToken,
        *,
        scoped_intent_id: object,
        offer_payload: object,
    ) -> TrustedPolicyEvaluation: ...


class ReliabilityPort(Protocol):
    def facts(self) -> tuple[ReliabilityFact, ...]: ...

    def need(self, session: GoldenPathSession) -> RankingNeed: ...


class MarketEvidencePort(Protocol):
    def collect(self, session: GoldenPathSession, clock: Clock) -> tuple[object, ...]: ...


class FaultHook(Protocol):
    def check(self, point: str) -> None:
        """Raise to abort the current unit of work at an injected point."""


class TransactionContext(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class UnitOfWork(Protocol):
    def transaction(self, intent_id: IntentId) -> TransactionContext:
        """Begin staged copies, commit all stores together, or roll them all back."""

    def transaction_many(self, intent_ids: tuple[IntentId, ...]) -> TransactionContext:
        """Lock multiple intents in sorted order for atomic replace."""

    def attach_capacity_ports(self, ports: Mapping[SupplierToken, SupplierPort]) -> None: ...

    def capture_capacity(self) -> None:
        """Refresh the rollback snapshot after attaching per-dispatch ports."""

    def inspect(self) -> object: ...
