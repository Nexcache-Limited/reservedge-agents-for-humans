"""Cloud-neutral ITAA domain kernel.

Entities, value objects, state machines, and redaction-safe domain events.
This package performs no I/O and imports no providers, frameworks, or generated
contract models.
"""

from __future__ import annotations

from itaa_domain.acceptance import Acceptance
from itaa_domain.booking_task_states import (
    ATTENTION_STATES,
    BOOKING_TASK_TRANSITIONS,
    IN_PROGRESS_STATES,
    LIVE_ONLY_STATES,
    OFFER_READY_STATES,
    SIMULATION_FORBIDDEN_STATES,
    SIMULATION_TERMINAL_STATES,
    BookingTaskAction,
    BookingTaskState,
    apply_booking_task_transition,
)
from itaa_domain.errors import (
    DomainInvariantError,
    DuplicateActionError,
    ExpiredResourceError,
    InvalidTransitionError,
    OfferVersionMismatchError,
    VersionConflictError,
)
from itaa_domain.events import DomainEvent, EventSpec, EventType, FieldPresence, ResourceType
from itaa_domain.identifiers import (
    AcceptanceId,
    ActorId,
    ApprovalId,
    AuthorizationId,
    BookingTaskId,
    BuyerToken,
    CorrelationId,
    CounterOfferId,
    IdempotencyKey,
    IntentId,
    LedgerId,
    OfferId,
    OrchestrationIntentId,
    PlanId,
    RequirementId,
    SignatureHandle,
    SupplierToken,
)
from itaa_domain.intent_states import (
    IntentState,
    ParentLifecycle,
    TaskMembership,
    TaskProjectionInput,
    project_intent_state,
)
from itaa_domain.offer import (
    OFFER_TERMINAL,
    OFFER_TRANSITIONS,
    Offer,
    OfferAction,
    OfferEvidence,
    OfferPrice,
    OfferState,
    OfferTerms,
)
from itaa_domain.protocol import TransitionRequest, TransitionResult
from itaa_domain.purchase_intent import (
    PURCHASE_INTENT_TERMINAL,
    PURCHASE_INTENT_TRANSITIONS,
    PurchaseIntent,
    PurchaseIntentAction,
    PurchaseIntentState,
)
from itaa_domain.requirement import Requirement
from itaa_domain.transaction import (
    TRANSACTION_TERMINAL,
    TRANSACTION_TRANSITIONS,
    AuthorizationReceipt,
    Transaction,
    TransactionAction,
    TransactionState,
)
from itaa_domain.value_objects import (
    ActorRef,
    ActorType,
    AirportCode,
    Money,
    PayloadHash,
    TimeWindow,
    Version,
)

PACKAGE_NAME = "itaa-domain"
PACKAGE_ROLE = "cloud-neutral-domain"

__all__ = [
    "PACKAGE_NAME",
    "PACKAGE_ROLE",
    "Acceptance",
    "AcceptanceId",
    "ATTENTION_STATES",
    "ActorId",
    "ActorRef",
    "ActorType",
    "AirportCode",
    "ApprovalId",
    "AuthorizationId",
    "AuthorizationReceipt",
    "BOOKING_TASK_TRANSITIONS",
    "BookingTaskAction",
    "BookingTaskId",
    "BookingTaskState",
    "BuyerToken",
    "CorrelationId",
    "CounterOfferId",
    "DomainEvent",
    "DomainInvariantError",
    "DuplicateActionError",
    "EventSpec",
    "EventType",
    "ExpiredResourceError",
    "FieldPresence",
    "IN_PROGRESS_STATES",
    "IdempotencyKey",
    "IntentId",
    "IntentState",
    "InvalidTransitionError",
    "LIVE_ONLY_STATES",
    "LedgerId",
    "Money",
    "OFFER_TERMINAL",
    "OFFER_TRANSITIONS",
    "Offer",
    "OfferAction",
    "OfferEvidence",
    "OfferId",
    "OfferPrice",
    "OfferState",
    "OfferTerms",
    "OFFER_READY_STATES",
    "OfferVersionMismatchError",
    "OrchestrationIntentId",
    "PURCHASE_INTENT_TERMINAL",
    "ParentLifecycle",
    "PlanId",
    "PURCHASE_INTENT_TRANSITIONS",
    "PayloadHash",
    "PurchaseIntent",
    "PurchaseIntentAction",
    "PurchaseIntentState",
    "Requirement",
    "RequirementId",
    "ResourceType",
    "SIMULATION_FORBIDDEN_STATES",
    "SIMULATION_TERMINAL_STATES",
    "SignatureHandle",
    "SupplierToken",
    "TRANSACTION_TERMINAL",
    "TRANSACTION_TRANSITIONS",
    "TaskMembership",
    "TaskProjectionInput",
    "TimeWindow",
    "Transaction",
    "TransactionAction",
    "TransactionState",
    "TransitionRequest",
    "TransitionResult",
    "Version",
    "VersionConflictError",
    "apply_booking_task_transition",
    "project_intent_state",
]
