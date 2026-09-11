"""Map Prioticket Distributor JSON onto provider-neutral experience offers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from itaa_application.external_search_port import (
    ExperienceOffer,
    ExternalSearchQuery,
    SearchProvenance,
)

PROVIDER_ID = "prioticket"
PRODUCTS_SCOPE = "https://www.prioticketapis.com/auth/distributor/products"


def _as_mapping(raw: object) -> Mapping[str, Any]:
    return raw if isinstance(raw, Mapping) else {}


def _text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return ""


def iter_items(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    data = payload.get("data")
    if isinstance(data, Mapping):
        for key in ("items", "products", "destinations"):
            rows = data.get(key)
            if isinstance(rows, list):
                for item in rows:
                    if isinstance(item, Mapping):
                        yield item
                return
        product = data.get("product")
        if isinstance(product, Mapping):
            yield product
            return
    rows = payload.get("items")
    if isinstance(rows, list):
        for item in rows:
            if isinstance(item, Mapping):
                yield item


def match_destination_id(payload: Mapping[str, Any], city: str) -> str:
    needle = " ".join(city.strip().lower().split())
    if not needle:
        return ""
    for item in iter_items(payload):
        name = _text(item.get("destination_name")).lower()
        slug = _text(item.get("destination_slug")).lower()
        if needle == name or needle in name or name in needle or needle.replace(" ", "-") in slug:
            return _text(item.get("destination_id"))
    return ""


def _duration_minutes(product: Mapping[str, Any], content: Mapping[str, Any]) -> int | None:
    raw = product.get("product_duration")
    if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        return value if value > 0 else None
    text = _text(content.get("product_duration_text")).lower()
    if "hour" in text:
        try:
            hours = float(text.split("hour", 1)[0].strip().split()[-1])
        except (ValueError, IndexError):
            return None
        minutes = int(hours * 60)
        return minutes if minutes > 0 else None
    return None


def _amount_minor(raw: object) -> int | None:
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw * 100 if raw < 1000 else raw
    if isinstance(raw, float):
        return int(round(raw * 100))
    if isinstance(raw, str) and raw.strip():
        try:
            return int(round(float(raw.strip()) * 100))
        except ValueError:
            return None
    return None


def _currency(product: Mapping[str, Any]) -> str | None:
    payment = _as_mapping(product.get("product_payment_detail"))
    currency = _as_mapping(payment.get("product_payment_currency"))
    code = _text(currency.get("currency_code"), product.get("product_currency")).upper()
    return code or None


def _photo(content: Mapping[str, Any]) -> str | None:
    images = content.get("product_images")
    if not isinstance(images, list):
        return None
    for item in images:
        if not isinstance(item, Mapping):
            continue
        url = _text(item.get("image_url"))
        if url.startswith("https://") and " " not in url:
            return url[:500]
    return None


def _location(product: Mapping[str, Any], fallback: str) -> str:
    destinations = product.get("product_destinations")
    if isinstance(destinations, list):
        names: list[str] = []
        for item in destinations:
            if isinstance(item, Mapping):
                name = _text(item.get("destination_name"))
                if name:
                    names.append(name)
            elif isinstance(item, str) and item.strip() and not item.startswith("PRODUCT_"):
                names.append(item.strip())
        if names:
            return ", ".join(names[:2])
    pickups = product.get("product_pickup_point_details")
    if isinstance(pickups, list):
        for item in pickups:
            if isinstance(item, Mapping):
                name = _text(item.get("pickup_point_name"))
                if name:
                    return name
    return fallback


def _category(product: Mapping[str, Any], content: Mapping[str, Any], title: str) -> str:
    categories = product.get("product_categories")
    if isinstance(categories, list):
        for item in categories:
            if isinstance(item, Mapping):
                name = _text(item.get("category_name"))
                if name:
                    return name
    supplier = _text(content.get("product_supplier_name"))
    lower = f"{title} {supplier}".lower()
    if "museum" in lower:
        return "Museum"
    if "tour" in lower:
        return "Tour"
    if "cruise" in lower or "boat" in lower:
        return "Cruise"
    if "show" in lower or "concert" in lower:
        return "Event"
    if supplier:
        return supplier
    return "Experience"


def _cancellation(product: Mapping[str, Any]) -> str | None:
    allowed = product.get("product_cancellation_allowed")
    if allowed is True:
        return "Cancellation allowed"
    if allowed is False:
        return "Non-refundable"
    return None


def _availability(product: Mapping[str, Any], query: ExternalSearchQuery) -> str:
    if product.get("product_availability") is False:
        return "unavailable"
    start = _text(product.get("product_start_date"))[:10]
    end = _text(product.get("product_end_date"))[:10]
    window = " – ".join(item for item in (start, end) if item)
    prefs = " ".join(query.preferences)
    if window and prefs:
        return f"available {window}; {prefs}"
    if window:
        return f"available {window}"
    if prefs:
        return f"available; {prefs}"
    if product.get("product_availability") is True:
        return "available"
    return "availability unknown"


def normalize_offers(
    payload: Mapping[str, Any],
    query: ExternalSearchQuery,
    source: SearchProvenance,
) -> tuple[ExperienceOffer, ...]:
    offers: list[ExperienceOffer] = []
    fallback = ""
    for product in iter_items(payload):
        content = _as_mapping(product.get("product_content"))
        title = _text(content.get("product_title"), product.get("product_title"))
        product_id = _text(product.get("product_id"), product.get("product_external_id"))
        if not title or not product_id:
            continue
        offers.append(
            ExperienceOffer(
                provider_id=PROVIDER_ID,
                source=source,
                external_id=product_id,
                title=title,
                category=_category(product, content, title),
                location=_location(product, fallback),
                availability=_availability(product, query),
                currency=_currency(product),
                amount_minor=_amount_minor(product.get("product_from_price")),
                duration_minutes=_duration_minutes(product, content),
                cancellation=_cancellation(product),
                photo_url=_photo(content),
            )
        )
        if len(offers) >= 6:
            break
    return tuple(offers)


def secret_in_text(blob: str, *secrets: str) -> bool:
    lower = blob.lower()
    for item in secrets:
        token = item.strip()
        if len(token) >= 8 and token.lower() in lower:
            return True
    return False
