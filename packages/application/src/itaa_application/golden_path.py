"""Framework-neutral JFK golden-path facade. FastAPI-free."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType

from itaa_application.approval_service import ApprovalService
from itaa_application.audit_service import AuditService
from itaa_application.dispatch_service import DispatchService
from itaa_application.errors import ApplicationError
from itaa_application.freeze import freeze_payload, thaw_payload
from itaa_application.idempotency_service import IdempotencyService
from itaa_application.market_evidence import SyntheticMarketEvidence
from itaa_application.offer_boundary import MappedOffer, accept_offer
from itaa_application.offer_terms_hash import offer_terms_hash
from itaa_application.portfolio import PortfolioOperations
from itaa_application.progress_events import NullProgressSink, ProgressEventKind, ProgressSink
from itaa_application.ranking_decision import decide
from itaa_application.session_models import (
    AcceptanceView,
    AcceptCommand,
    ActivityEntry,
    AuthorizeCommand,
    BuyerSessionState,
    BuyerSnapshot,
    DownsideView,
    GoldenPathSession,
    GovernanceCommand,
    RankedOfferView,
    SupplierOutcomeView,
    TransactionView,
    fit_for_rank,
)
from itaa_application.session_ports import (
    FaultHook,
    IdFactory,
    PolicyEvaluationPort,
    ReliabilityPort,
    SessionRepository,
    SupplierRosterPort,
    UnitOfWork,
)
from itaa_application.solicitation_service import SolicitationCollector, SolicitationSlot
from itaa_application.supplier_port import Clock, FrozenClock, SupplierPort, TerminalKind
from itaa_domain.acceptance import Acceptance
from itaa_domain.errors import (
    DomainInvariantError,
    DuplicateActionError,
    ExpiredResourceError,
    InvalidTransitionError,
    OfferVersionMismatchError,
    VersionConflictError,
)
from itaa_domain.identifiers import (
    AcceptanceId,
    ActorId,
    ApprovalId,
    AuthorizationId,
    BuyerToken,
    CorrelationId,
    IdempotencyKey,
    IntentId,
    OfferId,
    RequirementId,
    SignatureHandle,
    SupplierToken,
)
from itaa_domain.offer import Offer, OfferState, OfferTerms
from itaa_domain.protocol import TransitionRequest
from itaa_domain.purchase_intent import PurchaseIntent, PurchaseIntentState
from itaa_domain.requirement import Requirement
from itaa_domain.transaction import Transaction
from itaa_domain.value_objects import (
    AccessibilityNeed,
    ActorRef,
    ActorType,
    AddOn,
    AirportCode,
    AuthorizationAction,
    AuthorizationMode,
    CoveredPreference,
    Money,
    TimeWindow,
    VehicleClass,
    Version,
    format_utc,
    parse_utc,
)
from itaa_observability.audit import (
    AuditAction,
    AuditDecisionResult,
    AuditReason,
    AuditResourceType,
)
from itaa_policy.approvals import (
    ApprovalGrant,
    ApprovalKind,
    ApprovalPurpose,
    ApprovalRequest,
    ApprovalResourceType,
    ApprovalStatus,
)
from itaa_policy.canonical import (
    SEPARATOR_REQUIREMENT_CONFIRMATION,
    SEPARATOR_TRANSACTION_AUTHORIZATION,
    hash_canonical,
)
from itaa_policy.disclosure import DisclosurePurpose
from itaa_policy.envelopes import bind_solicitation
from itaa_policy.errors import PolicyConflictError, PolicyError
from itaa_policy.idempotency import (
    IdempotencyOperation,
    IdempotencyOutcomeKind,
    IdempotencyScope,
    ResultRef,
)

ENVIRONMENT = "local_simulation"
CATEGORY = "airport_parking"
_ADD_ONS = {item.value: item for item in AddOn}


@dataclass(frozen=True, slots=True)
class GoldenPathServices:
    approvals: ApprovalService
    dispatch: DispatchService
    collector: SolicitationCollector
    idempotency: IdempotencyService
    audit: AuditService


class SilentFaults:
    def check(self, point: str) -> None:
        del point


class FaultInjector:
    """Test-only hook. Production composition never installs a failing injector."""

    def __init__(self) -> None:
        self._points: set[str] = set()

    def fail_at(self, point: str) -> None:
        self._points.add(point)

    def clear(self) -> None:
        self._points.clear()

    def check(self, point: str) -> None:
        if point in self._points:
            self._points.discard(point)
            raise ApplicationError("internal", "injected_fault")


class GoldenPathFacade(PortfolioOperations):
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        clock: Clock,
        ids: IdFactory,
        roster: SupplierRosterPort,
        policies: PolicyEvaluationPort,
        reliability: ReliabilityPort,
        market: SyntheticMarketEvidence,
        services: GoldenPathServices,
        unit_of_work: UnitOfWork,
        faults: FaultHook | None = None,
        progress: ProgressSink | None = None,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._ids = ids
        self._roster = roster
        self._policies = policies
        self._reliability = reliability
        self._market = market
        self._services = services
        self._unit_of_work = unit_of_work
        self._faults = faults or SilentFaults()
        self._progress = progress or NullProgressSink()

    def now(self) -> datetime:
        """Return the composed clock instant. Intake mints from this, not a second epoch."""
        return self._clock.now()

    def create_purchase_intent(
        self,
        payload: Mapping[str, object],
        *,
        portfolio_id: str | None = None,
    ) -> BuyerSnapshot:
        frozen = _freeze_intent(payload)
        thawed = _require_mapping(thaw_payload(frozen), "payload")
        intent_id = IntentId(_require_str(thawed.get("intentId"), "intentId"))
        try:
            with self._unit_of_work.transaction(intent_id):
                if self._sessions.get(intent_id) is not None:
                    raise ApplicationError("intentId", "duplicate")
                return self._create_purchase_intent(
                    intent_id, thawed, frozen, portfolio_id=portfolio_id
                )
        except Exception as exc:
            raise map_closed_error(exc) from None

    def _create_purchase_intent(
        self,
        intent_id: IntentId,
        thawed: dict[str, object],
        frozen: MappingProxyType[str, object],
        *,
        portfolio_id: str | None = None,
        replaces_intent_id: str | None = None,
        requirement_id: str | None = None,
    ) -> BuyerSnapshot:
        created_at = parse_utc(thawed.get("createdAt"), "createdAt")
        expires_at = parse_utc(thawed.get("expiresAt"), "expiresAt")
        location = _require_mapping(thawed.get("location"), "location")
        window = _require_mapping(thawed.get("serviceWindow"), "serviceWindow")
        requirements = _require_mapping(thawed.get("requirements"), "requirements")
        constraints = _require_mapping(thawed.get("constraints"), "constraints")
        accessibility_raw = constraints.get("accessibility")
        if not isinstance(accessibility_raw, list):
            raise ApplicationError("accessibility", "required")
        requirement = Requirement.create(
            requirement_id=RequirementId(requirement_id or self._ids.requirement_id()),
            airport=AirportCode(_require_str(location.get("airportCode"), "airport")),
            service_window=TimeWindow.from_primitives(window.get("start"), window.get("end")),
            vehicle_class=VehicleClass(
                _require_str(requirements.get("vehicleClass"), "vehicleClass")
            ),
            covered=CoveredPreference(_require_str(requirements.get("covered"), "covered")),
            shuttle_max_minutes=_require_int(
                requirements.get("shuttleMaxMinutes"), "shuttleMaxMinutes"
            ),
            currency=_require_str(constraints.get("currency"), "currency"),
            accessibility=tuple(AccessibilityNeed(str(item)) for item in accessibility_raw),
            created_at=created_at,
        )
        intent = PurchaseIntent.draft(
            intent_id=intent_id,
            requirement_id=requirement.requirement_id,
            buyer_token=BuyerToken(_require_str(thawed.get("buyerToken"), "buyerToken")),
            created_at=created_at,
            expires_at=expires_at,
        )
        session = GoldenPathSession(
            purchase_intent=intent,
            requirement=requirement,
            intent_payload=frozen,
            state=BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION,
            market_evidence=(),
            transaction=Transaction.not_requested(created_at),
            portfolio_id=portfolio_id,
            replaces_intent_id=replaces_intent_id,
            activity=(ActivityEntry(created_at, "Request created"),),
        )
        evidence = self._market.collect(session, self._clock)
        session = replace(session, market_evidence=evidence)
        self._sessions.save(session)
        return self._snapshot(session)

    def confirm_requirement(self, intent_id: IntentId, command: GovernanceCommand) -> BuyerSnapshot:
        try:
            with self._unit_of_work.transaction(intent_id):
                return self._confirm_requirement(intent_id, command)
        except Exception as exc:
            raise map_closed_error(exc) from None

    def _confirm_requirement(
        self, intent_id: IntentId, command: GovernanceCommand
    ) -> BuyerSnapshot:
        session = self._require_session(intent_id)
        self._require_buyer_state(session, BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION)
        actor = _actor(command)
        occurred = self._clock.now()
        digest = hash_canonical(
            SEPARATOR_REQUIREMENT_CONFIRMATION,
            {"requirementId": session.requirement.requirement_id.to_primitive()},
        )
        grant = ApprovalGrant(
            approval_id=ApprovalId(command.approval_id),
            kind=ApprovalKind.REQUIREMENT_CONFIRMATION,
            purpose=ApprovalPurpose.REQUIREMENT_CONFIRMATION,
            actor=actor,
            owner_id=ActorId(command.owner_id),
            resource_type=ApprovalResourceType.REQUIREMENT,
            resource_id=session.requirement.requirement_id.to_primitive(),
            resource_version=session.requirement.revision,
            payload_hash=digest,
            issued_at=command.issued_at,
            expires_at=command.expires_at,
            status=ApprovalStatus.ACTIVE,
            correlation_id=CorrelationId(command.correlation_id),
        )
        self._issue_and_validate(grant, _request_from(grant, occurred), session.used_approval_ids)
        self._faults.check("a1.after_approval_and_audit")
        request = TransitionRequest(
            expected_revision=session.purchase_intent.revision,
            occurred_at=occurred,
            actor=actor,
            correlation_id=CorrelationId(command.correlation_id),
        )
        result = session.purchase_intent.confirm(request)
        self._audit_domain(result.event)
        updated = replace(
            session,
            purchase_intent=result.aggregate,
            state=BuyerSessionState.AWAITING_DISPATCH_APPROVAL,
            used_approval_ids=session.used_approval_ids | {command.approval_id},
            activity=session.activity + (ActivityEntry(occurred, "Details confirmed"),),
        )
        self._sessions.save(updated)
        return self._snapshot(updated)

    def approve_and_dispatch(
        self, intent_id: IntentId, command: GovernanceCommand
    ) -> BuyerSnapshot:
        try:
            with self._unit_of_work.transaction(intent_id):
                ports = self._roster.ports()
                self._unit_of_work.attach_capacity_ports(ports)
                self._unit_of_work.capture_capacity()
                return self._approve_and_dispatch(intent_id, command, ports)
        except Exception as exc:
            raise map_closed_error(exc) from None

    def _approve_and_dispatch(
        self,
        intent_id: IntentId,
        command: GovernanceCommand,
        ports: dict[SupplierToken, SupplierPort],
    ) -> BuyerSnapshot:
        session = self._require_session(intent_id)
        actor = _actor(command)
        occurred = self._clock.now()
        intent_key = intent_id.to_primitive()
        try:
            self._require_buyer_state(session, BuyerSessionState.AWAITING_DISPATCH_APPROVAL)
            if session.purchase_intent.state is not PurchaseIntentState.CONFIRMED:
                raise ApplicationError("state", "illegal_state")
            return self._solicit_and_rank(
                session, command, ports, actor=actor, occurred=occurred, intent_key=intent_key
            )
        except Exception:
            if self._progress_started(intent_key):
                self._emit(
                    intent_key,
                    ProgressEventKind.STREAM_COMPLETED,
                    occurred,
                    status="unavailable",
                    terminal=True,
                )
            else:
                self._abandon_empty_progress(intent_key)
            raise

    def _solicit_and_rank(
        self,
        session: GoldenPathSession,
        command: GovernanceCommand,
        ports: dict[SupplierToken, SupplierPort],
        *,
        actor: ActorRef,
        occurred: datetime,
        intent_key: str,
    ) -> BuyerSnapshot:
        recipients = self._roster.recipients(
            self._clock, expires_at=session.purchase_intent.expires_at
        )
        if len(recipients) != 3:
            raise ApplicationError("assignments", "must_be_three")
        self._emit(intent_key, ProgressEventKind.SOLICITATION_PREPARING, occurred)
        source = _require_mapping(thaw_payload(session.intent_payload), "payload")
        binding = bind_solicitation(
            source,
            intent_resource_id=session.purchase_intent.intent_id,
            intent_resource_version=session.purchase_intent.revision,
            purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
            expires_at=parse_utc(source.get("expiresAt"), "expiresAt"),
            recipients=recipients,
        )
        preview = session.purchase_intent.preview_disclosure(
            TransitionRequest(
                expected_revision=session.purchase_intent.revision,
                occurred_at=occurred,
                actor=actor,
                correlation_id=CorrelationId(command.correlation_id),
            ),
            binding.manifest.manifest_hash,
        )
        self._audit_domain(preview.event)
        grant = ApprovalGrant(
            approval_id=ApprovalId(command.approval_id),
            kind=ApprovalKind.PURCHASE_INTENT_DISPATCH,
            purpose=ApprovalPurpose.PURCHASE_INTENT_DISPATCH,
            actor=actor,
            owner_id=ActorId(command.owner_id),
            resource_type=ApprovalResourceType.PURCHASE_INTENT,
            resource_id=binding.manifest.intent_resource_id.to_primitive(),
            resource_version=binding.manifest.intent_resource_version,
            payload_hash=binding.manifest.manifest_hash,
            issued_at=command.issued_at,
            expires_at=command.expires_at,
            status=ApprovalStatus.ACTIVE,
            correlation_id=CorrelationId(command.correlation_id),
            content_hash=binding.manifest.content_hash,
            manifest_hash=binding.manifest.manifest_hash,
            recipient_count=len(binding.envelopes),
            solicitation_expires_at=parse_utc(binding.manifest.expires_at, "expires_at"),
        )
        self._issue_and_validate(grant, _request_from(grant, occurred), session.used_approval_ids)
        self._faults.check("a2.after_approval_and_audit")
        approved = preview.aggregate.approve_dispatch(
            TransitionRequest(
                expected_revision=preview.aggregate.revision,
                occurred_at=occurred,
                actor=actor,
                correlation_id=CorrelationId(command.correlation_id),
            ),
            ApprovalId(command.approval_id),
        )
        self._audit_domain(approved.event)
        dispatched = approved.aggregate.dispatch(
            TransitionRequest(
                expected_revision=approved.aggregate.revision,
                occurred_at=occurred,
                actor=actor,
                correlation_id=CorrelationId(command.correlation_id),
            )
        )
        self._audit_domain(dispatched.event)
        self._emit(intent_key, ProgressEventKind.SOLICITATION_DISPATCHED, occurred)
        for item in recipients:
            self._emit(
                intent_key,
                ProgressEventKind.SUPPLIER_WAITING,
                occurred,
                supplier_token=item.supplier_token.to_primitive(),
            )
        slots = tuple(
            SolicitationSlot(
                item.supplier_token,
                OfferId(self._ids.offer_id(item.supplier_token)),
                SignatureHandle(self._ids.signature(item.supplier_token)),
                CorrelationId(self._ids.correlation_id(item.supplier_token)),
            )
            for item in recipients
        )
        deadline = min(
            parse_utc(
                _require_mapping(source.get("solicitation"), "solicitation").get(
                    "responseDeadline"
                ),
                "responseDeadline",
            ),
            parse_utc(source.get("expiresAt"), "expiresAt"),
        )
        collected = self._services.collector.collect(
            approval_id=ApprovalId(command.approval_id),
            binding=binding,
            slots=slots,
            ports=ports,
            deadline=deadline,
            actor=actor,
            owner_id=ActorId(command.owner_id),
            clock=self._clock,
        )
        for response in collected.responses:
            kind, status = _progress_terminal(response.kind)
            self._emit(
                intent_key,
                kind,
                occurred,
                supplier_token=response.supplier_token.to_primitive(),
                status=status,
                correlation_id=response.correlation_id.to_primitive(),
            )
        self._faults.check("a2.after_collection_and_capacity")
        mapped: list[MappedOffer] = []
        for response in collected.responses:
            if response.kind is not TerminalKind.OFFER or response.payload is None:
                continue
            try:
                policy = self._policies.evaluate(
                    response.supplier_token,
                    scoped_intent_id=response.binding.scoped_intent_id
                    if response.binding is not None
                    else session.purchase_intent.intent_id,
                    offer_payload=thaw_payload(response.payload),
                )
                mapped.append(accept_offer(response, policy, evaluated_at=occurred, actor=actor))
            except (ApplicationError, DomainInvariantError, PolicyError):
                continue
        self._emit(intent_key, ProgressEventKind.VALIDATION_COMPLETED, occurred)
        decision = None
        if mapped:
            decision = decide(
                tuple(item.ranking_input for item in mapped),
                self._reliability.need(session),
                evaluated_at=occurred,
                reliability=self._reliability.facts(),
            )
            winner = decision.result.recommended_offer_id
            if winner is not None:
                mapped = [
                    _recommend(item, actor, command.correlation_id, occurred)
                    if item.offer.offer_id == winner
                    else item
                    for item in mapped
                ]
        self._emit(intent_key, ProgressEventKind.RANKING_COMPLETED, occurred)
        self._emit(intent_key, ProgressEventKind.RECOMMENDATION_READY, occurred)
        updated = replace(
            session,
            purchase_intent=dispatched.aggregate,
            state=BuyerSessionState.OFFERS_RANKED,
            collection=collected,
            mapped_offers=tuple(mapped),
            decision=decision,
            used_approval_ids=session.used_approval_ids | {command.approval_id},
            activity=session.activity
            + (
                ActivityEntry(occurred, "Supplier information approved"),
                ActivityEntry(occurred, "Three simulated suppliers contacted"),
                ActivityEntry(occurred, "Three private offers received"),
            ),
        )
        self._sessions.save(updated)
        snapshot = self._snapshot(updated)
        self._emit(
            intent_key,
            ProgressEventKind.STREAM_COMPLETED,
            occurred,
            status="complete",
            terminal=True,
        )
        return snapshot

    def get_buyer_snapshot(self, intent_id: IntentId) -> BuyerSnapshot:
        return self._snapshot(self._require_session(intent_id))

    def lookup_session(self, intent_id: IntentId) -> GoldenPathSession | None:
        """Return the in-memory session, or None after restart / unknown id."""
        return self._sessions.get(intent_id)

    def accept_recommended_or_selected_offer(
        self, intent_id: IntentId, command: AcceptCommand
    ) -> BuyerSnapshot:
        try:
            with self._unit_of_work.transaction(intent_id):
                return self._accept_recommended_or_selected_offer(intent_id, command)
        except Exception as exc:
            raise map_closed_error(exc) from None

    def _accept_recommended_or_selected_offer(
        self, intent_id: IntentId, command: AcceptCommand
    ) -> BuyerSnapshot:
        session = self._require_session(intent_id)
        self._require_buyer_state(session, BuyerSessionState.OFFERS_RANKED)
        occurred = self._clock.now()
        actor = _actor(command)
        selected = _select_offer(session, command.offer_id, command.offer_version, occurred)
        terms_doc = _require_terms(selected.offer)
        terms = offer_terms_hash(terms_doc)
        grant = ApprovalGrant(
            approval_id=ApprovalId(command.approval_id),
            kind=ApprovalKind.OFFER_ACCEPTANCE,
            purpose=ApprovalPurpose.OFFER_ACCEPTANCE,
            actor=actor,
            owner_id=ActorId(command.owner_id),
            resource_type=ApprovalResourceType.OFFER,
            resource_id=selected.offer.offer_id.to_primitive(),
            resource_version=selected.offer.offer_version,
            payload_hash=terms,
            issued_at=command.issued_at,
            expires_at=command.expires_at,
            status=ApprovalStatus.ACTIVE,
            correlation_id=CorrelationId(command.correlation_id),
            intent_id=selected.offer.intent_id,
            offer_id=selected.offer.offer_id,
            offer_version=selected.offer.offer_version,
            terms_hash=terms,
            offer_valid_until=terms_doc.validity.end,
        )
        self._issue_and_validate(grant, _request_from(grant, occurred), session.used_approval_ids)
        acceptance = Acceptance.record(
            acceptance_id=AcceptanceId(self._ids.acceptance_id()),
            intent_id=selected.offer.intent_id,
            offer_id=selected.offer.offer_id,
            offer_version=selected.offer.offer_version,
            accepted_terms_hash=terms,
            buyer_approval_id=ApprovalId(command.approval_id),
            created_at=occurred,
            expires_at=min(terms_doc.validity.end, session.purchase_intent.expires_at),
        )
        accepted = selected.offer.accept(
            TransitionRequest(
                expected_revision=selected.offer.revision,
                occurred_at=occurred,
                actor=actor,
                correlation_id=CorrelationId(command.correlation_id),
            ),
            acceptance,
        )
        self._audit_domain(accepted.event)
        self._faults.check("a3.after_audit")
        mapped = tuple(
            replace(item, offer=accepted.aggregate)
            if item.offer.offer_id == selected.offer.offer_id
            else item
            for item in session.mapped_offers
        )
        updated = replace(
            session,
            mapped_offers=mapped,
            acceptance=acceptance,
            state=BuyerSessionState.ACCEPTANCE_RECORDED,
            used_approval_ids=session.used_approval_ids | {command.approval_id},
            activity=session.activity + (ActivityEntry(occurred, "Offer selected"),),
        )
        self._sessions.save(updated)
        return self._snapshot(updated)

    def authorize_simulated_transaction(
        self, intent_id: IntentId, command: AuthorizeCommand
    ) -> BuyerSnapshot:
        if command.mode != AuthorizationMode.SIMULATED.value:
            raise ApplicationError("mode", "mode_forbidden")
        if command.action != AuthorizationAction.RESERVE_PARKING.value:
            raise ApplicationError("action", "must_be_reserve_parking")
        try:
            with self._unit_of_work.transaction(intent_id):
                return self._authorize_simulated_transaction(intent_id, command)
        except Exception as exc:
            raise map_closed_error(exc) from None

    def _authorize_simulated_transaction(
        self, intent_id: IntentId, command: AuthorizeCommand
    ) -> BuyerSnapshot:
        session = self._require_session(intent_id)
        if session.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED:
            return self._replay_or_conflict_authorization(session, command)
        self._require_buyer_state(session, BuyerSessionState.ACCEPTANCE_RECORDED)
        if session.acceptance is None:
            raise ApplicationError("acceptanceId", "required")
        occurred = self._clock.now()
        actor = _actor(command)
        selected = _offer_for_acceptance(session)
        _assert_authorization_match(session, command, selected)
        request_body = {
            "action": AuthorizationAction.RESERVE_PARKING.value,
            "amountMinor": command.amount_minor,
            "currency": command.currency,
            "supplierToken": command.supplier_token,
            "mode": AuthorizationMode.SIMULATED.value,
            "acceptanceId": command.acceptance_id,
        }
        digest = hash_canonical(SEPARATOR_TRANSACTION_AUTHORIZATION, request_body)
        grant = ApprovalGrant(
            approval_id=ApprovalId(command.approval_id),
            kind=ApprovalKind.TRANSACTION_AUTHORIZATION,
            purpose=ApprovalPurpose.TRANSACTION_AUTHORIZATION,
            actor=actor,
            owner_id=ActorId(command.owner_id),
            resource_type=ApprovalResourceType.TRANSACTION,
            resource_id=session.acceptance.acceptance_id.to_primitive(),
            resource_version=Version.initial(),
            payload_hash=digest,
            issued_at=command.issued_at,
            expires_at=command.expires_at,
            status=ApprovalStatus.ACTIVE,
            correlation_id=CorrelationId(command.correlation_id),
            simulation=True,
            acceptance_id=session.acceptance.acceptance_id,
            action=AuthorizationAction.RESERVE_PARKING,
            amount_minor=command.amount_minor,
            currency=command.currency,
            supplier_token=SupplierToken(command.supplier_token),
            mode=AuthorizationMode.SIMULATED,
            request_hash=digest,
            decision_expires_at=min(session.acceptance.expires_at, command.expires_at),
        )
        self._issue_and_validate(grant, _request_from(grant, occurred), session.used_approval_ids)
        self._faults.check("a4.after_approval")
        result_ref = ResultRef(self._ids.result_ref())
        scope = IdempotencyScope(
            actor.actor_id,
            IdempotencyOperation.AUTHORIZE_TRANSACTION,
            IdempotencyKey(command.idempotency_key),
        )

        def effect() -> Mapping[str, object]:
            return {"authorization": "simulated", "resultRef": result_ref.to_primitive()}

        outcome = self._services.idempotency.execute(
            scope=scope,
            request=request_body,
            occurred_at=occurred,
            expires_at=command.expires_at,
            result_ref=result_ref,
            effect=effect,
        )
        self._faults.check("a4.after_idempotency")
        if outcome.kind is IdempotencyOutcomeKind.REPLAYED:
            if session.authorization_result_ref is None:
                raise ApplicationError("idempotency_key", "request_mismatch")
            return self._snapshot(session)
        if outcome.kind is IdempotencyOutcomeKind.IN_PROGRESS:
            raise ApplicationError("idempotency_key", "in_progress")
        current = session.transaction or Transaction.not_requested(occurred)
        requested = current.request_from_acceptance(
            TransitionRequest(
                expected_revision=current.revision,
                occurred_at=occurred,
                actor=actor,
                correlation_id=CorrelationId(command.correlation_id),
            ),
            session.acceptance,
            selected.offer,
        )
        self._faults.check("a4.after_tx_requested")
        self._audit_domain(requested.event)
        self._faults.check("a4.after_audit_requested")
        required = requested.aggregate.require_approval(
            TransitionRequest(
                expected_revision=requested.aggregate.revision,
                occurred_at=occurred,
                actor=actor,
                correlation_id=CorrelationId(command.correlation_id),
            ),
            action=AuthorizationAction.RESERVE_PARKING,
            amount=Money(command.amount_minor, command.currency),
            supplier_token=SupplierToken(command.supplier_token),
            decision_expires_at=min(session.acceptance.expires_at, command.expires_at),
        )
        self._faults.check("a4.after_tx_required")
        self._audit_domain(required.event)
        self._faults.check("a4.after_audit_required")
        authorized = required.aggregate.authorize_simulated(
            TransitionRequest(
                expected_revision=required.aggregate.revision,
                occurred_at=occurred,
                actor=actor,
                correlation_id=CorrelationId(command.correlation_id),
            ),
            authorization_id=AuthorizationId(self._ids.authorization_id()),
            user_approval_id=ApprovalId(command.approval_id),
            idempotency_key=IdempotencyKey(command.idempotency_key),
            signature=SignatureHandle(self._ids.receipt_signature()),
            expires_at=min(session.acceptance.expires_at, command.expires_at),
        )
        self._faults.check("a4.after_tx_authorized")
        self._audit_domain(authorized.event)
        self._faults.check("a4.after_audit_authorized")
        updated = replace(
            session,
            transaction=authorized.aggregate,
            authorization_result_ref=outcome.result_ref,
            state=BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED,
            used_approval_ids=session.used_approval_ids | {command.approval_id},
            activity=session.activity
            + (ActivityEntry(occurred, "Simulated reservation authorized"),),
        )
        self._faults.check("a4.before_session_save")
        self._sessions.save(updated)
        return self._snapshot(updated)

    def _replay_or_conflict_authorization(
        self, session: GoldenPathSession, command: AuthorizeCommand
    ) -> BuyerSnapshot:
        actor = _actor(command)
        request_body = {
            "action": AuthorizationAction.RESERVE_PARKING.value,
            "amountMinor": command.amount_minor,
            "currency": command.currency,
            "supplierToken": command.supplier_token,
            "mode": AuthorizationMode.SIMULATED.value,
            "acceptanceId": command.acceptance_id,
        }
        existing = session.authorization_result_ref or ResultRef(self._ids.result_ref())

        def effect() -> Mapping[str, object]:
            return {"authorization": "simulated", "resultRef": existing.to_primitive()}

        outcome = self._services.idempotency.execute(
            scope=IdempotencyScope(
                actor.actor_id,
                IdempotencyOperation.AUTHORIZE_TRANSACTION,
                IdempotencyKey(command.idempotency_key),
            ),
            request=request_body,
            occurred_at=self._clock.now(),
            expires_at=command.expires_at,
            result_ref=existing,
            effect=effect,
        )
        if outcome.kind is IdempotencyOutcomeKind.REPLAYED:
            return self._snapshot(session)
        raise ApplicationError("idempotency_key", "request_mismatch")

    def _require_session(self, intent_id: IntentId) -> GoldenPathSession:
        session = self._sessions.get(intent_id)
        if session is None:
            raise ApplicationError("intentId", "unknown_resource")
        return session

    def _require_buyer_state(self, session: GoldenPathSession, expected: BuyerSessionState) -> None:
        if session.state is not expected:
            raise ApplicationError("state", "illegal_state")

    def _issue_and_validate(
        self,
        grant: ApprovalGrant,
        request: ApprovalRequest,
        used_approval_ids: frozenset[str],
    ) -> None:
        if grant.approval_id.to_primitive() in used_approval_ids:
            raise ApplicationError("approvalId", "approval_reused")
        try:
            self._services.approvals.issue(grant)
            decision = self._services.approvals.validate(grant.approval_id, request)
        except PolicyConflictError as exc:
            raise ApplicationError(exc.field, exc.code) from None
        except PolicyError as exc:
            raise ApplicationError(exc.field, exc.code) from None
        if not decision.allowed:
            reason = decision.reason.value if decision.reason is not None else "approval_denied"
            raise ApplicationError("approvalId", reason)
        self._services.audit.append_governance(
            event_id=self._ids.audit_event_id(),
            occurred_at=request.occurred_at,
            actor_type=grant.actor.category,
            actor_id=grant.actor.actor_id,
            action=AuditAction.APPROVAL_ALLOW,
            resource_type=AuditResourceType.APPROVAL,
            resource_id=grant.approval_id.to_primitive(),
            resource_version=grant.resource_version,
            decision=AuditDecisionResult.ALLOW,
            reason_codes=(AuditReason.ALLOWED,),
            correlation_id=grant.correlation_id,
            approval_id=grant.approval_id,
            simulation=True,
        )

    def _audit_domain(self, event: object) -> None:
        from itaa_domain.events import DomainEvent

        if type(event) is not DomainEvent:
            return
        self._services.audit.append_domain_event(event, event_id=self._ids.audit_event_id())

    def _progress_started(self, intent_id: str) -> bool:
        started = getattr(self._progress, "has_started", None)
        if callable(started):
            return bool(started(intent_id))
        return False

    def _abandon_empty_progress(self, intent_id: str) -> None:
        abandon = getattr(self._progress, "abandon_empty", None)
        if callable(abandon):
            abandon(intent_id)

    def _emit(
        self,
        intent_id: str,
        kind: ProgressEventKind,
        occurred_at: datetime,
        *,
        supplier_token: str | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        terminal: bool = False,
    ) -> None:
        self._progress.emit(
            intent_id=intent_id,
            kind=kind,
            occurred_at=occurred_at,
            supplier_token=supplier_token,
            status=status,
            correlation_id=correlation_id,
            terminal=terminal,
        )

    def _snapshot(self, session: GoldenPathSession) -> BuyerSnapshot:
        ranked: list[RankedOfferView] = []
        recommended = None
        downside = None
        if session.decision is not None:
            recommended = (
                session.decision.result.recommended_offer_id.to_primitive()
                if session.decision.result.recommended_offer_id is not None
                else None
            )
            if session.decision.result.downside is not None:
                downside_row = session.decision.result.downside
                downside = DownsideView(
                    downside_row.dimension.value,
                    downside_row.delta,
                    downside_row.versus_offer_id.to_primitive()
                    if downside_row.versus_offer_id is not None
                    else None,
                )
            mapped_by_id = {item.offer.offer_id: item for item in session.mapped_offers}
            evaluated_at = session.purchase_intent.updated_at
            for row in session.decision.result.ranked:
                mapped = mapped_by_id.get(row.offer_id)
                if mapped is None:
                    continue
                terms = _require_terms(mapped.offer)
                offer_id = row.offer_id.to_primitive()
                ranked.append(
                    RankedOfferView(
                        offer_id=offer_id,
                        supplier_token=mapped.offer.supplier_token.to_primitive(),
                        version=row.version,
                        rank=row.rank,
                        score_micros=row.score_micros,
                        total_minor=row.total_minor,
                        currency=mapped.ranking_input.currency,
                        recommended=offer_id == recommended,
                        simulation=True,
                        source_type="supplier_private_quote",
                        offer_class="standard",
                        issued_at=format_utc(mapped.offer.created_at),
                        valid_from=format_utc(terms.validity.start),
                        valid_until=format_utc(terms.validity.end),
                        terms_hash=offer_terms_hash(terms).to_primitive(),
                        tax_minor=terms.price.tax.amount_minor,
                        fees_minor=terms.price.fees.amount_minor,
                        fit=fit_for_rank(row.rank),
                        validity=_buyer_validity(terms, evaluated_at, mapped.offer.state),
                        inventory="not_held",
                        transaction_result=_buyer_transaction_result(session, offer_id),
                        completeness="complete" if terms.evidence else "incomplete",
                        evidence=tuple(
                            (item.evidence_type.value, item.ref.to_primitive())
                            for item in terms.evidence
                        ),
                    )
                )
        outcomes: list[SupplierOutcomeView] = []
        if session.collection is not None:
            for item in session.collection.responses:
                outcomes.append(
                    SupplierOutcomeView(
                        item.supplier_token.to_primitive(),
                        item.kind.value,
                        item.reason.value if item.reason is not None else None,
                    )
                )
        acceptance = None
        if session.acceptance is not None:
            acceptance = AcceptanceView(
                session.acceptance.acceptance_id.to_primitive(),
                session.acceptance.offer_id.to_primitive(),
                session.acceptance.offer_version.to_primitive(),
                session.acceptance.status.value,
            )
        transaction = None
        receipt = None if session.transaction is None else session.transaction.receipt
        if receipt is not None:
            transaction = TransactionView(
                receipt.authorization_id.to_primitive(),
                receipt.acceptance_id.to_primitive(),
                receipt.action.value,
                receipt.mode.value,
                receipt.amount.amount_minor,
                receipt.amount.currency,
                None
                if session.authorization_result_ref is None
                else session.authorization_result_ref.to_primitive(),
            )
        return BuyerSnapshot(
            environment=ENVIRONMENT,
            simulation=True,
            intent_id=session.purchase_intent.intent_id.to_primitive(),
            state=session.state,
            airport=session.requirement.airport.to_primitive(),
            category=CATEGORY,
            created_at=format_utc(session.purchase_intent.created_at),
            updated_at=format_utc(session.purchase_intent.updated_at),
            expires_at=format_utc(session.purchase_intent.expires_at),
            market_evidence=session.market_evidence,
            supplier_outcomes=tuple(outcomes),
            offers=tuple(ranked),
            recommended_offer_id=recommended,
            downside=downside,
            acceptance=acceptance,
            transaction=transaction,
            replaces_intent_id=session.replaces_intent_id,
            replaced_by_intent_id=session.replaced_by_intent_id,
            saved=session.saved,
            saved_at=None if session.saved_at is None else format_utc(session.saved_at),
            window_start=format_utc(session.requirement.service_window.start),
            window_end=format_utc(session.requirement.service_window.end),
        )


def _progress_terminal(kind: TerminalKind) -> tuple[ProgressEventKind, str | None]:
    mapping: dict[TerminalKind, tuple[ProgressEventKind, str | None]] = {
        TerminalKind.OFFER: (ProgressEventKind.SUPPLIER_OFFER_RECEIVED, None),
        TerminalKind.DECLINED: (ProgressEventKind.SUPPLIER_DECLINED, None),
        TerminalKind.TIMED_OUT: (ProgressEventKind.SUPPLIER_TIMED_OUT, "deadline"),
        TerminalKind.LATE: (ProgressEventKind.SUPPLIER_LATE, "deadline"),
        TerminalKind.INVALID: (ProgressEventKind.SUPPLIER_INVALID, "malformed"),
        TerminalKind.FAILED: (ProgressEventKind.SUPPLIER_FAILED, "closed"),
        TerminalKind.DENIED: (ProgressEventKind.SUPPLIER_FAILED, "dispatch_denied"),
    }
    return mapping[kind]


def _recommend(
    mapped: MappedOffer, actor: ActorRef, correlation_id: str, occurred: datetime
) -> MappedOffer:
    if mapped.offer.state is not OfferState.ELIGIBLE:
        return mapped
    result = mapped.offer.recommend(
        TransitionRequest(
            expected_revision=mapped.offer.revision,
            occurred_at=occurred,
            actor=actor,
            correlation_id=CorrelationId(correlation_id),
        )
    )
    return replace(mapped, offer=result.aggregate)


def _select_offer(
    session: GoldenPathSession, offer_id: str, offer_version: int, occurred: datetime
) -> MappedOffer:
    try:
        wanted = OfferId(offer_id)
    except DomainInvariantError as exc:
        raise ApplicationError(exc.field, exc.code) from None
    selected = next((item for item in session.mapped_offers if item.offer.offer_id == wanted), None)
    if selected is None:
        raise ApplicationError("offerId", "ineligible")
    if selected.offer.offer_version.to_primitive() != offer_version:
        raise ApplicationError("offerVersion", "stale_version")
    if _require_terms(selected.offer).validity.is_expired_at(occurred):
        raise ApplicationError("offerId", "expired")
    if selected.offer.state not in {OfferState.ELIGIBLE, OfferState.RECOMMENDED}:
        raise ApplicationError("offerId", "ineligible")
    return selected


def _require_terms(offer: Offer) -> OfferTerms:
    if offer.terms is None:
        raise ApplicationError("terms", "required")
    return offer.terms


def _buyer_validity(terms: OfferTerms, instant: datetime, state: OfferState) -> str:
    if state is OfferState.EXPIRED or terms.validity.is_expired_at(instant):
        return "expired"
    return "valid"


def _buyer_transaction_result(session: GoldenPathSession, offer_id: str) -> str:
    if (
        session.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED
        and session.acceptance is not None
        and session.acceptance.offer_id.to_primitive() == offer_id
    ):
        return "authorized_simulated"
    return "simulated"


def _offer_for_acceptance(session: GoldenPathSession) -> MappedOffer:
    if session.acceptance is None:
        raise ApplicationError("acceptanceId", "required")
    selected = next(
        (
            item
            for item in session.mapped_offers
            if item.offer.offer_id == session.acceptance.offer_id
        ),
        None,
    )
    if selected is None:
        raise ApplicationError("offerId", "ineligible")
    return selected


def _assert_authorization_match(
    session: GoldenPathSession, command: AuthorizeCommand, selected: MappedOffer
) -> None:
    if session.acceptance is None:
        raise ApplicationError("acceptanceId", "required")
    if command.acceptance_id != session.acceptance.acceptance_id.to_primitive():
        raise ApplicationError("acceptanceId", "mismatch")
    if command.supplier_token != selected.offer.supplier_token.to_primitive():
        raise ApplicationError("supplierToken", "mismatch")
    terms = _require_terms(selected.offer)
    price = terms.price.total
    if command.amount_minor != price.amount_minor:
        raise ApplicationError("amountMinor", "mismatch")
    if command.currency != price.currency:
        raise ApplicationError("currency", "mismatch")
    current = offer_terms_hash(terms)
    if session.acceptance.accepted_terms_hash != current:
        raise ApplicationError("termsHash", "mismatch")


def _actor(command: GovernanceCommand) -> ActorRef:
    return ActorRef(ActorType.BUYER, ActorId(command.actor_id))


def _request_from(grant: ApprovalGrant, occurred: datetime) -> ApprovalRequest:
    return ApprovalRequest(
        kind=grant.kind,
        purpose=grant.purpose,
        actor=grant.actor,
        owner_id=grant.owner_id,
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        resource_version=grant.resource_version,
        payload_hash=grant.payload_hash,
        occurred_at=occurred,
        content_hash=grant.content_hash,
        manifest_hash=grant.manifest_hash,
        recipient_count=grant.recipient_count,
        solicitation_expires_at=grant.solicitation_expires_at,
        intent_id=grant.intent_id,
        offer_id=grant.offer_id,
        offer_version=grant.offer_version,
        terms_hash=grant.terms_hash,
        offer_valid_until=grant.offer_valid_until,
        acceptance_id=grant.acceptance_id,
        action=grant.action,
        amount_minor=grant.amount_minor,
        currency=grant.currency,
        supplier_token=grant.supplier_token,
        mode=grant.mode,
        request_hash=grant.request_hash,
        decision_expires_at=grant.decision_expires_at,
    )


def _freeze_intent(payload: Mapping[str, object]) -> MappingProxyType[str, object]:
    if not isinstance(payload, Mapping):
        raise ApplicationError("payload", "must_be_object")
    frozen = freeze_payload(dict(payload))
    if not isinstance(frozen, Mapping):
        raise ApplicationError("payload", "must_be_object")
    return frozen  # type: ignore[return-value]


def _require_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ApplicationError(field, "required")
    return value


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ApplicationError(field, "required")
    return value


def _require_int(value: object, field: str) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise ApplicationError(field, "must_be_integer")
    return value


def map_closed_error(exc: Exception) -> ApplicationError:
    if isinstance(exc, ApplicationError):
        return exc
    if isinstance(exc, PolicyConflictError):
        return ApplicationError(exc.field, exc.code)
    if isinstance(exc, PolicyError):
        return ApplicationError(exc.field, exc.code)
    if isinstance(exc, InvalidTransitionError | DuplicateActionError | VersionConflictError):
        return ApplicationError("state", "illegal_state")
    if isinstance(exc, ExpiredResourceError):
        return ApplicationError("state", "expired")
    if isinstance(exc, OfferVersionMismatchError):
        return ApplicationError("offerVersion", "stale_version")
    if isinstance(exc, DomainInvariantError):
        return ApplicationError(exc.field, exc.code)
    return ApplicationError("internal", "closed")


def http_status_for(error: ApplicationError) -> int:
    if error.code in {
        "unknown_resource",
        "missing",
    }:
        return 404
    if error.code in {
        "illegal_state",
        "stale_version",
        "duplicate",
        "request_mismatch",
        "conflict",
        "completion_mismatch",
        "already_completed",
        "in_progress",
        "approval_reused",
    }:
        return 409
    if error.code in {
        "approval_denied",
        "mode_forbidden",
        "ineligible",
        "expired",
        "inactive",
        "kind_mismatch",
        "purpose_mismatch",
        "actor_mismatch",
        "owner_mismatch",
        "hash_mismatch",
        "must_be_simulated",
        "must_be_reserve_parking",
    }:
        return 422
    if error.code in {"closed", "injected_fault"} or error.field == "internal":
        return 500
    return 400


def default_clock(instant: datetime) -> FrozenClock:
    return FrozenClock(instant)
