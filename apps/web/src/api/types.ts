export const API_PREFIX = "/v1/simulations/airport-parking";
export const AGENT_PREFIX = "/v1/agent";

export type BuyerSessionState =
  | "AWAITING_REQUIREMENT_CONFIRMATION"
  | "AWAITING_DISPATCH_APPROVAL"
  | "OFFERS_RANKED"
  | "ACCEPTANCE_RECORDED"
  | "TRANSACTION_AUTHORIZED_SIMULATED"
  | "CANCELLED"
  | "SUPERSEDED";

export type SupplierOutcomeKind =
  | "OFFER"
  | "DECLINED"
  | "INVALID"
  | "TIMED_OUT"
  | "FAILED"
  | "DENIED"
  | "LATE";

export interface ClosedError {
  code: string;
  field: string | null;
  correlationId: string;
}

export interface ErrorEnvelope {
  error: ClosedError;
}

export interface LivenessResponse {
  status: "ok";
  environment: "local_simulation";
}

export interface ReadinessResponse {
  status: "ready";
  environment: "local_simulation";
  durability: "unsupported";
}

export interface Location {
  airportCode: string;
}

export interface ServiceWindow {
  start: string;
  end: string;
}

export interface Requirements {
  vehicleClass: "standard" | "compact" | "suv" | "oversized";
  covered: "none" | "preferred" | "required";
  shuttleMaxMinutes: number;
}

export interface Constraints {
  currency: string;
  accessibility: Array<"step_free" | "wheelchair" | "ev_charging">;
}

export interface Disclosure {
  profile: "parking_v1";
  approvedPayloadHash: string;
}

export interface Solicitation {
  responseDeadline: string;
  counteroffersAllowed: boolean;
}

export interface PurchaseIntent {
  schemaVersion: "1.0";
  intentId: string;
  buyerToken: string;
  category: "airport_parking";
  location: Location;
  serviceWindow: ServiceWindow;
  requirements: Requirements;
  constraints: Constraints;
  disclosure: Disclosure;
  solicitation: Solicitation;
  createdAt: string;
  expiresAt: string;
}

export interface GovernanceBody {
  actorId: string;
  ownerId: string;
  approvalId: string;
  correlationId: string;
  issuedAt: string;
  expiresAt: string;
}

export interface AcceptanceBody extends GovernanceBody {
  offerId: string;
  offerVersion: number;
}

export interface AuthorizationBody extends GovernanceBody {
  acceptanceId: string;
  amountMinor: number;
  currency: string;
  supplierToken: string;
  action: "reserve_parking";
  mode: "SIMULATED";
  idempotencyKey: string;
}

export interface MarketEvidenceItem {
  sourceType: string;
  sourceRef: string;
  observedAt: string;
  label: string;
}

export interface SupplierOutcome {
  supplierToken: string;
  kind: string;
  reason: string | null;
}

export interface RankedOffer {
  offerId: string;
  supplierToken: string;
  version: number;
  rank: number;
  scoreMicros?: number;
  totalMinor?: number;
  currency?: string;
  price?: {
    totalMinor: number;
    currency: string;
  };
  recommended: boolean;
  simulation: boolean;
}

export interface Downside {
  dimension: string;
  delta: number;
  versusOfferId: string | null;
}

export interface AcceptanceView {
  acceptanceId: string;
  offerId: string;
  offerVersion: number;
  status: string;
}

export interface TransactionView {
  authorizationId: string;
  acceptanceId: string;
  action: string;
  mode: string;
  amountMinor: number;
  currency: string;
  resultRef: string | null;
}

export interface BuyerSnapshot {
  environment: string;
  simulation: boolean;
  intentId: string;
  state: BuyerSessionState;
  airport: string;
  category: string;
  createdAt: string;
  updatedAt: string;
  expiresAt: string;
  marketEvidence: MarketEvidenceItem[];
  supplierOutcomes: SupplierOutcome[];
  offers: RankedOffer[];
  recommendedOfferId: string | null;
  downside: Downside | null;
  acceptance: AcceptanceView | null;
  transaction: TransactionView | null;
  replacesIntentId?: string | null;
  replacedByIntentId?: string | null;
  saved?: boolean;
  savedAt?: string | null;
  windowStart?: string | null;
  windowEnd?: string | null;
}

