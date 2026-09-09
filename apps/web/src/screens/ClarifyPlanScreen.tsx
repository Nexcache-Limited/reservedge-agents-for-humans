import { useEffect, useId, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { flushSync } from "react-dom";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ClosedApiError } from "../api/errors.js";
import type { ItaaApi } from "../api/types.js";
import type { AgentDomainState } from "../api/types.js";
import {
  AGENT_FAILURE_COPY,
  failAgentSession,
  mergeAgentView,
  projectAgentSession,
  turnAnswersFromSession,
  withUpdatingActivity,
} from "../intent-first/agent.js";
import {
  acceptTaskOverride,
  addTaskOverride,
  mergeSchedule,
  normalizeAnswers,
  parkingBookingStarted,
  parkingPrefill,
  projectPlan,
  provenanceLabel,
  provenanceNote,
  removeTaskOverride,
  supportedAddableKinds,
  taskStatusLabel,
  type PlanAnswers,
  type PlanSession,
  type PlanTask,
  type QuestionId,
  type TaskKind,
} from "../intent-first/plan.js";
import { rangeError } from "../intent-first/schedule.js";
import { usePortfolio } from "../reservedge/portfolio.js";
import { AgentChatPanel } from "./AgentChatPanel.js";
import { ClarifyScheduleFields } from "./ClarifyScheduleFields.js";

export function ClarifyPlanScreen({ api }: { api: ItaaApi }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { objective, planSession, setPlanSession } = usePortfolio();
  const routed = sessionFromState(location.state);
  const session = planSession ?? routed;
  useEffect(() => {
    if (planSession === null && routed !== null) {
      setPlanSession(routed);
    }
  }, [planSession, routed, setPlanSession]);
  if (session === null) {
    return <MissingPlan onCompose={() => navigate("/")} />;
  }
  const parkingId = session.agent?.domains?.parking?.intentId;
  if (
    parkingBookingStarted(session.agent?.domains?.parking) &&
    typeof parkingId === "string" &&
    parkingId.startsWith("pi_")
  ) {
    return <Navigate to={`/intents/${parkingId}`} replace />;
  }
  return (
    <ClarifyPlanBody
      api={api}
      session={session}
      fallbackObjective={objective}
      setPlanSession={setPlanSession}
      onExecute={(path, state) => navigate(path, { state })}
    />
  );
}

function sessionFromState(state: unknown): PlanSession | null {
  if (state === null || typeof state !== "object" || !("planSession" in state)) {
    return null;
  }
  const value = (state as { planSession?: unknown }).planSession;
  if (value === null || typeof value !== "object") {
    return null;
  }
  const candidate = value as PlanSession;
  if (typeof candidate.objective !== "string" || candidate.answers === undefined) {
    return null;
  }
  return {
    ...candidate,
    answers: normalizeAnswers(candidate.answers),
  };
}

function MissingPlan({ onCompose }: { onCompose: () => void }) {
  return (
    <div className="re-fade re-clarify-missing">
      <h2 className="re-h2">No plan in this session</h2>
      <p className="re-lead">
        Clarify &amp; plan lives in this browser session only. Session state is process-local and
        non-durable; it is not persisted to durable storage.
      </p>
      <button type="button" className="re-primary itaa-focus-ring" onClick={onCompose}>
        Start from an objective
      </button>
    </div>
  );
}

