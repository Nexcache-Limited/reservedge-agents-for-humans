"""COMP-AWS-04: conversation-first location split and catalog defaults."""

from __future__ import annotations

from itaa_api.agent_requirements import (
    apply_defaults,
    apply_patch,
    empty_domain,
    extract_conversation_patches,
    join_catalog_asks,
    parking_iata_from_text,
    refresh_completeness,
    sanitize_buyer_message,
)
from itaa_aws_adapter.projector import extract_facts, project_plan


def test_mumbai_new_york_does_not_set_parking_iata() -> None:
    text = (
        "travelling to New York for 10 days. Dates: 20th to 30th October. "
        "Departing from Mumbai. parking and rental car"
    )
    facts = extract_facts(text)
    assert facts.destination == "New York"
    assert facts.parkingAirport == ""
    assert parking_iata_from_text(text) == ""
    projection = project_plan(text)
    assert "JFK" not in projection.model_dump_json()


def test_parking_at_jfk_is_parking_specific_evidence() -> None:
    assert parking_iata_from_text("I need parking at JFK") == "JFK"
    assert parking_iata_from_text("JFK") == "JFK"


def test_system_proposal_never_becomes_explicit() -> None:
    domain = empty_domain("parking", provenance="explicit", accepted=True)
    apply_defaults(domain)
    fields = domain["fields"]
    assert isinstance(fields, dict)
    shuttle = fields["shuttleMaxMinutes"]
    assert isinstance(shuttle, dict)
    assert shuttle["source"] == "system_proposal"
    assert shuttle["provenance"] == "proposed"
    vehicle = fields["vehicleClass"]
    assert isinstance(vehicle, dict)
    assert vehicle["value"] == "standard"
    assert vehicle["source"] == "system_proposal"
    assert vehicle["provenance"] == "proposed"
    apply_patch(
        domain,
        "shuttleMaxMinutes",
        20,
        source="system_proposal",
        provenance="explicit",
    )
    updated = fields["shuttleMaxMinutes"]
    assert isinstance(updated, dict)
    assert updated["provenance"] == "proposed"


def test_empty_accessibility_default_is_present_not_missing() -> None:
    domain = empty_domain("parking", provenance="explicit", accepted=True)
    apply_patch(domain, "airportCode", "JFK", source="current_turn", provenance="explicit")
    apply_patch(
        domain, "start", "2026-10-20T01:00:00Z", source="current_turn", provenance="explicit"
    )
    apply_patch(domain, "end", "2026-10-30T17:00:00Z", source="current_turn", provenance="explicit")
    apply_patch(domain, "vehicleClass", "suv", source="current_turn", provenance="explicit")
    apply_patch(domain, "covered", "preferred", source="current_turn", provenance="explicit")
    apply_defaults(domain)
    refresh_completeness(domain, None)
    fields = domain["fields"]
    assert isinstance(fields, dict)
    access = fields["accessibility"]
    assert isinstance(access, dict)
    assert access["value"] == []
    assert access["provenance"] == "proposed"
    missing = domain["missing"]
    assert isinstance(missing, list)
    assert "accessibility" not in missing
    assert domain["completeness"] == "ready"


def test_change_parking_times_target_parking_only() -> None:
    patches = extract_conversation_patches(
        "change parking start from 2am to 1am and finish at 9pm",
        source="current_turn",
    )
    kinds = {item["kind"] for item in patches}
    assert kinds == {"parking"}
    fields = {item["fieldId"] for item in patches}
    assert "startTime" in fields
    assert "endTime" in fields


def test_offer_language_blocked_before_a2() -> None:
    text = sanitize_buyer_message("Ranked offers are ready for parking.", a2_complete=False)
    assert "ranked" not in text.lower()
    assert "request" in text.lower() or "authorize" in text.lower()


def test_ordinal_span_captures_parking_dates_without_inventing_airport() -> None:
    text = "travelling to London. need parking from 15th to 16th october"
    facts = extract_facts(text)
    assert facts.parkingStated is True
    assert facts.hasExactDates is True
    assert facts.startDate == "2026-10-15"
    assert facts.endDate == "2026-10-16"
    assert facts.parkingAirport == ""
    assert parking_iata_from_text(text) == ""
    projection = project_plan(text)
    asked = {question.id for question in projection.questions}
    assert asked.isdisjoint({"departureAirport", "carNeed", "dates"})
    patches = extract_conversation_patches(text, source="current_turn")
    fields = {item["fieldId"]: item["value"] for item in patches if item["kind"] == "parking"}
    assert str(fields["start"]).startswith("2026-10-15")
    assert str(fields["end"]).startswith("2026-10-16")
    assert "T12:00:00Z" not in str(fields["start"])
    assert "airportCode" not in fields


def test_heathrow_normalizes_to_lhr_only_as_named_airport() -> None:
    assert parking_iata_from_text("heathrow") == "LHR"
    assert parking_iata_from_text("I need parking at Heathrow") == "LHR"
    blob = "travelling to London. need parking from 15th to 16th october heathrow"
    assert parking_iata_from_text(blob) == "LHR"
    assert parking_iata_from_text("travelling to London. need parking") == ""
    from itaa_api.agent_requirements import apply_model_patches, empty_domain

    domain = empty_domain("parking", provenance="explicit", accepted=True)
    accepted, rejected = apply_model_patches(
        {"parking": domain},
        [{"kind": "parking", "fieldId": "airportCode", "value": "JFK", "evidence": ""}],
        conversation="travelling to London. need parking",
        last_user_message="heathrow",
        source="current_turn",
    )
    assert accepted == []
    assert rejected
    accepted_lhr, rejected_lhr = apply_model_patches(
        {"parking": domain},
        [{"kind": "parking", "fieldId": "airportCode", "value": "LHR", "evidence": "heathrow"}],
        conversation=blob,
        last_user_message="heathrow",
        source="current_turn",
    )
    assert rejected_lhr == []
    assert accepted_lhr
    fields = domain["fields"]
    assert isinstance(fields, dict)
    airport = fields["airportCode"]
    assert isinstance(airport, dict)
    assert airport["value"] == "LHR"


