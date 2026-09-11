"""Small in-repo city map for stay research. Not a geocoder and not parking IATA."""

from __future__ import annotations

from typing import Final

# city lower -> (display name, ISO-2, currency)
CITY_COUNTRY: Final[dict[str, tuple[str, str, str]]] = {
    "milan": ("Milan", "IT", "EUR"),
    "milano": ("Milan", "IT", "EUR"),
    "rome": ("Rome", "IT", "EUR"),
    "roma": ("Rome", "IT", "EUR"),
    "london": ("London", "GB", "GBP"),
    "new york": ("New York", "US", "USD"),
    "nyc": ("New York", "US", "USD"),
    "paris": ("Paris", "FR", "EUR"),
    "edinburgh": ("Edinburgh", "GB", "GBP"),
    "manchester": ("Manchester", "GB", "GBP"),
    "amsterdam": ("Amsterdam", "NL", "EUR"),
    "dublin": ("Dublin", "IE", "EUR"),
    "mumbai": ("Mumbai", "IN", "INR"),
    "bombay": ("Mumbai", "IN", "INR"),
    "miami": ("Miami", "US", "USD"),
    "barcelona": ("Barcelona", "ES", "EUR"),
    "madrid": ("Madrid", "ES", "EUR"),
    "berlin": ("Berlin", "DE", "EUR"),
    "tokyo": ("Tokyo", "JP", "JPY"),
    "dubai": ("Dubai", "AE", "AED"),
    "los angeles": ("Los Angeles", "US", "USD"),
    "chicago": ("Chicago", "US", "USD"),
    "boston": ("Boston", "US", "USD"),
    "san francisco": ("San Francisco", "US", "USD"),
    "toronto": ("Toronto", "CA", "CAD"),
    "sydney": ("Sydney", "AU", "AUD"),
}

ORIGIN_NATIONALITY: Final[dict[str, str]] = {
    "mumbai": "IN",
    "bombay": "IN",
    "india": "IN",
    "london": "GB",
    "manchester": "GB",
    "edinburgh": "GB",
    "new york": "US",
    "nyc": "US",
    "paris": "FR",
    "milan": "IT",
    "rome": "IT",
    "miami": "US",
    "los angeles": "US",
    "chicago": "US",
    "boston": "US",
    "san francisco": "US",
    "toronto": "CA",
    "sydney": "AU",
}


def lookup_city(raw: str) -> tuple[str, str, str]:
    token = " ".join(raw.strip().lower().split())
    if token in CITY_COUNTRY:
        return CITY_COUNTRY[token]
    return (raw.strip().title() or token.title(), "", "EUR")


def guest_nationality(origin: str, destination_country: str) -> str:
    token = " ".join(origin.strip().lower().split())
    if token in ORIGIN_NATIONALITY:
        return ORIGIN_NATIONALITY[token]
    if destination_country:
        return destination_country
    return "US"
