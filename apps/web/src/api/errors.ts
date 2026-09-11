import type { ClosedError } from "./types.js";

const RETRYABLE_CODES = new Set(["closed", "injected_fault"]);

const BUYER_MESSAGES: Record<string, string> = {
  schema_invalid: "The request could not be understood. Review the details and try again.",
  unknown_resource: "This request is not available in this browser session.",
  illegal_state: "That action is not available in the current step.",
  stale_version: "The selected offer is no longer the current version.",
  expired: "This approval or offer has expired. Start again from a fresh review.",
  approval_denied: "Governance did not allow this approval.",
  approval_reused: "That confirmation was already used. Refresh and try the current step.",
  request_mismatch: "The retry did not match the original authorization request.",
  mode_forbidden: "Only a simulated reservation can be authorized in this demo.",
  ineligible: "That offer cannot be accepted.",
  malformed: "The request was incomplete.",
  invalid_opaque_syntax: "An identifier was not in the expected form.",
  unavailable: "The extraction service is not available. Try again in a moment.",
  network_failure:
    "The service did not confirm the last action. Refresh status before trying again.",
  timeout: "That took too long. Nothing was sent to any supplier. Try Start booking again.",
};

export class ClosedApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | null;
  readonly correlationId: string;
  readonly retryable: boolean;
  readonly ambiguous: boolean;

  constructor(input: {
    status: number;
    code: string;
    field: string | null;
    correlationId: string;
    retryable?: boolean;
    ambiguous?: boolean;
  }) {
    super(buyerMessage(input.code, input.status));
    this.name = "ClosedApiError";
    this.status = input.status;
    this.code = input.code;
    this.field = input.field;
    this.correlationId = input.correlationId;
    this.retryable = input.retryable ?? isRetryable(input.status, input.code);
    this.ambiguous =
      input.ambiguous ??
      ((input.status >= 500 || input.status === 0) && input.code !== "injected_fault");
  }
}

export function buyerMessage(code: string, status: number): string {
  const mapped = BUYER_MESSAGES[code];
  if (mapped !== undefined) {
    return mapped;
  }
  if (status >= 500 || status === 0) {
    return "The service did not confirm the last action. Refresh status before trying again.";
  }
  return "The request could not be completed.";
}

export function isRetryable(status: number, code: string): boolean {
  return status === 0 || status >= 500 || RETRYABLE_CODES.has(code);
}

export function isClosedError(value: unknown): value is ClosedError {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.code === "string" &&
    (typeof record.field === "string" || record.field === null) &&
    typeof record.correlationId === "string"
  );
}

export function sanitizeLogValue(value: string): string {
  return value.replace(/\b(ap|ik|sg|bs|ar|cr)_[0-9a-hjkmnp-tv-z]{26}\b/gi, "[redacted]");
}
