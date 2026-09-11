"""Map LiteAPI JSON onto provider-neutral stay offers. Keep LiteAPI types here."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from itaa_application.external_search_port import (
    ExternalSearchQuery,
    SearchProvenance,
    StayOffer,
)

PROVIDER_ID = "liteapi"


def _as_mapping(raw: object) -> Mapping[str, Any]:
    return raw if isinstance(raw, Mapping) else {}


def iter_hotel_rows(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    data = payload.get("data")
    if isinstance(data, Mapping):
        hotels = data.get("hotels") or data.get("results") or data.get("items")
        if isinstance(hotels, list):
            for item in hotels:
                if isinstance(item, Mapping):
                    yield item
            return
    if isinstance(data, list):
        for item in data:
            if isinstance(item, Mapping):
                yield item


def hotel_catalog(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Sidecar hotel metadata from LiteAPI rates (`hotels` next to `data`)."""

    catalog: dict[str, Mapping[str, Any]] = {}
    hotels = payload.get("hotels")
    rows: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(hotels, Mapping):
        rows = [
            (_text(value.get("id"), value.get("hotelId"), key), value)
            for key, value in hotels.items()
            if isinstance(value, Mapping)
        ]
    elif isinstance(hotels, list):
        rows = [
            (_text(item.get("id"), item.get("hotelId")), item)
            for item in hotels
            if isinstance(item, Mapping)
        ]
    for hotel_id, item in rows:
        if hotel_id:
            catalog[hotel_id] = item
    return catalog