def test_model_patch_coercion_accepts_natural_closed_values() -> None:
    from itaa_api.agent_requirements import coerce_value, normalize_iata

    assert normalize_iata("LHR (Heathrow)") == "LHR"
    assert coerce_value("parking", "start", "2026-10-15T12:00:00") == "2026-10-15T12:00:00Z"
    assert coerce_value("parking", "start", "15 October 2026") == "2026-10-15"
    assert coerce_value("parking", "vehicleClass", "an SUV") == "suv"
    assert coerce_value("parking", "start", ["2026-10-15"]) == "2026-10-15"
    assert coerce_value("parking", "covered", "covered") == "preferred"
    assert coerce_value("parking", "covered", "I dont need covered parking") == "none"
    assert coerce_value("parking", "covered", "uncovered is fine") == "none"


def test_covered_refusal_is_none_not_preferred() -> None:
    from itaa_api.agent_requirements import apply_model_patches, empty_domain

    text = "I dont need covered parking"
    patches = extract_conversation_patches(text, source="current_turn")
    covered = [item for item in patches if item["fieldId"] == "covered"]
    assert covered
    assert covered[-1]["value"] == "none"
    domain = empty_domain("parking", provenance="explicit", accepted=True)
    accepted, rejected = apply_model_patches(
        {"parking": domain},
        [{"kind": "parking", "fieldId": "covered", "value": "preferred", "evidence": text}],
        conversation="need parking at Gatwick",
        last_user_message=text,
        source="current_turn",
    )
    assert accepted == []
    assert rejected
    accepted_none, rejected_none = apply_model_patches(
        {"parking": domain},
        [{"kind": "parking", "fieldId": "covered", "value": "none", "evidence": text}],
        conversation="need parking at Gatwick",
        last_user_message=text,
        source="current_turn",
    )
    assert rejected_none == []
    assert accepted_none
    fields = domain["fields"]
    assert isinstance(fields, dict)
    held = fields["covered"]
    assert isinstance(held, dict)
    assert held["value"] == "none"


def test_prefer_covered_is_not_confused_with_shuttle_negation() -> None:
    patches = extract_conversation_patches(
        "I have a standard EV, prefer covered parking, "
        "and don't want a shuttle longer than 20 minutes.",
        source="current_turn",
    )
    covered = [item["value"] for item in patches if item["fieldId"] == "covered"]
    assert covered[-1] == "preferred"


def test_rental_only_at_lhr_is_not_explicit_parking() -> None:
    text = "rental car needed on the 6th September in lhr"
    facts = extract_facts(text)
    assert facts.rentalStated is True
    assert facts.parkingStated is False
    assert facts.parkingAirport == ""
    projection = project_plan(text)
    parking = next((item for item in projection.tasks if item.kind == "parking"), None)
    rental = next(item for item in projection.tasks if item.kind == "rental")
    assert rental.provenance == "explicit"
    if parking is not None:
        assert parking.provenance != "explicit"
        assert parking.accepted is False
    assert parking_iata_from_text(text) == ""
    assert parking_iata_from_text("manchester") == "MAN"


def test_rental_then_parking_clause_wins_place_and_dates() -> None:
    blob = "need car rental from 19 to 23 October in Heathrow. parking in Manchester from 26 to 28"
    assert parking_iata_from_text(blob) == "MAN"
    patches = extract_conversation_patches(blob, source="current_turn")
    by_field = {item["fieldId"]: item["value"] for item in patches if item["kind"] == "parking"}
    assert by_field["airportCode"] == "MAN"
    assert str(by_field["start"]).startswith("2026-10-26")
    assert str(by_field["end"]).startswith("2026-10-28")


def test_gatwick_in_day_range_does_not_drop_dates_or_clocks() -> None:
    from itaa_api.agent_requirements import infer_year_month_for_day

    text = "parking needed in 13 to 16 Gatwick for 2 am to 10 pm with covered parking"
    patches = extract_conversation_patches(text, source="current_turn")
    by_field = {item["fieldId"]: item["value"] for item in patches if item["kind"] == "parking"}
    year, month = infer_year_month_for_day(13)
    assert by_field["airportCode"] == "LGW"
    assert by_field["covered"] == "preferred"
    assert str(by_field["start"]) == f"{year}-{month}-13T02:00:00Z"
    assert str(by_field["end"]) == f"{year}-{month}-16T22:00:00Z"
    follow = extract_conversation_patches(
        "I had already given 2 am to 10 pm in my previous message",
        source="current_turn",
        calendar_context=text,
    )
    times = {item["fieldId"]: item["value"] for item in follow if item["kind"] == "parking"}
    assert times["startTime"] == "02:00:00Z"
    assert times["endTime"] == "22:00:00Z"


def test_join_catalog_asks_combines_remaining_questions() -> None:
    combined = join_catalog_asks(
        [
            {"id": "airportCode", "ask": "Which airport do you need parking at?"},
            {
                "id": "start",
                "ask": (
                    "What time should parking start on 5 October, "
                    "and what time should it finish on 10 October?"
                ),
            },
            {"id": "covered", "ask": "Do you want covered parking, or is uncovered fine?"},
        ]
    )
    lower = combined.lower()
    assert "airport" in lower
    assert "time" in lower
    assert "covered" in lower
    assert join_catalog_asks([{"id": "covered", "ask": "Do you want covered parking?"}]) == (
        "Do you want covered parking?"
    )
