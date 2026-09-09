"""Adapter telemetry. Never records raw prompts or model responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from itaa_google_adapter import ADAPTER_VERSION
from itaa_google_adapter.privacy import record_is_prompt_free


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    model_name: str
    adapter_version: str
    prompt_template_version: str
    tool_call_id: str | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    correlation_id: str
    task: str

    def to_safe_mapping(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "model_name": self.model_name,
            "adapter_version": self.adapter_version,
            "prompt_template_version": self.prompt_template_version,
            "tool_call_id": self.tool_call_id,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "correlation_id": self.correlation_id,
            "task": self.task,
        }
        if not record_is_prompt_free(payload):
            raise ValueError("telemetry_contains_denied_fields")
        return payload


class TelemetrySink(Protocol):
    def emit(self, record: TelemetryRecord) -> None: ...


class NullTelemetry:
    def emit(self, record: TelemetryRecord) -> None:
        del record


class RecordingTelemetry:
    def __init__(self) -> None:
        self.records: list[TelemetryRecord] = []

    def emit(self, record: TelemetryRecord) -> None:
        record.to_safe_mapping()
        self.records.append(record)


def adapter_record(
    *,
    model_name: str,
    prompt_template_version: str,
    latency_ms: int,
    correlation_id: str,
    task: str,
    tool_call_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> TelemetryRecord:
    return TelemetryRecord(
        model_name=model_name,
        adapter_version=ADAPTER_VERSION,
        prompt_template_version=prompt_template_version,
        tool_call_id=tool_call_id,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        correlation_id=correlation_id,
        task=task,
    )


def as_log_fields(record: TelemetryRecord) -> dict[str, object]:
    return asdict(record)
