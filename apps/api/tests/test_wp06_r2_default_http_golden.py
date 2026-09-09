"""Default FastAPI composition must emit the locked JFK ranking vector."""

from __future__ import annotations

from copy import deepcopy
from itertools import count
from threading import Barrier, Thread

from fastapi.testclient import TestClient
from wp04_helpers import BUYER, CREATED_AT, EXPIRES_AT, OWNER
from wp06_fakes import build_facade as fixture_build_facade
from wp06_fakes import jfk_payload

from itaa_api.app import create_app
from itaa_api.composition import SeededRoster, SimulatorPolicyPort, build_facade
from itaa_application.errors import ApplicationError
from itaa_application.golden_path import FaultInjector
from itaa_application.session_models import BuyerSessionState, GovernanceCommand
from itaa_domain.identifiers import IntentId
from itaa_domain.value_objects import format_utc
from itaa_supplier_simulator.harness import seeded_ports

PREFIX = "/v1/simulations/airport-parking"
SKY = "sp_01k2m3n4p5q6r7s8t9v0w1x2b2"
PARK = "sp_01k2m3n4p5q6r7s8t9v0w1x2b1"
FLEX = "sp_01k2m3n4p5q6r7s8t9v0w1x2b3"
_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
_SEQ = count(1_000)


def _opaque(prefix: str) -> str:
    value = next(_SEQ)
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


def _gov() -> dict[str, object]:
    return {
        "actorId": BUYER.actor_id.to_primitive(),
        "ownerId": OWNER.to_primitive(),
        "approvalId": _opaque("ap_"),
        "correlationId": _opaque("cr_"),
        "issuedAt": format_utc(CREATED_AT),
        "expiresAt": format_utc(EXPIRES_AT),
    }


def _assert_locked(body: dict[str, object]) -> None:
    by_token = {item["supplierToken"]: item for item in body["offers"]}
    for item in body["offers"]:
        assert "scoreMicros" not in item
        assert "totalMinor" not in item
        assert "termsHash" in item
    assert by_token[SKY]["rank"] == 1
    assert by_token[SKY]["recommended"] is True
    assert by_token[SKY]["price"]["totalMinor"] == 14800
    assert by_token[PARK]["rank"] == 2
    assert by_token[PARK]["price"]["totalMinor"] == 11900
    assert by_token[FLEX]["rank"] == 3
    assert by_token[FLEX]["price"]["totalMinor"] == 16900
    assert body["recommendedOfferId"] == by_token[SKY]["offerId"]
    assert body["downside"]["delta"] == 2900
    assert body["downside"]["versusOfferId"] == by_token[PARK]["offerId"]
    outcomes = {item["kind"] for item in body["supplierOutcomes"]}
    assert outcomes == {"OFFER"}
    assert len(body["supplierOutcomes"]) == 3


def _dispatch(client: TestClient, payload: dict[str, object]) -> tuple[str, dict[str, object]]:
    created = client.post(f"{PREFIX}/intents", json=payload)
    assert created.status_code == 200, created.text
    intent_id = created.json()["intentId"]
    confirmed = client.post(f"{PREFIX}/intents/{intent_id}/confirm", json=_gov())
    assert confirmed.status_code == 200, confirmed.text
    dispatched = client.post(f"{PREFIX}/intents/{intent_id}/dispatch", json=_gov())
    assert dispatched.status_code == 200, dispatched.text
    return intent_id, dispatched.json()