def _hotel_block(row: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = row.get("hotel")
    return nested if isinstance(nested, Mapping) else row


def _text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _locality(hotel: Mapping[str, Any], fallback: str) -> str:
    address = hotel.get("address")
    city = ""
    country = ""
    if isinstance(address, Mapping):
        city = _text(address.get("city"), address.get("locality"), address.get("city_name"))
        country = _text(
            address.get("country"),
            address.get("countryCode"),
            address.get("country_code"),
        )
    city = city or _text(
        hotel.get("city"),
        hotel.get("cityName"),
        hotel.get("city_name"),
        hotel.get("locality"),
    )
    country = country or _text(
        hotel.get("country"),
        hotel.get("countryCode"),
        hotel.get("country_code"),
    )
    if city and country:
        return f"{city}, {country}"
    if city:
        return city
    if isinstance(address, str) and address.strip():
        return address.strip()[:120]
    return fallback


def _amount_minor(raw: object) -> tuple[int | None, str | None]:
    if isinstance(raw, Mapping):
        total = raw.get("total")
        if isinstance(total, list) and total:
            return _amount_minor(total[0])
        nested = raw.get("amount") or raw.get("value")
        currency = raw.get("currency") if isinstance(raw.get("currency"), str) else None
        amount, nested_currency = _amount_minor(nested)
        return amount, currency or nested_currency
    if isinstance(raw, bool):
        return None, None
    if isinstance(raw, int):
        return raw * 100 if raw < 1_000_000 else raw, None
    if isinstance(raw, float):
        return int(round(raw * 100)), None
    if isinstance(raw, str) and raw.strip():
        try:
            return int(round(float(raw) * 100)), None
        except ValueError:
            return None, None
    return None, None


def _rate_price(row: Mapping[str, Any]) -> tuple[int | None, str | None]:
    hotel = _hotel_block(row)
    candidates: list[object] = [
        row.get("minRate"),
        row.get("price"),
        hotel.get("minRate"),
        hotel.get("price"),
    ]
    room_types = row.get("roomTypes") or row.get("rooms") or hotel.get("roomTypes")
    if isinstance(room_types, list):
        for room in room_types:
            if not isinstance(room, Mapping):
                continue
            rates = room.get("rates") or room.get("rate")
            rate_list = rates if isinstance(rates, list) else [rates]
            for rate in rate_list:
                if isinstance(rate, Mapping):
                    candidates.append(rate.get("retailRate") or rate.get("price") or rate)
    for item in candidates:
        amount, currency = _amount_minor(item)
        if amount is not None:
            if currency is None and isinstance(item, Mapping):
                currency = item.get("currency") if isinstance(item.get("currency"), str) else None
            return amount, currency
    return None, None


def _https_url(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text.startswith("https://") or " " in text or len(text) > 500:
        return None
    return text


def _photo_url(hotel: Mapping[str, Any], meta: Mapping[str, Any]) -> str | None:
    blobs: list[Mapping[str, Any]] = [hotel, meta]
    for blob in blobs:
        for key in ("thumbnail", "main_photo", "mainPhoto", "image", "photo"):
            url = _https_url(blob.get(key))
            if url:
                return url
        images = blob.get("hotelImages") or blob.get("images") or blob.get("photos")
        if isinstance(images, list):
            for item in images:
                if isinstance(item, str):
                    url = _https_url(item)
                    if url:
                        return url
                if isinstance(item, Mapping):
                    url = _https_url(item.get("url") or item.get("src") or item.get("thumbnail"))
                    if url:
                        return url
    return None


def _rate_ref(row: Mapping[str, Any]) -> str | None:
    room_types = row.get("roomTypes") or row.get("rooms")
    candidates: list[object] = [row.get("offerId"), row.get("rateId")]
    if isinstance(room_types, list):
        for room in room_types:
            if not isinstance(room, Mapping):
                continue
            candidates.append(room.get("offerId"))
            rates = room.get("rates") or room.get("rate")
            rate_list = rates if isinstance(rates, list) else [rates]
            for rate in rate_list:
                if isinstance(rate, Mapping):
                    candidates.append(rate.get("offerId") or rate.get("rateId"))
    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _cancellation(row: Mapping[str, Any]) -> str | None:
    room_types = row.get("roomTypes") or row.get("rooms")
    blobs: list[Mapping[str, Any]] = [row]
    if isinstance(room_types, list):
        for room in room_types:
            if not isinstance(room, Mapping):
                continue
            blobs.append(room)
            rates = room.get("rates")
            if isinstance(rates, list):
                blobs.extend(item for item in rates if isinstance(item, Mapping))
    for blob in blobs:
        policies = blob.get("cancellationPolicies") or blob.get("cancellation")
        if isinstance(policies, str) and policies.strip():
            return policies.strip()[:180]
        if isinstance(policies, list):
            for policy in policies:
                if isinstance(policy, str) and policy.strip():
                    return policy.strip()[:180]
                if isinstance(policy, Mapping):
                    text = _text(
                        policy.get("description"),
                        policy.get("type"),
                        policy.get("name"),
                    )
                    if text:
                        return text[:180]
    return None


def normalize_offers(
    payload: Mapping[str, Any],
    query: ExternalSearchQuery,
    source: SearchProvenance,
) -> tuple[StayOffer, ...]:
    fallback_locality = query.destination.value
    catalog = hotel_catalog(payload)
    offers: list[StayOffer] = []
    for row in iter_hotel_rows(payload):
        hotel = _hotel_block(row)
        external_id = _text(
            hotel.get("id"),
            hotel.get("hotelId"),
            row.get("hotelId"),
            row.get("id"),
        )
        meta = catalog.get(external_id, {})
        name = _text(
            hotel.get("name"),
            hotel.get("hotelName"),
            row.get("name"),
            meta.get("name"),
            meta.get("hotelName"),
        )
        if not name or not external_id:
            continue
        amount, currency = _rate_price(row)
        locality = _locality(hotel, "") or _locality(meta, fallback_locality)
        offers.append(
            StayOffer(
                provider_id=PROVIDER_ID,
                source=source,
                external_id=external_id,
                name=name,
                locality=locality,
                check_in=query.start,
                check_out=query.end,
                currency=currency,
                amount_minor=amount,
                cancellation=_cancellation(row),
                availability="available",
                booking_authority="none",
                photo_url=_photo_url(hotel, meta),
                rate_ref=_rate_ref(row),
            )
        )
        if len(offers) >= 8:
            break
    return tuple(offers)
