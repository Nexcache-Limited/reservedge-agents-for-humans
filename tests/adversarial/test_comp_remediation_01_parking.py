"""COMP-REMEDIATION-01 parking clock/date combining and airport replies."""

from __future__ import annotations

from itaa_api.agent_requirements import (
    apply_model_patches,
    apply_patch,
    empty_domain,
    extract_conversation_patches,
    overlay_time_on_instant,
    resolve_airport_reply,
)


def test_clock_range_does_not_overwrite_october_trip_dates() -> None:
    patches = extract_conversation_patches(
        "hotel needed in manchester from 24 to 25 October. covered parking from 2 am to 10 pm",
        source="current_turn",
    )
    by_field = {item["fieldId"]: item["value"] for item in patches if item["kind"] == "parking"}
    assert str(by_field.get("start", "")).startswith("2026-10-24") or "startTime" in by_field
    if "start" in by_field:
        assert str(by_field["start"]).startswith("2026-10-24")
        assert str(by_field["end"]).startswith("2026-10-25")
        assert "T02:00:00Z" in str(by_field["start"])
        assert "T22:00:00Z" in str(by_field["end"])
    else:
        assert by_field["startTime"] == "02:00:00Z"
        assert by_field["endTime"] == "22:00:00Z"
        overlaid_start = overlay_time_on_instant("2026-10-24", str(by_field["startTime"]))
        overlaid_end = overlay_time_on_instant("2026-10-25", str(by_field["endTime"]))
        assert overlaid_start == "2026-10-24T02:00:00Z"
        assert overlaid_end == "2026-10-25T22:00:00Z"


def test_follow_up_clocks_overlay_existing_november_dates() -> None:
    follow = extract_conversation_patches(
        "8am on the 10th until 6pm on the 15th",
        source="current_turn",
        calendar_context=(
            "need hotel and covered parking at London heathrow from 10th to 15th November"
        ),
    )
    times = {item["fieldId"]: item["value"] for item in follow if item["kind"] == "parking"}
    start = overlay_time_on_instant("2026-11-10", str(times.get("startTime") or "08:00:00Z"))
    end = overlay_time_on_instant("2026-11-15", str(times.get("endTime") or "18:00:00Z"))
    assert start == "2026-11-10T08:00:00Z"
    assert end == "2026-11-15T18:00:00Z"


def test_am_pm_variants_and_overnight_parking() -> None:
    patches = extract_conversation_patches(
        "covered parking from 10 pm to 6 am",
        source="current_turn",
        calendar_context="parking at MAN from 24 to 25 October",
    )
    times = {item["fieldId"]: item["value"] for item in patches if item["kind"] == "parking"}
    assert times["startTime"] == "22:00:00Z"
    assert times["endTime"] == "06:00:00Z"
    start = overlay_time_on_instant("2026-10-24", str(times["startTime"]))
    end = overlay_time_on_instant("2026-10-25", str(times["endTime"]))
    assert start == "2026-10-24T22:00:00Z"
    assert end == "2026-10-25T06:00:00Z"


def test_model_patch_cannot_replace_confirmed_date_with_hour() -> None:
    domain = empty_domain("parking", provenance="explicit", accepted=True)
    apply_patch(
        domain,
        "start",
        "2026-10-24",
        source="earlier_turn",
        provenance="explicit",
    )
    accepted, rejected = apply_model_patches(
        {"parking": domain},
        [
            {
                "kind": "parking",
                "fieldId": "start",
                "value": "2026-10-02T02:00:00Z",
                "evidence": "2 am",
            }
        ],
        conversation=(
            "hotel needed in manchester from 24 to 25 October. covered parking from 2 am to 10 pm"
        ),
        last_user_message="covered parking from 2 am to 10 pm",
        source="current_turn",
    )
    assert rejected
    assert not any(item.get("fieldId") == "start" and item in accepted for item in accepted)
    fields = domain["fields"]
    assert isinstance(fields, dict)
    start = fields["start"]
    assert isinstance(start, dict)
    assert start["value"] == "2026-10-24"


def test_man_and_manchester_airport_resolve_deterministically() -> None:
    assert resolve_airport_reply("man") == "MAN"
    assert resolve_airport_reply("MAN") == "MAN"
    assert resolve_airport_reply("manchester") == "MAN"
    assert resolve_airport_reply("Manchester Airport") == "MAN"
    assert resolve_airport_reply("london") == ""
    assert resolve_airport_reply("heathrow") == "LHR"
