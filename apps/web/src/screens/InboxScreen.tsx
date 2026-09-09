import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { BuyerSessionState, ItaaApi } from "../api/types.js";
import { projectAgentSession } from "../intent-first/agent.js";
import {
  compactSharedContext,
  parkingBookingStarted,
  projectPlan,
  type ContextChip,
} from "../intent-first/plan.js";
import {
  DOMAIN_META,
  FILTERS,
  STATUS_STYLE,
  groupIntents,
  matchesFilter,
  type FilterKey,
  type IntentRow,
} from "../reservedge/inbox.js";
import { snapshotToRow } from "../reservedge/map-snapshot.js";
import {
  mergeAgentInboxRows,
  planSessionToRow,
  showRunningInboxChat,
  withParked,
} from "../reservedge/plan-inbox.js";
import { usePortfolio } from "../reservedge/portfolio.js";
import { readInbox } from "../session/memory.js";
import { AgentChatPanel } from "./AgentChatPanel.js";

function rowsFromMemory(): IntentRow[] {
  return readInbox().map((card) =>
    snapshotToRow({
      intentId: card.intentId,
      state: card.state as BuyerSessionState,
      airport: card.airport,
      updatedAt: card.updatedAt,
    }),
  );
}

export function InboxScreen({
  api,
  selectedId,
  onSelect,
}: {
  api: ItaaApi;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    intents,
    setIntents,
    planSession,
    setPlanSession,
    parkedSessions,
    setParkedSessions,
    setObjective,
    objective,
  } = usePortfolio();
  const rows = useMemo(
    () =>
      mergeAgentInboxRows(intents, [
        planSessionToRow(planSession),
        ...parkedSessions.map((item) => planSessionToRow(item)),
      ]),
    [intents, parkedSessions, planSession],
  );
  const [filter, setFilter] = useState<FilterKey>("all");
  const [source, setSource] = useState<"seed" | "api" | "memory">("seed");
  const switchedToRunning = useRef("");
  const switchedToHistory = useRef("");
  const liveRow = planSessionToRow(planSession);
  const runningChat = filter === "running" && showRunningInboxChat(planSession);

  useEffect(() => {
    if (liveRow?.status === "done") {
      const doneId = liveRow.id;
      if (switchedToHistory.current !== doneId) {
        switchedToHistory.current = doneId;
        setFilter("history");
      }
      return;
    }
    if (planSession == null) {
      return;
    }
    const startedId = liveRow?.id ?? "";
    if (showRunningInboxChat(planSession)) {
      if (filter === "history" || switchedToRunning.current !== startedId) {
        switchedToRunning.current = startedId;
        setFilter("running");
      }
      return;
    }
    if (filter === "history") {
      setFilter(liveRow?.status === "needs" ? "needs" : "all");
    }
  }, [filter, liveRow?.id, liveRow?.status, planSession]);

  useEffect(() => {
    let cancelled = false;
    api
      .listIntents()
      .then((remote) => {
        if (cancelled) {
          return;
        }
        const combined = [
          ...remote.needsYou,
          ...remote.running,
          ...remote.saved,
          ...remote.history,
        ];
        if (combined.length === 0) {
          const memory = rowsFromMemory();
          if (memory.length > 0) {
            setIntents(memory);
            setSource("memory");
            return;
          }
          return;
        }
        setSource("api");
        setIntents(combined.map(snapshotToRow));
      })
      .catch(() => {
        if (!cancelled) {
          const memory = rowsFromMemory();
          if (memory.length > 0) {
            setIntents(memory);
          }
          setSource("seed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, setIntents]);

  const shown = useMemo(() => rows.filter((row) => matchesFilter(row, filter)), [rows, filter]);
  const cardRows = useMemo(() => {
    if (!runningChat || liveRow == null) {
      return shown;
    }
    return shown.filter((row) => row.id !== liveRow.id);
  }, [liveRow, runningChat, shown]);
  const groups = useMemo(() => groupIntents(cardRows), [cardRows]);
  const needsCount = rows.filter(
    (row) => row.status === "decision" || row.status === "needs",
  ).length;
  const pendingCount = rows.filter((row) => row.status === "pending").length;
  const compact = location.pathname !== "/" && location.pathname !== "/bookings";

  function startNewIntent() {
    setParkedSessions((current) => withParked(current, planSession));
    setPlanSession(null);
    setObjective("");
    switchedToHistory.current = "";
    switchedToRunning.current = "";
    setFilter("all");
    navigate("/intents/new");
  }

  function removeBooking(row: IntentRow) {
    if (!row.canDelete) {
      return;
    }
    setParkedSessions((current) => {
      if (!current.some((item) => planSessionToRow(item)?.id === row.id)) {
        return current;
      }
      return current.filter((item) => planSessionToRow(item)?.id !== row.id);
    });
    if (planSessionToRow(planSession)?.id === row.id) {
      setPlanSession(null);
    }
    setIntents((current) => current.filter((item) => item.id !== row.id));
    if (row.id.startsWith("pi_")) {
      void api.deleteDraft(row.id).then(
        () => undefined,
        () => undefined,
      );
    }
  }

  return (
    <section className="re-list" aria-label="Your bookings">
      <div className="re-list-head">
        <div className="re-list-title-row">
          <h1 className="re-list-title">Bookings</h1>
          <button type="button" className="re-new itaa-focus-ring" onClick={startNewIntent}>
            New intent
          </button>
        </div>
        <p className="re-list-meta" data-source={source}>
          <span className="re-list-meta-web">
            {needsCount} need you · {pendingCount} pending
          </span>
          <span className="re-list-meta-mobile">
            {needsCount} waiting on you · {pendingCount} paused
          </span>
        </p>
        <div className="re-filter-row" role="tablist" aria-label="Intent filters">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={filter === item.key}
              className={`re-filter itaa-focus-ring${filter === item.key ? " is-on" : ""}`}
              onClick={() => {
                setFilter(item.key);
                if (item.key === "running" && liveRow?.status === "running") {
                  onSelect(liveRow.id);
                }
                if (item.key === "needs" && liveRow?.status === "needs") {
                  onSelect(liveRow.id);
                }
                if (
                  item.key === "pending" &&
                  (liveRow?.status === "pending" || liveRow?.status === "draft")
                ) {
                  onSelect(liveRow.id);
                }
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <BookingSharedContext />
      <div className="re-list-body">
        {runningChat && planSession != null ? (
          <div className="re-list-chat">
            <AgentChatPanel
              api={api}
              session={planSession}
              setPlanSession={setPlanSession}
              fallbackObjective={objective}
              compact
            />
          </div>
        ) : null}
        {groups.map((group) => (
          <div key={group.key}>
            <div className="re-day">{group.label}</div>
            {group.items.map((row) => (
              <IntentCard
                key={row.id}
                row={row}
                selected={row.id === selectedId && !compact ? true : row.id === selectedId}
                onOpen={() => onSelect(row.id)}
                onDelete={() => removeBooking(row)}
              />
            ))}
          </div>
        ))}
        {cardRows.length === 0 && !runningChat ? (
          <div className="re-empty">
            <div className="re-empty-title">Nothing here.</div>
            <p>No intents match this filter.</p>
            <button
              type="button"
              className="re-new re-new-empty itaa-focus-ring"
              onClick={startNewIntent}
            >
              New intent
            </button>
          </div>
        ) : null}
        <button type="button" className="re-new-mobile itaa-focus-ring" onClick={startNewIntent}>
          New intent
        </button>
      </div>
    </section>
  );
}

function BookingSharedContext() {
  const { planSession } = usePortfolio();
  if (planSession == null) {
    return null;
  }
  const projection =
    planSession.agent != null ? projectAgentSession(planSession) : projectPlan(planSession);
  const parking = planSession.agent?.domains?.parking;
  if (parkingBookingStarted(parking)) {
    const line = compactSharedContext(projection.facts, parking);
    if (line === "") {
      return null;
    }
    return (
      <div className="re-list-context is-compact">
        <div className="re-clarify-kicker">SHARED CONTEXT</div>
        <p className="re-list-context-line">{line}</p>
      </div>
    );
  }
  const gathering = planSession.phase === "clarify";
  const chips: ContextChip[] = gathering
    ? projection.chips.filter((chip) => chip.source !== "INFERRED")
    : projection.chips;
  if (chips.length === 0) {
    return null;
  }
  return (
    <div className="re-list-context">
      <div className="re-clarify-kicker">SHARED CONTEXT</div>
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
        Shared context never travels as one payload. Each task takes only the fields its own
        suppliers need.
      </p>
    </div>
  );
}

function IntentCard({
  row,
  selected,
  onOpen,
  onDelete,
}: {
  row: IntentRow;
  selected: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const style = STATUS_STYLE[row.status];
  return (
    <div className={`re-row${selected ? " is-selected" : ""}`}>
      <button type="button" className="re-row-open itaa-focus-ring" onClick={onOpen}>
        <div className="re-row-top">
          <span className="re-code">{DOMAIN_META[row.domain].code}</span>
          <span className="re-pill" style={{ background: style.bg, color: style.fg }}>
            {row.pillLabel ?? style.label}
          </span>
          <span className={`re-origin${row.id.startsWith("pi_") ? " re-origin-live" : ""}`}>
            {row.id.startsWith("pi_") ? "Live simulation" : "Demonstration"}
          </span>
          <span className="re-row-date">{row.date}</span>
        </div>
        <div className="re-row-title">{row.title}</div>
        <div className="re-row-sub">{row.sub}</div>
        <div className="re-row-date-mobile">{row.date}</div>
      </button>
      {row.canDelete ? (
        <button
          type="button"
          className="re-row-del itaa-focus-ring"
          title="Delete this intent"
          aria-label={`Delete ${row.title}`}
          onClick={onDelete}
        >
          ✕
        </button>
      ) : null}
    </div>
  );
}

export function InboxWelcome({ selected }: { selected: IntentRow | null }) {
  if (selected === null) {
    return (
      <div className="re-welcome">
        <p>Select an intent from the list, or start a new one.</p>
      </div>
    );
  }
  const style = STATUS_STYLE[selected.status];
  const live = selected.status !== "done" && selected.status !== "cancelled";
  const pending = selected.status === "pending" || selected.status === "draft";
  const offers = selected.status === "decision" || selected.status === "done";
  const research = selected.status === "running";
  const activeTab = offers ? "Offers" : research ? "Research" : "Request";
  return (
    <div className="re-intent-landing">
      <div className="re-status-card">
        <div className="re-status-id">
          <span className="re-code">{DOMAIN_META[selected.domain].code}</span>
          <span className="re-pill" style={{ background: style.bg, color: style.fg }}>
            {style.label}
          </span>
        </div>
        <span className="re-status-step">{selected.step}</span>
        <div className="re-status-actions">
          {pending ? (
            <button type="button" className="re-ghost re-ghost-fill itaa-focus-ring">
              Resume
            </button>
          ) : null}
          {live ? (
            <>
              <button type="button" className="re-ghost itaa-focus-ring">
                Keep pending
              </button>
              <button type="button" className="re-ghost itaa-focus-ring">
                Modify intent
              </button>
              <button type="button" className="re-ghost re-ghost-danger itaa-focus-ring">
                Cancel intent
              </button>
            </>
          ) : (
            <span className="re-status-note">Kept in history · read-only</span>
          )}
        </div>
      </div>
      <div className="re-intent-tabs" role="tablist" aria-label="Intent workspace">
        {["Request", "Research", "Offers", "Activity"].map((label) => (
          <button
            key={label}
            type="button"
            role="tab"
            aria-selected={label === activeTab}
            className={`re-intent-tab itaa-focus-ring${label === activeTab ? " is-on" : ""}`}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
