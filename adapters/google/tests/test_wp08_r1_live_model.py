from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import BaseModel
from wp08_helpers import CORRELATION, JFK_TEXT, locked_ranking_facts

from itaa_application.errors import ApplicationError
from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.live import (
    ExplainOutput,
    ExtractOutput,
    LiveModel,
    default_invoke,
    describe_live_path,
    extract_mapping_from_output,
    map_provider_error,
    minimize_payload,
    schema_for_task,
)
from itaa_google_adapter.mode import vertex_config_ready
from itaa_google_adapter.ports import (
    CancelToken,
    ExplanationRequest,
    ExtractionRequest,
    ModelRequest,
    QuotaExceeded,
    TimeoutExpired,
    TransientProviderError,
)
from itaa_google_adapter.resilience import FakeMonotonicClock, ResiliencePolicy
from itaa_google_adapter.telemetry import RecordingTelemetry


def _extract_request(text: str = JFK_TEXT) -> ModelRequest:
    return ModelRequest(
        task="extract",
        correlation_id=CORRELATION,
        payload={"text": text, "category": "airport_parking", "secret": "drop-me"},
    )


def _complete_extract(mapping: Mapping[str, object]) -> Mapping[str, object]:
    return {
        "mapping": dict(mapping),
        "input_tokens": 11,
        "output_tokens": 17,
        "model_name": "gemini-2.5-flash",
    }


def test_vertex_and_gemini_configuration_are_selected() -> None:
    described = describe_live_path()
    assert described["model"] == "gemini-2.5-flash"
    assert described["sdk"] == "google.adk"
    assert described["region"] in {"us-central1", described["region"]}
    assert "project_id" not in described


def test_minimized_extraction_and_explanation_payloads() -> None:
    extract = minimize_payload(_extract_request())
    assert extract == {"text": JFK_TEXT, "category": "airport_parking"}
    assert "secret" not in extract
    explain = minimize_payload(
        ModelRequest(
            task="explain",
            correlation_id=CORRELATION,
            payload={
                "winnerDisplayName": "SkyShield",
                "downsideDelta": 2900,
                "winnerId": "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
            },
        )
    )
    assert explain == {"winnerDisplayName": "SkyShield", "downsideDelta": 2900}
    assert "winnerId" not in explain
    assert schema_for_task("extract") is ExtractOutput
    assert schema_for_task("explain") is ExplainOutput


def test_injected_invoke_parses_structured_extract_and_explain() -> None:
    captured: dict[str, object] = {}

    def invoke(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del cancel
        captured["task"] = task
        captured["payload"] = dict(payload)
        captured["schema"] = schema
        if task == "extract":
            return _complete_extract(
                extract_mapping_from_output(
                    {
                        "airportCode": "JFK",
                        "start": "2026-09-03T13:00:00Z",
                        "end": "2026-09-08T22:00:00Z",
                        "vehicleClass": "standard",
                        "covered": "preferred",
                        "shuttleMaxMinutes": 20,
                        "currency": "USD",
                        "missing": [],
                        "ambiguous": [],
                    }
                )
            )
        return {
            "mapping": {"explanation": "SkyShield is the recommended simulated option."},
            "input_tokens": 4,
            "output_tokens": 6,
            "model_name": "gemini-2.5-flash",
        }

    model = LiveModel(invoke=invoke)
    extracted = model.complete(_extract_request())
    assert captured["schema"] is ExtractOutput
    assert captured["payload"] == {"text": JFK_TEXT, "category": "airport_parking"}
    proposal = extracted.mapping["proposal"]
    assert isinstance(proposal, Mapping)
    assert proposal["location"]["airportCode"] == "JFK"
    assert "intentId" not in proposal
    explained = model.complete(
        ModelRequest(
            task="explain",
            correlation_id=CORRELATION,
            payload={"winnerDisplayName": "SkyShield", "downsideDelta": 2900},
        )
    )
    assert captured["schema"] is ExplainOutput
    assert "SkyShield" in str(explained.mapping["explanation"])


def test_malformed_and_unknown_fields_are_rejected() -> None:
    def malformed(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema, cancel
        return {"mapping": "not-an-object"}

    def unknown(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema, cancel
        return {"mapping": {"proposal": {}, "secretItinerary": "blocked"}}

    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        LiveModel(invoke=malformed).complete(_extract_request())
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        LiveModel(invoke=unknown).complete(_extract_request())


def test_timeout_cancellation_quota_and_retry() -> None:
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
        raise AssertionError("cancel should have stopped invoke")

    def quota(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema, cancel
        raise QuotaExceeded()

    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(
            self,
            task: str,
            payload: Mapping[str, object],
            schema: type[BaseModel],
            cancel: CancelToken | None,
        ) -> Mapping[str, object]:
            del task, payload, schema, cancel
            self.calls += 1
            if self.calls == 1:
                raise TransientProviderError()
            return {
                "mapping": {"explanation": "SkyShield is the recommended simulated option."},
                "input_tokens": 2,
                "output_tokens": 3,
                "model_name": "gemini-2.5-flash",
            }

    extract = compose_agent(model=LiveModel(invoke=timed_out)).extract(
        ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION)
    )
    assert extract.fallback == "manual_structured_input"
    with pytest.raises(ApplicationError, match="request: cancelled"):
        compose_agent(model=LiveModel(invoke=cancelled)).extract(
            ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION),
            cancel=token,
        )
    with pytest.raises(ApplicationError, match="model: quota_exceeded"):
        compose_agent(model=LiveModel(invoke=quota)).extract(
            ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION)
        )
    flaky = Flaky()
    explained = compose_agent(
        model=LiveModel(invoke=flaky),
        clock=FakeMonotonicClock(),
        policy=ResiliencePolicy(max_attempts=2),
    ).explain(ExplanationRequest(facts=locked_ranking_facts()))
    assert flaky.calls == 2
    assert explained.grounded is True


def test_provider_errors_are_redacted() -> None:
    class QuotaBoom(Exception):
        pass

    class AuthBoom(Exception):
        pass

    quota = map_provider_error(QuotaBoom("quota 429 AIzaSECRET prompt leaked"))
    assert isinstance(quota, QuotaExceeded)
    auth = map_provider_error(AuthBoom("unauthenticated key=AIzaSECRET"))
    assert isinstance(auth, ApplicationError)
    assert auth.field == "model"
    assert auth.code == "unavailable"
    assert "AIza" not in str(auth)
    assert "SECRET" not in str(auth)
    assert "prompt" not in str(auth)


def test_token_latency_telemetry_omits_prompt_content() -> None:
    sink = RecordingTelemetry()

    def invoke(
        task: str,
        payload: Mapping[str, object],
        schema: type[BaseModel],
        cancel: CancelToken | None,
    ) -> Mapping[str, object]:
        del task, payload, schema, cancel
        return _complete_extract(
            extract_mapping_from_output(
                {
                    "airportCode": "JFK",
                    "start": "2026-09-03T13:00:00Z",
                    "end": "2026-09-08T22:00:00Z",
                    "vehicleClass": "standard",
                    "covered": "preferred",
                    "shuttleMaxMinutes": 20,
                    "currency": "USD",
                }
            )
        )

    compose_agent(model=LiveModel(invoke=invoke), telemetry=sink).extract(
        ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION)
    )
    assert sink.records
    for record in sink.records:
        payload = record.to_safe_mapping()
        blob = str(payload)
        assert "input_tokens" in payload or record.input_tokens == 11
        assert record.output_tokens == 17
        assert record.model_name == "gemini-2.5-flash"
        assert JFK_TEXT not in blob
        assert "prompt_text" not in payload
        assert "proposal" not in payload


