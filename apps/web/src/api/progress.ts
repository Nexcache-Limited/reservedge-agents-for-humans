import {
  API_PREFIX,
  type ProgressEventPayload,
  type ProgressReconnect,
  type ProgressSubscription,
} from "./types.js";

export const PROGRESS_EVENT_KINDS = [
  "SOLICITATION_PREPARING",
  "SOLICITATION_DISPATCHED",
  "SUPPLIER_WAITING",
  "SUPPLIER_OFFER_RECEIVED",
  "SUPPLIER_DECLINED",
  "SUPPLIER_TIMED_OUT",
  "SUPPLIER_LATE",
  "SUPPLIER_INVALID",
  "SUPPLIER_FAILED",
  "VALIDATION_COMPLETED",
  "RANKING_COMPLETED",
  "RECOMMENDATION_READY",
  "STREAM_COMPLETED",
] as const;

export interface OpenProgressOptions extends ProgressReconnect {
  baseUrl: string;
  intentId: string;
  onEvent: (event: ProgressEventPayload) => void;
  onError: () => void;
  eventSource?: typeof EventSource;
}

function parsePayload(raw: string): ProgressEventPayload | null {
  try {
    const parsed = JSON.parse(raw) as ProgressEventPayload;
    if (typeof parsed.kind !== "string" || typeof parsed.sequence !== "number") {
      return null;
    }
    if (typeof parsed.generationId !== "string" || parsed.generationId === "") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function openProgressStream(options: OpenProgressOptions): ProgressSubscription {
  const ctor = options.eventSource ?? globalThis.EventSource;
  if (typeof ctor !== "function") {
    options.onError();
    return { close: () => undefined };
  }
  const params = new URLSearchParams();
  if (options.generationId !== undefined && options.generationId !== "") {
    params.set("generationId", options.generationId);
  }
  if (options.lastEventId !== undefined && options.lastEventId !== "") {
    params.set("lastEventId", options.lastEventId);
  }
  const query = params.size > 0 ? `?${params.toString()}` : "";
  const url = `${options.baseUrl}${API_PREFIX}/intents/${encodeURIComponent(options.intentId)}/events${query}`;
  const source = new ctor(url);
  const handle = (message: Event) => {
    const data = "data" in message ? String((message as MessageEvent).data) : "";
    const payload = parsePayload(data);
    if (payload !== null) {
      options.onEvent(payload);
    }
  };
  for (const kind of PROGRESS_EVENT_KINDS) {
    source.addEventListener(kind, handle);
  }
  source.onerror = () => {
    source.close();
    options.onError();
  };
  return {
    close: () => {
      source.close();
    },
  };
}

export function openJsonMessageStream(options: {
  url: string;
  kinds: readonly string[];
  onEvent: (event: { kind: string; message: string }) => void;
  onError: () => void;
  eventSource?: typeof EventSource;
}): ProgressSubscription {
  const ctor = options.eventSource ?? globalThis.EventSource;
  if (typeof ctor !== "function") {
    return { close: () => undefined };
  }
  const source = new ctor(options.url);
  const handle = (message: Event) => {
    const data = "data" in message ? String((message as MessageEvent).data) : "";
    try {
      const parsed = JSON.parse(data) as { kind?: unknown; message?: unknown };
      if (typeof parsed.kind === "string" && typeof parsed.message === "string") {
        options.onEvent({ kind: parsed.kind, message: parsed.message });
      }
    } catch {
      return;
    }
  };
  for (const kind of options.kinds) {
    source.addEventListener(kind, handle);
  }
  source.onerror = () => {
    source.close();
    options.onError();
  };
  return {
    close: () => {
      source.close();
    },
  };
}
