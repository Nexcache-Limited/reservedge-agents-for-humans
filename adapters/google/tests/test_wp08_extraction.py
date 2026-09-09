from __future__ import annotations

from wp08_helpers import CORRELATION, JFK_TEXT

from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.fake import FakeModel
from itaa_google_adapter.ports import ExtractionRequest


def _request(text: str) -> ExtractionRequest:
    return ExtractionRequest(text=text, category="airport_parking", correlation_id=CORRELATION)


def test_valid_airport_parking_extraction_is_requirement_only() -> None:
    result = compose_agent().extract(_request(JFK_TEXT))
    assert result.requires_a1 is True
    assert result.accepted is False
    assert result.proposal is not None
    assert result.proposal["location"] == {"airportCode": "JFK"}
    assert result.proposal["serviceWindow"] == {
        "start": "2026-09-03T13:00:00Z",
        "end": "2026-09-08T22:00:00Z",
    }
    assert result.proposal["requirements"] == {
        "vehicleClass": "standard",
        "covered": "preferred",
        "shuttleMaxMinutes": 20,
    }
    assert result.proposal["constraints"]["currency"] == "USD"
    assert "intentId" not in result.proposal
    assert "buyerToken" not in result.proposal
    assert "createdAt" not in result.proposal
    assert result.field_attributions


def test_missing_required_fields_fail_closed() -> None:
    result = compose_agent().extract(_request("Need parking sometime near the airport."))
    assert result.proposal is None
    assert result.accepted is False
    assert result.requires_a1 is True
    assert "location.airportCode" in result.missing_fields
    assert "serviceWindow.start" in result.missing_fields


def test_conflicting_dates_fail_closed() -> None:
    text = (
        "JFK parking from 2026-09-03T13:00:00Z to 2026-09-08T22:00:00Z "
        "and also from 2026-09-10T13:00:00Z to 2026-09-12T22:00:00Z. "
        "Vehicle class standard. Covered preferred. Shuttle maximum 20 minutes. Currency USD."
    )
    result = compose_agent().extract(_request(text))
    assert result.proposal is None
    assert "serviceWindow.start" in result.ambiguous_fields


def test_conflicting_window_order_fails_closed() -> None:
    text = (
        "JFK parking from 2026-09-08T22:00:00Z to 2026-09-03T13:00:00Z. "
        "Vehicle class standard. Covered preferred. Shuttle maximum 20 minutes. Currency USD."
    )
    result = compose_agent().extract(_request(text))
    assert result.proposal is None
    assert result.accepted is False


def test_impossible_dates_and_times_fail_closed() -> None:
    text = (
        "JFK parking from 2026-02-30T13:00:00Z to 2026-09-08T25:00:00Z. "
        "Vehicle class standard. Covered preferred. Shuttle maximum 20 minutes. Currency USD."
    )
    result = compose_agent().extract(_request(text))
    assert result.proposal is None
    assert result.accepted is False


def test_malformed_and_unknown_fields_fail_closed() -> None:
    malformed = compose_agent(model=FakeModel(malformed=True)).extract(_request(JFK_TEXT))
    assert malformed.proposal is None
    unknown = compose_agent(model=FakeModel(unknown_fields=True)).extract(_request(JFK_TEXT))
    assert unknown.proposal is None
    assert unknown.accepted is False
