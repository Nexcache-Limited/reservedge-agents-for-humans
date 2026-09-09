from __future__ import annotations

from comp_aws_01_helpers import CORRELATION
from fastapi.testclient import TestClient

from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.app import create_aws_app
from itaa_aws_adapter.schemas import PlanAnswers

DATES_ONLY_OBJECTIVE = "I'm travelling from LHR to Edinburgh for a conference and need a car."
DEPARTURE_AND_CAR_OBJECTIVE = "I'm travelling to Edinburgh for a conference."
STRUCTURED_DATES = {
    "dates": "14–19 October 2026",
    "startDate": "2026-10-14",
    "endDate": "2026-10-19",
}


def _by_kind(tasks: list[object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for task in tasks:
        kind = getattr(task, "kind", None)
        if isinstance(kind, str):
            out[kind] = task
    return out


def test_structured_dates_update_projection_and_clear_dates_question() -> None:
    first_model, first, _events = compose_orchestrator().plan_turn(DATES_ONLY_OBJECTIVE)
    assert first.phase == "clarify"
    assert any(question.id == "dates" for question in first.questions)
    assert first.facts.hasExactDates is False
    assert first.facts.dates == ""
    assert [question.id for question in first.questions] == ["dates"]
    answers = PlanAnswers.model_validate(STRUCTURED_DATES)
    _model, projection, _later = compose_orchestrator().plan_turn(DATES_ONLY_OBJECTIVE, answers)
    assert answers.startDate == projection.facts.startDate == "2026-10-14"
    assert answers.endDate == projection.facts.endDate == "2026-10-19"
    assert answers.startDate in projection.facts.dates
    assert answers.endDate in projection.facts.dates
    assert projection.facts.hasExactDates is True
    assert all(question.id != "dates" for question in projection.questions)
    assert projection.phase == "forming"
    assert projection.facts.destination == "Edinburgh"
    assert projection.facts.departureAirport == "LHR"
    assert projection.facts.parkingAirport != "JFK"
    dumped = projection.model_dump_json().lower()
    assert "jfk" not in dumped
    assert "skyshield" not in dumped
    by_kind = _by_kind(projection.tasks)
    first_kind = _by_kind(first.tasks)
    assert by_kind["rental"].provenance == first_kind["rental"].provenance == "explicit"  # type: ignore[union-attr]
    assert "parking" not in by_kind
    assert "parking" not in first_kind
    assert by_kind["hotel"].provenance == first_kind["hotel"].provenance == "proposed"  # type: ignore[union-attr]
    del first_model


def test_structured_departure_airport_and_car_need() -> None:
    _model, first, _events = compose_orchestrator().plan_turn(DEPARTURE_AND_CAR_OBJECTIVE)
    asked = {question.id for question in first.questions}
    assert "departureAirport" in asked
    assert "carNeed" in asked
    assert first.facts.departureAirport == ""
    assert first.facts.carNeed == ""
    answers = PlanAnswers(
        departureAirport="LHR",
        carNeed="yes",
        startDate="2026-10-14",
        endDate="2026-10-19",
        dates="14–19 October 2026",
    )
    _later, projection, _events = compose_orchestrator().plan_turn(
        DEPARTURE_AND_CAR_OBJECTIVE, answers
    )
    assert projection.facts.departureAirport == "LHR"
    assert projection.facts.carNeed == "yes"
    assert "2026-10-14" in projection.facts.dates
    assert projection.facts.destination == "Edinburgh"
    assert projection.phase == "forming"
    asked = {question.id for question in projection.questions}
    assert asked.isdisjoint({"dates", "departureAirport", "carNeed"})
    by_kind = _by_kind(projection.tasks)
    assert by_kind["rental"].provenance != "explicit"  # type: ignore[union-attr]
    assert by_kind["hotel"].provenance == "proposed"  # type: ignore[union-attr]
    assert projection.facts.parkingAirport != "JFK"


def test_http_plan_turns_consumes_structured_answers() -> None:
    client = TestClient(create_aws_app())
    first = client.post(
        "/v1/aws/plan-turns",
        json={"objective": DATES_ONLY_OBJECTIVE, "correlationId": CORRELATION},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()["projection"]
    assert first_body["phase"] == "clarify"
    assert any(item["id"] == "dates" for item in first_body["questions"])
    second = client.post(
        "/v1/aws/plan-turns",
        json={
            "objective": DATES_ONLY_OBJECTIVE,
            "answers": STRUCTURED_DATES,
            "correlationId": CORRELATION,
        },
    )
    assert second.status_code == 200, second.text
    body = second.json()
    facts = body["projection"]["facts"]
    assert facts["startDate"] == "2026-10-14"
    assert facts["endDate"] == "2026-10-19"
    assert "2026-10-14" in facts["dates"]
    assert "2026-10-19" in facts["dates"]
    assert facts["hasExactDates"] is True
    assert all(item["id"] != "dates" for item in body["projection"]["questions"])
    assert body["projection"]["phase"] == "forming"
    assert "jfk" not in second.text.lower()
    departure = client.post(
        "/v1/aws/plan-turns",
        json={
            "objective": DEPARTURE_AND_CAR_OBJECTIVE,
            "answers": {
                "departureAirport": "LHR",
                "carNeed": "no",
                "startDate": "2026-10-14",
                "endDate": "2026-10-19",
            },
            "correlationId": CORRELATION,
        },
    )
    assert departure.status_code == 200, departure.text
    later = departure.json()["projection"]["facts"]
    assert later["departureAirport"] == "LHR"
    assert later["carNeed"] == "no"
    assert later["dates"]
