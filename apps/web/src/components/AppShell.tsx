import { useEffect, useMemo, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import type { ItaaApi } from "../api/types.js";
import { ReservedgeMark, SimChip } from "../reservedge/Mark.js";
import { SEED_INTENTS, type IntentRow } from "../reservedge/inbox.js";
import {
  isLiveChatRow,
  mergeAgentInboxRows,
  parkPlanSession,
  parkingHistoryRow,
  planSessionToRow,
} from "../reservedge/plan-inbox.js";
import { PortfolioContext, usePortfolio } from "../reservedge/portfolio.js";
import type { PlanSession } from "../intent-first/plan.js";
import { domainById, listDomains } from "../reservedge/registry.js";
import { InboxScreen } from "../screens/InboxScreen.js";

const RAIL = [
  { to: "/", label: "Intent", end: true, key: "intents" },
  { to: "/activity", label: "Activity", key: "activity" },
  { to: "/prefs", label: "Preferences", key: "prefs" },
  { to: "/data", label: "Privacy & data", key: "data" },
  { to: "/plan", label: "Account & plan", key: "plan" },
] as const;

const TABS = [
  { to: "/", label: "Intent", end: true },
  { to: "/bookings", label: "Booking Chats", end: true },
  { to: "/activity", label: "Activity", end: false },
] as const;

export function AppShell({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="re-app" data-route="workspace">
      <a className="itaa-skip itaa-focus-ring" href="#main">
        Skip to main content
      </a>
      <ReservedgeRail needsCount={0} />
      <MobileAppBar title={title} meta="" showBack showMark={false} backTo="/" />
      <div className="re-columns">
        <div className="re-detail">
          <DetailHeader title={title} meta="" />
          <main id="main" className="re-detail-body" tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>
      <MobileTabs />
    </div>
  );
}

export function PortfolioLayout({ api }: { api: ItaaApi }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [intents, setIntents] = useState(SEED_INTENTS);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [objective, setObjective] = useState("");
  const [planSession, setPlanSession] = useState<PlanSession | null>(null);
  const [parkedSessions, setParkedSessions] = useState<PlanSession[]>([]);
  const inbox = location.pathname === "/bookings";
  const selected = useMemo(
    () => intents.find((row) => row.id === selectedId) ?? null,
    [intents, selectedId],
  );
  useEffect(() => {
    const parts = location.pathname.split("/");
    if (
      parts[1] === "intents" &&
      parts[2] !== undefined &&
      parts[2] !== "new" &&
      parts[2] !== "clarify"
    ) {
      setSelectedId(parts[2]);
    }
    if (location.pathname === "/" || location.pathname === "/intents/new") {
      setSelectedId(null);
    }
  }, [location.pathname]);
  useEffect(() => {
    const agentRows = [
      planSessionToRow(planSession),
      parkingHistoryRow(planSession),
      ...parkedSessions.map((item) => planSessionToRow(item)),
    ];
    if (agentRows.every((row) => row == null)) {
      return;
    }
    setIntents((current) => mergeAgentInboxRows(current, agentRows));
    const row = planSessionToRow(planSession);
    if (location.pathname === "/intents/clarify" && row != null) {
      setSelectedId(row.id);
    }
  }, [location.pathname, parkedSessions, planSession, setIntents]);
  const header = headerFor(location.pathname, selected, planSession);
  const needsCount = intents.filter(
    (row) => row.status === "decision" || row.status === "needs",
  ).length;

  function activateParked(id: string): boolean {
    const parked = parkedSessions.find((item) => planSessionToRow(item)?.id === id);
    if (parked == null) {
      return false;
    }
    const currentId = planSessionToRow(planSession)?.id;
    setParkedSessions((current) => {
      const rest = current.filter((item) => planSessionToRow(item)?.id !== id);
      if (planSession == null || currentId === id) {
        return rest;
      }
      return [parkPlanSession(planSession), ...rest];
    });
    const active = { ...parked };
    delete active.shelf;
    setPlanSession(active);
    return true;
  }

  function selectIntent(id: string) {
    const restored = activateParked(id);
    setSelectedId(id);
    if (isLiveChatRow(planSession, id) || restored) {
      navigate("/intents/clarify");
      return;
    }
    if (id.startsWith("pi_")) {
      navigate(`/intents/${id}`);
      return;
    }
    const narrow =
      typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1179px)").matches;
    if (narrow) {
      navigate(`/intents/${id}`);
      return;
    }
    navigate("/bookings");
  }

  return (
    <PortfolioContext.Provider
      value={{
        intents,
        setIntents,
        selectedId,
        setSelectedId,
        objective,
        setObjective,
        planSession,
        setPlanSession,
        parkedSessions,
        setParkedSessions,
      }}
    >
      <div className="re-app" data-route={inbox ? "inbox" : "workspace"}>
        <a className="itaa-skip itaa-focus-ring" href="#main">
          Skip to main content
        </a>
        <ReservedgeRail needsCount={needsCount} />
        <MobileAppBar
          title={
            composeHome(location.pathname, selected)
              ? "New intent"
              : inbox
                ? "Booking Chats"
                : header.title
          }
          meta={composeHome(location.pathname, selected) ? "" : inbox ? "" : header.meta}
          showBack={!composeHome(location.pathname, selected)}
          showMark={composeHome(location.pathname, selected)}
          backTo={backTarget(location.pathname)}
        />
        <div className="re-columns">
          <InboxScreen api={api} selectedId={selectedId} onSelect={selectIntent} />
          <div className="re-detail">
            <DetailHeader title={header.title} meta={header.meta} />
            <main id="main" className="re-detail-body" tabIndex={-1}>
              <Outlet context={{ selected }} />
            </main>
          </div>
        </div>
        <MobileTabs />
      </div>
    </PortfolioContext.Provider>
  );
}

