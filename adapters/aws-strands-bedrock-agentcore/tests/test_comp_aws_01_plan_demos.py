from __future__ import annotations

from comp_aws_01_helpers import DEMO_A, DEMO_B, DEMO_C, GENERIC

from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.schemas import PlanAnswers


def _by_kind(tasks: list[object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for task in tasks:
        kind = getattr(task, "kind", None)
        if isinstance(kind, str):
            out[kind] = task
    return out


def test_demo_a_single_parking_explicit() -> None:
    _model, projection, events = compose_orchestrator().plan_turn(DEMO_A)
    by_kind = _by_kind(projection.tasks)
    parking = by_kind["parking"]
    assert parking.provenance == "explicit"  # type: ignore[union-attr]
    assert parking.support == "live_simulated"  # type: ignore[union-attr]
    assert "hotel" not in by_kind or by_kind["hotel"].provenance != "explicit"  # type: ignore[union-attr]
    assert projection.facts.parkingAirport == "JFK"
    assert all(event["kind"] != "FAILED_CLOSED" for event in events)
    dumped = projection.model_dump_json()
    assert "671000" not in dumped
    assert "SkyShield" not in dumped


def test_demo_b_multitask_provenance() -> None:
    _model, projection, _events = compose_orchestrator().plan_turn(DEMO_B)
    by_kind = _by_kind(projection.tasks)
    assert by_kind["rental"].provenance == "explicit"  # type: ignore[union-attr]
    assert by_kind["parking"].provenance == "inferred"  # type: ignore[union-attr]
    assert by_kind["hotel"].provenance == "proposed"  # type: ignore[union-attr]
    assert by_kind["hotel"].support == "sandbox_search"  # type: ignore[union-attr]
    assert "flight" not in by_kind or by_kind["flight"].provenance != "explicit"  # type: ignore[union-attr]
    assert projection.facts.destination == "Edinburgh"
    assert projection.facts.destinationAirport == "EDI"
    assert projection.facts.parkingAirport == ""
    assert len(projection.tasks) > 1


def test_demo_c_clarifies_and_is_not_jfk() -> None:
    _model, projection, events = compose_orchestrator().plan_turn(DEMO_C)
    assert projection.phase == "clarify"
    assert any(question.id == "dates" for question in projection.questions)
    assert projection.facts.parkingAirport != "JFK"
    assert [task.kind for task in projection.tasks] != ["parking"]
    dumped = projection.model_dump_json().lower()
    assert "jfk" not in dumped
    assert "skyshield" not in dumped
    assert any(event["kind"] == "CLARIFICATION_READY" for event in events)


def test_generic_objective_does_not_collapse_to_jfk() -> None:
    _model, projection, _events = compose_orchestrator().plan_turn(GENERIC)
    assert projection.facts.parkingAirport != "JFK"
    dumped = projection.model_dump_json().lower()
    assert "jfk" not in dumped
    assert "skyshield" not in dumped
    assert "manchester" in dumped or projection.facts.destination == "Manchester"


def test_model_cannot_upgrade_hotel_to_explicit() -> None:
    from itaa_aws_adapter.fake import fake_plan_turn
    from itaa_aws_adapter.projector import project_plan
    from itaa_aws_adapter.schemas import SuggestedTask

    turn = fake_plan_turn(DEMO_A)
    turn.suggestedTasks.append(SuggestedTask(kind="hotel", provenance="explicit"))
    projection = project_plan(DEMO_A, PlanAnswers(), turn)
    assert all(task.kind != "hotel" or task.provenance != "explicit" for task in projection.tasks)


def test_bedrock_named_city_is_not_gazetteer_limited() -> None:
    from itaa_aws_adapter.projector import project_plan
    from itaa_aws_adapter.schemas import ExtractedFacts, PlanTurn

    turn = PlanTurn(
        understanding="Stay in Osaka",
        facts=ExtractedFacts(
            destination="Osaka",
            startDate="2026-11-12",
            endDate="2026-11-15",
            hasExactDates=True,
            hotelStated=True,
        ),
        buyerSafeMessage="I have Osaka and the dates.",
    )
    projection = project_plan("hotel needed from 12 to 15 november", PlanAnswers(), turn)
    assert projection.facts.destination == "Osaka"
    assert projection.facts.startDate == "2026-11-12"
    assert projection.facts.endDate == "2026-11-15"
    assert projection.facts.parkingAirport == ""
    assert "jfk" not in projection.model_dump_json().lower()


def test_bedrock_iata_is_not_copied_as_a_city() -> None:
    from itaa_aws_adapter.projector import project_plan
    from itaa_aws_adapter.schemas import ExtractedFacts, PlanTurn

    turn = PlanTurn(
        understanding="Parking",
        facts=ExtractedFacts(destination="JFK", hotelStated=True),
        buyerSafeMessage="ok",
    )
    projection = project_plan("hotel needed from 12 to 15 november", PlanAnswers(), turn)
    assert projection.facts.destination != "JFK"
    assert projection.facts.parkingAirport == ""


def test_bedrock_dates_fill_when_extractor_misses() -> None:
    from itaa_aws_adapter.projector import project_plan
    from itaa_aws_adapter.schemas import ExtractedFacts, PlanTurn

    turn = PlanTurn(
        understanding="Stay in Osaka",
        facts=ExtractedFacts(
            destination="Osaka",
            startDate="2026-11-12",
            endDate="2026-11-15",
            hasExactDates=True,
            hotelStated=True,
        ),
        buyerSafeMessage="I have Osaka and the dates.",
    )
    projection = project_plan("I need a hotel in that city", PlanAnswers(), turn)
    assert projection.facts.destination == "Osaka"
    assert projection.facts.startDate == "2026-11-12"
    assert projection.facts.endDate == "2026-11-15"
    assert projection.facts.hasExactDates is True