export interface ProgressEventPayload {
  intentId: string;
  generationId: string;
  kind: string;
  sequence: number;
  occurredAt: string;
  simulation: boolean;
  supplierToken: string | null;
  status: string | null;
  correlationId: string | null;
  terminal: boolean;
}

export interface ProgressReconnect {
  lastEventId?: string;
  generationId?: string;
}

export interface ProgressHandlers {
  onEvent: (event: ProgressEventPayload) => void;
  onError: () => void;
}

export interface ProgressSubscription {
  close: () => void;
}

export interface IntakeEvidenceSpan {
  field: string;
  start: number;
  end: number;
}

export interface IntakeProposal {
  category?: string;
  location?: { airportCode?: string | null };
  serviceWindow?: { start?: string | null; end?: string | null };
  requirements?: {
    vehicleClass?: string | null;
    covered?: string | null;
    shuttleMaxMinutes?: number | null;
  };
  constraints?: {
    currency?: string | null;
    accessibility?: Array<"step_free" | "wheelchair" | "ev_charging">;
  };
}

export interface IntakeExtraction {
  intakeId: string;
  correlationId?: string;
  proposal: IntakeProposal | null;
  fieldConfidence: Record<string, number>;
  missingFields: string[];
  ambiguousFields: string[];
  evidenceSpans: IntakeEvidenceSpan[];
  fieldAttributions?: Array<{ field: string; origin: string; confidence: number }>;
  requiresA1?: boolean;
  accepted?: boolean;
  fallback?: string | null;
  rejectionCode?: string | null;
}

export interface IntakeIntentFields {
  intakeId: string;
  airportCode: string;
  start: string;
  end: string;
  vehicleClass: Requirements["vehicleClass"];
  covered: Requirements["covered"];
  shuttleMaxMinutes: number;
  currency: string;
  accessibility: Constraints["accessibility"];
}

export interface IntakeAcceptBody {
  offerId: string;
  offerVersion?: number;
}

export interface IntakeAuthorizeBody {
  acceptanceId?: string;
  amountMinor?: number;
  currency?: string;
  supplierToken?: string;
  action?: "reserve_parking";
  mode?: "SIMULATED";
}

export interface ActivityEntry {
  occurredAt: string;
  label: string;
}

export type AgentPhase = "clarify" | "forming" | "ready";
export type AgentTaskProvenance = "explicit" | "inferred" | "proposed";
export type AgentTaskSupport =
  | "live_simulated"
  | "demonstration"
  | "unsupported"
  | "sandbox_search";
export type AgentQuestionId = "dates" | "departureAirport" | "carNeed" | "helpWith";

export interface AgentFacts {
  destination: string;
  originCity?: string;
  destinationAirport: string;
  parkingAirport: string;
  departureAirport: string;
  dates: string;
  hasExactDates: boolean;
  hasLooseDates: boolean;
  startDate: string;
  endDate: string;
  carNeed: "yes" | "no" | "unsure" | "";
  parkingStated: boolean;
  rentalStated: boolean;
  entsStated: boolean;
  hotelStated: boolean;
  experienceStated?: boolean;
  experiencePreferences?: string[];
  flightStated: boolean;
  flightSatisfied?: boolean;
  helpWith?: string;
  landing: boolean;
  travel: boolean;
  conference: boolean;
  nights: boolean;
  tripLike: boolean;
  dayPart: string;
  timeFlexible: boolean;
}

export interface AgentPlanTask {
  id: string;
  kind: "parking" | "rental" | "ents" | "flight" | "hotel" | "experience";
  code: string;
  title: string;
  detail: string;
  provenance: AgentTaskProvenance;
  support: AgentTaskSupport;
  supportLabel: string;
  accepted: boolean;
}

export interface AgentQuestion {
  id: AgentQuestionId | string;
  label: string;
  why: string;
}

export interface AgentPlanProjection {
  facts: AgentFacts;
  questions: AgentQuestion[];
  tasks: AgentPlanTask[];
  phase: AgentPhase;
  title: string;
  summary: string;
  confirmedCount: number;
  proposedCount: number;
}