function composeHome(pathname: string, selected: IntentRow | null): boolean {
  return (pathname === "/" || pathname === "/intents/new") && selected === null;
}

function backTarget(pathname: string): string {
  if (
    pathname === "/bookings" ||
    pathname.startsWith("/intents/new") ||
    pathname === "/intents/clarify"
  ) {
    return "/";
  }
  return "/bookings";
}

function headerFor(
  pathname: string,
  selected: IntentRow | null,
  session: PlanSession | null,
): { title: string; meta: string } {
  if (pathname === "/" && selected === null) {
    return { title: "New intent", meta: "" };
  }
  if (pathname === "/bookings") {
    return { title: "Booking Chats", meta: "" };
  }
  if (pathname === "/intents/new") {
    return { title: "New intent", meta: "" };
  }
  if (pathname === "/intents/clarify") {
    const phase = session?.phase;
    const meta =
      phase === "ready"
        ? "Plan confirmed · nothing disclosed"
        : phase === "clarify"
          ? "Gathering answers · nothing disclosed"
          : "Plan forming · nothing disclosed";
    return { title: "Clarify & plan", meta };
  }
  if (pathname.startsWith("/intents/new/")) {
    const id = pathname.split("/").pop();
    const name = domainById(id ?? "")?.name ?? "New intent";
    return { title: `${name} · new intent`, meta: "" };
  }
  if (pathname === "/activity") {
    return { title: "Activity", meta: "Across every intent" };
  }
  if (pathname === "/prefs") {
    return { title: "Preferences", meta: "Never sent to suppliers" };
  }
  if (pathname === "/data") {
    return { title: "Your data", meta: "Export, history, delete" };
  }
  if (pathname === "/plan") {
    return { title: "Account & plan", meta: "Simulation only" };
  }
  if (selected) {
    return { title: selected.title, meta: selected.date };
  }
  return { title: "Reservedge", meta: "" };
}

