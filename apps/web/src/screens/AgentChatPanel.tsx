import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type FormEvent,
  type ReactNode,
  type SetStateAction,
} from "react";
import { flushSync } from "react-dom";
import type { ItaaApi } from "../api/types.js";
import {
  AGENT_FAILURE_COPY,
  AGENT_FALLBACK_COPY,
  AGENT_UPDATING_COPY,
  failAgentSession,
  isProgressActivity,
  mergeAgentView,
  projectAgentSession,
  withoutUpdatingActivity,
  withUpdatingActivity,
} from "../intent-first/agent.js";
import { firstTurnCopy, projectPlan, type PlanSession } from "../intent-first/plan.js";

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
  const inputId = compact ? "running-note" : "clarify-note";
  const threadRef = useRef<HTMLDivElement>(null);
  const composeRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

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

  useEffect(() => {
    const thread = threadRef.current;
    if (thread === null || !stickToBottom.current) {
      return;
    }
    thread.scrollTop = thread.scrollHeight;
    composeRef.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [session.agent?.transcript, session.agent?.activity, session.agent?.buyerSafeMessage, busy]);

  async function sendNote(event: FormEvent) {
    event.preventDefault();
    if (busy || draftNote.trim() === "") {
      return;
    }
    const message = draftNote.trim();
    setDraftNote("");
    const extraNote = `${session.extraNote} ${message}`.trim();
    if (session.agent && !failed) {
      const agent = session.agent;
      const last = agent.transcript[agent.transcript.length - 1];
      const alreadyShown = last?.role === "user" && last.text === message;
      const withUser = alreadyShown
        ? { ...session, extraNote }
        : {
            ...session,
            extraNote,
            agent: {
              ...agent,
              transcript: [...agent.transcript, { role: "user", text: message }],
            },
          };
      flushSync(() => {
        setBusy(true);
        setPlanSession(withUpdatingActivity(withUser));
      });
      try {
        const view = await api.postAgentTurn(agent.sessionId, { message });
        flushSync(() => {
          setPlanSession(mergeAgentView(withUser, view));
        });
      } catch {
        flushSync(() => {
          setPlanSession(failAgentSession(withUser, AGENT_FAILURE_COPY));
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
      <div
        className="re-clarify-thread"
        ref={threadRef}
        onScroll={() => {
          const thread = threadRef.current;
          if (thread === null) {
            return;
          }
          stickToBottom.current = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 72;
        }}
      >
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
      <div className="re-clarify-compose-wrap" ref={composeRef} aria-busy={busy || undefined}>
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
