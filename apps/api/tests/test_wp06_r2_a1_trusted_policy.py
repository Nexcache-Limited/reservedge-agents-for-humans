"""WP-06-R2-A1: independent trusted policy and unique generated identities."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from threading import Barrier, Lock, Thread

import pytest
from fastapi.testclient import TestClient
from wp04_helpers import BUYER, CREATED_AT, EXPIRES_AT, OCCURRED_AT, OWNER
from wp05_helpers import collected_offer, scoped_fixture
from wp06_fakes import jfk_payload

from itaa_api.app import create_app
from itaa_api.composition import (
    GoldenPathPolicyPort,
    SeededRoster,
    SequentialIdFactory,
    build_facade,
)
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import _select_offer
from itaa_application.offer_boundary import accept_offer
from itaa_application.session_models import (
    AcceptCommand,
    AuthorizeCommand,
    BuyerSessionState,
    GovernanceCommand,
)
from itaa_application.supplier_port import SupplierAttempt, SupplierPort, SupplierTerminal
from itaa_domain.identifiers import IntentId, SupplierToken
from itaa_domain.value_objects import LotType, format_utc
from itaa_observability.audit import AuditResourceType
from itaa_supplier_simulator.canonical import canonical_golden_ports, canonical_trusted_specs
from itaa_supplier_simulator.policy import PARKDIRECT, SKYSHIELD, TERMINALFLEX

PREFIX = "/v1/simulations/airport-parking"
SKY = SKYSHIELD.supplier_token.to_primitive()
PARK = PARKDIRECT.supplier_token.to_primitive()
UNKNOWN = SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2zz")
_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
_SEQ = 8_000


def _opaque(prefix: str) -> str:
    global _SEQ
    _SEQ += 1
    value = _SEQ
    body = ["0"] * 26
    for index in range(25, -1, -1):
        body[index] = _CROCKFORD[value % 32]
        value //= 32
    return prefix + "".join(body)


def _intent_payload() -> dict[str, object]:
    payload = deepcopy(jfk_payload())
    payload["intentId"] = _opaque("pi_")
    payload["buyerToken"] = _opaque("bs_")
    return payload


def _gov() -> GovernanceCommand:
    return GovernanceCommand(
        actor_id=BUYER.actor_id.to_primitive(),
        owner_id=OWNER.to_primitive(),
        approval_id=_opaque("ap_"),
        correlation_id=_opaque("cr_"),
        issued_at=CREATED_AT,
        expires_at=EXPIRES_AT,
    )


def _http_gov() -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": _opaque("ap_"),
        "correlationId": _opaque("cr_"),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def _dispatch(facade: object) -> tuple[IntentId, object]:
    payload = _intent_payload()
    created = facade.create_purchase_intent(payload)  # type: ignore[attr-defined]
    intent = IntentId(created.intent_id)
    facade.confirm_requirement(intent, _gov())  # type: ignore[attr-defined]
    return intent, facade.approve_and_dispatch(intent, _gov())  # type: ignore[attr-defined]


def _assert_closed(exc: ApplicationError, field: str, code: str, *forbidden: object) -> None:
    assert exc.field == field
    assert exc.code == code
    text = str(exc)
    assert text == f"{field}: {code}"
    for item in forbidden:
        if item is None:
            continue
        assert str(item) not in text


def _sky_binding() -> tuple[dict[str, object], object, object]:
    payload, binding = scoped_fixture("offer-skyshield.json")
    policy = GoldenPathPolicyPort().evaluate(
        binding.supplier_token,
        scoped_intent_id=binding.scoped_intent_id,
        offer_payload=payload,
    )
    return payload, binding, policy


def test_trusted_specs_load_from_fixture_json_at_import() -> None:
    specs = canonical_trusted_specs()
    sky = specs[SKYSHIELD.supplier_token]
    park = specs[PARKDIRECT.supplier_token]
    flex = specs[TERMINALFLEX.supplier_token]
    assert sky.floor_minor_per_day == 11900
    assert park.floor_minor_per_day == 9800
    assert flex.floor_minor_per_day == 13500
    assert sky.fees_minor == 1800
    assert sky.tax_minor == 1100
    assert sky.billable_days == 1
    assert sky.add_on_price_minor == 0
    assert LotType.COVERED in sky.lot_types
    assert sky.supplier_token == SKYSHIELD.supplier_token


def test_evaluate_ignores_dirty_payload_and_matches_clean() -> None:
    payload, binding, _policy = _sky_binding()
    dirty = deepcopy(payload)
    dirty["supplierToken"] = PARK
    dirty["service"]["lotType"] = "garage"
    dirty["service"]["addOns"] = ["ev_charging", "indoor_walkway"]
    dirty["service"]["availability"] = "limited_simulated"
    dirty["evidence"] = [{"type": "rate_card", "ref": "policy.skyshield.v9"}]
    dirty["price"]["feesMinor"] = 1
    dirty["price"]["taxMinor"] = 2
    dirty["price"]["subtotalMinor"] = 100
    dirty["price"]["totalMinor"] = 103
    dirty["terms"]["cancellation"] = "non_refundable"
    dirty["terms"]["refund"] = "none"
    dirty["validUntil"] = "2026-08-20T16:01:00Z"
    port = GoldenPathPolicyPort()
    clean = port.evaluate(
        binding.supplier_token,
        scoped_intent_id=binding.scoped_intent_id,
        offer_payload=payload,
    )
    mutated = port.evaluate(
        binding.supplier_token,
        scoped_intent_id=binding.scoped_intent_id,
        offer_payload=dirty,
    )
    assert clean == mutated
    assert clean.fees_minor == 1800
    assert clean.tax_minor == 1100
    assert clean.floor_minor_per_day == 11900
    assert LotType.COVERED in clean.lot_types
    assert clean.supplier_token == SKYSHIELD.supplier_token
    assert clean.supplier_token != PARKDIRECT.supplier_token
    assert str(clean) == str(mutated)


def test_unknown_supplier_evaluate_fails_closed() -> None:
    payload, binding = scoped_fixture("offer-skyshield.json")
    with pytest.raises(ApplicationError) as caught:
        GoldenPathPolicyPort().evaluate(
            UNKNOWN,
            scoped_intent_id=binding.scoped_intent_id,
            offer_payload=payload,
        )
    _assert_closed(
        caught.value,
        "supplierToken",
        "unknown",
        UNKNOWN.to_primitive(),
        SKY,
        payload.get("offerId"),
    )


def test_mutation_supplier_identity_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["supplierToken"] = PARK
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "supplierToken", "mismatch", PARK, SKY, mutated.get("offerId"))


def test_mutation_lot_type_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["service"]["lotType"] = "garage"
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "lotType", "unsupported", "garage", SKY)


def test_mutation_addons_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["service"]["addOns"] = ["ev_charging", "indoor_walkway"]
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "addOns", "unsupported", "indoor_walkway", SKY)


def test_mutation_availability_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["service"]["availability"] = "limited_simulated"
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "availability", "unsupported", "limited_simulated", SKY)


def test_mutation_evidence_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["evidence"] = [{"type": "rate_card", "ref": "policy.skyshield.v9"}]
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "evidence", "mismatch", "policy.skyshield.v9", "rate_card", SKY)


def test_mutation_fees_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["price"]["feesMinor"] = 1
    mutated["price"]["totalMinor"] = (
        int(mutated["price"]["subtotalMinor"]) + 1 + int(mutated["price"]["taxMinor"])
    )
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "feesMinor", "mismatch", "1801", SKY)


def test_mutation_tax_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["price"]["taxMinor"] = 2
    mutated["price"]["totalMinor"] = (
        int(mutated["price"]["subtotalMinor"]) + int(mutated["price"]["feesMinor"]) + 2
    )
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "taxMinor", "mismatch", SKY)


def test_mutation_cancellation_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["terms"]["cancellation"] = "free_until_48h"
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "cancellation", "unsupported", "free_until_48h", SKY)


def test_mutation_refund_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["terms"]["refund"] = "none"
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "refund", "unsupported", "none", SKY)


def test_mutation_validity_too_short_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["validUntil"] = "2026-08-20T16:10:00Z"
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "validity", "out_of_range", "2026-08-20T16:10:00Z", SKY)


def test_mutation_price_floor_fails_closed() -> None:
    payload, binding, policy = _sky_binding()
    mutated = deepcopy(payload)
    mutated["price"]["subtotalMinor"] = 11800
    mutated["price"]["totalMinor"] = (
        11800 + int(mutated["price"]["feesMinor"]) + int(mutated["price"]["taxMinor"])
    )
    with pytest.raises(ApplicationError) as caught:
        accept_offer(collected_offer(mutated, binding), policy, evaluated_at=OCCURRED_AT)
    _assert_closed(caught.value, "subtotalMinor", "price_floor", "11800", SKY)


def test_select_offer_rejects_foreign_intent_offer_id() -> None:
    facade = build_facade()
    first_intent, first = _dispatch(facade)
    second_intent, second = _dispatch(facade)
    foreign = first.recommended_offer_id
    assert foreign is not None
    session = facade._sessions.get(second_intent)
    assert session is not None
    with pytest.raises(ApplicationError) as caught:
        _select_offer(session, foreign, 1, OCCURRED_AT)
    _assert_closed(caught.value, "offerId", "ineligible", foreign, first_intent.to_primitive())
    with pytest.raises(ApplicationError) as caught_accept:
        facade.accept_recommended_or_selected_offer(
            second_intent,
            AcceptCommand(
                actor_id=BUYER.actor_id.to_primitive(),
                owner_id=OWNER.to_primitive(),
                approval_id=_opaque("ap_"),
                correlation_id=_opaque("cr_"),
                issued_at=CREATED_AT,
                expires_at=EXPIRES_AT,
                offer_id=foreign,
                offer_version=1,
            ),
        )
    _assert_closed(
        caught_accept.value,
        "offerId",
        "ineligible",
        foreign,
        first_intent.to_primitive(),
    )
    assert second.state is BuyerSessionState.OFFERS_RANKED


class _MutatingSupplier:
    def __init__(
        self, inner: SupplierPort, mutate: Callable[[dict[str, object]], dict[str, object]]
    ) -> None:
        self._inner = inner
        self._mutate = mutate

    @property
    def remaining_capacity(self) -> int:
        return int(self._inner.remaining_capacity)  # type: ignore[attr-defined]

    def restore_capacity(self, remaining: int) -> None:
        self._inner.restore_capacity(remaining)  # type: ignore[attr-defined]

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        terminal = self._inner.attempt(request)
        if terminal.payload is None:
            return terminal
        mutated = self._mutate(deepcopy(dict(terminal.payload)))
        return replace(terminal, payload=mutated)


def test_http_drops_mutated_skyshield_without_echo() -> None:
    ports = canonical_golden_ports()

    def mutate(payload: dict[str, object]) -> dict[str, object]:
        service = payload["service"]
        assert isinstance(service, dict)
        service["lotType"] = "garage"
        return payload

    ports[SKYSHIELD.supplier_token] = _MutatingSupplier(ports[SKYSHIELD.supplier_token], mutate)
    client = TestClient(create_app(build_facade(roster=SeededRoster(ports))))
    created = client.post(f"{PREFIX}/intents", json=_intent_payload())
    assert created.status_code == 200
    intent_id = created.json()["intentId"]
    confirmed = client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_http_gov())
    assert confirmed.status_code == 200
    dispatched = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_http_gov())
    assert dispatched.status_code == 200
    body = dispatched.json()
    tokens = {item["supplierToken"] for item in body["offers"]}
    assert SKY not in tokens
    assert PARK in tokens
    assert TERMINALFLEX.supplier_token.to_primitive() in tokens
    assert len(body["offers"]) == 2
    assert "garage" not in dispatched.text
    assert "671000" not in dispatched.text.replace(",", "")


def test_audit_and_generated_ids_are_unique_across_intents() -> None:
    facade = build_facade()
    first_intent, first = _dispatch(facade)
    second_intent, second = _dispatch(facade)
    first_session = facade._sessions.get(first_intent)
    second_session = facade._sessions.get(second_intent)
    assert first_session is not None and second_session is not None
    first_offers = {item.offer.offer_id.to_primitive() for item in first_session.mapped_offers}
    second_offers = {item.offer.offer_id.to_primitive() for item in second_session.mapped_offers}
    assert first_offers.isdisjoint(second_offers)
    first_req = first_session.requirement.requirement_id.to_primitive()
    second_req = second_session.requirement.requirement_id.to_primitive()
    assert first_req != second_req
    first_sigs = {
        item.offer.terms.signature.to_primitive()
        for item in first_session.mapped_offers
        if item.offer.terms is not None
    }
    second_sigs = {
        item.offer.terms.signature.to_primitive()
        for item in second_session.mapped_offers
        if item.offer.terms is not None
    }
    assert first_sigs.isdisjoint(second_sigs)
    assert first_session.collection is not None and second_session.collection is not None
    first_corr = {item.correlation_id.to_primitive() for item in first_session.collection.responses}
    second_corr = {
        item.correlation_id.to_primitive() for item in second_session.collection.responses
    }
    assert first_corr.isdisjoint(second_corr)
    first_invites = {item.invitation.to_primitive() for item in first_session.collection.responses}
    second_invites = {
        item.invitation.to_primitive() for item in second_session.collection.responses
    }
    assert first_invites == second_invites
    first_scoped = {
        item.binding.scoped_intent_id.to_primitive()
        for item in first_session.collection.responses
        if item.binding is not None
    }
    second_scoped = {
        item.binding.scoped_intent_id.to_primitive()
        for item in second_session.collection.responses
        if item.binding is not None
    }
    assert first_scoped == second_scoped
    accepted_first = facade.accept_recommended_or_selected_offer(
        first_intent,
        AcceptCommand(
            actor_id=BUYER.actor_id.to_primitive(),
            owner_id=OWNER.to_primitive(),
            approval_id=_opaque("ap_"),
            correlation_id=_opaque("cr_"),
            issued_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            offer_id=first.recommended_offer_id or "",
            offer_version=1,
        ),
    )
    accepted_second = facade.accept_recommended_or_selected_offer(
        second_intent,
        AcceptCommand(
            actor_id=BUYER.actor_id.to_primitive(),
            owner_id=OWNER.to_primitive(),
            approval_id=_opaque("ap_"),
            correlation_id=_opaque("cr_"),
            issued_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            offer_id=second.recommended_offer_id or "",
            offer_version=1,
        ),
    )
    assert accepted_first.acceptance is not None and accepted_second.acceptance is not None
    assert accepted_first.acceptance.acceptance_id != accepted_second.acceptance.acceptance_id
    first_winner = next(item for item in first.offers if item.recommended)
    second_winner = next(item for item in second.offers if item.recommended)
    authorized_first = facade.authorize_simulated_transaction(
        first_intent,
        AuthorizeCommand(
            actor_id=BUYER.actor_id.to_primitive(),
            owner_id=OWNER.to_primitive(),
            approval_id=_opaque("ap_"),
            correlation_id=_opaque("cr_"),
            issued_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            acceptance_id=accepted_first.acceptance.acceptance_id,
            amount_minor=first_winner.total_minor,
            currency="USD",
            supplier_token=first_winner.supplier_token,
            action="reserve_parking",
            mode="SIMULATED",
            idempotency_key=_opaque("ik_"),
        ),
    )
    authorized_second = facade.authorize_simulated_transaction(
        second_intent,
        AuthorizeCommand(
            actor_id=BUYER.actor_id.to_primitive(),
            owner_id=OWNER.to_primitive(),
            approval_id=_opaque("ap_"),
            correlation_id=_opaque("cr_"),
            issued_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            acceptance_id=accepted_second.acceptance.acceptance_id,
            amount_minor=second_winner.total_minor,
            currency="USD",
            supplier_token=second_winner.supplier_token,
            action="reserve_parking",
            mode="SIMULATED",
            idempotency_key=_opaque("ik_"),
        ),
    )
    assert authorized_first.transaction is not None
    assert authorized_second.transaction is not None
    assert (
        authorized_first.transaction.authorization_id
        != authorized_second.transaction.authorization_id
    )
    assert authorized_first.transaction.result_ref != authorized_second.transaction.result_ref
    records = facade._unit_of_work.audit.committed_records()
    event_ids = [item.event_id for item in records]
    assert event_ids
    assert len(event_ids) == len(set(event_ids))
    offer_resources = {
        item.resource_id for item in records if item.resource_type is AuditResourceType.OFFER
    }
    first_audited = offer_resources & first_offers
    second_audited = offer_resources & second_offers
    assert first_audited
    assert second_audited
    assert first_audited.isdisjoint(second_audited)
    assert first.recommended_offer_id in first_audited
    assert second.recommended_offer_id in second_audited


def test_sequential_id_factory_is_unique_and_thread_safe() -> None:
    factory = SequentialIdFactory()
    collected: list[str] = []
    guard = Lock()
    barrier = Barrier(8)

    def worker() -> None:
        barrier.wait()
        local = [
            factory.offer_id(SKYSHIELD.supplier_token),
            factory.signature(SKYSHIELD.supplier_token),
            factory.correlation_id(SKYSHIELD.supplier_token),
            factory.acceptance_id(),
            factory.authorization_id(),
            factory.audit_event_id(),
            factory.result_ref(),
            factory.requirement_id(),
        ]
        with guard:
            collected.extend(local)

    threads = [Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(collected) == 64
    assert len(set(collected)) == 64
