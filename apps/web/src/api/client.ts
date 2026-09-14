import { ClosedApiError, isClosedError } from "./errors.js";
import { openJsonMessageStream, openProgressStream } from "./progress.js";
import {
  AGENT_PREFIX,
  API_PREFIX,
  type AgentEventHandlers,
  type AgentGrantBody,
  type AgentSessionCreateBody,
  type AgentTurnBody,
  type AuthorizationBody,
  type IntakeAcceptBody,
  type IntakeAuthorizeBody,
  type IntakeIntentFields,
  type ItaaApi,
  type PurchaseIntent,
} from "./types.js";

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export const AGENT_REQUEST_TIMEOUT_MS = 90_000;

function intentPath(intentId: string, suffix = ""): string {
  return `${API_PREFIX}/intents/${encodeURIComponent(intentId)}${suffix}`;
}

function agentPath(sessionId: string, suffix = ""): string {
  return `${AGENT_PREFIX}/sessions/${encodeURIComponent(sessionId)}${suffix}`;
}

function intakePath(intentId: string, suffix: string): string {
  return `${API_PREFIX}/intake/intents/${encodeURIComponent(intentId)}${suffix}`;
}

export function createItaaApi(options: ApiClientOptions = {}): ItaaApi {
  const baseUrl = options.baseUrl ?? "";
  const fetchImpl = options.fetchImpl ?? fetch;

  async function request<T>(
    path: string,
    init: RequestInit & { idempotencyKey?: string } = {},
  ): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body !== undefined && !headers.has("content-type")) {
      headers.set("content-type", "application/json");
    }
    if (init.idempotencyKey !== undefined) {
      headers.set("Idempotency-Key", init.idempotencyKey);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), AGENT_REQUEST_TIMEOUT_MS);
    let response: Response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        ...init,
        headers,
        credentials: "same-origin",
        signal: init.signal ?? controller.signal,
      });
    } catch (error) {
      const aborted =
        (error instanceof DOMException && error.name === "AbortError") ||
        (error instanceof Error && error.name === "AbortError");
      throw new ClosedApiError({
        status: 0,
        code: aborted ? "timeout" : "network_failure",
        field: "request",
        correlationId: "unavailable",
        retryable: true,
        ambiguous: true,
      });
    } finally {
      clearTimeout(timer);
    }

    let payload: unknown = null;
    const text = await response.text();
    if (text !== "") {
      try {
        payload = JSON.parse(text) as unknown;
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      const envelope =
        typeof payload === "object" && payload !== null && "error" in payload
          ? (payload as { error: unknown }).error
          : null;
      const closed = isClosedError(envelope) ? envelope : null;
      throw new ClosedApiError({
        status: response.status,
        code: closed?.code ?? (response.status >= 500 ? "closed" : "malformed"),
        field: closed?.field ?? "request",
        correlationId: closed?.correlationId ?? "unavailable",
        retryable: response.status >= 500 || closed?.code === "injected_fault",
        ambiguous: response.status >= 500 && closed?.code !== "injected_fault",
      });
    }

    return payload as T;
  }

  return {
    healthz: () => request("/healthz"),
    readyz: () => request("/readyz"),
    createIntent: (body: PurchaseIntent) =>
      request(`${API_PREFIX}/intents`, { method: "POST", body: JSON.stringify(body) }),
    getSnapshot: (intentId: string) => request(intentPath(intentId)),
    confirmRequirement: (intentId, body) =>
      request(intentPath(intentId, "/confirm"), { method: "POST", body: JSON.stringify(body) }),
    approveAndDispatch: (intentId, body) =>
      request(intentPath(intentId, "/dispatch"), { method: "POST", body: JSON.stringify(body) }),
    acceptOffer: (intentId, body) =>
      request(intentPath(intentId, "/acceptances"), { method: "POST", body: JSON.stringify(body) }),
    authorizeTransaction: (intentId, body: AuthorizationBody, headerIdempotencyKey: string) =>
      request(intentPath(intentId, "/transaction-authorizations"), {
        method: "POST",
        body: JSON.stringify(body),
        idempotencyKey: headerIdempotencyKey,
      }),
    extractIntake: (text, category) =>
      request(`${API_PREFIX}/intake/extractions`, {
        method: "POST",
        body: JSON.stringify({ text, category }),
      }),
    confirmIntakeIntent: (body: IntakeIntentFields) =>
      request(`${API_PREFIX}/intake/intents`, { method: "POST", body: JSON.stringify(body) }),
    intakeConfirm: (intentId) =>
      request(intakePath(intentId, "/confirm"), { method: "POST", body: "{}" }),
    intakeDispatch: (intentId) =>
      request(intakePath(intentId, "/dispatch"), { method: "POST", body: "{}" }),
    intakeAccept: (intentId, body: IntakeAcceptBody) =>
      request(intakePath(intentId, "/acceptances"), {
        method: "POST",
        body: JSON.stringify(body),
      }),
    intakeAuthorize: (intentId, body: IntakeAuthorizeBody = {}) =>
      request(intakePath(intentId, "/transaction-authorizations"), {
        method: "POST",
        body: JSON.stringify(body),
      }),
    listIntents: () => request(`${API_PREFIX}/intake/intents`),
    getOwnedIntent: (intentId) => request(intakePath(intentId, "")),
    cancelIntent: (intentId) =>
      request(intakePath(intentId, "/cancel"), { method: "POST", body: "{}" }),
    replaceIntent: (intentId, idempotencyKey) =>
      request(intakePath(intentId, "/replace"), {
        method: "POST",
        body: "{}",
        idempotencyKey,
      }),
    deleteDraft: async (intentId) => {
      await request(intakePath(intentId, ""), { method: "DELETE" });
    },
    saveIntent: (intentId) =>
      request(intakePath(intentId, "/save"), { method: "POST", body: "{}" }),
    unsaveIntent: (intentId) => request(intakePath(intentId, "/save"), { method: "DELETE" }),
    intentActivity: async (intentId) => {
      const body = await request<{ activity: Array<{ occurredAt: string; label: string }> }>(
        intakePath(intentId, "/activity"),
      );
      return body.activity;
    },
    subscribeProgress: (intentId, handlers, reconnect) =>
      openProgressStream({
        baseUrl,
        intentId,
        onEvent: handlers.onEvent,
        onError: handlers.onError,
        ...(reconnect?.lastEventId !== undefined ? { lastEventId: reconnect.lastEventId } : {}),
        ...(reconnect?.generationId !== undefined ? { generationId: reconnect.generationId } : {}),
      }),
    createAgentSession: (body: AgentSessionCreateBody) =>
      request(`${AGENT_PREFIX}/sessions`, { method: "POST", body: JSON.stringify(body) }),
    getAgentSession: (sessionId: string) => request(agentPath(sessionId)),
    postAgentTurn: (sessionId: string, body: AgentTurnBody) =>
      request(agentPath(sessionId, "/turns"), { method: "POST", body: JSON.stringify(body) }),
    confirmAgentSession: (sessionId: string) =>
      request(agentPath(sessionId, "/confirm"), { method: "POST", body: "{}" }),
    grantAgentSession: (sessionId: string, body: AgentGrantBody) =>
      request(agentPath(sessionId, "/grants"), { method: "POST", body: JSON.stringify(body) }),
    subscribeAgentEvents: (sessionId: string, handlers: AgentEventHandlers) =>
      openJsonMessageStream({
        url: `${baseUrl}${agentPath(sessionId, "/events")}`,
        kinds: AGENT_ACTIVITY_KINDS,
        onEvent: handlers.onEvent,
        onError: handlers.onError,
      }),
  };
}

export const AGENT_ACTIVITY_KINDS = [
  "OBJECTIVE_RECEIVED",
  "CHECKING_MISSING",
  "CLARIFICATION_READY",
  "PLAN_UPDATING",
  "PLAN_READY",
  "PLAN_CONFIRMED",
  "PARKING_RESEARCHING",
  "OFFERS_COMPARING",
  "RECOMMENDATION_PREPARING",
  "AWAITING_HUMAN_APPROVAL",
  "FALLBACK_DETERMINISTIC",
  "FAILED_CLOSED",
] as const;
