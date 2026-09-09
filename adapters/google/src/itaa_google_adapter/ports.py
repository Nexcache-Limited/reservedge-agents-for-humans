"""Provider-neutral adapter ports. No cloud SDK types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

FieldOrigin = Literal["extracted", "user_confirmed", "deterministic_default"]


class CancelToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def check(self) -> None:
        if self._cancelled:
            raise CancelledError()


class CancelledError(Exception):
    """In-flight adapter work was cancelled."""


class TimeoutExpired(Exception):
    """Deadline elapsed before the model returned."""


class QuotaExceeded(Exception):
    """Upstream quota or rate limit was hit."""


class TransientProviderError(Exception):
    """Retryable provider failure. Must not carry prompt or credential text."""


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    field: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class FieldAttribution:
    field: str
    origin: FieldOrigin
    confidence: float
    evidence_start: int | None = None
    evidence_end: int | None = None
    no_evidence: bool = False


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    text: str
    category: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ExtractionResponse:
    proposal: Mapping[str, object] | None
    field_confidence: Mapping[str, float]
    missing_fields: tuple[str, ...]
    ambiguous_fields: tuple[str, ...]
    evidence_spans: tuple[EvidenceSpan, ...]
    requires_a1: bool
    accepted: bool
    fallback: str | None = None
    field_attributions: tuple[FieldAttribution, ...] = ()
    rejection_code: str | None = None


@dataclass(frozen=True, slots=True)
class SafeOfferSummary:
    supplier_token: str
    display_name: str
    offer_id: str
    rank: int
    score_micros: int
    total_minor: int
    currency: str
    recommended: bool


@dataclass(frozen=True, slots=True)
class RankingFacts:
    winner_id: str
    winner_display_name: str
    offers: tuple[SafeOfferSummary, ...]
    downside_delta: int
    downside_dimension: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ExplanationRequest:
    facts: RankingFacts


@dataclass(frozen=True, slots=True)
class ExplanationResponse:
    explanation: str
    grounded: bool
    fallback: str | None = None


@dataclass(frozen=True, slots=True)
class ModelRequest:
    task: Literal["extract", "explain"]
    correlation_id: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ModelResponse:
    mapping: Mapping[str, object]
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_name: str = "fake-deterministic"


class ModelPort(Protocol):
    def complete(
        self,
        request: ModelRequest,
        *,
        cancel: CancelToken | None = None,
        deadline_ms: int | None = None,
    ) -> ModelResponse: ...


class MonotonicClock(Protocol):
    def now_ms(self) -> int: ...

    def sleep_ms(self, duration_ms: int, cancel: CancelToken | None = None) -> None: ...


class ExtractionPort(Protocol):
    def extract(self, request: ExtractionRequest) -> ExtractionResponse: ...


class ExplanationPort(Protocol):
    def explain(self, request: ExplanationRequest) -> ExplanationResponse: ...
