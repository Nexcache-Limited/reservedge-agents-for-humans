"""Cross-field contract invariants that JSON Schema cannot reliably express."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from itaa_validate_contracts.errors import ContractViolation


def parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError(f"timestamp is not UTC Z: {value}")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _violation(schema_key: str, source: str, path: str, message: str) -> ContractViolation:
    return ContractViolation(
        schema_key=schema_key,
        source=source,
        path=path,
        keyword="invariant",
        message=message,
    )


def check_invariants(
    document: dict[str, Any], *, schema_key: str, source: str
) -> list[ContractViolation]:
    if schema_key == "purchase-intent":
        return _purchase_intent(document, source)
    if schema_key == "offer":
        return _offer(document, source)
    if schema_key == "counter-offer":
        return _window(document, source, schema_key, "createdAt", "expiresAt", "/expiresAt")
    if schema_key == "acceptance":
        return _window(document, source, schema_key, "createdAt", "expiresAt", "/expiresAt")
    if schema_key == "transaction-authorization":
        return _window(document, source, schema_key, "authorizedAt", "expiresAt", "/expiresAt")
    if schema_key == "buyer-offer":
        return _buyer_offer(document, source)
    if schema_key == "cost-ledger":
        return _cost_ledger(document, source)
    return []


def _window(
    document: dict[str, Any],
    source: str,
    schema_key: str,
    start_field: str,
    end_field: str,
    path: str,
) -> list[ContractViolation]:
    try:
        start = parse_utc(str(document[start_field]))
        end = parse_utc(str(document[end_field]))
    except (KeyError, TypeError, ValueError) as exc:
        return [_violation(schema_key, source, path, f"cannot compare times: {exc}")]
    if end <= start:
        return [
            _violation(
                schema_key,
                source,
                path,
                f"{end_field} must be after {start_field}",
            )
        ]
    return []


def _purchase_intent(document: dict[str, Any], source: str) -> list[ContractViolation]:
    schema_key = "purchase-intent"
    found: list[ContractViolation] = []
    window = document.get("serviceWindow", {})
    try:
        start = parse_utc(str(window["start"]))
        end = parse_utc(str(window["end"]))
        if end <= start:
            found.append(
                _violation(schema_key, source, "/serviceWindow", "service end must be after start")
            )
    except (KeyError, TypeError, ValueError) as exc:
        found.append(
            _violation(schema_key, source, "/serviceWindow", f"invalid service window: {exc}")
        )
    found.extend(_window(document, source, schema_key, "createdAt", "expiresAt", "/expiresAt"))
    try:
        created = parse_utc(str(document["createdAt"]))
        expires = parse_utc(str(document["expiresAt"]))
        deadline = parse_utc(str(document["solicitation"]["responseDeadline"]))
        if not (created < deadline <= expires):
            found.append(
                _violation(
                    schema_key,
                    source,
                    "/solicitation/responseDeadline",
                    "response deadline must be after createdAt and no later than expiresAt",
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        found.append(
            _violation(
                schema_key,
                source,
                "/solicitation/responseDeadline",
                f"invalid response deadline: {exc}",
            )
        )
    return found


def _offer(document: dict[str, Any], source: str) -> list[ContractViolation]:
    schema_key = "offer"
    found = _window(document, source, schema_key, "validFrom", "validUntil", "/validUntil")
    price = document.get("price", {})
    try:
        subtotal = int(price["subtotalMinor"])
        fees = int(price["feesMinor"])
        tax = int(price["taxMinor"])
        total = int(price["totalMinor"])
        if total != subtotal + fees + tax:
            found.append(
                _violation(
                    schema_key,
                    source,
                    "/price/totalMinor",
                    "totalMinor must equal subtotalMinor + feesMinor + taxMinor",
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        found.append(_violation(schema_key, source, "/price", f"invalid price components: {exc}"))
    return found


SIMULATION_ZERO_LEDGER_BUCKETS = (
    "confirmedBookingMinor",
    "authorizedLiveMinor",
    "bookingPendingMinor",
    "depositsHoldsMinor",
    "payableNowMinor",
)

SILENT_LEDGER_TOTAL_FIELDS = (
    "totalMinor",
    "combinedMinor",
    "convertedTotalMinor",
    "grandTotalMinor",
)


def _buyer_offer(document: dict[str, Any], source: str) -> list[ContractViolation]:
    schema_key = "buyer-offer"
    found: list[ContractViolation] = []
    if "scoreMicros" in document:
        found.append(
            _violation(
                schema_key,
                source,
                "/scoreMicros",
                "buyer Offer projection must not contain scoreMicros",
            )
        )
    found.extend(_window(document, source, schema_key, "validFrom", "validUntil", "/validUntil"))
    if document.get("simulation") is True:
        if document.get("inventory") != "not_held":
            found.append(
                _violation(
                    schema_key,
                    source,
                    "/inventory",
                    "simulation buyer Offer inventory must be not_held",
                )
            )
        if "inventoryHeldUntil" in document:
            found.append(
                _violation(
                    schema_key,
                    source,
                    "/inventoryHeldUntil",
                    "simulation buyer Offer must omit inventoryHeldUntil; "
                    "validUntil does not imply a hold",
                )
            )
    return found


def _cost_ledger(document: dict[str, Any], source: str) -> list[ContractViolation]:
    schema_key = "cost-ledger"
    found: list[ContractViolation] = []
    rows = document.get("rows")
    if not isinstance(rows, list):
        return [_violation(schema_key, source, "/rows", "rows must be an array")]
    row_currencies: set[str] = set()
    simulation = document.get("simulation") is True
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            found.append(_violation(schema_key, source, f"/rows/{index}", "row must be an object"))
            continue
        currency = row.get("currency")
        if isinstance(currency, str):
            row_currencies.add(currency)
        if simulation:
            for bucket in SIMULATION_ZERO_LEDGER_BUCKETS:
                value = row.get(bucket)
                if value not in (0, None):
                    found.append(
                        _violation(
                            schema_key,
                            source,
                            f"/rows/{index}/{bucket}",
                            f"simulation ledger {bucket} must be 0",
                        )
                    )
    declared = document.get("currencies")
    if isinstance(declared, list):
        declared_set = {item for item in declared if isinstance(item, str)}
        if declared_set != row_currencies:
            found.append(
                _violation(
                    schema_key,
                    source,
                    "/currencies",
                    "currencies must match the distinct currencies present on rows",
                )
            )
    fx = document.get("fx")
    fx_complete = False
    if fx is not None:
        if not isinstance(fx, dict):
            found.append(_violation(schema_key, source, "/fx", "fx must be an object"))
        else:
            missing = [name for name in ("rate", "source", "timestamp") if name not in fx]
            if missing:
                found.append(
                    _violation(
                        schema_key,
                        source,
                        "/fx",
                        f"fx metadata incomplete: missing {', '.join(missing)}",
                    )
                )
            else:
                fx_complete = True
                try:
                    parse_utc(str(fx["timestamp"]))
                except (TypeError, ValueError) as exc:
                    found.append(
                        _violation(
                            schema_key, source, "/fx/timestamp", f"invalid fx timestamp: {exc}"
                        )
                    )
    silent_totals = [name for name in SILENT_LEDGER_TOTAL_FIELDS if name in document]
    if len(row_currencies) > 1 and silent_totals and not fx_complete:
        for name in silent_totals:
            found.append(
                _violation(
                    schema_key,
                    source,
                    f"/{name}",
                    "mixed currencies cannot be summed without evidenced fx metadata",
                )
            )
    return found
