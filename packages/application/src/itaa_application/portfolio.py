"""Buyer-scoped portfolio lifecycle. Process-local; not durable."""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import datetime
from typing import NoReturn, cast

from itaa_application.errors import ApplicationError
from itaa_application.local_memory import ReplaceRecord
from itaa_application.session_models import (
    ActivityEntry,
    BuyerSessionState,
    BuyerSnapshot,
    GoldenPathSession,
    GovernanceCommand,
    ReplaceResult,
)
from itaa_domain.identifiers import ApprovalId, CorrelationId, IntentId
from itaa_domain.protocol import TransitionRequest
from itaa_domain.purchase_intent import PurchaseIntentState
from itaa_domain.requirement import Requirement
from itaa_domain.transaction import TransactionState
from itaa_domain.value_objects import (
    ActorRef,
    CancellationReason,
    ClosureReason,
    format_utc,
)
from itaa_policy.approvals import ApprovalRevocation
from itaa_policy.canonical import SEPARATOR_IDEMPOTENCY_REQUEST, hash_canonical

_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
_PORTFOLIO_PREFIX = "pf_"
_TERMINAL_BUYER = frozenset(
    {
        BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED,
        BuyerSessionState.CANCELLED,
        BuyerSessionState.SUPERSEDED,
    }
)
_POST_DISPATCH = frozenset(
    {
        BuyerSessionState.OFFERS_RANKED,
        BuyerSessionState.ACCEPTANCE_RECORDED,
    }
)


def mint_opaque(prefix: str) -> str:
    raw = secrets.token_bytes(26)
    return prefix + "".join(_CROCKFORD[byte % 32] for byte in raw)


def mint_portfolio_id() -> str:
    return mint_opaque(_PORTFOLIO_PREFIX)


def require_portfolio_id(raw: str) -> str:
    if not raw.startswith(_PORTFOLIO_PREFIX) or len(raw) != 29:
        raise ApplicationError("portfolio", "unknown_resource")
    if any(char not in _CROCKFORD for char in raw[3:]):
        raise ApplicationError("portfolio", "unknown_resource")
    return raw


def require_idempotency_key(raw: str) -> str:
    if not raw.startswith("ik_") or len(raw) != 29:
        raise ApplicationError("idempotencyKey", "schema_invalid")
    if any(char not in _CROCKFORD for char in raw[3:]):
        raise ApplicationError("idempotencyKey", "schema_invalid")
    return raw


def _owned(session: object, portfolio_id: str) -> bool:
    stored = getattr(session, "portfolio_id", None)
    return stored == portfolio_id