function ReservedgeRail({ needsCount }: { needsCount: number }) {
  const location = useLocation();
  const { planSession } = usePortfolio();
  const intentTo = planSession !== null ? "/intents/clarify" : "/";
  const intentsOn =
    ["/", "/bookings", "/intents/new", "/intents/clarify"].includes(location.pathname) ||
    location.pathname.startsWith("/intents/");
  return (
    <aside className="re-rail" aria-label="Primary">
      <div className="re-brand">
        <ReservedgeMark size={28} />
        <span className="re-wordmark">Reservedge</span>
        <SimChip tone="rail" />
      </div>
      <div className="re-rail-nav">
        {RAIL.map((item) => {
          const on = item.key === "intents" ? intentsOn : location.pathname === item.to;
          return (
            <NavLink
              key={item.key}
              to={item.key === "intents" ? intentTo : item.to}
              end={"end" in item ? item.end : false}
              className={`re-rail-btn itaa-focus-ring${on ? " is-on" : ""}`}
            >
              <span className="re-rail-bar" aria-hidden />
              {item.label}
              {item.key === "intents" && needsCount > 0 ? (
                <span className="re-rail-count">{needsCount}</span>
              ) : null}
            </NavLink>
          );
        })}
      </div>
      <div className="re-domains">
        <div className="re-domains-label">DOMAINS LIVE</div>
        {listDomains().map((domain) => (
          <div key={domain.id} className="re-domain-row">
            <span className="re-code re-code-dark">{domain.code}</span>
            {domain.name}
          </div>
        ))}
        <p>
          The domain picker is no longer the front door. One booking holds many tasks, each with its
          own requirement, disclosure and authorization.
        </p>
      </div>
    </aside>
  );
}

function DetailHeader({ title, meta }: { title: string; meta: string }) {
  return (
    <header className="re-detail-head">
      <div className="re-ellipsis re-detail-title">{title}</div>
      {meta ? <span className="re-detail-meta">{meta}</span> : null}
      <div className="re-sim-control">
        <span>Simulation mode</span>
        <span className="re-toggle" aria-hidden>
          <span className="re-toggle-knob" />
        </span>
      </div>
    </header>
  );
}

function MobileAppBar({
  title,
  meta,
  showBack,
  showMark,
  backTo,
}: {
  title: string;
  meta: string;
  showBack: boolean;
  showMark: boolean;
  backTo: string;
}) {
  const navigate = useNavigate();
  return (
    <header className="re-appbar">
      {showBack ? (
        <button
          type="button"
          className="re-back itaa-focus-ring"
          aria-label="Back to intents"
          onClick={() => navigate(backTo)}
        >
          ‹
        </button>
      ) : null}
      {showMark ? <ReservedgeMark size={30} /> : null}
      <div className="re-appbar-copy">
        <div className="re-ellipsis">{title}</div>
        {meta ? <div className="re-appbar-meta">{meta}</div> : null}
      </div>
      <SimChip tone="light" />
    </header>
  );
}

function MobileTabs() {
  const location = useLocation();
  const { planSession } = usePortfolio();
  const intentTo = planSession !== null ? "/intents/clarify" : "/";
  return (
    <nav className="re-tabs" aria-label="Primary">
      {TABS.map((item) => {
        const to = item.label === "Intent" ? intentTo : item.to;
        const on =
          (item.label === "Intent" &&
            (location.pathname === "/" ||
              location.pathname === "/intents/new" ||
              location.pathname === "/intents/clarify" ||
              location.pathname.startsWith("/intents/new/"))) ||
          (item.label === "Booking Chats" &&
            (location.pathname === "/bookings" ||
              (location.pathname.startsWith("/intents/") &&
                !location.pathname.startsWith("/intents/new") &&
                location.pathname !== "/intents/clarify"))) ||
          (item.label === "Activity" && location.pathname === "/activity");
        return (
          <NavLink
            key={item.label}
            to={to}
            end={item.end}
            className={`re-tab itaa-focus-ring${on ? " is-on" : ""}`}
          >
            <span className="re-tab-bar" aria-hidden />
            {item.label}
          </NavLink>
        );
      })}
    </nav>
  );
}
