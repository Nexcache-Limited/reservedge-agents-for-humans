"""COMP-AWS-04: raw objective stays out of PI, supplier envelopes, ranking, and audit."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient
from wp04_helpers import A1_ID, A2_ID  # type: ignore[import-not-found]
from wp06_fakes import (  # type: ignore[import-not-found]
    FixtureRoster,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_application import golden_path as golden_path_mod
from itaa_application.errors import ApplicationError
from itaa_application.ranking_decision import decide as original_decide
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.schemas import PlanAnswers

MARKER = "MARKER_OBJECTIVE_DO_NOT_COPY_7f3a"
OBJECTIVE = f"{MARKER} I'll need a car next month for a quiet weekend."


class _Provider:
    def __init__(self) -> None:
        self.roster = FixtureRoster()
        self.facade = build_facade(roster=self.roster)
        self.orch = compose_orchestrator(self.facade)

    def plan_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        answers = PlanAnswers.model_validate(payload.get("answers") or {})
        model, projection, events = self.orch.plan_turn(str(payload["objective"]), answers)
        dumped = model.model_dump(mode="json")
        dumped.pop("evidence", None)
        return {
            "planTurn": dumped,
            "projection": projection.model_dump(mode="json"),
            "events": events,
        }

    def execute_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        tool = str(payload["tool"])
        inner = payload.get("payload")
        result = self.orch.execute_turn(tool, inner if isinstance(inner, dict) else {})
        return {"tool": tool, "result": result}


def _blob(value: Any) -> str:
    return json.dumps(value, default=str).lower()


def test_public_session_and_handoff_omit_raw_objective() -> None:
    provider = _Provider()
    client = TestClient(build_agent_app(provider))
    created = client.post(f"{PREFIX}/sessions", json={"objective": OBJECTIVE})
    assert created.status_code == 200, created.text
    body = created.json()
    transcript = _blob(body.pop("transcript", None))
    assert MARKER.lower() in transcript
    assert MARKER.lower() not in _blob(body)
    assert "objective" not in created.json()
    session_id = created.json()["sessionId"]
    fetched = client.get(f"{PREFIX}/sessions/{session_id}").json()
    fetched.pop("transcript", None)
    assert MARKER.lower() not in _blob(fetched)
    confirmed = client.post(f"{PREFIX}/sessions/{session_id}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    payload = confirmed.json()
    payload.pop("transcript", None)
    assert MARKER.lower() not in _blob(payload)
    assert MARKER.lower() not in _blob(confirmed.json()["parkingHandoff"])
    with pytest.raises(ApplicationError):
        provider.facade.get_buyer_snapshot(intent_id())


def test_purchase_intent_ranking_supplier_audit_never_see_agent_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ranking_needs: list[object] = []

    def _capture(*args: Any, **kwargs: Any) -> Any:
        ranking_needs.append(args[1] if len(args) > 1 else kwargs.get("need"))
        return original_decide(*args, **kwargs)

    monkeypatch.setattr(golden_path_mod, "decide", _capture)
    provider = _Provider()
    client = TestClient(build_agent_app(provider))
    created = client.post(f"{PREFIX}/sessions", json={"objective": OBJECTIVE})
    assert created.status_code == 200
    facade = provider.facade
    snapshot = facade.create_purchase_intent(jfk_payload())
    confirmed = facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    ranked = facade.get_buyer_snapshot(intent_id())
    haystack = " ".join(
        (
            _blob(snapshot.to_primitive()),
            _blob(confirmed.to_primitive()),
            _blob(dispatched.to_primitive()),
            _blob(ranked.to_primitive()),
            _blob(ranking_needs),
        )
    )
    assert ranking_needs
    assert MARKER.lower() not in haystack
    for port in provider.roster.ports().values():
        seen = getattr(port, "seen_envelopes", [])
        assert MARKER.lower() not in _blob(seen)
    records = facade._unit_of_work.audit.committed_records()  # noqa: SLF001
    assert MARKER.lower() not in _blob(records)