def test_unknown_task_and_missing_extract_fields_fail_closed() -> None:
    with pytest.raises(ApplicationError, match="task: unknown"):
        schema_for_task("rank")
    with pytest.raises(ApplicationError, match="task: unknown"):
        LiveModel(invoke=lambda task, payload, schema, cancel: _complete_extract({})).complete(
            ModelRequest(task="rank", correlation_id=CORRELATION, payload={})
        )  # type: ignore[arg-type]
    mapping = extract_mapping_from_output({"missing": ["location.airportCode"], "ambiguous": []})
    assert mapping["proposal"] is None
    assert mapping["missing"] == ["location.airportCode"]


def test_default_invoke_fails_closed_without_vertex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert vertex_config_ready() is False
    with pytest.raises(ApplicationError, match="model: unavailable"):
        default_invoke("extract", {"text": "x", "category": "airport_parking"}, ExtractOutput, None)


def test_default_invoke_maps_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "owner-project")
    monkeypatch.setenv("ITAA_GCP_REGION", "us-central1")
    monkeypatch.setattr("itaa_google_adapter.live.live_sdk_available", lambda: False)
    with pytest.raises(ApplicationError, match="model: unavailable"):
        default_invoke("extract", {"text": "x", "category": "airport_parking"}, ExtractOutput, None)


def test_run_adk_uses_llm_agent_without_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    class FakeSession:
        def create_session(self, **kwargs: object) -> None:
            del kwargs

    class FakeEvent:
        def __init__(self) -> None:
            self.usage_metadata = type(
                "Usage",
                (),
                {"prompt_token_count": 9, "candidates_token_count": 5},
            )()
            self.content = type(
                "Content",
                (),
                {
                    "parts": [
                        type(
                            "Part",
                            (),
                            {
                                "text": (
                                    '{"explanation":"SkyShield is the recommended '
                                    'simulated option."}'
                                )
                            },
                        )()
                    ]
                },
            )()

        def is_final_response(self) -> bool:
            return True

    class FakeRunner:
        def __init__(self, **kwargs: object) -> None:
            captured["runner"] = kwargs

        async def run_async(self, **kwargs: object):
            del kwargs
            yield FakeEvent()

    class FakeTypes:
        class Part:
            def __init__(self, text: str) -> None:
                self.text = text

        class Content:
            def __init__(self, role: str, parts: list[object]) -> None:
                self.role = role
                self.parts = parts

        class GenerateContentConfig:
            def __init__(self, **kwargs: object) -> None:
                self.kwargs = kwargs

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "owner-project")
    monkeypatch.setenv("ITAA_GCP_REGION", "us-central1")
    monkeypatch.setattr(
        "itaa_google_adapter.live._import_adk",
        lambda: (FakeAgent, FakeRunner, FakeSession, FakeTypes),
    )
    import asyncio

    from itaa_google_adapter.live import run_adk

    result = asyncio.run(
        run_adk(
            "explain",
            {"winnerDisplayName": "SkyShield", "downsideDelta": 2900},
            ExplainOutput,
            None,
        )
    )
    assert captured["output_schema"] is ExplainOutput
    assert "tools" not in captured
    assert "timeout" not in captured
    assert captured["generate_content_config"] is not None
    assert captured["model"] == "gemini-2.5-flash"
    assert result["input_tokens"] == 9
    assert result["output_tokens"] == 5
    assert "SkyShield" in str(result["mapping"]["explanation"])
