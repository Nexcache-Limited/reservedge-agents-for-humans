import { createContext, useContext, type Dispatch, type SetStateAction } from "react";
import type { PlanSession } from "../intent-first/plan.js";
import { SEED_INTENTS, type DomainId, type IntentRow } from "./inbox.js";
import { listDomains } from "./registry.js";

export function landingTab(row: IntentRow | null): "request" | "research" | "offers" | "activity" {
  if (row === null) {
    return "request";
  }
  if (row.stage === "offers" || row.stage === "gate" || row.stage === "done") {
    return "offers";
  }
  if (row.stage === "research") {
    return "research";
  }
  return "request";
}

export interface PortfolioValue {
  intents: IntentRow[];
  setIntents: Dispatch<SetStateAction<IntentRow[]>>;
  selectedId: string | null;
  setSelectedId: Dispatch<SetStateAction<string | null>>;
  objective: string;
  setObjective: Dispatch<SetStateAction<string>>;
  planSession: PlanSession | null;
  setPlanSession: Dispatch<SetStateAction<PlanSession | null>>;
  parkedSessions: PlanSession[];
  setParkedSessions: Dispatch<SetStateAction<PlanSession[]>>;
}

export const PortfolioContext = createContext<PortfolioValue>({
  intents: SEED_INTENTS,
  setIntents: () => undefined,
  selectedId: null,
  setSelectedId: () => undefined,
  objective: "",
  setObjective: () => undefined,
  planSession: null,
  setPlanSession: () => undefined,
  parkedSessions: [],
  setParkedSessions: () => undefined,
});

export function usePortfolio(): PortfolioValue {
  return useContext(PortfolioContext);
}

export const DOMAIN_IDS: DomainId[] = listDomains().map((domain) => domain.id);
