"""Compose the competition stay-search port. CI/default remains credential-free."""

from __future__ import annotations

from itaa_application.external_search_port import ExternalSearchPort, FlightSearchPort
from itaa_liteapi_hotels.adapter import LiteApiStaySearchAdapter, liteapi_api_key, stay_search_mode
from itaa_liteapi_hotels.fake import FakeStaySearchAdapter
from itaa_liteapi_hotels.fake_flights import FakeFlightSearchAdapter
from itaa_liteapi_hotels.flights import LiteApiFlightSearchAdapter, flight_search_mode

ENV_MODE = "ITAA_STAY_SEARCH_MODE"
ENV_API_KEY = "ITAA_LITEAPI_API_KEY"
ENV_TIMEOUT_MS = "ITAA_LITEAPI_TIMEOUT_MS"
ENV_LIVE_TEST = "ITAA_LITEAPI_LIVE_TEST"


def compose_stay_search_port() -> ExternalSearchPort:
    if stay_search_mode() == "sandbox" and liteapi_api_key():
        return LiteApiStaySearchAdapter.from_env()
    return FakeStaySearchAdapter()


def compose_flight_search_port() -> FlightSearchPort:
    if flight_search_mode() == "sandbox" and liteapi_api_key():
        return LiteApiFlightSearchAdapter.from_env()
    return FakeFlightSearchAdapter()