def _complete_a3_a4(client: TestClient, intent_id: str, dispatched: dict[str, object]) -> None:
    accepted = client.post(
        f"{PREFIX}/intents/{intent_id}/acceptances",
        json={**_gov(), "offerId": dispatched["recommendedOfferId"], "offerVersion": 1},
    )
    assert accepted.status_code == 200, accepted.text
    winner = next(item for item in dispatched["offers"] if item["recommended"])
    key = _opaque("ik_")
    body = {
        **_gov(),
        "acceptanceId": accepted.json()["acceptance"]["acceptanceId"],
        "amountMinor": winner["price"]["totalMinor"],
        "currency": "USD",
        "supplierToken": winner["supplierToken"],
        "action": "reserve_parking",
        "mode": "SIMULATED",
        "idempotencyKey": key,
    }
    first = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert first.status_code == 200, first.text
    assert first.json()["transaction"]["mode"] == "SIMULATED"
    assert first.json()["transaction"]["action"] == "reserve_parking"
    replay = client.post(
        f"{PREFIX}/intents/{intent_id}/transaction-authorizations",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["transaction"]["resultRef"] == first.json()["transaction"]["resultRef"]
    assert (
        replay.json()["transaction"]["authorizationId"]
        == first.json()["transaction"]["authorizationId"]
    )
    snapshot = client.get(f"{PREFIX}/intents/{intent_id}")
    assert snapshot.json()["state"] == "TRANSACTION_AUTHORIZED_SIMULATED"


def test_default_fastapi_http_emits_locked_golden_vector() -> None:
    client = TestClient(create_app(build_facade()))
    intent_id, dispatched = _dispatch(client, _intent_payload())
    _assert_locked(dispatched)
    _complete_a3_a4(client, intent_id, dispatched)


def test_sequential_fresh_intents_remain_deterministic() -> None:
    client = TestClient(create_app(build_facade()))
    first_id, first = _dispatch(client, _intent_payload())
    second_id, second = _dispatch(client, _intent_payload())
    assert first_id != second_id
    _assert_locked(first)
    _assert_locked(second)
    first_ids = {item["offerId"] for item in first["offers"]}
    second_ids = {item["offerId"] for item in second["offers"]}
    assert first_ids.isdisjoint(second_ids)
    _complete_a3_a4(client, first_id, first)
    third_id, third = _dispatch(client, _intent_payload())
    assert third_id != first_id
    _assert_locked(third)
    third_ids = {item["offerId"] for item in third["offers"]}
    assert third_ids.isdisjoint(first_ids)
    assert third_ids.isdisjoint(second_ids)


def test_concurrent_fresh_intents_do_not_interfere() -> None:
    facade = build_facade()
    barrier = Barrier(2)
    results: list[object] = []

    def worker() -> None:
        payload = _intent_payload()
        barrier.wait()
        created = facade.create_purchase_intent(payload)

        def command() -> GovernanceCommand:
            gov = _gov()
            return GovernanceCommand(
                actor_id=str(gov["actorId"]),
                owner_id=str(gov["ownerId"]),
                approval_id=str(gov["approvalId"]),
                correlation_id=str(gov["correlationId"]),
                issued_at=CREATED_AT,
                expires_at=EXPIRES_AT,
            )

        intent = IntentId(created.intent_id)
        facade.confirm_requirement(intent, command())
        dispatched = facade.approve_and_dispatch(intent, command())
        results.append(dispatched)

    threads = [Thread(target=worker), Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 2
    offer_sets: list[set[str]] = []
    for snapshot in results:
        assert snapshot.state is BuyerSessionState.OFFERS_RANKED  # type: ignore[union-attr]
        scores = {item.supplier_token: item.score_micros for item in snapshot.offers}  # type: ignore[union-attr]
        assert scores[SKY] == 671_000
        assert scores[PARK] == 660_000
        assert scores[FLEX] == 535_000
        winner = next(item for item in snapshot.offers if item.recommended)  # type: ignore[union-attr]
        assert winner.supplier_token == SKY
        assert snapshot.recommended_offer_id == winner.offer_id  # type: ignore[union-attr]
        offer_sets.append({item.offer_id for item in snapshot.offers})  # type: ignore[union-attr]
    assert offer_sets[0].isdisjoint(offer_sets[1])


def test_failed_dispatch_does_not_consume_later_capacity() -> None:
    faults = FaultInjector()
    facade = build_facade(faults=faults)
    payload = _intent_payload()
    created = facade.create_purchase_intent(payload)

    def command() -> GovernanceCommand:
        gov = _gov()
        return GovernanceCommand(
            actor_id=str(gov["actorId"]),
            owner_id=str(gov["ownerId"]),
            approval_id=str(gov["approvalId"]),
            correlation_id=str(gov["correlationId"]),
            issued_at=CREATED_AT,
            expires_at=EXPIRES_AT,
        )

    intent = IntentId(created.intent_id)
    facade.confirm_requirement(intent, command())
    faults.fail_at("a2.after_collection_and_capacity")
    try:
        facade.approve_and_dispatch(intent, command())
        raise AssertionError("expected injected fault")
    except ApplicationError as exc:
        assert exc.field == "internal"
        assert exc.code == "injected_fault"
    retry = facade.approve_and_dispatch(intent, command())
    scores = {item.supplier_token: item.score_micros for item in retry.offers}
    assert scores[SKY] == 671_000
    assert scores[PARK] == 660_000
    assert scores[FLEX] == 535_000
    winner = next(item for item in retry.offers if item.recommended)
    assert winner.supplier_token == SKY
    assert retry.recommended_offer_id == winner.offer_id


def test_fixture_facade_and_default_http_vectors_cannot_drift() -> None:
    fixture_client = TestClient(create_app(fixture_build_facade()))
    default_client = TestClient(create_app(build_facade()))
    _, fixture_body = _dispatch(fixture_client, deepcopy(jfk_payload()))
    _, default_body = _dispatch(default_client, _intent_payload())
    _assert_locked(fixture_body)
    _assert_locked(default_body)
    fixture_ranks = {item["supplierToken"]: item["rank"] for item in fixture_body["offers"]}
    default_ranks = {item["supplierToken"]: item["rank"] for item in default_body["offers"]}
    assert fixture_ranks == default_ranks
    fixture_totals = {
        item["supplierToken"]: item["price"]["totalMinor"] for item in fixture_body["offers"]
    }
    default_totals = {
        item["supplierToken"]: item["price"]["totalMinor"] for item in default_body["offers"]
    }
    assert fixture_totals == default_totals
    assert fixture_body["downside"]["delta"] == default_body["downside"]["delta"]


def test_a3_cannot_accept_offer_id_from_another_intent() -> None:
    client = TestClient(create_app(build_facade()))
    first_id, first = _dispatch(client, _intent_payload())
    second_id, second = _dispatch(client, _intent_payload())
    foreign = first["recommendedOfferId"]
    response = client.post(
        f"{PREFIX}/intents/{second_id}/acceptances",
        json={**_gov(), "offerId": foreign, "offerVersion": 1},
    )
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "offerId"
    assert response.json()["error"]["code"] == "ineligible"
    assert set(response.json()["error"]) == {"code", "field", "correlationId"}
    assert foreign not in response.text
    assert first_id not in response.text
    _assert_locked(second)


def test_seeded_economic_ports_do_not_emit_locked_vector() -> None:
    """Document the WP-06-R2 mismatch: 6-day SimulatedSupplier economics."""
    client = TestClient(
        create_app(
            build_facade(
                roster=SeededRoster(seeded_ports()),
                policies=SimulatorPolicyPort(),
            )
        )
    )
    _, body = _dispatch(client, deepcopy(jfk_payload()))
    for item in body["offers"]:
        assert "scoreMicros" not in item
    totals = {item["supplierToken"]: item["price"]["totalMinor"] for item in body["offers"]}
    assert totals[SKY] == 21300
    assert totals[SKY] != 14800
