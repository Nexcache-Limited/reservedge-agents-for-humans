from __future__ import annotations

from wp08_helpers import CORRELATION, JFK_TEXT, locked_ranking_facts

from itaa_application.errors import ApplicationError
from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.explanation import deterministic_explanation
from itaa_google_adapter.fake import FakeModel
from itaa_google_adapter.ports import (
    CancelToken,
    ExplanationRequest,
    ExtractionRequest,
    ModelRequest,
    ModelResponse,
    TransientProviderError,
)
from itaa_google_adapter.resilience import FakeMonotonicClock, ResiliencePolicy


class FlakyThenOk:
    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        request: ModelRequest,
        *,
        cancel: CancelToken | None = None,
        deadline_ms: int | None = None,
    ) -> ModelResponse:
        del request, cancel, deadline_ms
        self.calls += 1
        if self.calls == 1:
            raise TransientProviderError()
        return ModelResponse(
            mapping={
                "explanation": (
                    "SkyShield is the recommended simulated airport-parking option. "
                    "The ranking scores, offer totals, and downside remain those already "
                    "shown on the buyer snapshot."
                )
            },
            model_name="fake-deterministic",
            input_tokens=1,
            output_tokens=1,
        )


def test_timeout_returns_manual_or_deterministic_fallback() -> None:
    clock = FakeMonotonicClock()
    policy = ResiliencePolicy(timeout_ms=50, max_attempts=1)
    extract = compose_agent(
        model=FakeModel(clock=clock, delay_ms=80),
        clock=clock,
        policy=policy,
    ).extract(ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION))
    assert extract.proposal is None
    assert extract.fallback == "manual_structured_input"
    facts = locked_ranking_facts()
    clock = FakeMonotonicClock()
    explained = compose_agent(
        model=FakeModel(clock=clock, delay_ms=80),
        clock=clock,
        policy=policy,
    ).explain(ExplanationRequest(facts=facts), cancel=CancelToken())
    assert explained.explanation == deterministic_explanation(facts)
    assert explained.fallback == "deterministic_facts"


def test_quota_fails_closed() -> None:
    try:
        compose_agent(model=FakeModel(quota=True)).extract(
            ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION)
        )
    except ApplicationError as exc:
        assert exc.field == "model"
        assert exc.code == "quota_exceeded"
    else:
        raise AssertionError("expected quota failure")


def test_retry_then_success_does_not_mutate() -> None:
    model = FlakyThenOk()
    clock = FakeMonotonicClock()
    result = compose_agent(
        model=model,
        clock=clock,
        policy=ResiliencePolicy(max_attempts=2),
    ).explain(ExplanationRequest(facts=locked_ranking_facts()))
    assert model.calls == 2
    assert result.grounded is True


def test_cancellation_stops_in_flight_fake_work() -> None:
    token = CancelToken()
    token.cancel()
    try:
        compose_agent(model=FakeModel(delay_ms=10)).extract(
            ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION),
            cancel=token,
        )
    except ApplicationError as exc:
        assert exc.field == "request"
        assert exc.code == "cancelled"
    else:
        raise AssertionError("expected cancellation")
