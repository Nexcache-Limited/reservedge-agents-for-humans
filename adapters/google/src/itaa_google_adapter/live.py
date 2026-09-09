"""Live Vertex path. google.adk is imported only inside this module."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator

from itaa_application.errors import ApplicationError
from itaa_domain.errors import DomainInvariantError
from itaa_domain.value_objects import parse_utc
from itaa_google_adapter import (
    DEFAULT_MODEL_NAME,
    DEFAULT_REGION,
    EXPLAIN_TEMPLATE_VERSION,
    EXTRACT_TEMPLATE_VERSION,
)
from itaa_google_adapter.extraction import proposal_from_extracted_fields
from itaa_google_adapter.mode import (
    apply_vertex_location,
    configured_region,
    uses_vertex,
    vertex_config_ready,
    vertex_project,
)
from itaa_google_adapter.ports import (
    CancelledError,
    CancelToken,
    ModelRequest,
    ModelResponse,
    QuotaExceeded,
    TimeoutExpired,
    TransientProviderError,
)
from itaa_google_adapter.privacy import REQUIREMENT_FIELDS
from itaa_google_adapter.resilience import ResiliencePolicy, live_timeout_ready

_SDK_MODULE = "google.adk"
_REFUSAL_MARKERS = frozenset({"SAFETY", "BLOCKED", "RECITATION", "PROHIBITED"})
_QUOTA_MARKERS = ("quota", "rate limit", "429", "resourceexhausted", "resource_exhausted")
_TIMEOUT_MARKERS = ("timeout", "deadline", "timed out")
_CANCEL_MARKERS = ("cancel", "cancelled", "canceled")
_AUTH_MARKERS = ("unauthenticated", "unauthorized", "invalid credential", "permission denied")
_TRANSIENT_MARKERS = ("unavailable", "503", "500", "internal", "temporarily")
ALLOWED_INVOKE_KEYS: frozenset[str] = frozenset(
    {"mapping", "input_tokens", "output_tokens", "model_name"}
)
ALLOWED_MAPPING_KEYS: frozenset[str] = frozenset(
    {
        "proposal",
        "missing",
        "ambiguous",
        "confidence",
        "evidence",
        "attributions",
        "status",
        "explanation",
    }
)

EXTRACT_INSTRUCTIONS = f"""You extract airport-parking requirement evidence only.
Template version: {EXTRACT_TEMPLATE_VERSION}.
Use the structured output schema. Do not invent identifiers, hashes, disclosure
values, solicitation deadlines, or fixture data.
Do not rank, compute money, approve, confirm, dispatch, isolate, or authorize.
If a required field is absent, list it in missing. If dates conflict or are
impossible, list them in ambiguous.
Do not combine tools with this structured output.
"""

EXPLAIN_INSTRUCTIONS = f"""You explain an already-ranked airport-parking snapshot.
Template version: {EXPLAIN_TEMPLATE_VERSION}.
Name the recommended option. Do not change scores, totals, ranks, or downside.
Do not invent prices. Do not approve, dispatch, or authorize.
Do not combine tools with this structured output.
"""

InvokeFn = Callable[
    [str, Mapping[str, object], type[BaseModel], CancelToken | None],
    Mapping[str, object],
]


VehicleClass = Literal["standard", "compact", "suv", "oversized"]
CoveredPreference = Literal["none", "preferred", "required"]
AccessibilityNeed = Literal["step_free", "wheelchair", "ev_charging"]
SchemaFieldName = Literal[
    "airportCode",
    "start",
    "end",
    "vehicleClass",
    "covered",
    "shuttleMaxMinutes",
    "currency",
    "accessibility",
    "location.airportCode",
    "serviceWindow.start",
    "serviceWindow.end",
    "requirements.vehicleClass",
    "requirements.covered",
    "requirements.shuttleMaxMinutes",
    "constraints.currency",
    "constraints.accessibility",
]
UTC_INSTANT_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
IATA_OR_CURRENCY_PATTERN = r"^[A-Z]{3}$"
LEAF_TO_REQUIREMENT: dict[str, str] = {
    "airportCode": "location.airportCode",
    "start": "serviceWindow.start",
    "end": "serviceWindow.end",
    "vehicleClass": "requirements.vehicleClass",
    "covered": "requirements.covered",
    "shuttleMaxMinutes": "requirements.shuttleMaxMinutes",
    "currency": "constraints.currency",
    "accessibility": "constraints.accessibility",
}
ALLOWED_SCHEMA_FIELDS: frozenset[str] = frozenset(LEAF_TO_REQUIREMENT) | frozenset(
    REQUIREMENT_FIELDS
)


class EvidenceItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: SchemaFieldName = Field(description="Approved requirement field path or leaf name.")
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ExtractOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    airportCode: str | None = Field(
        default=None,
        pattern=IATA_OR_CURRENCY_PATTERN,
        description="Canonical uppercase three-letter airport code.",
    )
    start: str | None = Field(
        default=None,
        pattern=UTC_INSTANT_PATTERN,
        description="Canonical UTC start instant ending with Z.",
    )
    end: str | None = Field(
        default=None,
        pattern=UTC_INSTANT_PATTERN,
        description="Canonical UTC end instant ending with Z.",
    )
    vehicleClass: VehicleClass | None = Field(
        default=None,
        description="Closed vehicle class: standard, compact, suv, or oversized.",
    )
    covered: CoveredPreference | None = Field(
        default=None,
        description="Closed covered preference: none, preferred, or required.",
    )
    shuttleMaxMinutes: StrictInt | None = Field(
        default=None,
        ge=0,
        le=180,
        description="Integer shuttle maximum in minutes, 0 through 180.",
    )
    currency: str | None = Field(
        default=None,
        pattern=IATA_OR_CURRENCY_PATTERN,
        description="Canonical uppercase three-letter currency code.",
    )
    accessibility: list[AccessibilityNeed] | None = Field(
        default=None,
        description=(
            "Closed vocabulary only: step_free, wheelchair, ev_charging. "
            "Map electric vehicle, EV, EV charging, and standard EV to ev_charging "
            "when that is the stated access need. Omit the field when no access need is stated."
        ),
    )
    missing: list[SchemaFieldName] = Field(default_factory=list)
    ambiguous: list[SchemaFieldName] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    evidence: list[EvidenceItemModel] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def _closed_confidence(cls, value: dict[str, float]) -> dict[str, float]:
        cleaned: dict[str, float] = {}
        for key, raw in value.items():
            if key not in ALLOWED_SCHEMA_FIELDS:
                raise ValueError("invalid_confidence_field")
            number = float(raw)
            if not 0.0 <= number <= 1.0:
                raise ValueError("invalid_confidence_range")
            cleaned[key] = number
        return cleaned

    @field_validator("evidence")
    @classmethod
    def _closed_evidence_span(cls, value: list[EvidenceItemModel]) -> list[EvidenceItemModel]:
        for item in value:
            if item.end < item.start:
                raise ValueError("invalid_evidence_span")
        return value

    @field_validator("start", "end")
    @classmethod
    def _canonical_utc_instant(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parse_utc(value, "serviceWindow.start")
        except (DomainInvariantError, ValueError, TypeError):
            raise ValueError("invalid_utc_instant") from None
        return value


class ExplainOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str


def live_sdk_available() -> bool:
    try:
        importlib.import_module(_SDK_MODULE)
    except ImportError:
        return False
    return True


def configured_model_name() -> str:
    import os

    return os.environ.get("ITAA_GEMINI_MODEL", DEFAULT_MODEL_NAME)


def live_runtime_ready() -> bool:
    return live_sdk_available() and vertex_config_ready() and live_timeout_ready()


def schema_for_task(task: str) -> type[BaseModel]:
    if task == "extract":
        return ExtractOutput
    if task == "explain":
        return ExplainOutput
    raise ApplicationError("task", "unknown")


def minimize_payload(request: ModelRequest) -> dict[str, object]:
    if request.task == "extract":
        return {
            "text": str(request.payload.get("text", "")),
            "category": str(request.payload.get("category", "")),
        }
    if request.task == "explain":
        return {
            "winnerDisplayName": str(request.payload.get("winnerDisplayName", "")),
            "downsideDelta": request.payload.get("downsideDelta"),
        }
    raise ApplicationError("task", "unknown")


def _canonical_field_name(name: str) -> str:
    return LEAF_TO_REQUIREMENT.get(name, name)


def extract_mapping_from_output(data: Mapping[str, object]) -> dict[str, object]:
    missing_raw = data.get("missing")
    ambiguous_raw = data.get("ambiguous")
    missing = (
        [_canonical_field_name(str(item)) for item in missing_raw]
        if isinstance(missing_raw, list)
        else []
    )
    ambiguous = (
        [_canonical_field_name(str(item)) for item in ambiguous_raw]
        if isinstance(ambiguous_raw, list)
        else []
    )
    if missing or ambiguous:
        return {"proposal": None, "missing": missing, "ambiguous": ambiguous}
    fields: dict[str, object] = {}
    for key in (
        "airportCode",
        "start",
        "end",
        "vehicleClass",
        "covered",
        "shuttleMaxMinutes",
        "currency",
        "accessibility",
    ):
        value = data.get(key)
        if value is not None:
            fields[key] = value
    proposal = proposal_from_extracted_fields(fields) if fields else None
    confidence_raw = data.get("confidence")
    confidence: dict[str, float] = {}
    if isinstance(confidence_raw, Mapping):
        for key, value in confidence_raw.items():
            confidence[_canonical_field_name(str(key))] = float(value)
    evidence_raw = data.get("evidence")
    evidence: list[object] = []
    if isinstance(evidence_raw, list):
        for item in evidence_raw:
            if isinstance(item, Mapping):
                evidence.append(
                    {
                        "field": _canonical_field_name(str(item.get("field", ""))),
                        "start": item.get("start"),
                        "end": item.get("end"),
                    }
                )
    return {
        "proposal": proposal,
        "missing": missing,
        "ambiguous": ambiguous,
        "confidence": confidence,
        "evidence": evidence,
    }


def _closed_error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}:{type(exc).__module__}".lower()


def map_provider_error(exc: BaseException) -> BaseException:
    blob = _closed_error_text(exc)
    if any(marker in blob for marker in _CANCEL_MARKERS):
        return CancelledError()
    if any(marker in blob for marker in _TIMEOUT_MARKERS):
        return TimeoutExpired()
    if any(marker in blob for marker in _QUOTA_MARKERS):
        return QuotaExceeded()
    if any(marker in blob for marker in _AUTH_MARKERS):
        return ApplicationError("model", "unavailable")
    if "refused" in blob or "safety" in blob or "blocked" in blob:
        return ApplicationError("model", "refused")
    if "validation" in blob or "schema" in blob:
        return ApplicationError("model", "schema_invalid")
    if any(marker in blob for marker in _TRANSIENT_MARKERS):
        return TransientProviderError()
    return ApplicationError("model", "unavailable")


def _import_adk() -> tuple[Any, Any, Any, Any]:
    try:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types
    except ImportError as exc:
        raise ApplicationError("model", "unavailable") from exc
    return LlmAgent, Runner, InMemorySessionService, types


def _token_count(usage: object, *names: str) -> int | None:
    if usage is None:
        return None
    for name in names:
        value = getattr(usage, name, None)
        if isinstance(value, int):
            return value
        if isinstance(usage, Mapping) and isinstance(usage.get(name), int):
            return int(usage[name])
    return None


def _event_refusal(event: object) -> bool:
    finish = getattr(event, "finish_reason", None)
    llm_response = getattr(event, "llm_response", None)
    if finish is None and llm_response is not None:
        finish = getattr(llm_response, "finish_reason", None)
    token = str(finish or "").upper()
    return any(marker in token for marker in _REFUSAL_MARKERS)


def _parse_structured(text: str, schema: type[BaseModel]) -> dict[str, object]:
    try:
        parsed = schema.model_validate_json(text)
    except ValidationError as exc:
        raise ApplicationError("model", "schema_invalid") from exc
    data = parsed.model_dump()
    if schema is ExtractOutput:
        return extract_mapping_from_output(data)
    return {"explanation": str(data.get("explanation", ""))}


def extraction_generate_content_config(types: Any) -> Any:
    """Approved low-variance structured generation. No tools. No second timeout."""

    return types.GenerateContentConfig(
        temperature=0.0,
        candidate_count=1,
        max_output_tokens=1024,
        seed=1,
    )


async def run_adk(
    task: str,
    payload: Mapping[str, object],
    schema: type[BaseModel],
    cancel: CancelToken | None,
) -> dict[str, object]:
    if cancel is not None:
        cancel.check()
    if not vertex_config_ready():
        raise ApplicationError("model", "unavailable")
    apply_vertex_location()
    llm_agent_cls, runner_cls, session_cls, types = _import_adk()
    instruction = EXTRACT_INSTRUCTIONS if task == "extract" else EXPLAIN_INSTRUCTIONS
    agent = llm_agent_cls(
        model=configured_model_name(),
        name="itaa_extract_v3" if task == "extract" else "itaa_explain_v1",
        instruction=instruction,
        output_schema=schema,
        generate_content_config=extraction_generate_content_config(types),
    )
    session_service = session_cls()
    app_name = "itaa-google-adapter"
    user_id = "adapter"
    session_id = "live"
    created = session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if inspect.isawaitable(created):
        await created
    runner = runner_cls(agent=agent, app_name=app_name, session_service=session_service)
    message = json.dumps(dict(payload), separators=(",", ":"))
    content = types.Content(role="user", parts=[types.Part(text=message)])
    mapping: dict[str, object] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    events = runner.run_async(user_id=user_id, session_id=session_id, new_message=content)
    async for event in events:
        if cancel is not None:
            cancel.check()
        if _event_refusal(event):
            raise ApplicationError("model", "refused")
        usage = getattr(event, "usage_metadata", None)
        llm_response = getattr(event, "llm_response", None)
        if usage is None and llm_response is not None:
            usage = getattr(llm_response, "usage_metadata", None)
        prompt_tokens = _token_count(usage, "prompt_token_count", "input_tokens")
        candidate_tokens = _token_count(usage, "candidates_token_count", "output_tokens")
        if prompt_tokens is not None:
            input_tokens = prompt_tokens
        if candidate_tokens is not None:
            output_tokens = candidate_tokens
        is_final = getattr(event, "is_final_response", None)
        final = bool(is_final()) if callable(is_final) else False
        event_content = getattr(event, "content", None)
        parts = getattr(event_content, "parts", None) if event_content is not None else None
        if final and parts:
            text = getattr(parts[0], "text", None)
            if isinstance(text, str) and text.strip():
                mapping = _parse_structured(text, schema)
    if mapping is None:
        raise ApplicationError("model", "schema_invalid")
    return {
        "mapping": mapping,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model_name": configured_model_name(),
    }


async def run_adk_bounded(
    task: str,
    payload: Mapping[str, object],
    schema: type[BaseModel],
    cancel: CancelToken | None,
    deadline_ms: int,
) -> dict[str, object]:
    """Run ADK under the remaining overall deadline. Cancels the ADK task on timeout."""

    if deadline_ms <= 0:
        raise TimeoutExpired()
    if cancel is not None:
        cancel.check()
    adk_task = asyncio.create_task(run_adk(task, payload, schema, cancel))

    async def watch_cancel() -> None:
        if cancel is None:
            await asyncio.Event().wait()
            return
        while not adk_task.done() and not cancel.cancelled:
            await asyncio.sleep(0.005)

    watcher = asyncio.create_task(watch_cancel())
    wait_set: set[asyncio.Task[Any]] = {adk_task, watcher}
    try:
        done, leftover = await asyncio.wait(
            wait_set,
            timeout=deadline_ms / 1000.0,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for pending in leftover:
            pending.cancel()
        if leftover:
            await asyncio.gather(*leftover, return_exceptions=True)
        if cancel is not None and cancel.cancelled:
            raise CancelledError()
        if adk_task in done and not adk_task.cancelled():
            return adk_task.result()
        raise TimeoutExpired()
    except CancelledError:
        raise
    except TimeoutExpired:
        raise
    finally:
        if not watcher.done():
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        if not adk_task.done():
            adk_task.cancel()
            await asyncio.gather(adk_task, return_exceptions=True)


def default_invoke(
    task: str,
    payload: Mapping[str, object],
    schema: type[BaseModel],
    cancel: CancelToken | None,
    deadline_ms: int | None = None,
) -> Mapping[str, object]:
    if cancel is not None:
        cancel.check()
    if not live_sdk_available():
        raise ApplicationError("model", "unavailable")
    if not vertex_config_ready():
        raise ApplicationError("model", "unavailable")
    budget = ResiliencePolicy().timeout_ms if deadline_ms is None else deadline_ms
    try:
        return asyncio.run(run_adk_bounded(task, payload, schema, cancel, budget))
    except (
        ApplicationError,
        CancelledError,
        TimeoutExpired,
        QuotaExceeded,
        TransientProviderError,
    ):
        raise
    except TimeoutError:
        raise TimeoutExpired() from None
    except asyncio.CancelledError:
        if cancel is not None and cancel.cancelled:
            raise CancelledError() from None
        raise TimeoutExpired() from None
    except BaseException as exc:
        mapped = map_provider_error(exc)
        raise mapped from None


def _validate_invoke_result(result: Mapping[str, object]) -> dict[str, object]:
    extra = {str(key) for key in result} - ALLOWED_INVOKE_KEYS
    if extra:
        raise ApplicationError("model", "schema_invalid")
    mapping = result.get("mapping")
    if not isinstance(mapping, Mapping):
        raise ApplicationError("model", "schema_invalid")
    unknown = {str(key) for key in mapping} - ALLOWED_MAPPING_KEYS
    if unknown:
        raise ApplicationError("model", "schema_invalid")
    model_name = result.get("model_name", configured_model_name())
    if not isinstance(model_name, str):
        raise ApplicationError("model", "schema_invalid")
    input_tokens = result.get("input_tokens")
    output_tokens = result.get("output_tokens")
    if input_tokens is not None and not isinstance(input_tokens, int):
        raise ApplicationError("model", "schema_invalid")
    if output_tokens is not None and not isinstance(output_tokens, int):
        raise ApplicationError("model", "schema_invalid")
    return {
        "mapping": dict(mapping),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model_name": model_name,
    }


class LiveModel:
    """Live completion. Production composition must use Vertex + ADC."""

    def __init__(self, *, invoke: InvokeFn | None = None) -> None:
        self._invoke = invoke

    def complete(
        self,
        request: ModelRequest,
        *,
        cancel: CancelToken | None = None,
        deadline_ms: int | None = None,
    ) -> ModelResponse:
        if cancel is not None:
            cancel.check()
        if request.task not in {"extract", "explain"}:
            raise ApplicationError("task", "unknown")
        payload = minimize_payload(request)
        schema = schema_for_task(request.task)
        if self._invoke is not None:
            raw = self._invoke(request.task, payload, schema, cancel)
        else:
            raw = default_invoke(request.task, payload, schema, cancel, deadline_ms=deadline_ms)
        if not isinstance(raw, Mapping):
            raise ApplicationError("model", "schema_invalid")
        cleaned = _validate_invoke_result(raw)
        return ModelResponse(
            mapping=cleaned["mapping"],  # type: ignore[arg-type]
            input_tokens=cleaned["input_tokens"],  # type: ignore[arg-type]
            output_tokens=cleaned["output_tokens"],  # type: ignore[arg-type]
            model_name=str(cleaned["model_name"]),
        )


def describe_live_path() -> dict[str, str]:
    return {
        "model": configured_model_name(),
        "region": configured_region() or DEFAULT_REGION,
        "vertex": "true" if uses_vertex() else "false",
        "sdk": _SDK_MODULE,
        "project_configured": "true" if vertex_project() else "false",
    }
