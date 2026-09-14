import { useId, useRef, useState, useEffect } from "react";
import { flushSync } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { ClosedApiError } from "../api/errors.js";
import type { ItaaApi } from "../api/types.js";
import {
  AGENT_FAILURE_COPY,
  AGENT_OBJECTIVE_COPY,
  sessionFromAgentView,
} from "../intent-first/agent.js";
import { simulationNoteFor, SUGGESTED_OBJECTIVES } from "../intent-first/objective.js";
import { withParked } from "../reservedge/plan-inbox.js";
import { usePortfolio } from "../reservedge/portfolio.js";
import { listDomains } from "../reservedge/registry.js";

export function IntentComposer({ api }: { api: ItaaApi }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { objective, setObjective, planSession, setPlanSession, setParkedSessions } =
    usePortfolio();
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const headingId = useId();
  const ready = objective.trim() !== "";
  const domains = listDomains();

  useEffect(() => {
    const reset = (location.state as { composerReset?: number } | null)?.composerReset;
    if (reset !== undefined) {
      setObjective("");
      setNote(null);
    }
  }, [location.state, setObjective]);

  function applySuggestion(text: string) {
    setObjective(text);
    setNote("Suggestion applied. You can edit it before starting.");
    fieldRef.current?.focus();
  }

  async function startBooking() {
    if (!ready || busy) {
      return;
    }
    const text = objective.trim();
    flushSync(() => {
      setBusy(true);
      setFailed(false);
      setNote(AGENT_OBJECTIVE_COPY);
    });
    try {
      const view = await api.createAgentSession({ objective: text });
      const session = sessionFromAgentView(text, view);
      flushSync(() => {
        setParkedSessions((current) => withParked(current, planSession));
        setPlanSession(session);
        setObjective("");
        setNote("Nothing is sent to any supplier from this step. Clarify and plan next.");
        setBusy(false);
      });
      navigate("/intents/clarify", { state: { planSession: session } });
    } catch (error) {
      const closed = error instanceof ClosedApiError;
      flushSync(() => {
        setFailed(true);
        setNote(
          closed
            ? `${AGENT_FAILURE_COPY}. ${error.message} Nothing was sent to any supplier.`
            : `${AGENT_FAILURE_COPY}. Nothing was sent to any supplier.`,
        );
      });
    } finally {
      setBusy(false);
    }
  }

  function startDomain(domainId: string) {
    const domain = domains.find((item) => item.id === domainId);
    if (domain === undefined) {
      return;
    }
    setParkedSessions((current) => withParked(current, planSession));
    setPlanSession(null);
    setNote(
      domain.simulation === "competition_path"
        ? simulationNoteFor("parking")
        : simulationNoteFor(domain.id),
    );
    navigate(`/intents/new/${domain.id}`, {
      state: { objective: objective.trim() },
    });
  }

  return (
    <div className="re-fade re-intent-compose">
      <div className="re-eyebrow">NEW INTENT</div>
      <h2 className="re-h2 re-intent-compose-title" id={headingId}>
        What are you planning or trying to get done?
      </h2>
      <p className="re-lead">
        Describe it the way you&apos;d say it out loud. Reservedge works out which bookings it
        implies, asks only for what it&apos;s missing, and shows you every field before anything
        leaves this workspace.
      </p>
      <div className="re-intent-compose-card">
        <textarea
          ref={fieldRef}
          className="re-intent-compose-field itaa-focus-ring"
          aria-labelledby={headingId}
          placeholder="I'm planning a five-day trip to New York in October."
          value={objective}
          rows={4}
          disabled={busy}
          onChange={(event) => setObjective(event.target.value)}
        />
        <div className="re-intent-compose-footer">
          <p className="re-intent-compose-disclosure">
            Nothing is sent to any supplier from this step.
          </p>
          <button
            type="button"
            className="re-primary itaa-focus-ring"
            disabled={!ready || busy}
            aria-busy={busy || undefined}
            onClick={startBooking}
          >
            {busy ? <span className="re-processing-spinner" aria-hidden /> : null}
            Start booking
          </button>
        </div>
      </div>
      {note !== null ? (
        <p
          className={
            busy
              ? "re-intent-compose-note re-processing"
              : failed
                ? "re-intent-compose-note is-error"
                : "re-intent-compose-note"
          }
          role={failed ? "alert" : "status"}
          aria-live={failed ? "assertive" : "polite"}
        >
          {busy ? <span className="re-processing-spinner" aria-hidden /> : null}
          {note}
        </p>
      ) : null}
      <div className="re-intent-suggestions">
        {SUGGESTED_OBJECTIVES.map((item) => (
          <button
            key={item}
            type="button"
            className="re-chip-btn itaa-focus-ring"
            onClick={() => applySuggestion(item)}
          >
            {item}
          </button>
        ))}
      </div>
      <div className="re-intent-direct">
        <div className="re-intent-direct-title">Already know the exact booking?</div>
        <p>
          Start one task directly. It becomes a one-task booking, so the same requirement,
          disclosure and authorization steps still apply.
        </p>
        <div className="re-intent-direct-row">
          {domains.map((domain) => (
            <button
              key={domain.id}
              type="button"
              className="re-intent-direct-btn itaa-focus-ring"
              onClick={() => startDomain(domain.id)}
            >
              <span className="re-code">{domain.code}</span>
              {domain.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
