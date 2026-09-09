"""Compose the deterministic fake by default. Live SDK is opt-in only."""

from __future__ import annotations

from collections.abc import Mapping

from itaa_application.errors import ApplicationError
from itaa_application.golden_path import GoldenPathFacade
from itaa_google_adapter import EXPLAIN_TEMPLATE_VERSION, EXTRACT_TEMPLATE_VERSION
from itaa_google_adapter.explanation import deterministic_explanation, explanation_from_mapping
from itaa_google_adapter.extraction import (
    manual_fallback,
    parse_attributions,
    validate_proposal,
)
from itaa_google_adapter.fake import FakeModel
from itaa_google_adapter.mode import MODE_LIVE, resolve_model_mode
from itaa_google_adapter.ports import (
    CancelledError,
    CancelToken,
    EvidenceSpan,
    ExplanationRequest,
    ExplanationResponse,
    ExtractionRequest,
    ExtractionResponse,
    ModelPort,
    ModelRequest,
    ModelResponse,
    MonotonicClock,
    QuotaExceeded,
    TimeoutExpired,
    TransientProviderError,
)
from itaa_google_adapter.privacy import scan_extraction_text
from itaa_google_adapter.resilience import (
    ResiliencePolicy,
    SystemMonotonicClock,
    is_retryable,
    production_resilience_policy,
    run_with_resilience,
)
from itaa_google_adapter.telemetry import RecordingTelemetry, TelemetrySink, adapter_record
from itaa_google_adapter.tools import FacadeTools