function ClarifyPlanBody({
  api,
  session,
  fallbackObjective,
  setPlanSession,
  onExecute,
}: {
  api: ItaaApi;
  session: PlanSession;
  fallbackObjective: string;
  setPlanSession: Dispatch<SetStateAction<PlanSession | null>>;
  onExecute: (
    path: string,
    state: { objective: string; knownParking: Record<string, string> },
  ) => void;
}) {
  const projection = useMemo(
    () => (session.agent ? projectAgentSession(session) : projectPlan(session)),
    [session],
  );
  const headingId = useId();
  const [busy, setBusy] = useState(false);
  const objectiveText = session.objective || fallbackObjective;
  const blocking = projection.questions;
  const ready = session.phase === "ready";
  const gathering = session.phase === "clarify";
  const narrow = useNarrow();
  const failed = session.agent?.failed === true;
  const agentBacked = session.agent !== undefined && session.agent !== null;
  const visibleTasks = gathering
    ? projection.tasks.filter((task) => task.provenance === "explicit")
    : projection.tasks;

  function patch(next: Partial<PlanSession>) {
    setPlanSession({ ...session, ...next });
  }

  function setAnswer(id: QuestionId, value: string) {
    patch({
      answers: mergeSchedule(session.answers, { [id]: value }, projection.facts.dates),
    });
  }

  function setSchedule(next: Partial<PlanAnswers>) {
    patch({
      answers: mergeSchedule(session.answers, next, projection.facts.dates),
    });
  }

  async function updatePlan() {
    if (busy || rangeError(session.answers) !== "") {
      return;
    }
    if (session.agent && !failed) {
      flushSync(() => {
        setBusy(true);
        setPlanSession(withUpdatingActivity(session));
      });
      try {
        const view = await api.postAgentTurn(session.agent.sessionId, {
          answers: turnAnswersFromSession(session),
        });
        flushSync(() => {
          setPlanSession(mergeAgentView({ ...session, phase: "forming", pane: "plan" }, view));
        });
      } catch (error) {
        flushSync(() => {
          setPlanSession(
            failAgentSession(
              session,
              error instanceof ClosedApiError ? AGENT_FAILURE_COPY : AGENT_FAILURE_COPY,
            ),
          );
        });
      } finally {
        setBusy(false);
      }
      return;
    }
    patch({ phase: "forming", pane: "plan" });
  }

  async function confirmPlan() {
    if (busy || projection.tasks.length === 0) {
      return;
    }
    if (session.agent && !failed) {
      flushSync(() => {
        setBusy(true);
        setPlanSession(withUpdatingActivity(session));
      });
      try {
        const view = await api.confirmAgentSession(session.agent.sessionId);
        flushSync(() => {
          setPlanSession(mergeAgentView({ ...session, phase: "ready", pane: "plan" }, view));
        });
      } catch {
        flushSync(() => {
          setPlanSession(failAgentSession(session, AGENT_FAILURE_COPY));
        });
      } finally {
        setBusy(false);
      }
      return;
    }
    patch({ phase: "ready", pane: "plan" });
  }

  function removeTask(id: string) {
    patch({
      overrides: [...session.overrides.filter((item) => item.id !== id), removeTaskOverride(id)],
    });
  }

  function acceptTask(id: string) {
    patch({
      overrides: [...session.overrides.filter((item) => item.id !== id), acceptTaskOverride(id)],
    });
  }

  function addTask(kind: TaskKind) {
    const override = addTaskOverride(kind);
    patch({
      overrides: [...session.overrides.filter((item) => item.id !== override.id), override],
    });
  }

  function beginParking() {
    if (session.agent?.domains?.parking) {
      return;
    }
    const prefill = parkingPrefill(objectiveText, projection.facts, session.answers);
    const handoff = session.agent?.parkingHandoff ?? null;
    onExecute(handoff?.path || "/intents/new/parking", {
      objective: prefill.draft,
      knownParking: { ...prefill.knownParking, ...(handoff?.fields ?? {}) },
    });
  }

  function beginDemo(kind: "rental" | "ents") {
    onExecute(`/intents/new/${kind}`, {
      objective: objectiveText,
      knownParking: {},
    });
  }

  const addable = supportedAddableKinds(projection.tasks);
  const parkingWorkspace = session.agent?.domains?.parking != null;
  const composerHandoff = !agentBacked || !parkingWorkspace;
  const executableParking =
    ready && composerHandoff && projection.tasks.some((task) => task.kind === "parking");
  const executableRental =
    ready && composerHandoff && projection.tasks.some((task) => task.kind === "rental");
  const executableEnts =
    ready && composerHandoff && projection.tasks.some((task) => task.kind === "ents");
  const parkingDomain = session.agent?.domains?.parking;
  const rentalDomain = session.agent?.domains?.rental;
  const liveParking =
    parkingDomain != null &&
    (parkingDomain.accepted === true || parkingDomain.provenance === "explicit");

  return (
    <div className="re-fade re-clarify">
      {narrow ? (
        <div className="re-clarify-panes" role="tablist" aria-label="Clarify and plan">
          <button
            type="button"
            role="tab"
            aria-selected={session.pane === "conversation"}
            className={`re-clarify-pane itaa-focus-ring${session.pane === "conversation" ? " is-on" : ""}`}
            onClick={() => patch({ pane: "conversation" })}
          >
            Conversation
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={session.pane === "plan"}
            className={`re-clarify-pane itaa-focus-ring${session.pane === "plan" ? " is-on" : ""}`}
            onClick={() => patch({ pane: "plan" })}
          >
            {gathering
              ? "Plan"
              : `Plan · ${projection.tasks.length} ${projection.tasks.length === 1 ? "task" : "tasks"}`}
          </button>
        </div>
      ) : null}

      <AgentChatPanel
        api={api}
        session={session}
        setPlanSession={setPlanSession}
        fallbackObjective={fallbackObjective}
        hidden={narrow && session.pane !== "conversation"}
        headingId={headingId}
      >
        {gathering && blocking.length > 0 && parkingDomain == null ? (
          <ClarificationCard
            questions={blocking}
            answers={session.answers}
            facts={projection.facts}
            onAnswer={setAnswer}
            onSchedule={setSchedule}
            onUpdate={() => updatePlan()}
            phase={session.phase}
            busy={busy}
          />
        ) : (
          <p className="re-clarify-enough">
            Already supplied facts were kept and are not asked again.
          </p>
        )}
      </AgentChatPanel>

      <section
        className="re-clarify-plan"
        hidden={narrow && session.pane !== "plan"}
        aria-labelledby="clarify-plan-heading"
      >
        <div className="re-clarify-plan-head">
          <span className="re-clarify-kicker">PLAN</span>
          <span
            className={`re-clarify-status${ready ? " is-ready" : gathering ? " is-gathering" : ""}`}
          >
            {ready ? "Confirmed" : gathering ? "Gathering" : "Forming"}
          </span>
        </div>
        <h2 className="re-h2 re-clarify-plan-title" id="clarify-plan-heading">
          {projection.title}
        </h2>
        <p className="re-lead re-clarify-plan-lead">
          {gathering && parkingDomain == null
            ? "I'll assemble booking tasks after these answers. No domain is selected yet."
            : projection.summary}
        </p>
        {gathering && visibleTasks.length === 0 && parkingDomain == null ? (
          <div className="re-clarify-hold">
            <p>Booking tasks are not selected yet.</p>
            <p>
              Answer the questions first. Then the plan will call the matching booking domains from
              what you have told me. Nothing is sent to any supplier from this step.
            </p>
          </div>
        ) : (
          <div className="re-clarify-tasks">
            {visibleTasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                ready={ready}
                onRemove={() => removeTask(task.id)}
                onAccept={() => acceptTask(task.id)}
                onBeginParking={beginParking}
                onBeginDemo={beginDemo}
                executableParking={executableParking && task.kind === "parking"}
                executableRental={executableRental && task.kind === "rental"}
                executableEnts={executableEnts && task.kind === "ents"}
              />
            ))}
            {gathering && !agentBacked ? (
              <p className="re-clarify-hold">
                Other booking tasks wait until these answers are in. Nothing is sent to any supplier
                from this step.
              </p>
            ) : null}
          </div>
        )}
        {liveParking ? (
          <ParkingDomainPane
            domain={parkingDomain}
            busy={busy}
            onEdit={(fieldId, value) => {
              if (!session.agent) {
                return;
              }
              void api
                .postAgentTurn(session.agent.sessionId, {
                  patches: [{ domain: "parking", fieldId, value }],
                })
                .then((view) => setPlanSession(mergeAgentView(session, view)))
                .catch(() => setPlanSession(failAgentSession(session, AGENT_FAILURE_COPY)));
            }}
          />
        ) : null}
        {rentalDomain ? <RentalDomainPane domain={rentalDomain} /> : null}
        {addable.length > 0 && !ready && !gathering ? (
          <div className="re-clarify-add">
            <div className="re-clarify-add-label">Add a supported task</div>
            {addable.map((kind) => (
              <button
                key={kind}
                type="button"
                className="re-chip-btn itaa-focus-ring"
                onClick={() => addTask(kind)}
              >
                Add {kindLabel(kind)}
              </button>
            ))}
          </div>
        ) : null}
        <p className="re-clarify-honesty">
          This plan is formed in this browser session for review. It is not production planning
          intelligence. Session state is process-local and non-durable — not persisted to durable
          storage — and nothing is sent to any supplier from this step.
        </p>
        {ready ? (
          <p className="re-clarify-confirmed" role="status">
            Plan confirmed. Task execution is available on supported tasks only.
          </p>
        ) : failed ? (
          <p className="re-clarify-waiting">Could not confirm this plan from a failed step.</p>
        ) : (session.phase === "forming" || blocking.length === 0) && !narrow ? (
          <button
            type="button"
            className="re-primary itaa-focus-ring re-clarify-confirm"
            disabled={projection.tasks.length === 0 || busy}
            aria-busy={busy || undefined}
            onClick={() => confirmPlan()}
          >
            {busy ? <span className="re-processing-spinner" aria-hidden /> : null}
            Confirm plan
          </button>
        ) : session.phase === "clarify" && blocking.length > 0 ? (
          <p className="re-clarify-waiting">
            Answer and update the plan before confirming. No task execution starts yet.
          </p>
        ) : null}
      </section>
      {narrow && !ready && !failed && (session.phase === "forming" || blocking.length === 0) ? (
        <div className="re-clarify-mobile-actions">
          <button
            type="button"
            className="re-primary itaa-focus-ring"
            disabled={projection.tasks.length === 0 || busy}
            aria-busy={busy || undefined}
            onClick={() => confirmPlan()}
          >
            {busy ? <span className="re-processing-spinner" aria-hidden /> : null}
            Confirm plan
          </button>
          <p>Nothing is sent to any supplier from this step.</p>
        </div>
      ) : null}
    </div>
  );
}

