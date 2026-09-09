"""Timeouts, bounded retries with jitter, quota, and cancellation.

Resilience ownership (one contract; do not add a second timeout stack):

- ``ResiliencePolicy.timeout_ms`` is the **overall deadline** for one
  ``GoogleAdapterAgent._complete`` call, shared across retries.
- ``run_with_resilience`` owns remaining-budget calculation, retry
  classification, backoff sleep, and mapping exhausted
  ``TransientProviderError`` to ``ApplicationError("model", "unavailable")``.
- ``LiveModel`` / ``run_adk_bounded`` own the **asynchronous** provider
  deadline (``asyncio.timeout`` / task cancellation) using that remaining
  budget. They must not apply an independent full timeout per attempt.
- ``GoogleAdapterAgent`` owns closed HTTP-facing mapping: timeout fallbacks,
  ``request: cancelled``, ``model: quota_exceeded``.
- ``compose_agent`` / ``GoogleAdapterAgent`` default to
  ``SystemMonotonicClock``. Tests inject ``FakeMonotonicClock``.
- ``SystemMonotonicClock.sleep_ms`` is the only real waiter. Tests inject a
  sleeper; production uses ``time.sleep``.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from itaa_application.errors import ApplicationError
from itaa_google_adapter.ports import (
    CancelToken,
    MonotonicClock,
    QuotaExceeded,
    TimeoutExpired,
    TransientProviderError,
)

SLEEP_SLICE_MS = 25
ENV_TIMEOUT_MS = "ITAA_GOOGLE_TIMEOUT_MS"
APPROVED_LIVE_TIMEOUT_MS = 30_000
LIVE_TIMEOUT_MIN_MS = 5_000
LIVE_TIMEOUT_MAX_MS = 45_000
FAKE_TIMEOUT_MS = 2_000
SleepFn = Callable[[float], None]
MonotonicFn = Callable[[], float]


@dataclass(frozen=True, slots=True)
class ResiliencePolicy:
    timeout_ms: int = FAKE_TIMEOUT_MS
    max_attempts: int = 2
    base_backoff_ms: int = 20
    jitter_ms: int = 15


def parse_live_timeout_ms() -> int:
    """Fail closed on missing, non-integer, zero, negative, or excessive values."""

    raw = os.environ.get(ENV_TIMEOUT_MS)
    if raw is None:
        raise ApplicationError("model", "schema_invalid")
    text = raw.strip()
    if text == "" or not text.isdigit() or text != str(int(text)):
        raise ApplicationError("model", "schema_invalid")
    value = int(text)
    if value < LIVE_TIMEOUT_MIN_MS or value > LIVE_TIMEOUT_MAX_MS:
        raise ApplicationError("model", "schema_invalid")
    return value


def live_timeout_ready() -> bool:
    try:
        parse_live_timeout_ms()
    except ApplicationError:
        return False
    return True


def production_resilience_policy() -> ResiliencePolicy:
    """Fake stays fast. Live requires ITAA_GOOGLE_TIMEOUT_MS within approved bounds."""

    from itaa_google_adapter.mode import MODE_LIVE, resolve_model_mode

    raw = os.environ.get(ENV_TIMEOUT_MS)
    if resolve_model_mode() == MODE_LIVE:
        return ResiliencePolicy(timeout_ms=parse_live_timeout_ms())
    if raw is not None and raw.strip() != "":
        parse_live_timeout_ms()
    return ResiliencePolicy()


class FakeMonotonicClock:
    """Deterministic clock for tests. Never uses wall-clock sleep."""

    def __init__(self, start_ms: int = 0) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, duration_ms: int) -> None:
        self._now += max(0, duration_ms)

    def sleep_ms(self, duration_ms: int, cancel: CancelToken | None = None) -> None:
        if cancel is not None:
            cancel.check()
        if duration_ms <= 0:
            return
        self.advance(duration_ms)
        if cancel is not None:
            cancel.check()


class SystemMonotonicClock:
    """Wall-clock monotonic clock. Production retry backoff uses this sleeper."""

    def __init__(
        self,
        *,
        sleeper: SleepFn | None = None,
        monotonic: MonotonicFn | None = None,
        slice_ms: int = SLEEP_SLICE_MS,
    ) -> None:
        self._sleep: SleepFn = sleeper if sleeper is not None else time.sleep
        self._monotonic: MonotonicFn = monotonic if monotonic is not None else time.monotonic
        self._slice_ms = max(1, slice_ms)

    def now_ms(self) -> int:
        return int(self._monotonic() * 1000)

    def sleep_ms(self, duration_ms: int, cancel: CancelToken | None = None) -> None:
        if cancel is not None:
            cancel.check()
        if duration_ms <= 0:
            return
        deadline = self._monotonic() + (duration_ms / 1000.0)
        slice_s = self._slice_ms / 1000.0
        while True:
            if cancel is not None:
                cancel.check()
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return
            self._sleep(min(slice_s, remaining))


def jittered_backoff_ms(
    attempt: int,
    policy: ResiliencePolicy,
    jitter_draw: Callable[[int], int],
) -> int:
    delay = int(policy.base_backoff_ms * (2**attempt))
    extra = int(jitter_draw(policy.jitter_ms))
    return delay + max(0, extra)


def is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, TransientProviderError)


def remaining_ms(clock: MonotonicClock, started_ms: int, timeout_ms: int) -> int:
    return timeout_ms - (clock.now_ms() - started_ms)


def run_with_resilience[T](
    operation: Callable[[int], T],
    *,
    clock: MonotonicClock,
    policy: ResiliencePolicy,
    cancel: CancelToken | None = None,
    retryable: Callable[[BaseException], bool] | None = None,
    jitter_draw: Callable[[int], int] | None = None,
) -> T:
    """Retry only non-mutating model calls. Do not wrap facade mutations here.

    ``operation`` receives the remaining overall deadline in milliseconds.
    """

    started = clock.now_ms()
    draw = jitter_draw or (lambda bound: 0)
    classify = retryable or is_retryable
    for attempt in range(policy.max_attempts):
        if cancel is not None:
            cancel.check()
        budget = remaining_ms(clock, started, policy.timeout_ms)
        if budget <= 0:
            raise TimeoutExpired()
        try:
            result = operation(budget)
        except TimeoutExpired:
            raise
        except QuotaExceeded:
            raise ApplicationError("model", "quota_exceeded") from None
        except ApplicationError:
            raise
        except BaseException as exc:
            if not classify(exc):
                raise
            if attempt + 1 >= policy.max_attempts:
                break
            delay = jittered_backoff_ms(attempt, policy, draw)
            leftover = remaining_ms(clock, started, policy.timeout_ms)
            if leftover <= 0:
                raise TimeoutExpired() from None
            clock.sleep_ms(min(delay, leftover), cancel)
            continue
        if remaining_ms(clock, started, policy.timeout_ms) <= 0:
            raise TimeoutExpired()
        return result
    raise ApplicationError("model", "unavailable") from None
