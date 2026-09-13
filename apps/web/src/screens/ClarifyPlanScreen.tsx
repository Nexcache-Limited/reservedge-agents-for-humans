import {
  Fragment,
  useEffect,
  useId,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { flushSync } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { ClosedApiError } from "../api/errors.js";
import type {
  AgentDomainState,
  AgentExperienceSearch,
  AgentFlightSearch,
  AgentPendingSearchAuthorization,
  AgentStaySearch,
  ItaaApi,
} from "../api/types.js";
import { formatMoney, supplierDisplayName } from "../fixtures/golden.js";
import {
  AGENT_FAILURE_COPY,
  failAgentSession,
  mergeAgentView,
  projectAgentSession,
  syncPlanSessionWithSnapshot,
  turnAnswersFromSession,
  withUpdatingActivity,
} from "../intent-first/agent.js";
import {
  acceptTaskOverride,
  addTaskOverride,
  mergeSchedule,
  normalizeAnswers,
  parkingNeedsTimes,
  parkingPrefill,
  projectPlan,
  provenanceLabel,
  provenanceNote,
  refinementPinKind,
  removeTaskOverride,
  sortPlanTasks,
  supportedAddableKinds,
  taskStatusLabel,
  type ContextChip,
  type ExtractedFacts,
  type PlanAnswers,
  type PlanSession,
  type PlanTask,
  type QuestionId,
  type TaskKind,
} from "../intent-first/plan.js";
import { formatHumanRange, rangeError } from "../intent-first/schedule.js";
import { hideDesktopWorkspaceChat } from "../reservedge/plan-inbox.js";
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
  const blocking = projection.questions.filter((question) => question.id !== "helpWith");
  const dateCardOnly =
    blocking.length > 0 &&
    blocking.every((question) => question.id === "dates") &&
    !parkingNeedsTimes(projection.facts);
  const cardQuestions = dateCardOnly ? [] : blocking;
  const ready = session.phase === "ready";
  const gathering = session.phase === "clarify";
  const narrow = useNarrow();
  const failed = session.agent?.failed === true;
  const agentBacked = session.agent !== undefined && session.agent !== null;
  const visibleTasks = sortPlanTasks(
    gathering
      ? projection.tasks.filter((task) => task.provenance === "explicit")
      : projection.tasks,
    refinementPinKind(session),
  );

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

  async function holdStay(offerId: string) {
    if (!session.agent || busy || failed) {
      return;
    }
    flushSync(() => {
      setBusy(true);
      setPlanSession(withUpdatingActivity(session));
    });
    try {
      const view = await api.postAgentTurn(session.agent.sessionId, {
        tool: "book_stay_sandbox",
        payload: { offerId },
      });
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

  const parkingDomain = session.agent?.domains?.parking;
  const rentalDomain = session.agent?.domains?.rental;
  const localConfirmChrome =
    !agentBacked ||
    session.agent?.fallback === true ||
    (session.agent?.pendingSearchAuthorization == null &&
      session.agent?.staySearch == null &&
      session.agent?.experienceSearch == null &&
      session.agent?.flightSearch == null &&
      parkingDomain == null);
  const addable = supportedAddableKinds(projection.tasks, {
    liveAgent: agentBacked && session.agent?.fallback !== true && !localConfirmChrome,
  });
  const parkingWorkspace = parkingDomain != null;
  const composerHandoff = !agentBacked || !parkingWorkspace;
  const executableParking =
    ready && composerHandoff && projection.tasks.some((task) => task.kind === "parking");
  const executableRental =
    ready && composerHandoff && projection.tasks.some((task) => task.kind === "rental");
  const executableEnts =
    ready && composerHandoff && projection.tasks.some((task) => task.kind === "ents");

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

      {narrow || !hideDesktopWorkspaceChat(session) ? (
        <AgentChatPanel
          api={api}
          session={session}
          setPlanSession={setPlanSession}
          fallbackObjective={fallbackObjective}
          hidden={narrow && session.pane !== "conversation"}
          headingId={headingId}
        >
          {gathering && cardQuestions.length > 0 && parkingDomain == null ? (
            <ClarificationCard
              questions={cardQuestions}
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
      ) : null}

      <section
        className="re-clarify-plan"
        hidden={narrow && session.pane !== "plan"}
        aria-labelledby="clarify-plan-heading"
      >
        <div className="re-clarify-plan-head">
          <span className="re-clarify-kicker">WORKSPACE</span>
          <span
            className={`re-clarify-status${ready ? " is-ready" : gathering ? " is-gathering" : ""}`}
          >
            {session.agent?.pendingSearchAuthorization
              ? "Ready to search"
              : ready
                ? "Confirmed"
                : gathering
                  ? "Gathering"
                  : "Forming"}
          </span>
        </div>
        <h2 className="re-h2 re-clarify-plan-title" id="clarify-plan-heading">
          {projection.title}
        </h2>
        {agentBacked ? (
          <p className="re-clarify-persist">
            Session state is process-local and non-durable; it is not persisted to durable storage.
          </p>
        ) : null}
        <SharedContextStrip chips={hideDesktopWorkspaceChat(session) ? [] : projection.chips} />
        <p className="re-lead re-clarify-plan-lead">
          {gathering && parkingDomain == null
            ? "I'll assemble booking tasks after these answers. No domain is selected yet."
            : projection.summary}
        </p>
        {visibleTasks.length === 0 &&
        !(
          parkingDomain != null &&
          (parkingDomain.accepted === true || parkingDomain.provenance === "explicit")
        ) &&
        !(
          rentalDomain != null &&
          (rentalDomain.accepted === true || rentalDomain.provenance === "explicit")
        ) &&
        session.agent?.staySearch == null &&
        session.agent?.experienceSearch == null ? (
          <div className="re-clarify-hold">
            <p>Booking tasks are not selected yet.</p>
            <p>
              Answer in chat first. Domains appear only when you name them. Nothing is sent to any
              supplier from this step.
            </p>
          </div>
        ) : (
          <div className="re-clarify-tasks">
            {visibleTasks.map((task) => {
              const stayLane =
                task.kind === "hotel" &&
                agentBacked &&
                (task.provenance === "explicit" || session.agent?.staySearch != null);
              const experienceLane =
                task.kind === "experience" &&
                agentBacked &&
                (task.provenance === "explicit" || session.agent?.experienceSearch != null);
              const flightLane = task.kind === "flight" && agentBacked;
              const parkingLane =
                task.kind === "parking" &&
                parkingDomain != null &&
                (parkingDomain.accepted === true || parkingDomain.provenance === "explicit");
              const rentalLane =
                task.kind === "rental" &&
                rentalDomain != null &&
                (rentalDomain.accepted === true || rentalDomain.provenance === "explicit");
              return (
                <Fragment key={task.id}>
                  {stayLane ? (
                    <StayDomainLane
                      task={task}
                      search={session.agent?.staySearch ?? null}
                      facts={projection.facts}
                      pending={session.agent?.pendingSearchAuthorization ?? null}
                      busy={busy}
                      onSandboxHold={holdStay}
                    />
                  ) : experienceLane ? (
                    <ExperienceDomainLane
                      task={task}
                      search={session.agent?.experienceSearch ?? null}
                      destination={projection.facts.destination}
                      pending={session.agent?.pendingSearchAuthorization ?? null}
                    />
                  ) : flightLane ? (
                    <FlightDomainLane
                      task={task}
                      search={session.agent?.flightSearch ?? null}
                      facts={projection.facts}
                      pending={session.agent?.pendingSearchAuthorization ?? null}
                      ready={ready}
                      onRemove={() => removeTask(task.id)}
                      onAccept={() => acceptTask(task.id)}
                    />
                  ) : parkingLane && parkingDomain ? (
                    <ParkingDomainPane
                      task={task}
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
                          .catch(() =>
                            setPlanSession(failAgentSession(session, AGENT_FAILURE_COPY)),
                          );
                      }}
                      onTake={(offerId) => {
                        if (!session.agent) {
                          return;
                        }
                        const intentId =
                          typeof parkingDomain.intentId === "string" ? parkingDomain.intentId : "";
                        const offer = (parkingDomain.offerSet.snapshot?.offers ?? []).find(
                          (item) => item.offerId === offerId,
                        );
                        if (intentId.startsWith("pi_") && offer !== undefined) {
                          void api
                            .intakeAccept(intentId, { offerId, offerVersion: offer.version })
                            .then((next) =>
                              setPlanSession(syncPlanSessionWithSnapshot(session, next)),
                            )
                            .catch(() =>
                              setPlanSession(failAgentSession(session, AGENT_FAILURE_COPY)),
                            );
                          return;
                        }
                        void api
                          .grantAgentSession(session.agent.sessionId, {
                            gate: "A3",
                            domain: "parking",
                            offerId,
                          })
                          .then((view) => setPlanSession(mergeAgentView(session, view)))
                          .catch(() =>
                            setPlanSession(failAgentSession(session, AGENT_FAILURE_COPY)),
                          );
                      }}
                    />
                  ) : rentalLane ? (
                    <RentalDomainPane domain={rentalDomain} task={task} />
                  ) : (
                    <TaskCard
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
                  )}
                </Fragment>
              );
            })}
            {gathering && !agentBacked ? (
              <p className="re-clarify-hold">
                Other booking tasks wait until these answers are in. Nothing is sent to any supplier
                from this step.
              </p>
            ) : null}
          </div>
        )}
        {session.agent?.staySearch && !visibleTasks.some((task) => task.kind === "hotel") ? (
          <StayDomainLane
            task={
              visibleTasks.find((task) => task.kind === "hotel") ?? {
                id: "task-hotel",
                kind: "hotel",
                code: "Ht",
                title: "Hotel",
                detail: "Stay search",
                provenance: "explicit",
                support: "sandbox_search",
                supportLabel: "Sandbox hotel search",
                accepted: true,
              }
            }
            search={session.agent.staySearch}
            facts={projection.facts}
            pending={session.agent?.pendingSearchAuthorization ?? null}
            busy={busy}
            onSandboxHold={holdStay}
          />
        ) : null}
        {session.agent?.experienceSearch &&
        !visibleTasks.some((task) => task.kind === "experience") ? (
          <ExperienceDomainLane
            task={{
              id: "task-experience",
              kind: "experience",
              code: "Ex",
              title: "Experience",
              detail: "Experience search",
              provenance: "explicit",
              support: "sandbox_search",
              supportLabel: "Sandbox experience search",
              accepted: true,
            }}
            search={session.agent.experienceSearch}
            destination={projection.facts.destination}
            pending={session.agent?.pendingSearchAuthorization ?? null}
          />
        ) : null}
        {session.agent?.flightSearch && !visibleTasks.some((task) => task.kind === "flight") ? (
          <FlightDomainLane
            task={{
              id: "task-flight",
              kind: "flight",
              code: "Fl",
              title: "Flight",
              detail: "Flight search",
              provenance: "explicit",
              support: "sandbox_search",
              supportLabel: "Sandbox flight search",
              accepted: true,
            }}
            search={session.agent.flightSearch}
            facts={projection.facts}
            pending={session.agent?.pendingSearchAuthorization ?? null}
          />
        ) : null}
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
        {ready ? (
          <p className="re-clarify-confirmed" role="status">
            Plan confirmed. Stay and experience results appear below when those tasks are on the
            plan. Keep talking to add parking or a rental.
          </p>
        ) : failed ? (
          <p className="re-clarify-waiting">Could not confirm this plan from a failed step.</p>
        ) : localConfirmChrome &&
          (session.phase === "forming" || blocking.length === 0) &&
          !narrow ? (
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
        ) : localConfirmChrome && session.phase === "clarify" && blocking.length > 0 ? (
          <p className="re-clarify-waiting">
            {dateCardOnly
              ? "Reply with your dates in the chat. Confirm becomes available after that."
              : "Answer and update the plan before confirming. No task execution starts yet."}
          </p>
        ) : null}
      </section>
      {narrow &&
      localConfirmChrome &&
      !ready &&
      !failed &&
      (session.phase === "forming" || blocking.length === 0) ? (
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
          <p>Stay search is research only. Parking still waits for A1–A4.</p>
        </div>
      ) : null}
    </div>
  );
}

function SharedContextStrip({ chips }: { chips: ContextChip[] }) {
  if (chips.length === 0) {
    return null;
  }
  return (
    <div className="re-workspace-context">
      <div className="re-clarify-kicker">SHARED BOOKING CONTEXT</div>
      <div className="re-clarify-chips">
        {chips.map((chip) => (
          <span key={chip.id} className="re-clarify-chip">
            {chip.label}
            <span
              className={`re-clarify-chip-src is-${chip.source.replace(" ", "-").toLowerCase()}`}
            >
              {chip.source}
            </span>
          </span>
        ))}
      </div>
      <p className="re-clarify-footnote">
        Shared facts never travel as one payload. Each domain sends only its minimised envelope.
      </p>
    </div>
  );
}

function StayDomainLane({
  task,
  search,
  facts,
  pending,
  busy,
  onSandboxHold,
}: {
  task: PlanTask;
  search: AgentStaySearch | null;
  facts: ExtractedFacts;
  pending: AgentPendingSearchAuthorization | null;
  busy: boolean;
  onSandboxHold: (offerId: string) => Promise<void>;
}) {
  const destReady = facts.destination.trim() !== "";
  const datesReady = facts.startDate.trim() !== "" && facts.endDate.trim() !== "";
  const requirementReady = destReady && datesReady;
  const pendingReady = pending?.capabilities.includes("stay.search") === true;
  const status = search
    ? search.stale === true
      ? "stale"
      : search.status === "ok"
        ? "offers"
        : search.status
    : pendingReady
      ? "Ready to search"
      : requirementReady
        ? "Ready"
        : "waiting";
  return (
    <section className={`re-domain-lane${search?.stale === true ? " is-stale" : ""}`}>
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">STAY</span>
        <span className="re-clarify-task-title">{task.title}</span>
        <span className={`re-clarify-provenance is-${task.provenance}`}>
          {provenanceLabel(task.provenance)}
        </span>
        <span className="re-domain-capability">stay.search</span>
        {search ? (
          <span className="re-stay-search-source">{searchSourceLabel(search)}</span>
        ) : (
          <span className={`re-clarify-status${pendingReady ? " is-ready" : ""}`}>{status}</span>
        )}
      </div>
      <div className="re-domain-chips">
        {facts.destination ? <span className="re-fact-chip">{facts.destination}</span> : null}
        {facts.startDate && facts.endDate ? (
          <span className="re-fact-chip">{formatHumanRange(facts.startDate, facts.endDate)}</span>
        ) : null}
      </div>
      {search?.stale === true ? (
        <p className="re-clarify-hold" role="status">
          Hotel results are stale after a stay requirement change. Other domains are unchanged.
        </p>
      ) : null}
      {search ? (
        <StaySearchPanel search={search} busy={busy} onSandboxHold={onSandboxHold} />
      ) : (
        <>
          <p className="re-clarify-task-detail">{task.detail}</p>
          <p className="re-clarify-task-why">{provenanceNote(task.provenance)}</p>
          <p className={`re-clarify-support is-${task.support}`}>{task.supportLabel}</p>
          {requirementReady ? null : (
            <p className="re-clarify-hold">
              Stay search waits until destination and dates are on the stay requirement.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function searchSourceLabel(search: AgentStaySearch): string {
  if (search.source === "sandbox") {
    return "LiteAPI sandbox";
  }
  if (search.source === "fake") {
    return "labelled fake";
  }
  return search.source;
}

function FlightDomainLane({
  task,
  search,
  facts,
  pending,
  ready = false,
  onRemove,
  onAccept,
}: {
  task: PlanTask;
  search: AgentFlightSearch | null;
  facts: ExtractedFacts;
  pending: AgentPendingSearchAuthorization | null;
  ready?: boolean;
  onRemove?: () => void;
  onAccept?: () => void;
}) {
  const pendingReady = pending?.capabilities.includes("flight.search") === true;
  const origin = facts.originCity || facts.departureAirport;
  const dest = facts.destination || facts.destinationAirport;
  const requirementReady =
    origin.trim() !== "" && dest.trim() !== "" && facts.startDate.trim() !== "";
  const unconfirmed = !task.accepted;
  const inferredOrProposed = task.provenance === "inferred" || task.provenance === "proposed";
  const status = search
    ? search.stale === true
      ? "stale"
      : search.status === "ok"
        ? "offers"
        : search.status
    : pendingReady
      ? "Ready to search"
      : task.provenance === "proposed"
        ? "Proposed"
        : requirementReady
          ? "Ready"
          : "waiting";
  return (
    <article
      className={`re-domain-lane re-flight-lane${search?.stale === true ? " is-stale" : ""}`}
    >
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">FLIGHT</span>
        <span className="re-clarify-task-title">{task.title}</span>
        <span className={`re-clarify-provenance is-${task.provenance}`}>
          {provenanceLabel(task.provenance)}
        </span>
        <span className="re-domain-capability">flight.search</span>
        {search ? (
          <span className="re-stay-search-source">{search.source}</span>
        ) : (
          <span className={`re-clarify-status${pendingReady ? " is-ready" : ""}`}>{status}</span>
        )}
      </div>
      <div className="re-domain-chips">
        {origin ? <span className="re-fact-chip">{origin}</span> : null}
        {dest ? <span className="re-fact-chip">{dest}</span> : null}
        {facts.startDate ? <span className="re-fact-chip">{facts.startDate}</span> : null}
      </div>
      {search?.stale === true ? (
        <p className="re-clarify-hold" role="status">
          Flight results are stale after a route or date change. Other domains are unchanged.
        </p>
      ) : null}
      {search ? (
        <FlightSearchPanel search={search} />
      ) : (
        <>
          <p className="re-clarify-task-detail">{task.detail}</p>
          <p className="re-clarify-task-why">{provenanceNote(task.provenance)}</p>
          <p className={`re-clarify-support is-${task.support}`}>{task.supportLabel}</p>
          {task.provenance === "proposed" ? (
            <p className="re-clarify-hold">
              Inactive until you confirm you want flight help. Prefer a departure window or
              direct-only is optional.
            </p>
          ) : requirementReady ? null : (
            <p className="re-clarify-hold">
              Flight search waits until origin, destination, and date are known, then a chat
              confirmation.
            </p>
          )}
          <div className="re-clarify-task-actions">
            {unconfirmed && inferredOrProposed && !ready && onAccept && onRemove ? (
              <>
                <button type="button" className="re-ghost-fill itaa-focus-ring" onClick={onAccept}>
                  {task.provenance === "proposed" ? "Add to plan" : "Confirm task"}
                </button>
                <button type="button" className="re-ghost itaa-focus-ring" onClick={onRemove}>
                  Not needed
                </button>
              </>
            ) : null}
            {ready && task.support === "unsupported" ? (
              <span className="re-clarify-no-exec">No supplier execution in this build.</span>
            ) : null}
          </div>
        </>
      )}
    </article>
  );
}

function FlightSearchPanel({ search }: { search: AgentFlightSearch }) {
  return (
    <article className="re-stay-search re-offer-rail" aria-label={search.label}>
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">{search.label.toUpperCase()}</span>
        <span className="re-stay-search-source">{search.source}</span>
      </div>
      <p className="re-stay-search-lead">{search.buyerSafeMessage}</p>
      {search.status !== "ok" ? (
        <p className="re-clarify-hold" role="status">
          {search.buyerSafeMessage}
        </p>
      ) : (
        <ul className="re-stay-search-list" aria-label="Flight offers, scroll sideways">
          {search.offers.map((offer) => {
            const price = offer.price;
            const amount =
              typeof price?.amountMinor === "number" && price.currency
                ? formatMoney(price.amountMinor, price.currency)
                : (price?.currency ?? "");
            const stops =
              offer.stops === 0 ? "direct" : `${offer.stops} stop${offer.stops === 1 ? "" : "s"}`;
            return (
              <li key={offer.id} className="re-stay-search-item">
                <strong>
                  {offer.origin} → {offer.destination}
                </strong>
                <span>{offer.airline}</span>
                <span>
                  {offer.departure} → {offer.arrival}
                </span>
                <span>
                  {stops}
                  {amount ? ` · ${amount}` : ""}
                  {offer.cabin ? ` · ${offer.cabin}` : ""}
                </span>
                {offer.baggage ? <span>{offer.baggage}</span> : null}
                <span>Sandbox search. Not a ticket.</span>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}

function experienceSourceLabel(search: AgentExperienceSearch): string {
  if (search.source === "sandbox" && search.providerId === "prioticket") {
    return "Prioticket sandbox";
  }
  if (search.source === "sandbox") {
    return "experience sandbox";
  }
  if (search.source === "fake") {
    return "labelled fake";
  }
  return search.source;
}

function ExperienceDomainLane({
  task,
  search,
  destination,
  pending,
}: {
  task: PlanTask;
  search: AgentExperienceSearch | null;
  destination: string;
  pending: AgentPendingSearchAuthorization | null;
}) {
  const destReady = destination.trim() !== "";
  const pendingReady = pending?.capabilities.includes("experience.search") === true;
  const status = search
    ? search.stale === true
      ? "stale"
      : "offers"
    : pendingReady
      ? "Ready to search"
      : destReady
        ? "Ready"
        : "waiting";
  return (
    <section
      className={`re-domain-lane re-experience-lane${search?.stale === true ? " is-stale" : ""}`}
    >
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">EXPERIENCE</span>
        <span className="re-clarify-task-title">{task.title}</span>
        <span className={`re-clarify-provenance is-${task.provenance}`}>
          {provenanceLabel(task.provenance)}
        </span>
        <span className="re-domain-capability">experience.search</span>
        {search ? (
          <span className="re-experience-search-source">{experienceSourceLabel(search)}</span>
        ) : (
          <span className={`re-clarify-status${pendingReady ? " is-ready" : ""}`}>{status}</span>
        )}
      </div>
      {destination ? (
        <div className="re-domain-chips">
          <span className="re-fact-chip">{destination}</span>
        </div>
      ) : null}
      {search?.stale === true ? (
        <p className="re-clarify-hold" role="status">
          Experience results are stale after an experience preference change. Other domains are
          unchanged.
        </p>
      ) : null}
      {search ? (
        <ExperienceSearchPanel search={search} />
      ) : (
        <>
          <p className="re-clarify-task-detail">{task.detail}</p>
          <p className="re-clarify-task-why">{provenanceNote(task.provenance)}</p>
          <p className={`re-clarify-support is-${task.support}`}>{task.supportLabel}</p>
          {destReady ? null : (
            <p className="re-clarify-hold">
              Experience search waits until a destination is on the experience requirement.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function ExperienceSearchPanel({ search }: { search: AgentExperienceSearch }) {
  return (
    <article className="re-experience-search re-offer-rail" aria-label={search.label}>
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">{search.label.toUpperCase()}</span>
        <span className="re-experience-search-source">{search.source}</span>
      </div>
      <p className="re-experience-search-lead">{search.buyerSafeMessage}</p>
      {search.status !== "ok" ? (
        <p className="re-clarify-hold" role="status">
          {search.buyerSafeMessage}
        </p>
      ) : (
        <ul className="re-experience-search-list" aria-label="Experience offers, scroll sideways">
          {search.offers.map((offer) => {
            const price = offer.price;
            const amount =
              typeof price?.amountMinor === "number" && price.currency
                ? formatMoney(price.amountMinor, price.currency)
                : (price?.currency ?? "");
            const duration =
              typeof offer.durationMinutes === "number" && offer.durationMinutes > 0
                ? `${offer.durationMinutes} min`
                : "";
            return (
              <li key={offer.id} className="re-experience-search-item">
                {offer.photoUrl ? (
                  <img
                    className="re-experience-search-photo"
                    src={offer.photoUrl}
                    alt=""
                    width={216}
                    height={128}
                  />
                ) : null}
                <strong>{offer.title}</strong>
                <span className="re-experience-category">{offer.category}</span>
                <span>{offer.location}</span>
                <span>
                  {offer.availability || "availability unknown"}
                  {duration ? ` · ${duration}` : ""}
                  {amount ? ` · ${amount}` : ""}
                </span>
                {offer.cancellation ? <span>{offer.cancellation}</span> : null}
                <span>Research only. Not a booking.</span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="re-experience-search-note">
        Prioticket research and availability only. Booking is not enabled in this competition cut.
      </p>
    </article>
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
                        onClick={() => onAnswer(question.id, choice.id)}
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
  if (kind === "experience") {
    return "experience";
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

function formatBuyerInstant(raw: string): string {
  const match = raw.trim().match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
  if (match === null) {
    return raw;
  }
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const month = months[Number(match[2]) - 1] ?? match[2];
  const day = String(Number(match[3]));
  if (match[4] === undefined) {
    return `${day} ${month} ${match[1]}`;
  }
  return `${day} ${month} ${match[1]}, ${match[4]}:${match[5]}`;
}

function fieldDisplay(domain: AgentDomainState, id: string): string {
  const raw = fieldValue(domain, id);
  if ((id === "start" || id === "end") && raw !== "") {
    return formatBuyerInstant(raw);
  }
  return raw;
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

function parkingInstantChip(value: string): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
  if (!match) {
    return value;
  }
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const month = months[Number(match[2]) - 1] ?? match[2];
  const day = String(Number(match[3]));
  if (match[4] && match[5]) {
    return `${day} ${month} ${match[4]}:${match[5]}`;
  }
  return `${day} ${month}`;
}

function ParkingDomainPane({
  task,
  domain,
  busy,
  onEdit,
  onTake,
}: {
  task: PlanTask;
  domain: AgentDomainState;
  busy: boolean;
  onEdit: (fieldId: string, value: string) => void;
  onTake: (offerId: string) => void;
}) {
  const offers = domain.offerSet.snapshot?.offers ?? [];
  const stale = domain.offerSet.stale;
  const [expanded, setExpanded] = useState(false);
  const airport = fieldDisplay(domain, "airportCode");
  const start = fieldValue(domain, "start");
  const end = fieldValue(domain, "end");
  const covered = fieldValue(domain, "covered");
  const vehicle = fieldValue(domain, "vehicleClass");
  return (
    <article className={`re-domain-lane re-domain-pane${stale ? " is-stale" : ""}`}>
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">PARKING</span>
        <span className="re-clarify-task-title">{task.title}</span>
        <span className={`re-clarify-task-status is-${task.accepted ? "confirmed" : "pending"}`}>
          {taskStatusLabel(task)}
        </span>
        <span className={`re-clarify-provenance is-${task.provenance}`}>
          {provenanceLabel(task.provenance)}
        </span>
        <span className="re-domain-capability">parking.search</span>
        <span className="re-sim-label">simulated</span>
        <span
          className={`re-clarify-status${domain.completeness === "offers" || domain.completeness === "ready" ? " is-ready" : ""}`}
        >
          {stale
            ? "Stale offers"
            : domain.completeness === "ready"
              ? "Ready to search"
              : domain.completeness}
        </span>
      </div>
      <p className={`re-clarify-support is-${task.support}`}>{task.supportLabel}</p>
      <p className="re-clarify-task-why">
        Simulated parking path. Conversation is the primary editor. Selection is not a booking.
      </p>
      <div className="re-domain-chips">
        {airport ? <span className="re-fact-chip">{airport}</span> : null}
        {start && end ? (
          <span className="re-fact-chip">
            {parkingInstantChip(start)} → {parkingInstantChip(end)}
          </span>
        ) : null}
        {covered === "preferred" || covered === "required" ? (
          <span className="re-fact-chip">Covered</span>
        ) : covered === "none" ? (
          <span className="re-fact-chip">Uncovered</span>
        ) : null}
        {vehicle ? (
          <span className="re-fact-chip">
            {vehicle.charAt(0).toUpperCase() + vehicle.slice(1)} vehicle
          </span>
        ) : null}
      </div>
      <button
        type="button"
        className="re-domain-edit itaa-focus-ring"
        onClick={() => setExpanded((on) => !on)}
      >
        {expanded ? "Hide details" : "Edit details"}
      </button>
      {expanded ? (
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
      ) : null}
      {domain.missing.length > 0 ? (
        <p className="re-clarify-hold">Missing: {domain.missing.join(", ")}</p>
      ) : null}
      {stale ? (
        <p className="re-clarify-hold">
          Parking offers are stale. Updated offers require a new authorization. Other domains are
          unchanged.
        </p>
      ) : null}
      {offers.length > 0 ? (
        <ul className="re-parking-offer-cards" aria-label="Simulated parking offers">
          {offers.map((offer) => {
            const amount =
              offer.currency && offer.totalMinor !== undefined
                ? formatMoney(offer.totalMinor, offer.currency)
                : "";
            return (
              <li key={offer.offerId} className="re-parking-offer-card">
                <strong>{supplierDisplayName(offer.supplierToken)}</strong>
                <span>
                  {offer.recommended ? "Recommended · " : ""}
                  {offer.simulation ? "simulated" : "labelled"}
                  {amount ? ` · ${amount}` : ""}
                </span>
                {stale ? <span>not selectable</span> : null}
                {offer.recommended && !stale ? (
                  <button
                    type="button"
                    className="re-primary itaa-focus-ring"
                    disabled={busy}
                    onClick={() => onTake(offer.offerId)}
                  >
                    Take this one
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </article>
  );
}

function RentalDomainPane({
  domain,
  task,
}: {
  domain: AgentDomainState | undefined;
  task: PlanTask;
}) {
  return (
    <article className="re-domain-lane re-domain-pane">
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">RENTAL</span>
        <span className="re-clarify-task-title">{task.title}</span>
        <span className="re-domain-capability">rental.search</span>
        <span className="re-clarify-status">no adapter</span>
      </div>
      <p className={`re-clarify-support is-${task.support}`}>{task.supportLabel}</p>
      <p className="re-clarify-task-why">
        Requirement only. No rental inventory adapter is integrated, so no offers are shown and none
        are invented.
      </p>
      <p className="re-clarify-task-detail">
        When: {domain ? fieldValue(domain, "when") || "—" : "—"} · Class:{" "}
        {domain ? fieldValue(domain, "class") || "—" : "—"}
      </p>
    </article>
  );
}

function StaySearchPanel({
  search,
  busy,
  onSandboxHold,
}: {
  search: AgentStaySearch;
  busy: boolean;
  onSandboxHold: (offerId: string) => Promise<void>;
}) {
  const destination = search.query?.destination?.value ?? "";
  const held = search.offers.some((offer) => offer.sandboxHold?.status === "ok");
  return (
    <article className="re-stay-search re-offer-rail" aria-label={search.label}>
      <div className="re-clarify-plan-head">
        <span className="re-clarify-kicker">{search.label.toUpperCase()}</span>
        <span className="re-stay-search-source">{search.source}</span>
      </div>
      <p className="re-stay-search-lead">{search.buyerSafeMessage}</p>
      {search.status !== "ok" ? (
        <p className="re-clarify-hold" role="status">
          {search.buyerSafeMessage}
        </p>
      ) : (
        <ul className="re-stay-search-list" aria-label="Stay offers, scroll sideways">
          {search.offers.map((offer) => {
            const price = offer.price;
            const amount =
              typeof price?.amountMinor === "number" && price.currency
                ? formatMoney(price.amountMinor, price.currency)
                : (price?.currency ?? "");
            const hold = offer.sandboxHold;
            return (
              <li key={offer.id} className="re-stay-search-item">
                {offer.photoUrl ? (
                  <img
                    className="re-stay-search-photo"
                    src={offer.photoUrl}
                    alt=""
                    width={216}
                    height={128}
                  />
                ) : null}
                <strong>{offer.name}</strong>
                <span>
                  {offer.locality}
                  {destination && offer.locality.toLowerCase().includes(destination.toLowerCase())
                    ? ""
                    : destination
                      ? ` · ${destination}`
                      : ""}
                </span>
                <span>
                  {offer.checkIn} → {offer.checkOut}
                  {amount ? ` · ${amount}` : ""}
                </span>
                {offer.cancellation ? <span>{offer.cancellation}</span> : null}
                <span>{offer.availability || "availability unknown"}</span>
                {hold?.status === "ok" ? (
                  <span className="re-stay-search-hold">
                    Sandbox booked{hold.bookingId ? ` · ${hold.bookingId}` : ""}. Simulated payment.
                    No charge.
                  </span>
                ) : (
                  <button
                    type="button"
                    className="re-chip-btn itaa-focus-ring"
                    disabled={busy}
                    onClick={() => {
                      void onSandboxHold(offer.id);
                    }}
                  >
                    Request sandbox hold
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <p className="re-stay-search-note">
        {held
          ? "Sandbox booking is simulated. No charge. Stopped after book."
          : "Research until a sandbox hold. Not a live reservation."}
      </p>
    </article>
  );
}
