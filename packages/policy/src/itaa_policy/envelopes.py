"""Supplier-specific envelopes and exact dispatch-manifest binding."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import ActorId, BuyerToken, IntentId, SupplierToken
from itaa_domain.value_objects import ActorRef, PayloadHash, Version, parse_utc, require_utc
from itaa_policy.approvals import (
    ApprovalDecision,
    ApprovalGrant,
    ApprovalKind,
    ApprovalPurpose,
    ApprovalRequest,
    ApprovalResourceType,
    validate_approval,
)
from itaa_policy.canonical import (
    SEPARATOR_DISCLOSURE_MANIFEST,
    SEPARATOR_SUPPLIER_ENVELOPE,
    hash_canonical,
)
from itaa_policy.disclosure import (
    MAX_RECIPIENTS,
    PROFILE_ID,
    DisclosurePreview,
    DisclosurePurpose,
    _copy_mapping,
    inspect_parking_v1,
)
from itaa_policy.errors import PolicyError
from itaa_policy.isolation import (
    SupplierCapability,
    SupplierInvitationToken,
    SupplierPrincipal,
    SupplierResourceScope,
    authorize_supplier,
)

_RECIPIENT_ROW_KEYS: Final[tuple[str, ...]] = (
    "supplierToken",
    "invitationToken",
    "scopedIntentId",
    "scopedBuyerToken",
    "envelopeHash",
)
_OPAQUE_CODES: Final[frozenset[str]] = frozenset(
    {"invalid_opaque_syntax", "must_be_string", "invalid_sha256_shape"}
)


@dataclass(frozen=True, slots=True)
class RecipientAssignment:
    supplier_token: SupplierToken
    invitation: SupplierInvitationToken
    scoped_intent_id: IntentId
    scoped_buyer_token: BuyerToken
    valid_from: datetime
    valid_until: datetime
    capabilities: frozenset[SupplierCapability]

    def __post_init__(self) -> None:
        if not isinstance(self.supplier_token, SupplierToken):
            raise PolicyError("supplier_token", "invalid_opaque_syntax")
        if not isinstance(self.invitation, SupplierInvitationToken):
            raise PolicyError("invitation_token", "invalid_opaque_syntax")
        if not isinstance(self.scoped_intent_id, IntentId):
            raise PolicyError("scoped_intent_id", "invalid_opaque_syntax")
        if not isinstance(self.scoped_buyer_token, BuyerToken):
            raise PolicyError("scoped_buyer_token", "invalid_opaque_syntax")
        require_utc(self.valid_from, "valid_from")
        require_utc(self.valid_until, "valid_until")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))


@dataclass(frozen=True, slots=True)
class SupplierEnvelope:
    assignment: RecipientAssignment
    payload: MappingProxyType[str, object]
    content_hash: PayloadHash
    envelope_hash: PayloadHash
    scope: SupplierResourceScope

    def __post_init__(self) -> None:
        if type(self.assignment) is not RecipientAssignment:
            raise PolicyError("assignment", "invalid_type")
        if type(self.scope) is not SupplierResourceScope:
            raise PolicyError("scope", "invalid_type")
        _assert_envelope_consistency(self)

    def payload_dict(self) -> dict[str, object]:
        return _copy_mapping(self.payload)


@dataclass(frozen=True, slots=True)
class EnvelopeManifest:
    content_hash: PayloadHash
    intent_resource_id: IntentId
    intent_resource_version: Version
    purpose: DisclosurePurpose
    expires_at: str
    recipients: tuple[dict[str, str], ...]
    manifest_hash: PayloadHash


@dataclass(frozen=True, slots=True)
class SolicitationBinding:
    preview: DisclosurePreview
    envelopes: tuple[SupplierEnvelope, ...]
    manifest: EnvelopeManifest


def bind_solicitation(
    source: Mapping[str, object],
    *,
    intent_resource_id: IntentId,
    intent_resource_version: Version,
    purpose: DisclosurePurpose,
    expires_at: datetime,
    recipients: Sequence[RecipientAssignment],
) -> SolicitationBinding:
    assigned = tuple(recipients)
    if not assigned or len(assigned) > MAX_RECIPIENTS:
        raise PolicyError("recipients", "count_out_of_range")
    _assert_unique(assigned)
    _, seed_preview = inspect_parking_v1(
        source,
        intent_resource_id=intent_resource_id,
        intent_resource_version=intent_resource_version,
        purpose=purpose,
        expires_at=expires_at,
    )
    envelopes: list[SupplierEnvelope] = []
    for assignment in sorted(assigned, key=lambda item: item.supplier_token.to_primitive()):
        envelope = _build_envelope(source, assignment, seed_preview.content_hash)
        if envelope.content_hash != seed_preview.content_hash:
            raise PolicyError("content_hash", "mismatch")
        envelopes.append(envelope)
    _assert_identical_content(envelopes)
    recipient_rows = tuple(
        {
            "supplierToken": item.assignment.supplier_token.to_primitive(),
            "invitationToken": item.assignment.invitation.to_primitive(),
            "scopedIntentId": item.assignment.scoped_intent_id.to_primitive(),
            "scopedBuyerToken": item.assignment.scoped_buyer_token.to_primitive(),
            "envelopeHash": item.envelope_hash.to_primitive(),
        }
        for item in envelopes
    )
    manifest_material = {
        "contentHash": seed_preview.content_hash.to_primitive(),
        "intentResourceId": intent_resource_id.to_primitive(),
        "intentResourceVersion": intent_resource_version.to_primitive(),
        "purpose": purpose.value,
        "expiresAt": seed_preview.expires_at,
        "recipients": list(recipient_rows),
    }
    manifest_hash = hash_canonical(SEPARATOR_DISCLOSURE_MANIFEST, manifest_material)
    _, preview = inspect_parking_v1(
        source,
        intent_resource_id=intent_resource_id,
        intent_resource_version=intent_resource_version,
        purpose=purpose,
        expires_at=expires_at,
        recipient_count=len(envelopes),
        manifest_hash=manifest_hash,
    )
    manifest = EnvelopeManifest(
        content_hash=seed_preview.content_hash,
        intent_resource_id=intent_resource_id,
        intent_resource_version=intent_resource_version,
        purpose=purpose,
        expires_at=seed_preview.expires_at,
        recipients=recipient_rows,
        manifest_hash=manifest_hash,
    )
    return SolicitationBinding(preview=preview, envelopes=tuple(envelopes), manifest=manifest)


@dataclass(frozen=True, slots=True)
class DispatchAuthorization:
    allowed: bool
    decision: ApprovalDecision
    envelope: SupplierEnvelope | None

    def __post_init__(self) -> None:
        if self.allowed is not self.decision.allowed:
            raise PolicyError("allowed", "decision_mismatch")
        if self.allowed:
            if self.envelope is None:
                raise PolicyError("envelope", "required")
            return
        if self.envelope is not None:
            raise PolicyError("envelope", "must_be_absent")


def verify_dispatch(
    binding: SolicitationBinding,
    *,
    supplier_token: SupplierToken,
    purpose: DisclosurePurpose,
    intent_resource_version: Version,
    occurred_at: datetime,
) -> SupplierEnvelope:
    """Verify envelope membership, the approved recipient set, and live window.

    This is not dispatch authorization.
    """
    instant = require_utc(occurred_at, "occurred_at")
    if purpose is not binding.manifest.purpose:
        raise PolicyError("purpose", "mismatch")
    if intent_resource_version != binding.manifest.intent_resource_version:
        raise PolicyError("intent_resource_version", "mismatch")
    if binding.preview.recipient_count != len(binding.envelopes):
        raise PolicyError("recipient_count", "mismatch")
    if binding.preview.manifest_hash != binding.manifest.manifest_hash:
        raise PolicyError("manifest_hash", "mismatch")
    match = next(
        (item for item in binding.envelopes if item.assignment.supplier_token == supplier_token),
        None,
    )
    if match is None:
        raise PolicyError("supplier_token", "not_in_manifest")
    _assert_envelope_consistency(match, supplier_token=supplier_token)
    recomputed = hash_canonical(SEPARATOR_SUPPLIER_ENVELOPE, match.payload_dict())
    if recomputed != match.envelope_hash:
        raise PolicyError("envelope_hash", "mismatch")
    if match.content_hash != binding.manifest.content_hash:
        raise PolicyError("content_hash", "mismatch")
    disclosure = match.payload["disclosure"]
    if not isinstance(disclosure, Mapping):
        raise PolicyError("disclosure", "must_be_object")
    if disclosure.get("approvedPayloadHash") != match.content_hash.to_primitive():
        raise PolicyError("approved_payload_hash", "mismatch")
    if disclosure.get("profile") != PROFILE_ID:
        raise PolicyError("disclosure_profile", "mismatch")
    if instant < match.assignment.valid_from:
        raise PolicyError("envelope", "not_yet_valid")
    if instant >= match.assignment.valid_until:
        raise PolicyError("envelope", "expired")
    expires_at = match.payload["expiresAt"]
    if not isinstance(expires_at, str):
        raise PolicyError("expires_at", "invalid_value")
    if instant >= parse_utc(expires_at, "expires_at"):
        raise PolicyError("approval", "expired")
    membership = {
        "contentHash": binding.manifest.content_hash.to_primitive(),
        "intentResourceId": binding.manifest.intent_resource_id.to_primitive(),
        "intentResourceVersion": binding.manifest.intent_resource_version.to_primitive(),
        "purpose": binding.manifest.purpose.value,
        "expiresAt": binding.manifest.expires_at,
        "recipients": list(binding.manifest.recipients),
    }
    if hash_canonical(SEPARATOR_DISCLOSURE_MANIFEST, membership) != binding.manifest.manifest_hash:
        raise PolicyError("manifest_hash", "mismatch")
    _require_manifest_set_binding(binding, match)
    return match


def authorize_dispatch(
    grant: ApprovalGrant | None,
    *,
    binding: SolicitationBinding,
    supplier_token: SupplierToken,
    occurred_at: datetime,
    actor: ActorRef,
    owner_id: ActorId,
) -> DispatchAuthorization:
    """Evaluate a supplied A2 grant snapshot plus envelope/scope binding.

    This does not read a repository and does not prove revocation. The
    application authorization boundary is ``DispatchService.authorize``.
    """

    try:
        solicitation = parse_utc(binding.manifest.expires_at, "expires_at")
    except DomainInvariantError as exc:
        raise PolicyError("expires_at", "invalid_value") from exc
    request = ApprovalRequest(
        kind=ApprovalKind.PURCHASE_INTENT_DISPATCH,
        purpose=ApprovalPurpose.PURCHASE_INTENT_DISPATCH,
        actor=actor,
        owner_id=owner_id,
        resource_type=ApprovalResourceType.PURCHASE_INTENT,
        resource_id=binding.manifest.intent_resource_id.to_primitive(),
        resource_version=binding.manifest.intent_resource_version,
        payload_hash=binding.manifest.manifest_hash,
        occurred_at=occurred_at,
        content_hash=binding.manifest.content_hash,
        manifest_hash=binding.manifest.manifest_hash,
        recipient_count=len(binding.envelopes),
        solicitation_expires_at=solicitation,
    )
    decision = validate_approval(grant, request)
    if not decision.allowed:
        return DispatchAuthorization(False, decision, None)
    envelope = verify_dispatch(
        binding,
        supplier_token=supplier_token,
        purpose=binding.manifest.purpose,
        intent_resource_version=binding.manifest.intent_resource_version,
        occurred_at=occurred_at,
    )
    _assert_envelope_consistency(envelope, supplier_token=supplier_token)
    isolation = authorize_supplier(
        granted=envelope.scope,
        principal=SupplierPrincipal(supplier_token),
        invitation=envelope.assignment.invitation,
        intent_id=envelope.assignment.scoped_intent_id,
        capability=SupplierCapability.INVITATION_READ,
        occurred_at=occurred_at,
    )
    if not isolation.allowed:
        raise PolicyError("scope", isolation.reason.value)
    return DispatchAuthorization(True, decision, envelope)


def _build_envelope(
    source: Mapping[str, object],
    assignment: RecipientAssignment,
    content_hash: PayloadHash,
) -> SupplierEnvelope:
    payload, _preview = inspect_parking_v1(
        source,
        intent_resource_id=assignment.scoped_intent_id,
        intent_resource_version=Version(1),
        purpose=DisclosurePurpose.PURCHASE_INTENT_DISPATCH,
        expires_at=assignment.valid_until,
    )
    del _preview
    envelope_payload = _copy_mapping(payload)
    envelope_payload["intentId"] = assignment.scoped_intent_id.to_primitive()
    envelope_payload["buyerToken"] = assignment.scoped_buyer_token.to_primitive()
    disclosure = envelope_payload.get("disclosure")
    if not isinstance(disclosure, dict):
        raise PolicyError("disclosure", "must_be_object")
    disclosure["approvedPayloadHash"] = content_hash.to_primitive()
    envelope_hash = hash_canonical(SEPARATOR_SUPPLIER_ENVELOPE, envelope_payload)
    forbidden_keys = {"recipientCount", "competitor", "otherSupplier", "envelopeHash"}
    _reject_leaks(envelope_payload, forbidden_keys)
    scope = SupplierResourceScope(
        principal=SupplierPrincipal(assignment.supplier_token),
        invitation=assignment.invitation,
        intent_id=assignment.scoped_intent_id,
        capabilities=assignment.capabilities,
        valid_from=assignment.valid_from,
        valid_until=assignment.valid_until,
    )
    return SupplierEnvelope(
        assignment=assignment,
        payload=MappingProxyType(envelope_payload),
        content_hash=content_hash,
        envelope_hash=envelope_hash,
        scope=scope,
    )


@dataclass(frozen=True, slots=True)
class _BoundRecipientRow:
    supplier_token: SupplierToken
    invitation: SupplierInvitationToken
    scoped_intent_id: IntentId
    scoped_buyer_token: BuyerToken
    envelope_hash: PayloadHash


def _opaque_value[T](field: str, constructor: Callable[[str], T], value: str) -> T:
    try:
        return constructor(value)
    except (DomainInvariantError, PolicyError) as exc:
        code = exc.code if exc.code in _OPAQUE_CODES else "invalid_opaque_syntax"
        raise PolicyError(field, code) from exc


def _parse_recipient_row(row: object) -> _BoundRecipientRow:
    if not isinstance(row, Mapping):
        raise PolicyError("recipient_row", "invalid_shape")
    keys = list(row)
    if any(not isinstance(key, str) for key in keys):
        raise PolicyError("recipient_row", "invalid_shape")
    allowed = set(_RECIPIENT_ROW_KEYS)
    if set(keys) - allowed:
        raise PolicyError("recipient_row", "unknown_field")
    if allowed - set(keys):
        raise PolicyError("recipient_row", "invalid_shape")
    values: dict[str, str] = {}
    for key in _RECIPIENT_ROW_KEYS:
        value = row[key]
        if type(value) is not str:
            raise PolicyError("recipient_row", "invalid_shape")
        values[key] = value
    return _BoundRecipientRow(
        supplier_token=_opaque_value("supplier_token", SupplierToken, values["supplierToken"]),
        invitation=_opaque_value(
            "invitation_token", SupplierInvitationToken, values["invitationToken"]
        ),
        scoped_intent_id=_opaque_value("scoped_intent_id", IntentId, values["scopedIntentId"]),
        scoped_buyer_token=_opaque_value(
            "scoped_buyer_token", BuyerToken, values["scopedBuyerToken"]
        ),
        envelope_hash=_opaque_value("envelope_hash", PayloadHash, values["envelopeHash"]),
    )


def _require_unique(values: Sequence[str], field: str) -> None:
    if len(set(values)) != len(values):
        raise PolicyError(field, "duplicate")


def _envelope_bound_row(envelope: SupplierEnvelope) -> _BoundRecipientRow:
    assignment = envelope.assignment
    return _BoundRecipientRow(
        supplier_token=assignment.supplier_token,
        invitation=assignment.invitation,
        scoped_intent_id=assignment.scoped_intent_id,
        scoped_buyer_token=assignment.scoped_buyer_token,
        envelope_hash=envelope.envelope_hash,
    )


def _require_row_matches_envelope(row: _BoundRecipientRow, envelope: SupplierEnvelope) -> None:
    expected = _envelope_bound_row(envelope)
    if row.supplier_token != expected.supplier_token:
        raise PolicyError("supplier_token", "mismatch")
    if row.invitation != expected.invitation:
        raise PolicyError("invitation_token", "mismatch")
    if row.scoped_intent_id != expected.scoped_intent_id:
        raise PolicyError("scoped_intent_id", "mismatch")
    if row.scoped_buyer_token != expected.scoped_buyer_token:
        raise PolicyError("scoped_buyer_token", "mismatch")
    if row.envelope_hash != expected.envelope_hash:
        raise PolicyError("envelope_hash", "mismatch")


def _require_manifest_set_binding(binding: SolicitationBinding, selected: SupplierEnvelope) -> None:
    rows = tuple(_parse_recipient_row(row) for row in binding.manifest.recipients)
    envelopes = binding.envelopes
    if len(rows) != len(envelopes) or len(rows) != binding.preview.recipient_count:
        raise PolicyError("recipient_count", "mismatch")
    _require_unique([row.supplier_token.to_primitive() for row in rows], "supplier_token")
    _require_unique([row.invitation.to_primitive() for row in rows], "invitation_token")
    _require_unique([row.scoped_intent_id.to_primitive() for row in rows], "scoped_intent_id")
    _require_unique([row.scoped_buyer_token.to_primitive() for row in rows], "scoped_buyer_token")
    _require_unique([row.envelope_hash.to_primitive() for row in rows], "envelope_hash")
    _require_unique(
        [item.assignment.supplier_token.to_primitive() for item in envelopes], "supplier_token"
    )
    _require_unique(
        [item.assignment.invitation.to_primitive() for item in envelopes], "invitation_token"
    )
    _require_unique(
        [item.assignment.scoped_intent_id.to_primitive() for item in envelopes],
        "scoped_intent_id",
    )
    _require_unique(
        [item.assignment.scoped_buyer_token.to_primitive() for item in envelopes],
        "scoped_buyer_token",
    )
    _require_unique([item.envelope_hash.to_primitive() for item in envelopes], "envelope_hash")
    rows_by_supplier = {row.supplier_token: row for row in rows}
    for envelope in envelopes:
        _assert_envelope_consistency(envelope)
        recomputed = hash_canonical(SEPARATOR_SUPPLIER_ENVELOPE, envelope.payload_dict())
        if recomputed != envelope.envelope_hash:
            raise PolicyError("envelope_hash", "mismatch")
        if envelope.content_hash != binding.manifest.content_hash:
            raise PolicyError("content_hash", "mismatch")
        row = rows_by_supplier.get(envelope.assignment.supplier_token)
        if row is None:
            raise PolicyError("recipient_row", "missing")
        _require_row_matches_envelope(row, envelope)
    selected_row = rows_by_supplier.get(selected.assignment.supplier_token)
    if selected_row is None:
        raise PolicyError("recipient_row", "missing")
    _require_row_matches_envelope(selected_row, selected)


def _assert_envelope_consistency(
    envelope: SupplierEnvelope,
    *,
    supplier_token: SupplierToken | None = None,
) -> None:
    assignment = envelope.assignment
    scope = envelope.scope
    if assignment.supplier_token != scope.principal.supplier_token:
        raise PolicyError("supplier_token", "assignment_scope_mismatch")
    if assignment.invitation != scope.invitation:
        raise PolicyError("invitation", "assignment_scope_mismatch")
    if assignment.scoped_intent_id != scope.intent_id:
        raise PolicyError("scoped_intent_id", "assignment_scope_mismatch")
    if assignment.valid_from != scope.valid_from or assignment.valid_until != scope.valid_until:
        raise PolicyError("validity_window", "assignment_scope_mismatch")
    if assignment.capabilities != scope.capabilities:
        raise PolicyError("capabilities", "assignment_scope_mismatch")
    if envelope.payload.get("intentId") != assignment.scoped_intent_id.to_primitive():
        raise PolicyError("scoped_intent_id", "payload_mismatch")
    if envelope.payload.get("buyerToken") != assignment.scoped_buyer_token.to_primitive():
        raise PolicyError("scoped_buyer_token", "payload_mismatch")
    if supplier_token is not None and (
        supplier_token != assignment.supplier_token
        or supplier_token != scope.principal.supplier_token
    ):
        raise PolicyError("supplier_token", "mismatch")


def _assert_unique(recipients: Sequence[RecipientAssignment]) -> None:
    suppliers = [item.supplier_token.to_primitive() for item in recipients]
    invitations = [item.invitation.to_primitive() for item in recipients]
    intents = [item.scoped_intent_id.to_primitive() for item in recipients]
    buyers = [item.scoped_buyer_token.to_primitive() for item in recipients]
    if len(set(suppliers)) != len(suppliers):
        raise PolicyError("supplier_token", "duplicate")
    if len(set(invitations)) != len(invitations):
        raise PolicyError("invitation_token", "duplicate")
    if len(set(intents)) != len(intents):
        raise PolicyError("scoped_intent_id", "duplicate")
    if len(set(buyers)) != len(buyers):
        raise PolicyError("scoped_buyer_token", "duplicate")


def _assert_identical_content(envelopes: Sequence[SupplierEnvelope]) -> None:
    if not envelopes:
        return
    first = _content_view(envelopes[0].payload_dict())
    for item in envelopes[1:]:
        if _content_view(item.payload_dict()) != first:
            raise PolicyError("envelope", "content_mismatch")
        if item.envelope_hash == envelopes[0].envelope_hash:
            raise PolicyError("envelope_hash", "must_differ")


def _content_view(payload: Mapping[str, object]) -> dict[str, object]:
    copied = _copy_mapping(payload)
    copied.pop("intentId", None)
    copied.pop("buyerToken", None)
    return copied


def _reject_leaks(payload: Mapping[str, object], forbidden: set[str]) -> None:
    for key, value in payload.items():
        token = "".join(char for char in key.lower() if char.isalnum())
        if key in forbidden or token in {"recipientcount", "competitor", "envelopehash"}:
            raise PolicyError("envelope", "forbidden_field")
        if isinstance(value, Mapping):
            _reject_leaks(value, forbidden)
