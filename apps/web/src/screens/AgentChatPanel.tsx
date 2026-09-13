import {
  useEffect,
  useId,
  useMemo,
  useState,
  type Dispatch,
  type FormEvent,
  type ReactNode,
  type SetStateAction,
} from "react";
import { flushSync } from "react-dom";
import { useNavigate } from "react-router-dom";
import type { ItaaApi } from "../api/types.js";
import type { AgentGrantBody, RankedOffer } from "../api/types.js";
import {
  AGENT_FAILURE_COPY,
  AGENT_FALLBACK_COPY,
  AGENT_UPDATING_COPY,
  failAgentSession,
  isProgressActivity,
  mergeAgentView,
  projectAgentSession,
  syncPlanSessionWithSnapshot,
  withoutUpdatingActivity,
  withUpdatingActivity,
} from "../intent-first/agent.js";
import { firstTurnCopy, projectPlan, type PlanSession } from "../intent-first/plan.js";
import { formatMoney } from "../fixtures/golden.js";

export function AgentChatPanel({
  api,
  session,
  setPlanSession,
  fallbackObjective,
  compact = false,
  hidden = false,
  headingId,
  children,
}: {
  api: ItaaApi;
  session: PlanSession;
  setPlanSession: Dispatch<SetStateAction<PlanSession | null>>;
  fallbackObjective: string;
  compact?: boolean;
  hidden?: boolean;
  headingId?: string;
  children?: ReactNode;
}) {
  const navigate = useNavigate();
  const generatedId = useId();
  const labelId = headingId ?? generatedId;
  const [draftNote, setDraftNote] = useState("");
  const [busy, setBusy] = useState(false);
  const projection = useMemo(
    () => (session.agent ? projectAgentSession(session) : projectPlan(session)),
    [session],
  );
  const objectiveText = session.objective || fallbackObjective;
  const failed = session.agent?.failed === true;
  const fallback = session.agent?.fallback === true;
  const agentBacked = session.agent !== undefined && session.agent !== null;
  const parkingOffers = session.agent?.domains?.parking?.offerSet.snapshot?.offers ?? [];
  const completeness = session.agent?.domains?.parking?.completeness;
  const pendingGrant = session.agent?.pendingAuthorization;
  const blockedA3 =
    pendingGrant?.gate === "A3" &&
    (parkingOffers.length === 0 || completeness === "accepted" || completeness === "authorized");
  const showGrant =
    pendingGrant != null &&
    completeness !== "authorized" &&
    !blockedA3 &&
    pendingGrant.gate !== "A2" &&
    pendingGrant.gate !== "A1";
  const inputId = compact ? "running-note" : "clarify-note";

  useEffect(() => {
    const sessionId = session.agent?.sessionId;
    if (sessionId === undefined || failed) {
      return;
    }
    const subscription = api.subscribeAgentEvents(sessionId, {
      onEvent: (event) => {
        if (isProgressActivity(event.message)) {
          return;
        }
        setPlanSession((current) => {
          if (current === null || current.agent === undefined || current.agent === null) {
            return current;
          }
          if (current.agent.activity.some((item) => item.message === event.message)) {
            return current;
          }
          return {
            ...current,
            agent: {
              ...current.agent,
              activity: [...withoutUpdatingActivity(current.agent.activity), event],
            },
          };
        });
      },
      onError: () => undefined,
    });
    return () => {
      subscription.close();
    };
  }, [api, failed, session.agent?.sessionId, setPlanSession]);

  async function sendGrant(body: AgentGrantBody) {
    if (!session.agent || failed || busy) {
      return;
    }
    const parking = session.agent.domains?.parking;
    const intentId = typeof parking?.intentId === "string" ? parking.intentId : "";
    const liveParking = intentId.startsWith("pi_") && (body.gate === "A3" || body.gate === "A4");
    flushSync(() => {
      setBusy(true);
      setPlanSession(withUpdatingActivity(session));
    });
    try {
      if (liveParking && body.gate === "A3") {
        const offers = parking?.offerSet.snapshot?.offers ?? [];
        const offerId =
          body.offerId ??
          parking?.offerSet.snapshot?.recommendedOfferId ??
          offers.find((item) => item.recommended)?.offerId;
        const offer = offers.find((item) => item.offerId === offerId);
        if (offerId === undefined || offer === undefined) {
          throw new Error("missing offer");
        }
        const next = await api.intakeAccept(intentId, {
          offerId,
          offerVersion: offer.version,
        });
        flushSync(() => {
          setPlanSession(syncPlanSessionWithSnapshot(session, next));
        });
        return;
      }
      if (liveParking && body.gate === "A4") {
        const next = await api.intakeAuthorize(intentId);
        flushSync(() => {
          setPlanSession(syncPlanSessionWithSnapshot(session, next));
        });
        navigate(`/intents/${intentId}/confirmation`);
        return;
      }
      const view = await api.grantAgentSession(session.agent.sessionId, body);
      flushSync(() => {
        setPlanSession(mergeAgentView(session, view));
      });
    } catch {
      flushSync(() => {
        setPlanSession(failAgentSession(session, AGENT_FAILURE_COPY));
      });
    } finally {
      setBusy(false);
    }
  }

  async function sendNote(event: FormEvent) {
    event.preventDefault();
    if (busy || draftNote.trim() === "") {
      return;
    }
    const message = draftNote.trim();
    setDraftNote("");
    const pending = session.agent?.pendingAuthorization;
    if (
      session.agent &&
      !failed &&
      pending &&
      (pending.gate === "A3" || pending.gate === "A4") &&
      isAffirmativeGrant(message)
    ) {
      await sendGrant({
        gate: pending.gate as AgentGrantBody["gate"],
        domain: "parking",
        ...(typeof pending.offerId === "string" ? { offerId: pending.offerId } : {}),
      });
      return;
    }
    const extraNote = `${session.extraNote} ${message}`.trim();
    if (session.agent && !failed) {
      flushSync(() => {
        setBusy(true);
        setPlanSession(withUpdatingActivity({ ...session, extraNote }));
      });
      try {
        const view = await api.postAgentTurn(session.agent.sessionId, { message });
        flushSync(() => {
          setPlanSession(mergeAgentView({ ...session, extraNote }, view));
        });
      } catch {
        flushSync(() => {
          setPlanSession(failAgentSession({ ...session, extraNote }, AGENT_FAILURE_COPY));
        });
      } finally {
        setBusy(false);
      }
      return;
    }
    setPlanSession({ ...session, extraNote });
  }

  return (
    <section
      className={`re-clarify-chat${compact ? " is-running" : ""}`}
      hidden={hidden}
      aria-labelledby={labelId}
    >
      <div className="re-clarify-chat-head">
        <span className="re-clarify-kicker" id={labelId}>
          {compact ? "RUNNING" : "CONVERSATION"}
        </span>
        <span className="re-clarify-kicker-note">
          {compact ? "Continue this booking" : agentBacked ? "Active session" : "Intake only"}
        </span>
      </div>
      <div className="re-clarify-thread">
        <div className="re-clarify-log">
          {agentBacked && (session.agent?.transcript.length ?? 0) > 0 ? (
            <>
              {session.agent?.transcript.map((item, index) => (
                <div
                  key={`${item.role}-${index}`}
                  className={
                    item.role === "user"
                      ? "re-clarify-bubble re-clarify-bubble-user"
                      : "re-clarify-bubble re-clarify-bubble-agent"
                  }
                >
                  {item.text}
                </div>
              ))}
            </>
          ) : (
            <>
              <div className="re-clarify-bubble re-clarify-bubble-user">{objectiveText}</div>
              {session.extraNote.trim() !== "" ? (
                <div className="re-clarify-bubble re-clarify-bubble-user">{session.extraNote}</div>
              ) : null}
              <div className="re-clarify-agent">
                <span className="re-clarify-mark" aria-hidden />
                <div className="re-clarify-bubble re-clarify-bubble-agent">
                  {firstTurnCopy(projection.facts) || projection.summary}
                </div>
              </div>
            </>
          )}
          {session.agent?.activity
            .filter((event) => !isProgressActivity(event.message))
            .map((event) => (
              <p key={`${event.kind}-${event.message}`} className="re-clarify-enough">
                {event.message}
              </p>
            ))}
          {showGrant && session.agent?.pendingAuthorization ? (
            <button
              type="button"
              className="re-primary itaa-focus-ring re-clarify-update"
              disabled={busy}
              aria-busy={busy || undefined}
              onClick={() =>
                sendGrant({
                  gate: session.agent?.pendingAuthorization?.gate as AgentGrantBody["gate"],
                  domain: "parking",
                  ...(typeof session.agent?.pendingAuthorization?.offerId === "string"
                    ? { offerId: session.agent.pendingAuthorization.offerId }
                    : {}),
                })
              }
            >
              {busy ? <span className="re-processing-spinner" aria-hidden /> : null}
              {grantLabel(session.agent.pendingAuthorization.gate, parkingOffers)}
            </button>
          ) : null}
          {fallback ? (
            <p className="re-clarify-enough" role="status">
              {AGENT_FALLBACK_COPY}
            </p>
          ) : null}
          {failed ? (
            <p className="re-clarify-error" role="alert">
              {session.agent?.failureMessage || AGENT_FAILURE_COPY}
            </p>
          ) : (
            children
          )}
        </div>
      </div>
      <div className="re-clarify-compose-wrap" aria-busy={busy || undefined}>
        {busy ? (
          <p className="re-clarify-progress" role="status">
            <span className="re-processing-spinner" aria-hidden />
            {session.agent?.activity.find((item) => isProgressActivity(item.message))?.message ??
              AGENT_UPDATING_COPY}
          </p>
        ) : null}
        <form className="re-clarify-compose" onSubmit={sendNote}>
          <label className="itaa-visually-hidden" htmlFor={inputId}>
            Add anything else about this trip
          </label>
          <input
            id={inputId}
            className="re-clarify-input itaa-focus-ring"
            value={draftNote}
            placeholder="Add anything else about this trip…"
            onChange={(event) => setDraftNote(event.target.value)}
            disabled={busy}
          />
          <button
            type="submit"
            className={`re-clarify-send itaa-focus-ring${draftNote.trim() !== "" && !busy ? " is-ready" : ""}`}
            aria-label="Add note"
            aria-busy={busy || undefined}
            disabled={busy || draftNote.trim() === ""}
          >
            {busy ? <span className="re-processing-spinner" aria-hidden /> : "→"}
          </button>
        </form>
      </div>
    </section>
  );
}

function isAffirmativeGrant(text: string): boolean {
  return /^(yes|yeah|yep|ok|okay|please|confirm|go ahead|request offers|authorize|accept)([.!]?)$/i.test(
    text.trim(),
  );
}

function grantLabel(gate: string, offers: RankedOffer[] = []): string {
  if (gate === "A1") {
    return "Confirm parking requirement";
  }
  if (gate === "A2") {
    return "Request parking offers";
  }
  if (gate === "A3") {
    return "Accept recommended offer";
  }
  const selected =
    offers.find((item) => item.recommended) ?? offers.find((item) => item.totalMinor !== undefined);
  if (
    selected !== undefined &&
    selected.totalMinor !== undefined &&
    typeof selected.currency === "string" &&
    selected.currency !== ""
  ) {
    return `Authorize ${formatMoney(selected.totalMinor, selected.currency)}`;
  }
  return "Authorize simulated reservation";
}
