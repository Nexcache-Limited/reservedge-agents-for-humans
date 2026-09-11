import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useOutletContext,
  useParams,
} from "react-router-dom";
import type { ItaaApi } from "./api/types.js";
import { PortfolioLayout } from "./components/AppShell.js";
import type { IntentRow } from "./reservedge/inbox.js";
import { isLiveChatRow } from "./reservedge/plan-inbox.js";
import { usePortfolio } from "./reservedge/portfolio.js";
import { Composer } from "./screens/Composer.js";
import { DataScreen, GlobalActivity, PlanScreen, PrefsScreen } from "./screens/GlobalViews.js";
import { IntentComposer } from "./screens/IntentComposer.js";
import { ClarifyPlanScreen } from "./screens/ClarifyPlanScreen.js";
import { LiveParkingWorkspace } from "./screens/LiveParkingWorkspace.js";
import { NotFoundScreen } from "./screens/NotFoundScreen.js";
import { SeedWorkspace } from "./screens/SeedWorkspace.js";

function InboxHome({ api }: { api: ItaaApi }) {
  const { selected } = useOutletContext<{ selected: IntentRow | null }>();
  const { planSession } = usePortfolio();
  if (selected?.id.startsWith("pi_")) {
    return <LiveParkingWorkspace api={api} intentId={selected.id} />;
  }
  if (selected && isLiveChatRow(planSession, selected.id) && selected.status !== "done") {
    return <Navigate to="/intents/clarify" replace />;
  }
  if (selected) {
    return <SeedWorkspace selected={selected} />;
  }
  return <IntentComposer api={api} />;
}

export function AppRoutes({ api }: { api: ItaaApi }) {
  return (
    <Routes>
      <Route element={<PortfolioLayout api={api} />}>
        <Route path="/" element={<IntentComposer api={api} />} />
        <Route path="/bookings" element={<InboxHome api={api} />} />
        <Route path="/live" element={<Navigate to="/bookings" replace />} />
        <Route path="/intents/new" element={<IntentComposer api={api} />} />
        <Route path="/intents/clarify" element={<ClarifyPlanScreen api={api} />} />
        <Route path="/intents/new/:domainId" element={<Composer api={api} />} />
        <Route path="/intents/:intentId" element={<IntentOrSeed api={api} />} />
        <Route
          path="/intents/:intentId/confirmation"
          element={<LiveParkingWorkspace api={api} confirmationRoute />}
        />
        <Route path="/activity" element={<GlobalActivity />} />
        <Route path="/prefs" element={<PrefsScreen />} />
        <Route path="/data" element={<DataScreen />} />
        <Route path="/plan" element={<PlanScreen />} />
        <Route path="/inbox" element={<Navigate to="/bookings" replace />} />
      </Route>
      <Route path="*" element={<NotFoundScreen />} />
    </Routes>
  );
}

function IntentOrSeed({ api }: { api: ItaaApi }) {
  const { intentId } = useParams();
  const { selected } = useOutletContext<{ selected: IntentRow | null }>();
  const { intents, selectedId, planSession } = usePortfolio();
  const row =
    selected ?? intents.find((item) => item.id === intentId || item.id === selectedId) ?? null;
  if (intentId?.startsWith("pi_")) {
    return <LiveParkingWorkspace api={api} />;
  }
  if (row?.domain === "stay" && isLiveChatRow(planSession, row.id) && row.status !== "done") {
    return <Navigate to="/intents/clarify" replace />;
  }
  return <SeedWorkspace selected={row} />;
}

export function App({ api }: { api: ItaaApi }) {
  return (
    <BrowserRouter>
      <AppRoutes api={api} />
    </BrowserRouter>
  );
}