export interface AgentStaySandboxHold {
  status: string;
  bookingId: string;
  simulatedPayment: boolean;
}

export interface AgentStayOffer {
  id: string;
  name: string;
  locality: string;
  checkIn: string;
  checkOut: string;
  price?: { currency?: string; amountMinor?: number } | null;
  cancellation: string | null;
  availability: string;
  bookingAuthority: "none";
  photoUrl?: string;
  sandboxHold?: AgentStaySandboxHold;
  offerKind?: "regular" | "curated";
}

export interface AgentExperienceOffer {
  id: string;
  title: string;
  category: string;
  location: string;
  availability: string;
  price?: { currency?: string; amountMinor?: number } | null;
  durationMinutes?: number | null;
  cancellation: string | null;
  bookingAuthority: "none";
  photoUrl?: string;
  offerKind?: "regular" | "curated";
}

export interface AgentExperienceSearch {
  status: string;
  label: string;
  providerId: string;
  source: "fake" | "sandbox" | "live" | string;
  query?: {
    domain?: string;
    destination?: { kind: string; value: string };
    preferences?: string[];
    checkIn?: string;
    checkOut?: string;
  } | null;
  offers: AgentExperienceOffer[];
  buyerSafeMessage: string;
  bookingAuthority: "none";
  fetchedAt?: string;
  warnings?: string[];
  stale?: boolean;
  offerKind?: "regular" | "curated";
}

export interface AgentStaySearch {
  status: string;
  label: string;
  providerId: string;
  source: "fake" | "sandbox" | "live" | string;
  query?: {
    domain?: string;
    destination?: { kind: string; value: string };
    origin?: { kind: string; value: string };
    checkIn?: string;
    checkOut?: string;
  } | null;
  offers: AgentStayOffer[];
  buyerSafeMessage: string;
  bookingAuthority: "none";
  fetchedAt?: string;
  warnings?: string[];
  stale?: boolean;
  offerKind?: "regular" | "curated";
}

export interface AgentSharedContextFact {
  id: string;
  label: string;
  value: string;
  source: string;
  provenance: string;
}

export interface AgentSharedBookingContext {
  facts: AgentSharedContextFact[];
  note: string;
}

export interface AgentWorkspaceMeta {
  persistence: string;
  note: string;
}

export interface AgentParkingHandoff {
  path: string;
  support: AgentTaskSupport | null;
  fields: Record<string, unknown>;
}

export type AgentFieldSource = "current_turn" | "earlier_turn" | "direct_edit" | "system_proposal";
export type AgentGate = "A1" | "A2" | "A3" | "A4";

export interface AgentDomainField {
  value: unknown;
  source: AgentFieldSource | string;
  provenance: AgentTaskProvenance | string;
}

export interface AgentOfferSet {
  stale: boolean;
  intentId?: string | null;
  snapshot?: {
    intentId?: string;
    state?: string;
    offers?: RankedOffer[];
    recommendedOfferId?: string | null;
    acceptance?: AcceptanceView | null;
    transaction?: TransactionView | null;
  } | null;
}

export interface AgentDomainState {
  kind: string;
  support: AgentTaskSupport | string;
  provenance: AgentTaskProvenance | string;
  accepted: boolean;
  fields: Record<string, AgentDomainField>;
  missing: string[];
  ask: Array<{ id: string; ask: string }>;
  completeness: string;
  offerSet: AgentOfferSet;
  intentId?: string | null;
}

export interface AgentTranscriptItem {
  turnId?: string;
  role: "user" | "agent" | string;
  text: string;
}

export interface AgentPendingAuthorization {
  gate: AgentGate | string;
  domain: string;
  prompt: string;
  resourceId?: string | null;
  offerId?: string | null;
}

export interface AgentToolTraceItem {
  kind: string;
  tool?: string;
}

