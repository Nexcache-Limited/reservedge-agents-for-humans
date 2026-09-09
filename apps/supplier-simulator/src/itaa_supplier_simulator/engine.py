"""Deterministic isolated simulated supplier. Availability is simulated."""

from __future__ import annotations

from datetime import datetime, timedelta

from itaa_application.errors import ApplicationError
from itaa_application.supplier_port import (
    ClosedReason,
    SupplierAttempt,
    SupplierPort,
    SupplierTerminal,
    TerminalKind,
    validity_duration_in_bounds,
)
from itaa_contracts_generated.offer import Offer as ContractOffer
from itaa_domain.value_objects import JS_SAFE_MAX, format_utc, parse_utc
from itaa_supplier_simulator.economics import billable_days, require_minor, scale_amount
from itaa_supplier_simulator.policy import SimulatedPolicy


class SimulatedSupplier(SupplierPort):
    def __init__(self, policy: SimulatedPolicy, *, remaining_capacity: int | None = None) -> None:
        if type(policy) is not SimulatedPolicy:
            raise ApplicationError("policy", "invalid")
        remaining = policy.capacity if remaining_capacity is None else remaining_capacity
        if type(remaining) is not int or isinstance(remaining, bool):
            raise ApplicationError("remaining_capacity", "must_be_integer")
        if remaining < 0 or remaining > policy.capacity:
            raise ApplicationError("remaining_capacity", "out_of_range")
        self._policy = policy
        self._remaining = remaining

    @property
    def remaining_capacity(self) -> int:
        return self._remaining

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        token = request.envelope.assignment.supplier_token
        if token != self._policy.supplier_token:
            raise ApplicationError("supplier_token", "mismatch")
        payload = request.envelope.payload_dict()
        reason = self._decline(payload, request)
        if reason is not None:
            return self._declined(reason, request)
        effective_until = _effective_until(request, self._policy)
        if not validity_duration_in_bounds(
            request.occurred_at,
            effective_until,
            minimum_seconds=self._policy.min_validity_seconds,
            maximum_seconds=self._policy.max_validity_seconds,
        ):
            return self._declined(ClosedReason.VALIDITY_WINDOW, request)
        offer = self._offer(payload, request, effective_until)
        ContractOffer.model_validate(offer)
        self._remaining -= 1
        return SupplierTerminal(
            TerminalKind.OFFER,
            token,
            request.correlation_id,
            request.invitation,
            request.occurred_at,
            payload=offer,
        )

    def _declined(self, reason: ClosedReason, request: SupplierAttempt) -> SupplierTerminal:
        return SupplierTerminal(
            TerminalKind.DECLINED,
            request.envelope.assignment.supplier_token,
            request.correlation_id,
            request.invitation,
            request.occurred_at,
            reason,
        )

    def _decline(self, payload: dict[str, object], request: SupplierAttempt) -> ClosedReason | None:
        policy = self._policy
        if payload.get("category") != "airport_parking":
            return ClosedReason.UNSUPPORTED_CATEGORY
        location = payload.get("location")
        airport = location.get("airportCode") if isinstance(location, dict) else None
        if airport not in policy.airports:
            return ClosedReason.UNSUPPORTED_AIRPORT
        requirements = payload.get("requirements")
        vehicle = requirements.get("vehicleClass") if isinstance(requirements, dict) else None
        if vehicle not in policy.vehicles:
            return ClosedReason.UNSUPPORTED_VEHICLE
        if self._remaining < 1:
            return ClosedReason.INSUFFICIENT_CAPACITY
        if request.occurred_at >= request.deadline:
            return ClosedReason.RESPONSE_DEADLINE
        window = payload.get("serviceWindow")
        if not isinstance(window, dict):
            return ClosedReason.UNSUPPORTED_SERVICE
        start = parse_utc(window.get("start"), "service_start")
        end = parse_utc(window.get("end"), "service_end")
        days = billable_days(start, end)
        if policy.discount_micros > policy.max_discount_micros:
            return ClosedReason.DISCOUNT_CAP
        listed = require_minor(policy.list_minor_per_day, "list") * days
        if listed > JS_SAFE_MAX:
            raise ApplicationError("listed", "overflow")
        demanded = scale_amount(listed, policy.demand_micros)
        discounted = scale_amount(demanded, 1_000_000 - policy.discount_micros)
        incentive = demanded - discounted
        if incentive > policy.acquisition_budget_minor:
            return ClosedReason.ACQUISITION_CAP
        floor = policy.floor_minor_per_day * days
        if discounted < floor:
            return ClosedReason.PRICE_FLOOR
        if policy.add_ons and policy.add_on_price_minor <= policy.add_on_cost_minor:
            return ClosedReason.ADD_ON_MARGIN
        if policy.cancellation.value == "non_refundable" and policy.refund.value != "none":
            return ClosedReason.CANCELLATION_PAIR
        if policy.cancellation.value != "non_refundable" and policy.refund.value == "none":
            return ClosedReason.CANCELLATION_PAIR
        return None

    def _offer(
        self,
        payload: dict[str, object],
        request: SupplierAttempt,
        valid_until: datetime,
    ) -> dict[str, object]:
        policy = self._policy
        window = payload.get("serviceWindow")
        if not isinstance(window, dict):
            raise ApplicationError("service_window", "invalid")
        days = billable_days(
            parse_utc(window.get("start"), "service_start"),
            parse_utc(window.get("end"), "service_end"),
        )
        listed = policy.list_minor_per_day * days
        demanded = scale_amount(listed, policy.demand_micros)
        discounted = scale_amount(demanded, 1_000_000 - policy.discount_micros)
        floor = policy.floor_minor_per_day * days
        subtotal = discounted if discounted >= floor else floor
        subtotal += policy.add_on_price_minor
        if subtotal > JS_SAFE_MAX:
            raise ApplicationError("subtotalMinor", "overflow")
        total = subtotal + policy.fees_minor + policy.tax_minor
        if total > JS_SAFE_MAX:
            raise ApplicationError("totalMinor", "overflow")
        return {
            "schemaVersion": "1.0",
            "offerId": request.offer_id.to_primitive(),
            "intentId": request.envelope.assignment.scoped_intent_id.to_primitive(),
            "supplierToken": policy.supplier_token.to_primitive(),
            "version": 1,
            "status": "submitted",
            "price": {
                "subtotalMinor": subtotal,
                "feesMinor": policy.fees_minor,
                "taxMinor": policy.tax_minor,
                "totalMinor": total,
                "currency": "USD",
            },
            "service": {
                "lotType": policy.lot_type.value,
                "shuttleMinutes": policy.shuttle_minutes,
                "distanceMeters": policy.distance_metres,
                "availability": policy.availability,
                "addOns": [item.value for item in policy.add_ons],
            },
            "terms": {
                "cancellation": policy.cancellation.value,
                "refund": policy.refund.value,
            },
            "validFrom": format_utc(request.occurred_at),
            "validUntil": format_utc(valid_until),
            "evidence": [
                {"type": "supplier_policy", "ref": policy.policy_ref},
                {"type": "rate_card", "ref": policy.rate_ref},
                {"type": "lot_rules", "ref": policy.lot_ref},
                {"type": "availability_snapshot", "ref": policy.availability_ref},
            ],
            "simulation": True,
            "signature": request.signature.to_primitive(),
        }


def _effective_until(request: SupplierAttempt, policy: SimulatedPolicy) -> datetime:
    return min(
        request.occurred_at + timedelta(seconds=policy.validity_seconds),
        request.deadline,
        request.envelope.assignment.valid_until,
    )