function ClarificationCard({
  questions,
  answers,
  facts,
  onAnswer,
  onSchedule,
  onUpdate,
  phase,
  busy,
}: {
  questions: ReturnType<typeof projectPlan>["questions"];
  answers: PlanSession["answers"];
  facts: ReturnType<typeof projectPlan>["facts"];
  onAnswer: (id: QuestionId, value: string) => void;
  onSchedule: (next: Partial<PlanAnswers>) => void;
  onUpdate: () => void;
  phase: PlanSession["phase"];
  busy: boolean;
}) {
  const invalid = rangeError(answers);
  return (
    <div className="re-clarify-card">
      <div className="re-clarify-card-head">
        <span className="re-clarify-kicker">
          CLARIFICATION · {questions.length} OF {questions.length}
        </span>
        <span className="re-clarify-blocking">Blocking</span>
      </div>
      <div className="re-clarify-fields">
        {questions.map((question) =>
          question.id === "dates" ? (
            <ClarifyScheduleFields
              key={question.id}
              answers={answers}
              facts={facts}
              onChange={onSchedule}
            />
          ) : (
            <div key={question.id} className="re-clarify-field">
              <label className="re-clarify-label" htmlFor={`clarify-${question.id}`}>
                {question.label}
              </label>
              {question.kind === "choice" ? (
                <div className="re-clarify-choices" role="group" aria-label={question.label}>
                  {(question.choices ?? []).map((choice) => {
                    const selected = answers.carNeed === choice.id;
                    return (
                      <button
                        key={choice.id}
                        type="button"
                        className={`re-clarify-choice itaa-focus-ring${selected ? " is-on" : ""}`}
                        aria-pressed={selected}
                        onClick={() => onAnswer("carNeed", choice.id)}
                      >
                        {choice.label}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <input
                  id={`clarify-${question.id}`}
                  className="re-clarify-text itaa-focus-ring"
                  value={answers.departureAirport}
                  onChange={(event) => onAnswer(question.id, event.target.value)}
                />
              )}
              <p className="re-clarify-why">
                {question.why}
                {question.unblocks.length > 0 ? ` Unblocks ${question.unblocks.join(", ")}.` : ""}
              </p>
            </div>
          ),
        )}
      </div>
      {phase === "clarify" ? (
        <button
          type="button"
          className="re-primary itaa-focus-ring re-clarify-update"
          disabled={invalid !== "" || busy}
          aria-busy={busy || undefined}
          onClick={onUpdate}
        >
          {busy ? <span className="re-processing-spinner" aria-hidden /> : null}
          Answer and update plan
        </button>
      ) : null}
      <p className="re-clarify-skip">
        Skipping is fine. Unanswered fields become missing details on the affected tasks.
      </p>
    </div>
  );
}

function TaskCard({
  task,
  ready,
  onRemove,
  onAccept,
  onBeginParking,
  onBeginDemo,
  executableParking,
  executableRental,
  executableEnts,
}: {
  task: PlanTask;
  ready: boolean;
  onRemove: () => void;
  onAccept: () => void;
  onBeginParking: () => void;
  onBeginDemo: (kind: "rental" | "ents") => void;
  executableParking: boolean;
  executableRental: boolean;
  executableEnts: boolean;
}) {
  const unconfirmed = !task.accepted;
  const inferredOrProposed = task.provenance === "inferred" || task.provenance === "proposed";
  return (
    <article className={`re-clarify-task${task.provenance === "proposed" ? " is-proposed" : ""}`}>
      <div className="re-clarify-task-row">
        <span className="re-code">{task.code}</span>
        <span className="re-clarify-task-title">{task.title}</span>
        <span className={`re-clarify-task-status is-${task.accepted ? "confirmed" : "pending"}`}>
          {taskStatusLabel(task)}
        </span>
        <span className={`re-clarify-provenance is-${task.provenance}`}>
          {provenanceLabel(task.provenance)}
        </span>
      </div>
      <p className="re-clarify-task-detail">{task.detail}</p>
      <p className="re-clarify-task-why">{provenanceNote(task.provenance)}</p>
      <p className={`re-clarify-support is-${task.support}`}>{task.supportLabel}</p>
      <div className="re-clarify-task-actions">
        {unconfirmed && inferredOrProposed && !ready ? (
          <button type="button" className="re-ghost-fill itaa-focus-ring" onClick={onAccept}>
            {task.provenance === "proposed" ? "Add to plan" : "Confirm task"}
          </button>
        ) : null}
        {!ready && unconfirmed && inferredOrProposed ? (
          <button type="button" className="re-ghost itaa-focus-ring" onClick={onRemove}>
            Not needed
          </button>
        ) : null}
        {executableParking ? (
          <button type="button" className="re-primary itaa-focus-ring" onClick={onBeginParking}>
            Begin parking requirement
          </button>
        ) : null}
        {executableRental ? (
          <button
            type="button"
            className="re-ghost-fill itaa-focus-ring"
            onClick={() => onBeginDemo("rental")}
          >
            Open rental demonstration
          </button>
        ) : null}
        {executableEnts ? (
          <button
            type="button"
            className="re-ghost-fill itaa-focus-ring"
            onClick={() => onBeginDemo("ents")}
          >
            Open entertainment demonstration
          </button>
        ) : null}
        {ready && task.support === "unsupported" ? (
          <span className="re-clarify-no-exec">No supplier execution in this build.</span>
        ) : null}
      </div>
    </article>
  );
}

function kindLabel(kind: TaskKind): string {
  if (kind === "parking") {
    return "airport parking";
  }
  if (kind === "rental") {
    return "rental car";
  }
  return "entertainment";
}

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() =>
    typeof window.matchMedia === "function"
      ? window.matchMedia("(max-width: 1179px)").matches
      : false,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const media = window.matchMedia("(max-width: 1179px)");
    const onChange = () => setNarrow(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

function fieldValue(domain: AgentDomainState, id: string): string {
  const held = domain.fields[id];
  if (held === undefined || held.value === undefined || held.value === null) {
    return "";
  }
  if (Array.isArray(held.value)) {
    return held.value.join(", ");
  }
  return String(held.value);
}

function ParkingDomainPane({
  domain,
  busy,
  onEdit,
}: {
  domain: AgentDomainState;
  busy: boolean;
  onEdit: (fieldId: string, value: string) => void;
}) {
  const offers = domain.offerSet.snapshot?.offers ?? [];
  const stale = domain.offerSet.stale;
  return (
    <article className="re-domain-pane">
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">PARKING</span>
        <span className={`re-clarify-status${domain.completeness === "offers" ? " is-ready" : ""}`}>
          {stale ? "Stale offers" : domain.completeness}
        </span>
      </div>
      <p className="re-clarify-task-why">
        Provenance {domain.provenance}. Direct edits and conversation use the same validator.
      </p>
      <dl className="re-domain-fields">
        {["airportCode", "start", "end", "vehicleClass", "covered"].map((id) => (
          <div key={id} className="re-domain-field">
            <dt>{id}</dt>
            <dd>
              <input
                key={`${id}-${fieldValue(domain, id)}`}
                className="re-clarify-text itaa-focus-ring"
                defaultValue={fieldValue(domain, id)}
                disabled={busy}
                aria-label={`Parking ${id}`}
                onBlur={(event) => {
                  const next = event.target.value.trim();
                  if (next !== fieldValue(domain, id)) {
                    onEdit(id, next);
                  }
                }}
              />
              <span className="re-domain-src">
                {domain.fields[id]?.provenance ?? "missing"} · {domain.fields[id]?.source ?? "—"}
              </span>
            </dd>
          </div>
        ))}
      </dl>
      {domain.missing.length > 0 ? (
        <p className="re-clarify-hold">Missing: {domain.missing.join(", ")}</p>
      ) : null}
      {stale ? (
        <p className="re-clarify-hold">
          Parking offers are stale. Updated offers require a new authorization.
        </p>
      ) : null}
      {offers.length > 0 ? (
        <ol className="re-domain-offers">
          {offers.map((offer) => (
            <li key={offer.offerId}>
              Rank {offer.rank}
              {offer.recommended ? " · recommended" : ""}
              {offer.currency && offer.totalMinor !== undefined
                ? ` · ${offer.currency} ${(offer.totalMinor / 100).toFixed(2)}`
                : ""}
              {stale ? " · not selectable" : ""}
            </li>
          ))}
        </ol>
      ) : null}
    </article>
  );
}

function RentalDomainPane({ domain }: { domain: AgentDomainState }) {
  return (
    <article className="re-domain-pane">
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">RENTAL</span>
        <span className="re-clarify-status">demonstration</span>
      </div>
      <p className="re-clarify-task-why">Demonstration only. No supplier ranking in this build.</p>
      <p className="re-clarify-task-detail">
        When: {fieldValue(domain, "when") || "—"} · Class: {fieldValue(domain, "class") || "—"}
      </p>
    </article>
  );
}