export interface AgentSessionView {
  sessionId: string;
  projection: AgentPlanProjection;
  questions: AgentQuestion[];
  toolTrace: AgentToolTraceItem[];
  pendingAuthorizations: Array<Record<string, string>>;
  pendingAuthorization?: AgentPendingAuthorization | null;
  parkingHandoff: AgentParkingHandoff | null;
  confirmed: boolean;
  fallback: boolean;
  correlationId: string;
  transcript?: AgentTranscriptItem[];
  domains?: Record<string, AgentDomainState>;
  buyerSafeMessage?: string;
  staySearch?: AgentStaySearch | null;
  experienceSearch?: AgentExperienceSearch | null;
  sharedBookingContext?: AgentSharedBookingContext | null;
  workspace?: AgentWorkspaceMeta | null;
}

export interface AgentSessionCreateBody {
  objective: string;
}

export interface AgentTurnBody {
  answers?: {
    departureAirport?: string;
    carNeed?: "yes" | "no" | "unsure";
    dates?: string;
    startDate?: string;
    endDate?: string;
  };
  message?: string;
  tool?: string;
  payload?: Record<string, unknown>;
  patches?: Array<{ domain: string; fieldId: string; value: unknown }>;
}

export interface AgentGrantBody {
  gate: AgentGate;
  domain?: "parking";
  offerId?: string;
  offerVersion?: number;
  confirm?: true;
}

export interface AgentActivityEvent {
  kind: string;
  message: string;
}

export interface AgentEventHandlers {
  onEvent: (event: AgentActivityEvent) => void;
  onError: () => void;
}

export interface PortfolioList {
  needsYou: BuyerSnapshot[];
  running: BuyerSnapshot[];
  saved: BuyerSnapshot[];
  history: BuyerSnapshot[];
}

export interface ReplaceResult {
  previous: BuyerSnapshot;
  draft: BuyerSnapshot;
}

export interface ItaaApi {
  healthz(): Promise<LivenessResponse>;
  readyz(): Promise<ReadinessResponse>;
  createIntent(body: PurchaseIntent): Promise<BuyerSnapshot>;
  getSnapshot(intentId: string): Promise<BuyerSnapshot>;
  confirmRequirement(intentId: string, body: GovernanceBody): Promise<BuyerSnapshot>;
  approveAndDispatch(intentId: string, body: GovernanceBody): Promise<BuyerSnapshot>;
  acceptOffer(intentId: string, body: AcceptanceBody): Promise<BuyerSnapshot>;
  authorizeTransaction(
    intentId: string,
    body: AuthorizationBody,
    headerIdempotencyKey: string,
  ): Promise<BuyerSnapshot>;
  extractIntake(text: string, category: "airport_parking"): Promise<IntakeExtraction>;
  confirmIntakeIntent(body: IntakeIntentFields): Promise<BuyerSnapshot>;
  intakeConfirm(intentId: string): Promise<BuyerSnapshot>;
  intakeDispatch(intentId: string): Promise<BuyerSnapshot>;
  intakeAccept(intentId: string, body: IntakeAcceptBody): Promise<BuyerSnapshot>;
  intakeAuthorize(intentId: string, body?: IntakeAuthorizeBody): Promise<BuyerSnapshot>;
  listIntents(): Promise<PortfolioList>;
  getOwnedIntent(intentId: string): Promise<BuyerSnapshot>;
  cancelIntent(intentId: string): Promise<BuyerSnapshot>;
  replaceIntent(intentId: string, idempotencyKey: string): Promise<ReplaceResult>;
  deleteDraft(intentId: string): Promise<void>;
  saveIntent(intentId: string): Promise<BuyerSnapshot>;
  unsaveIntent(intentId: string): Promise<BuyerSnapshot>;
  intentActivity(intentId: string): Promise<ActivityEntry[]>;
  subscribeProgress(
    intentId: string,
    handlers: ProgressHandlers,
    reconnect?: ProgressReconnect,
  ): ProgressSubscription;
  createAgentSession(body: AgentSessionCreateBody): Promise<AgentSessionView>;
  getAgentSession(sessionId: string): Promise<AgentSessionView>;
  postAgentTurn(sessionId: string, body: AgentTurnBody): Promise<AgentSessionView>;
  confirmAgentSession(sessionId: string): Promise<AgentSessionView>;
  grantAgentSession(sessionId: string, body: AgentGrantBody): Promise<AgentSessionView>;
  subscribeAgentEvents(sessionId: string, handlers: AgentEventHandlers): ProgressSubscription;
}