def _as_mapping(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value
    raise ApplicationError("payload", "schema_invalid")


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _spans(value: object) -> tuple[EvidenceSpan, ...]:
    built: list[EvidenceSpan] = []
    for item in _as_list(value):
        if not isinstance(item, Mapping):
            continue
        field = item.get("field")
        start = item.get("start")
        end = item.get("end")
        if isinstance(field, str) and isinstance(start, int) and isinstance(end, int):
            built.append(EvidenceSpan(field, start, end))
    return tuple(built)


class GoogleAdapterAgent:
    def __init__(
        self,
        *,
        model: ModelPort | None = None,
        tools: FacadeTools | None = None,
        telemetry: TelemetrySink | None = None,
        clock: MonotonicClock | None = None,
        policy: ResiliencePolicy | None = None,
    ) -> None:
        self._model = model or FakeModel()
        self._tools = tools
        self._telemetry = telemetry or RecordingTelemetry()
        self._clock = clock if clock is not None else SystemMonotonicClock()
        self._policy = policy or ResiliencePolicy()
        self.tool_invocations: list[str] = []

    def extract(
        self,
        request: ExtractionRequest,
        *,
        cancel: CancelToken | None = None,
    ) -> ExtractionResponse:
        started = self._clock.now_ms()
        if request.category != "airport_parking":
            raise ApplicationError("category", "must_be_airport_parking")
        if scan_extraction_text(request):
            self._emit("extract", started, None, request.correlation_id)
            return validate_proposal(None, request=request)
        try:
            model_response = self._complete(
                ModelRequest(
                    task="extract",
                    correlation_id=request.correlation_id,
                    payload={"text": request.text, "category": request.category},
                ),
                cancel=cancel,
            )
        except TimeoutExpired:
            self._emit("extract", started, None, request.correlation_id)
            return manual_fallback()
        except CancelledError:
            raise ApplicationError("request", "cancelled") from None
        mapping = model_response.mapping
        try:
            proposal = _as_mapping(mapping.get("proposal")) if "proposal" in mapping else None
        except ApplicationError:
            self._emit("extract", started, model_response.input_tokens, request.correlation_id)
            return manual_fallback()
        missing = tuple(str(item) for item in _as_list(mapping.get("missing")))
        ambiguous = tuple(str(item) for item in _as_list(mapping.get("ambiguous")))
        confidence_raw = mapping.get("confidence")
        confidence: dict[str, float] = {}
        if isinstance(confidence_raw, Mapping):
            confidence = {str(key): float(value) for key, value in confidence_raw.items()}
        result = validate_proposal(
            proposal,
            request=request,
            missing=missing,
            ambiguous=ambiguous,
            evidence=_spans(mapping.get("evidence")),
            confidence=confidence,
            attributions=parse_attributions(mapping.get("attributions")),
        )
        self._emit(
            "extract",
            started,
            model_response.input_tokens,
            request.correlation_id,
            output_tokens=model_response.output_tokens,
            model_name=model_response.model_name,
        )
        return result

    def explain(
        self,
        request: ExplanationRequest,
        *,
        cancel: CancelToken | None = None,
    ) -> ExplanationResponse:
        started = self._clock.now_ms()
        facts = request.facts
        payload = {
            "winnerId": facts.winner_id,
            "winnerDisplayName": facts.winner_display_name,
            "downsideDelta": facts.downside_delta,
        }
        try:
            model_response = self._complete(
                ModelRequest(task="explain", correlation_id=facts.correlation_id, payload=payload),
                cancel=cancel,
            )
        except TimeoutExpired:
            self._emit("explain", started, None, facts.correlation_id)
            return ExplanationResponse(
                explanation=deterministic_explanation(facts),
                grounded=True,
                fallback="deterministic_facts",
            )
        except CancelledError:
            raise ApplicationError("request", "cancelled") from None
        result = explanation_from_mapping(model_response.mapping, facts)
        self._emit(
            "explain",
            started,
            model_response.input_tokens,
            facts.correlation_id,
            output_tokens=model_response.output_tokens,
            model_name=model_response.model_name,
            template=EXPLAIN_TEMPLATE_VERSION,
        )
        return result

    def call_tool(self, name: str, payload: Mapping[str, object]) -> dict[str, object]:
        if self._tools is None:
            raise ApplicationError("tool", "unavailable")
        self.tool_invocations.append(name)
        return self._tools.call(name, payload)

    def _complete(self, request: ModelRequest, cancel: CancelToken | None) -> ModelResponse:
        def operation(deadline_ms: int) -> ModelResponse:
            return self._model.complete(request, cancel=cancel, deadline_ms=deadline_ms)

        try:
            return run_with_resilience(
                operation,
                clock=self._clock,
                policy=self._policy,
                cancel=cancel,
                retryable=is_retryable,
            )
        except QuotaExceeded:
            raise ApplicationError("model", "quota_exceeded") from None
        except TransientProviderError:
            raise ApplicationError("model", "unavailable") from None

    def _emit(
        self,
        task: str,
        started_ms: int,
        input_tokens: int | None,
        correlation_id: str,
        *,
        output_tokens: int | None = None,
        model_name: str = "fake-deterministic",
        template: str | None = None,
    ) -> None:
        chosen = template
        if chosen is None:
            chosen = EXTRACT_TEMPLATE_VERSION if task == "extract" else EXPLAIN_TEMPLATE_VERSION
        self._telemetry.emit(
            adapter_record(
                model_name=model_name,
                prompt_template_version=chosen,
                latency_ms=max(0, self._clock.now_ms() - started_ms),
                correlation_id=correlation_id,
                task=task,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )


def compose_agent(
    *,
    facade: GoldenPathFacade | None = None,
    model: ModelPort | None = None,
    telemetry: TelemetrySink | None = None,
    clock: MonotonicClock | None = None,
    policy: ResiliencePolicy | None = None,
) -> GoogleAdapterAgent:
    tools = FacadeTools(facade) if facade is not None else None
    chosen = model
    resolved_clock: MonotonicClock = clock if clock is not None else SystemMonotonicClock()
    resolved_policy = policy if policy is not None else production_resilience_policy()
    if chosen is None:
        mode = resolve_model_mode()
        if mode == MODE_LIVE:
            from itaa_google_adapter.live import LiveModel

            chosen = LiveModel()
        elif clock is not None:
            chosen = FakeModel(clock=clock)
        else:
            chosen = FakeModel()
    return GoogleAdapterAgent(
        model=chosen,
        tools=tools,
        telemetry=telemetry,
        clock=resolved_clock,
        policy=resolved_policy,
    )
