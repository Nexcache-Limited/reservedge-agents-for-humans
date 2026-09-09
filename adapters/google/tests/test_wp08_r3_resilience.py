"""WP-08-R3: overall deadline, real backoff sleep, closed transient exhaustion."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Mapping
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from wp08_helpers import CORRELATION, JFK_TEXT, locked_ranking_facts

from itaa_application.errors import ApplicationError
from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.app import create_google_app
from itaa_google_adapter.explanation import deterministic_explanation
from itaa_google_adapter.live import LiveModel, default_invoke, map_provider_error
from itaa_google_adapter.ports import (
    CancelledError,
    CancelToken,
    ExplanationRequest,
    ExtractionRequest,
    ModelRequest,
    ModelResponse,
    QuotaExceeded,
    TimeoutExpired,
    TransientProviderError,
)
from itaa_google_adapter.resilience import (
    FakeMonotonicClock,
    ResiliencePolicy,
    SystemMonotonicClock,
)
from itaa_google_adapter.telemetry import RecordingTelemetry


def _extraction() -> ExtractionRequest:
    return ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION)


def _system_clock_with_log() -> tuple[SystemMonotonicClock, list[float], list[float]]:
    now = [1_000.0]
    sleeps: list[float] = []

    def monotonic() -> float:
        return now[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    clock = SystemMonotonicClock(sleeper=sleeper, monotonic=monotonic, slice_ms=1_000)
    return clock, sleeps, now


class AlwaysTransient:
    def complete(
        self,
        request: ModelRequest,
        *,
        cancel: CancelToken | None = None,
        deadline_ms: int | None = None,
    ) -> ModelResponse:
        del request, cancel, deadline_ms
        raise TransientProviderError()


class TwoTransientThenOk:
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
        if self.calls < 3:
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
        )


def _fresh_live() -> ModuleType:
    from itaa_google_adapter import live as live_mod

    return live_mod


def test_production_composition_uses_system_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = compose_agent()
    assert type(agent._clock) is SystemMonotonicClock  # noqa: SLF001
    assert agent._clock._sleep is time.sleep  # noqa: SLF001
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_GOOGLE_TIMEOUT_MS", "30000")
    live_agent = compose_agent()
    assert type(live_agent._clock) is SystemMonotonicClock  # noqa: SLF001
    assert live_agent._clock._sleep is time.sleep  # noqa: SLF001
    live = _fresh_live()
    assert isinstance(live_agent._model, live.LiveModel)  # noqa: SLF001


def test_fake_mode_can_inject_fake_clock() -> None:
    clock = FakeMonotonicClock(start_ms=7)
    agent = compose_agent(clock=clock)
    assert agent._clock is clock  # noqa: SLF001
    assert clock.now_ms() == 7


def test_hanging_adk_is_cancelled_by_async_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    cancelled = threading.Event()

    async def hang(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> dict[str, object]:
        del task, payload, schema, cancel
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        raise AssertionError("hang completed")

    live = _fresh_live()
    monkeypatch.setattr(live, "run_adk", hang)
    t0 = time.monotonic()
    with pytest.raises(TimeoutExpired):
        asyncio.run(
            live.run_adk_bounded("explain", {"winnerDisplayName": "SkyShield"}, BaseModel, None, 40)
        )
    elapsed = time.monotonic() - t0
    assert started.wait(timeout=1.0)
    assert cancelled.wait(timeout=1.0)
    assert elapsed < 0.2


def test_cancel_during_adk_is_not_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    cancelled = threading.Event()
    token = CancelToken()

    async def hang(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> dict[str, object]:
        del task, payload, schema, cancel
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        raise AssertionError("hang completed")

    live = _fresh_live()
    monkeypatch.setattr(live, "run_adk", hang)

    def cancel_after_start() -> None:
        assert started.wait(timeout=1.0)
        token.cancel()

    worker = threading.Thread(target=cancel_after_start, daemon=True)
    worker.start()
    with pytest.raises(CancelledError):
        asyncio.run(
            live.run_adk_bounded(
                "explain", {"winnerDisplayName": "SkyShield"}, BaseModel, token, 500
            )
        )
    worker.join(timeout=1.0)
    assert cancelled.wait(timeout=1.0)


def test_retries_share_one_overall_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    cancelled = threading.Event()
    calls = {"n": 0}

    async def hang(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> dict[str, object]:
        del task, payload, schema, cancel
        calls["n"] += 1
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        raise AssertionError("hang completed")

    live = _fresh_live()
    monkeypatch.setattr(live, "live_sdk_available", lambda: True)
    monkeypatch.setattr(live, "vertex_config_ready", lambda: True)
    monkeypatch.setattr(live, "run_adk", hang)
    policy = ResiliencePolicy(timeout_ms=50, max_attempts=3, base_backoff_ms=1, jitter_ms=0)
    t0 = time.monotonic()
    result = compose_agent(
        model=live.LiveModel(),
        clock=SystemMonotonicClock(),
        policy=policy,
    ).extract(_extraction())
    elapsed = time.monotonic() - t0
    assert result.fallback == "manual_structured_input"
    assert started.wait(timeout=1.0)
    assert cancelled.wait(timeout=1.0)
    assert calls["n"] == 1
    assert elapsed < 0.25


def test_timeout_extract_uses_manual_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hang(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> dict[str, object]:
        del task, payload, schema, cancel
        await asyncio.Event().wait()
        raise AssertionError("hang completed")

    live = _fresh_live()
    monkeypatch.setattr(live, "live_sdk_available", lambda: True)
    monkeypatch.setattr(live, "vertex_config_ready", lambda: True)
    monkeypatch.setattr(live, "run_adk", hang)
    result = compose_agent(
        model=live.LiveModel(),
        clock=SystemMonotonicClock(),
        policy=ResiliencePolicy(timeout_ms=40, max_attempts=1),
    ).extract(_extraction())
    assert result.proposal is None
    assert result.fallback == "manual_structured_input"


def test_timeout_explain_uses_deterministic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hang(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> dict[str, object]:
        del task, payload, schema, cancel
        await asyncio.Event().wait()
        raise AssertionError("hang completed")

    live = _fresh_live()
    monkeypatch.setattr(live, "live_sdk_available", lambda: True)
    monkeypatch.setattr(live, "vertex_config_ready", lambda: True)
    monkeypatch.setattr(live, "run_adk", hang)
    facts = locked_ranking_facts()
    result = compose_agent(
        model=live.LiveModel(),
        clock=SystemMonotonicClock(),
        policy=ResiliencePolicy(timeout_ms=40, max_attempts=1),
    ).explain(ExplanationRequest(facts=facts))
    assert result.explanation == deterministic_explanation(facts)
    assert result.fallback == "deterministic_facts"
    assert result.grounded is True


def test_system_backoff_uses_injected_sleeper_duration() -> None:
    clock, sleeps, _now = _system_clock_with_log()
    model = TwoTransientThenOk()
    result = compose_agent(
        model=model,
        clock=clock,
        policy=ResiliencePolicy(max_attempts=3, base_backoff_ms=20, jitter_ms=0, timeout_ms=2_000),
    ).explain(ExplanationRequest(facts=locked_ranking_facts()))
    assert model.calls == 3
    assert result.grounded is True
    assert sleeps == pytest.approx([0.02, 0.04])


def test_cancel_before_sleep_does_not_wait() -> None:
    clock, sleeps, _now = _system_clock_with_log()
    token = CancelToken()
    token.cancel()
    with pytest.raises(ApplicationError, match="request: cancelled"):
        compose_agent(
            model=AlwaysTransient(), clock=clock, policy=ResiliencePolicy(max_attempts=2)
        ).extract(
            _extraction(),
            cancel=token,
        )
    assert sleeps == []


def test_cancel_during_sliced_sleep_stops_remaining_delay() -> None:
    now = [1_000.0]
    sleeps: list[float] = []
    token = CancelToken()

    def monotonic() -> float:
        return now[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds
        token.cancel()

    clock = SystemMonotonicClock(sleeper=sleeper, monotonic=monotonic, slice_ms=10)
    with pytest.raises(ApplicationError, match="request: cancelled"):
        compose_agent(
            model=AlwaysTransient(),
            clock=clock,
            policy=ResiliencePolicy(max_attempts=3, base_backoff_ms=80, jitter_ms=0),
        ).extract(_extraction(), cancel=token)
    assert sleeps == pytest.approx([0.01])
    assert sum(sleeps) < 0.08


def test_exhausted_transient_is_model_unavailable() -> None:
    clock = FakeMonotonicClock()
    with pytest.raises(ApplicationError, match="model: unavailable") as raised:
        compose_agent(
            model=AlwaysTransient(),
            clock=clock,
            policy=ResiliencePolicy(max_attempts=2, jitter_ms=0),
        ).extract(_extraction())
    assert raised.value.field == "model"
    assert raised.value.code == "unavailable"
    assert "TransientProviderError" not in str(raised.value)


def test_exhausted_transient_http_is_not_internal_closed() -> None:
    application = create_google_app()
    application.state.google_agent = compose_agent(
        model=AlwaysTransient(),
        clock=FakeMonotonicClock(),
        policy=ResiliencePolicy(max_attempts=2, jitter_ms=0),
    )
    client = TestClient(application)
    response = client.post(
        "/v1/google/extractions",
        json={"text": JFK_TEXT, "category": "airport_parking", "correlationId": CORRELATION},
    )
    body = response.json()
    assert body["error"]["field"] == "model"
    assert body["error"]["code"] == "unavailable"
    assert body["error"]["field"] != "internal"
    assert body["error"]["code"] != "closed"
    assert response.status_code != 500
    dumped = response.text.lower()
    assert "transient" not in dumped
    assert "traceback" not in dumped
    assert JFK_TEXT.lower() not in dumped


def test_error_classes_remain_independent() -> None:
    sink = RecordingTelemetry()

    def quota(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema, cancel
        raise QuotaExceeded()

    def refused(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema, cancel
        raise ApplicationError("model", "refused")

    def invalid(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema, cancel
        raise ApplicationError("model", "schema_invalid")

    def timed_out(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema, cancel
        raise TimeoutExpired()

    token = CancelToken()
    token.cancel()

    def cancelled(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema
        if cancel is not None:
            cancel.check()
        raise AssertionError("should have cancelled")

    clock = FakeMonotonicClock()
    policy = ResiliencePolicy(max_attempts=2, jitter_ms=0)
    with pytest.raises(ApplicationError, match="model: quota_exceeded"):
        compose_agent(
            model=LiveModel(invoke=quota), clock=clock, policy=policy, telemetry=sink
        ).extract(_extraction())
    with pytest.raises(ApplicationError, match="model: refused"):
        compose_agent(model=LiveModel(invoke=refused), clock=clock, policy=policy).extract(
            _extraction()
        )
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_agent(model=LiveModel(invoke=invalid), clock=clock, policy=policy).extract(
            _extraction()
        )
    timed = compose_agent(model=LiveModel(invoke=timed_out), clock=clock, policy=policy).extract(
        _extraction()
    )
    assert timed.fallback == "manual_structured_input"
    with pytest.raises(ApplicationError, match="request: cancelled"):
        compose_agent(model=LiveModel(invoke=cancelled), clock=clock, policy=policy).extract(
            _extraction(),
            cancel=token,
        )
    with pytest.raises(ApplicationError, match="model: unavailable"):
        compose_agent(model=AlwaysTransient(), clock=clock, policy=policy).extract(_extraction())
    for record in sink.records:
        payload = record.to_safe_mapping()
        blob = str(payload)
        assert "QuotaExceeded" not in blob
        assert JFK_TEXT not in blob
        assert "prompt_text" not in payload
        assert "AIza" not in blob


def test_zero_and_negative_system_sleep_return_immediately() -> None:
    clock, sleeps, _now = _system_clock_with_log()
    clock.sleep_ms(0)
    clock.sleep_ms(-5)
    assert sleeps == []


def test_closed_mapping_omits_provider_text() -> None:
    class UnavailableBackend(Exception):
        pass

    mapped = map_provider_error(UnavailableBackend("AIzaSECRET prompt leaked owner-project"))
    assert isinstance(mapped, TransientProviderError)
    assert "AIza" not in str(mapped)
    assert "prompt" not in str(mapped)
    assert "owner-project" not in str(mapped)
    assert "UnavailableBackend" not in str(mapped)


def test_default_invoke_without_vertex_stays_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(ApplicationError, match="model: unavailable"):
        default_invoke("extract", {"text": "x", "category": "airport_parking"}, BaseModel, None, 50)