class PortfolioOperations:
    """Mixin for GoldenPathFacade. Do not list every process session."""

    def list_buyer_snapshots(self, portfolio_id: str) -> tuple[BuyerSnapshot, ...]:
        scope = require_portfolio_id(portfolio_id)
        owned = [
            session
            for session in self._sessions.list_all()  # type: ignore[attr-defined]
            if _owned(session, scope)
        ]
        owned.sort(
            key=lambda session: (
                session.purchase_intent.updated_at,
                session.requirement.airport.to_primitive(),
                session.purchase_intent.created_at,
            ),
            reverse=True,
        )
        return tuple(self._buyer_snapshot(session) for session in owned)

    def get_owned_snapshot(self, intent_id: IntentId, portfolio_id: str) -> BuyerSnapshot:
        scope = require_portfolio_id(portfolio_id)
        return self._buyer_snapshot(self._owned_session(intent_id, scope))

    def cancel_purchase_intent(
        self,
        intent_id: IntentId,
        portfolio_id: str,
        command: GovernanceCommand,
    ) -> BuyerSnapshot:
        scope = require_portfolio_id(portfolio_id)
        try:
            with self._unit_of_work.transaction(intent_id):  # type: ignore[attr-defined]
                return self._cancel_purchase_intent(intent_id, scope, command)
        except Exception as exc:
            _raise_mapped(exc)

    def replace_purchase_intent(
        self,
        intent_id: IntentId,
        portfolio_id: str,
        command: GovernanceCommand,
        idempotency_key: str,
    ) -> ReplaceResult:
        scope = require_portfolio_id(portfolio_id)
        key = require_idempotency_key(idempotency_key)
        replacement_id = IntentId(mint_opaque("pi_"))
        try:
            with self._unit_of_work.transaction_many((intent_id, replacement_id)):  # type: ignore[attr-defined]
                return self._replace_purchase_intent(intent_id, replacement_id, scope, command, key)
        except Exception as exc:
            _raise_mapped(exc)

    def delete_undisclosed_draft(self, intent_id: IntentId, portfolio_id: str) -> None:
        scope = require_portfolio_id(portfolio_id)
        try:
            with self._unit_of_work.transaction(intent_id):  # type: ignore[attr-defined]
                self._delete_undisclosed_draft(intent_id, scope)
        except Exception as exc:
            _raise_mapped(exc)

    def set_saved(self, intent_id: IntentId, portfolio_id: str, saved: bool) -> BuyerSnapshot:
        scope = require_portfolio_id(portfolio_id)
        try:
            with self._unit_of_work.transaction(intent_id):  # type: ignore[attr-defined]
                return self._set_saved(intent_id, scope, saved)
        except Exception as exc:
            _raise_mapped(exc)

    def buyer_activity(self, intent_id: IntentId, portfolio_id: str) -> tuple[dict[str, str], ...]:
        scope = require_portfolio_id(portfolio_id)
        session = self._owned_session(intent_id, scope)
        return tuple(
            {"occurredAt": format_utc(item.occurred_at), "label": item.label}
            for item in session.activity
        )

    def _owned_session(self, intent_id: IntentId, portfolio_id: str) -> GoldenPathSession:
        session = self._sessions.get(intent_id)  # type: ignore[attr-defined]
        if session is None or not _owned(session, portfolio_id):
            raise ApplicationError("intentId", "unknown_resource")
        return cast(GoldenPathSession, session)

    def _cancel_purchase_intent(
        self,
        intent_id: IntentId,
        portfolio_id: str,
        command: GovernanceCommand,
    ) -> BuyerSnapshot:
        session = self._owned_session(intent_id, portfolio_id)
        if session.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED:
            raise ApplicationError("state", "illegal_state")
        if session.state in {BuyerSessionState.CANCELLED, BuyerSessionState.SUPERSEDED}:
            raise ApplicationError("state", "illegal_state")
        self._reject_pending_transaction(session)
        self._faults.check("cancel.after_ownership")  # type: ignore[attr-defined]
        self._revoke_active_approvals(session, command)
        self._faults.check("cancel.after_revoke")  # type: ignore[attr-defined]
        actor = _actor(command)
        occurred = self._clock.now()  # type: ignore[attr-defined]
        request = TransitionRequest(
            expected_revision=session.purchase_intent.revision,
            occurred_at=occurred,
            actor=actor,
            correlation_id=CorrelationId(command.correlation_id),
        )
        result = session.purchase_intent.cancel(request, CancellationReason.BUYER_REVOKED)
        self._audit_domain(result.event)  # type: ignore[attr-defined]
        updated = replace(
            session,
            purchase_intent=result.aggregate,
            state=BuyerSessionState.CANCELLED,
            saved=False,
            saved_at=None,
            activity=_append_activity(session, occurred, "Request cancelled"),
        )
        self._faults.check("cancel.before_save")  # type: ignore[attr-defined]
        self._sessions.save(updated)  # type: ignore[attr-defined]
        return self._buyer_snapshot(updated)

    def _replace_purchase_intent(
        self,
        intent_id: IntentId,
        replacement_id: IntentId,
        portfolio_id: str,
        command: GovernanceCommand,
        idempotency_key: str,
    ) -> ReplaceResult:
        session = self._owned_session(intent_id, portfolio_id)
        request_hash = hash_canonical(
            SEPARATOR_IDEMPOTENCY_REQUEST,
            {"original": intent_id.to_primitive(), "portfolio": portfolio_id},
        ).to_primitive()
        log = getattr(self._unit_of_work, "replace_log", None)  # type: ignore[attr-defined]
        if log is None:
            raise ApplicationError("internal", "closed")
        existing = log.get(portfolio_id, idempotency_key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ApplicationError("idempotencyKey", "request_mismatch")
            previous = self._owned_session(IntentId(existing.original_intent_id), portfolio_id)
            draft = self._owned_session(IntentId(existing.replacement_intent_id), portfolio_id)
            return ReplaceResult(
                self._buyer_snapshot(previous),
                self._buyer_snapshot(draft),
            )
        if session.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED:
            raise ApplicationError("state", "illegal_state")
        if session.state in {BuyerSessionState.CANCELLED, BuyerSessionState.SUPERSEDED}:
            raise ApplicationError("state", "illegal_state")
        self._reject_pending_transaction(session)
        self._revoke_active_approvals(session, command)
        actor = _actor(command)
        occurred = self._clock.now()  # type: ignore[attr-defined]
        request = TransitionRequest(
            expected_revision=session.purchase_intent.revision,
            occurred_at=occurred,
            actor=actor,
            correlation_id=CorrelationId(command.correlation_id),
        )
        dispatched = session.purchase_intent.state is PurchaseIntentState.DISPATCHED
        if dispatched or session.state in _POST_DISPATCH:
            result = session.purchase_intent.close(request, ClosureReason.SUPERSEDED)
            buyer_state = BuyerSessionState.SUPERSEDED
            label = "Replaced with a revised request"
        else:
            result = session.purchase_intent.cancel(request, CancellationReason.BUYER_REVOKED)
            buyer_state = BuyerSessionState.CANCELLED
            label = "Replaced with a revised request"
        self._audit_domain(result.event)  # type: ignore[attr-defined]
        self._faults.check("replace.after_original")  # type: ignore[attr-defined]
        closed = replace(
            session,
            purchase_intent=result.aggregate,
            state=buyer_state,
            replaced_by_intent_id=replacement_id.to_primitive(),
            saved=False,
            saved_at=None,
            activity=_append_activity(session, occurred, label),
        )
        self._sessions.save(closed)  # type: ignore[attr-defined]
        draft_session = self._draft_from_requirement(
            session,
            replacement_id,
            portfolio_id,
            occurred,
            command,
        )
        self._faults.check("replace.before_draft_save")  # type: ignore[attr-defined]
        self._sessions.save(draft_session)  # type: ignore[attr-defined]
        log.put(
            portfolio_id,
            idempotency_key,
            ReplaceRecord(
                request_hash=request_hash,
                original_intent_id=intent_id.to_primitive(),
                replacement_intent_id=replacement_id.to_primitive(),
            ),
        )
        return ReplaceResult(
            self._buyer_snapshot(closed),
            self._buyer_snapshot(draft_session),
        )

    def _draft_from_requirement(
        self,
        source: GoldenPathSession,
        replacement_id: IntentId,
        portfolio_id: str,
        occurred: datetime,
        command: GovernanceCommand,
    ) -> GoldenPathSession:
        requirement_src: Requirement = source.requirement
        payload: dict[str, object] = {
            "schemaVersion": "1.0",
            "intentId": replacement_id.to_primitive(),
            "buyerToken": mint_opaque("bs_"),
            "category": "airport_parking",
            "location": {"airportCode": requirement_src.airport.to_primitive()},
            "serviceWindow": requirement_src.service_window.to_primitive(),
            "requirements": {
                "vehicleClass": requirement_src.vehicle_class.value,
                "covered": requirement_src.covered.value,
                "shuttleMaxMinutes": requirement_src.shuttle_max_minutes,
            },
            "constraints": {
                "currency": requirement_src.currency,
                "accessibility": [item.value for item in requirement_src.accessibility],
            },
            "createdAt": format_utc(occurred),
            "expiresAt": format_utc(source.purchase_intent.expires_at),
        }
        snapshot = self._create_purchase_intent(  # type: ignore[attr-defined]
            replacement_id,
            payload,
            _freeze(payload),
            portfolio_id=portfolio_id,
            replaces_intent_id=source.purchase_intent.intent_id.to_primitive(),
            requirement_id=mint_opaque("rq_"),
        )
        del snapshot
        created = self._sessions.get(replacement_id)  # type: ignore[attr-defined]
        if created is None:
            raise ApplicationError("internal", "closed")
        return cast(GoldenPathSession, created)

    def _delete_undisclosed_draft(self, intent_id: IntentId, portfolio_id: str) -> None:
        session = self._owned_session(intent_id, portfolio_id)
        if session.state is not BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION:
            raise ApplicationError("intentId", "conflict")
        if session.purchase_intent.state is not PurchaseIntentState.DRAFT:
            raise ApplicationError("intentId", "conflict")
        if session.used_approval_ids:
            raise ApplicationError("intentId", "conflict")
        if session.collection is not None or session.mapped_offers or session.decision is not None:
            raise ApplicationError("intentId", "conflict")
        if session.acceptance is not None:
            raise ApplicationError("intentId", "conflict")
        tx = session.transaction
        if tx is not None and tx.state is not TransactionState.NOT_REQUESTED:
            raise ApplicationError("intentId", "conflict")
        if session.replaced_by_intent_id is not None or session.replaces_intent_id is not None:
            raise ApplicationError("intentId", "conflict")
        self._faults.check("delete.before_remove")  # type: ignore[attr-defined]
        self._sessions.delete(intent_id)  # type: ignore[attr-defined]

    def _set_saved(self, intent_id: IntentId, portfolio_id: str, saved: bool) -> BuyerSnapshot:
        session = self._owned_session(intent_id, portfolio_id)
        if session.state in _TERMINAL_BUYER:
            raise ApplicationError("state", "illegal_state")
        occurred = self._clock.now()  # type: ignore[attr-defined]
        updated = replace(
            session,
            saved=saved,
            saved_at=occurred if saved else None,
        )
        self._sessions.save(updated)  # type: ignore[attr-defined]
        return self._buyer_snapshot(updated)

    def _revoke_active_approvals(self, session: object, command: GovernanceCommand) -> None:
        occurred = self._clock.now()  # type: ignore[attr-defined]
        used: frozenset[str] = session.used_approval_ids  # type: ignore[attr-defined]
        repo = getattr(self._unit_of_work, "approvals", None)  # type: ignore[attr-defined]
        if repo is None:
            return
        for raw in used:
            approval_id = ApprovalId(raw)
            resolution = repo.resolve(approval_id)
            if resolution.grant is None or resolution.revoked:
                continue
            self._services.approvals.revoke(  # type: ignore[attr-defined]
                ApprovalRevocation(
                    revocation_id=ApprovalId(mint_opaque("ap_")),
                    target_id=approval_id,
                    occurred_at=occurred,
                    correlation_id=CorrelationId(command.correlation_id),
                )
            )

    def _reject_pending_transaction(self, session: object) -> None:
        tx = session.transaction  # type: ignore[attr-defined]
        if tx is None:
            return
        if tx.state is TransactionState.NOT_REQUESTED:
            return
        if tx.state is TransactionState.AUTHORIZED_SIMULATED:
            raise ApplicationError("state", "illegal_state")
        raise ApplicationError("transaction", "illegal_state")

    def _buyer_snapshot(self, session: GoldenPathSession) -> BuyerSnapshot:
        snapshot = self._snapshot(session)  # type: ignore[attr-defined]
        return cast(BuyerSnapshot, snapshot)


def _append_activity(session: object, occurred: datetime, label: str) -> tuple[ActivityEntry, ...]:
    current: tuple[ActivityEntry, ...] = getattr(session, "activity", ())
    return current + (ActivityEntry(occurred, label),)


def _actor(command: GovernanceCommand) -> ActorRef:
    from itaa_application.golden_path import _actor as real_actor

    return real_actor(command)


def _freeze(payload: dict[str, object]) -> object:
    from itaa_application.golden_path import _freeze_intent

    return _freeze_intent(payload)


def _raise_mapped(exc: Exception) -> NoReturn:
    from itaa_application.golden_path import map_closed_error

    mapped = map_closed_error(exc)
    raise ApplicationError(mapped.field, mapped.code)
