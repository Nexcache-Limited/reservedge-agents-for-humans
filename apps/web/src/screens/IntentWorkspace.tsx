import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ClosedApiError } from "../api/errors.js";
import { governanceIds } from "../api/ids.js";
import type {
  ActivityEntry,
  BuyerSnapshot,
  ItaaApi,
  ProgressEventPayload,
  RankedOffer,
} from "../api/types.js";
import { Button, LiveRegion, StatusIndicator, Surface, Text } from "../components/primitives.js";
import {
  DISCLOSED_FIELDS,
  RETAINED_FIELDS,
  WITHHELD_FIELDS,
  formatMoney,
  supplierDisplayName,
} from "../fixtures/golden.js";
import {
  clearIdempotencyKey,
  idempotencyKeyFor,
  isCompetitionIntent,
  rememberSnapshot,
  sessionActor,
} from "../session/memory.js";
import {
  a3AcceptanceView,
  a3Eligibility,
  allSuppliersUnavailable,
  downsideCopy,
  offerCards,
  offerMoney,
  partialSuppliers,
  progressAnnouncement,
  progressLanes,
  stageFor,
  STATE_LABEL,
  supplierLanes,
  whyRecommended,
  formatHumanDate,
} from "../view-models/workspace.js";

const STAGES = [
  "Request",
  "Confirm details",
  "Share with suppliers",
  "Offers",
  "Compare",
  "Select offer",
  "Authorize",
  "Completed",
] as const;

export function IntentWorkspace({
  api,
  confirmationRoute = false,
}: {
  api: ItaaApi;
  confirmationRoute?: boolean;
}) {
  const { intentId = "" } = useParams();
  const navigate = useNavigate();
  const [snapshot, setSnapshot] = useState<BuyerSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState("");
  const [selectedOfferId, setSelectedOfferId] = useState<string | null>(null);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const inflight = useRef(false);
  const progressRef = useRef<{ close: () => void } | null>(null);
  const [progressEvents, setProgressEvents] = useState<ProgressEventPayload[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [confirm, setConfirm] = useState<null | "cancel" | "delete" | "replace">(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = isCompetitionIntent(intentId)
        ? await api.getOwnedIntent(intentId)
        : await api.getSnapshot(intentId);
      setSnapshot(next);
      rememberSnapshot(next);
      setSelectedOfferId((current) => current ?? next.recommendedOfferId);
      setNeedsRefresh(false);
      setLive(`Intent is ${STATE_LABEL[next.state]}.`);
    } catch (caught) {
      const message =
        caught instanceof ClosedApiError ? caught.message : "Unable to load this intent.";
      setError(message);
      setSnapshot(null);
    } finally {
      setLoading(false);
    }
  }, [api, intentId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (snapshot === null) {
      return;
    }
    let cancelled = false;
    void api
      .intentActivity(snapshot.intentId)
      .then((entries) => {
        if (!cancelled) {
          setActivity(entries);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setActivity([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, snapshot]);

  useEffect(() => {
    return () => {
      progressRef.current?.close();
    };
  }, []);

  const runMutation = useCallback(
    async (action: () => Promise<BuyerSnapshot>, afterAmbiguousRefresh = true) => {
      if (inflight.current || busy) {
        return;
      }
      inflight.current = true;
      setBusy(true);
      setError(null);
      try {
        const next = await action();
        setSnapshot(next);
        rememberSnapshot(next);
        setSelectedOfferId((current) => current ?? next.recommendedOfferId);
        setNeedsRefresh(false);
        setLive(`Updated to ${STATE_LABEL[next.state]}.`);
        if (next.state === "TRANSACTION_AUTHORIZED_SIMULATED") {
          navigate(`/intents/${next.intentId}/confirmation`);
        }
      } catch (caught) {
        if (caught instanceof ClosedApiError && caught.ambiguous && afterAmbiguousRefresh) {
          setNeedsRefresh(true);
          setError(caught.message);
          try {
            const refreshed = await api.getSnapshot(intentId);
            setSnapshot(refreshed);
            rememberSnapshot(refreshed);
          } catch {
            // keep the mutation error
          }
        } else if (caught instanceof ClosedApiError) {
          setError(caught.message);
        } else {
          setError("The request could not be completed.");
        }
      } finally {
        inflight.current = false;
        setBusy(false);
      }
    },
    [api, busy, intentId, navigate],
  );

  const competition = isCompetitionIntent(intentId);
  const actor = useMemo(() => (competition ? null : sessionActor()), [competition]);
  const selected = snapshot?.offers.find((item) => item.offerId === selectedOfferId) ?? null;
  const authorized = snapshot?.state === "TRANSACTION_AUTHORIZED_SIMULATED";
  const title = confirmationRoute && authorized ? "Simulated receipt" : "Airport parking intent";

  if (loading) {
    return (
      <>
        <h1 className="itaa-text itaa-text--display">{title}</h1>
        <LiveRegion message="Loading intent." />
        <StatusIndicator variant="working" label="Loading" />
      </>
    );
  }

  if (snapshot === null) {
    return (
      <>
        <h1 className="itaa-text itaa-text--display">{title}</h1>
        <LiveRegion message={error ?? "Intent not found."} politeness="assertive" />
        <Surface>
          <StatusIndicator variant="denial" label="Unknown intent" />
          <p className="itaa-text itaa-text--body">
            {error ?? "This request is not available in this browser session."}
          </p>
          <Button id="unknown-inbox" variant="primary" onClick={() => navigate("/")}>
            Return to Intent Inbox
          </Button>
        </Surface>
      </>
    );
  }

  if (confirmationRoute && snapshot.state !== "TRANSACTION_AUTHORIZED_SIMULATED") {
    return <Navigate to={`/intents/${snapshot.intentId}`} replace />;
  }

  const stage = stageFor(snapshot.state);
  const disabledReason = busy
    ? "A request is already in progress."
    : needsRefresh
      ? "Refresh status before another consequential action."
      : undefined;

  return (
    <>
      <h1 className="itaa-text itaa-text--display">{title}</h1>
      <LiveRegion message={live} />
      {error !== null ? (
        <div className="itaa-error" role="alert">
          <Text role="label" as="p">
            Could not complete that action
          </Text>
          <p className="itaa-text itaa-text--body">{error}</p>
          {needsRefresh ? (
            <Button id="refresh-status" variant="ghost" onClick={() => void load()}>
              Refresh status
            </Button>
          ) : null}
        </div>
      ) : null}
      {competition ? (
        <PortfolioActions
          snapshot={snapshot}
          busy={busy}
          onSave={() =>
            void runMutation(() =>
              snapshot.saved === true
                ? api.unsaveIntent(snapshot.intentId)
                : api.saveIntent(snapshot.intentId),
            )
          }
          onConfirm={setConfirm}
        />
      ) : null}
      <ol className="itaa-stage-track" aria-label="Request progress">
        {STAGES.map((label, index) => {
          const currentIndex = currentStageIndex(snapshot);
          const state =
            index < currentIndex ? "completed" : index === currentIndex ? "current" : "future";
          return (
            <li
              key={label}
              aria-current={state === "current" ? "step" : undefined}
              data-state={state}
            >
              {label}
            </li>
          );
        })}
      </ol>
      {snapshot.state === "CANCELLED" || snapshot.state === "SUPERSEDED" ? (
        <Surface>
          <StatusIndicator variant="neutral" label={STATE_LABEL[snapshot.state]} />
          <p className="itaa-text itaa-text--body">
            {snapshot.state === "SUPERSEDED"
              ? "This request was replaced with a revised request."
              : "This request was cancelled. Start a new demonstration if you still need parking."}
          </p>
        </Surface>
      ) : null}
      {snapshot.state !== "CANCELLED" &&
      snapshot.state !== "SUPERSEDED" &&
      stage === "requirement" ? (
        <RequirementStage
          snapshot={snapshot}
          busy={busy}
          disabledReason={disabledReason}
          competition={competition}
          onConfirm={() =>
            void runMutation(() =>
              competition
                ? api.intakeConfirm(snapshot.intentId)
                : api.confirmRequirement(
                    snapshot.intentId,
                    governanceIds(actor?.actorId ?? "", actor?.ownerId ?? ""),
                  ),
            )
          }
        />
      ) : null}
      {stage === "disclosure" ? (
        <DisclosureStage
          snapshot={snapshot}
          busy={busy}
          disabledReason={disabledReason}
          progressEvents={progressEvents}
          onDecline={() => navigate("/")}
          onDispatch={() => {
            progressRef.current?.close();
            setProgressEvents([]);
            const handle: { close: () => void } = { close: () => undefined };
            const subscription = api.subscribeProgress(snapshot.intentId, {
              onEvent: (event) => {
                setProgressEvents((current) => {
                  const generationId = current[0]?.generationId ?? event.generationId;
                  if (event.generationId !== generationId) {
                    return current;
                  }
                  if (
                    current.some(
                      (item) =>
                        item.generationId === event.generationId &&
                        item.sequence === event.sequence,
                    )
                  ) {
                    return current;
                  }
                  return [...current, event];
                });
                setLive(progressAnnouncement(event));
                if (event.terminal) {
                  handle.close();
                }
              },
              onError: () => {
                handle.close();
              },
            });
            handle.close = () => {
              subscription.close();
            };
            progressRef.current = subscription;
            void runMutation(() =>
              competition
                ? api.intakeDispatch(snapshot.intentId)
                : api.approveAndDispatch(
                    snapshot.intentId,
                    governanceIds(actor?.actorId ?? "", actor?.ownerId ?? ""),
                  ),
            );
          }}
        />
      ) : null}
      {stage === "offers" ? (
        <OffersStage
          snapshot={snapshot}
          selected={selected}
          busy={busy}
          stale={needsRefresh}
          disabledReason={disabledReason}
          onSelect={setSelectedOfferId}
          onRefresh={() => void load()}
          onInbox={() => navigate("/")}
          onAccept={() => {
            if (selected === null) {
              return;
            }
            const gate = a3Eligibility(snapshot, selected, { stale: needsRefresh });
            if (!gate.eligible) {
              return;
            }
            void runMutation(() =>
              competition
                ? api.intakeAccept(snapshot.intentId, {
                    offerId: selected.offerId,
                    offerVersion: selected.version,
                  })
                : api.acceptOffer(snapshot.intentId, {
                    ...governanceIds(actor?.actorId ?? "", actor?.ownerId ?? ""),
                    offerId: selected.offerId,
                    offerVersion: selected.version,
                  }),
            );
          }}
        />
      ) : null}
      {stage === "authorization" ? (
        <AuthorizationStage
          snapshot={snapshot}
          busy={busy}
          disabledReason={disabledReason}
          onAuthorize={() => {
            const accepted = snapshot.acceptance;
            const offer = snapshot.offers.find((item) => item.offerId === accepted?.offerId);
            if (accepted === null || offer === undefined) {
              return;
            }
            const money = offerMoney(offer);
            void runMutation(() =>
              competition
                ? api.intakeAuthorize(snapshot.intentId)
                : api.authorizeTransaction(
                    snapshot.intentId,
                    {
                      ...governanceIds(actor?.actorId ?? "", actor?.ownerId ?? ""),
                      acceptanceId: accepted.acceptanceId,
                      amountMinor: money.totalMinor,
                      currency: money.currency,
                      supplierToken: offer.supplierToken,
                      action: "reserve_parking",
                      mode: "SIMULATED",
                      idempotencyKey: idempotencyKeyFor(snapshot.intentId),
                    },
                    idempotencyKeyFor(snapshot.intentId),
                  ),
            );
          }}
        />
      ) : null}
      {stage === "receipt" ? (
        <ReceiptStage
          snapshot={snapshot}
          onInbox={() => {
            clearIdempotencyKey(snapshot.intentId);
            navigate("/");
          }}
        />
      ) : null}
      {activity.length > 0 ? (
        <Surface>
          <Text role="heading" as="h2">
            Activity
          </Text>
          <ol className="itaa-timeline">
            {activity.map((entry) => (
              <li key={`${entry.occurredAt}-${entry.label}`}>
                <span className="itaa-text itaa-text--meta">
                  {formatHumanDate(entry.occurredAt)}
                </span>
                <span className="itaa-text itaa-text--body"> {entry.label}</span>
              </li>
            ))}
          </ol>
        </Surface>
      ) : null}
      {confirm !== null ? (
        <Surface>
          <div
            className="itaa-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
          >
            <h2 id="confirm-title" className="itaa-text itaa-text--heading">
              {confirm === "delete"
                ? "Delete this draft?"
                : confirm === "replace"
                  ? "Start a revised request?"
                  : "Cancel this request?"}
            </h2>
            <p className="itaa-text itaa-text--body">
              {confirm === "delete"
                ? "This removes the unpublished draft. It cannot be undone."
                : confirm === "replace"
                  ? "The original request will be closed and a new draft will be created from the same details."
                  : "Suppliers will not be contacted further. This cannot be undone."}
            </p>
            <div className="itaa-actions">
              <Button
                id="confirm-destructive"
                variant="destructive"
                busy={busy}
                onClick={() => {
                  const action = confirm;
                  setConfirm(null);
                  if (action === "delete") {
                    void api.deleteDraft(snapshot.intentId).then(
                      () => navigate("/"),
                      (caught: unknown) => {
                        setError(
                          caught instanceof ClosedApiError
                            ? caught.message
                            : "This draft could not be deleted. Cancel the request instead.",
                        );
                      },
                    );
                    return;
                  }
                  if (action === "replace") {
                    void runMutation(async () => {
                      const result = await api.replaceIntent(
                        snapshot.intentId,
                        idempotencyKeyFor(`replace:${snapshot.intentId}`),
                      );
                      navigate(`/intents/${result.draft.intentId}`);
                      return result.draft;
                    });
                    return;
                  }
                  void runMutation(() => api.cancelIntent(snapshot.intentId));
                }}
              >
                {confirm === "delete"
                  ? "Delete draft"
                  : confirm === "replace"
                    ? "Start revised request"
                    : "Cancel request"}
              </Button>
              <Button id="confirm-keep" variant="ghost" onClick={() => setConfirm(null)}>
                Keep request
              </Button>
            </div>
          </div>
        </Surface>
      ) : null}
    </>
  );
}

function PortfolioActions({
  snapshot,
  busy,
  onSave,
  onConfirm,
}: {
  snapshot: BuyerSnapshot;
  busy: boolean;
  onSave: () => void;
  onConfirm: (action: "cancel" | "delete" | "replace") => void;
}) {
  const terminal =
    snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED" ||
    snapshot.state === "CANCELLED" ||
    snapshot.state === "SUPERSEDED";
  const cleanDraft = snapshot.state === "AWAITING_REQUIREMENT_CONFIRMATION";
  if (terminal) {
    return null;
  }
  return (
    <div className="itaa-actions">
      {cleanDraft ? (
        <Button
          id="delete-draft"
          variant="destructive"
          disabled={busy}
          onClick={() => onConfirm("delete")}
        >
          Delete draft
        </Button>
      ) : (
        <Button
          id="cancel-request"
          variant="destructive"
          disabled={busy}
          onClick={() => onConfirm("cancel")}
        >
          Cancel request
        </Button>
      )}
      <Button
        id="replace-request"
        variant="ghost"
        disabled={busy}
        onClick={() => onConfirm("replace")}
      >
        Start a revised request
      </Button>
      <Button id="save-later" variant="ghost" disabled={busy} onClick={onSave}>
        {snapshot.saved === true ? "Saved for later" : "Save for later"}
      </Button>
    </div>
  );
}

function currentStageIndex(snapshot: BuyerSnapshot): number {
  if (snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED") {
    return 7;
  }
  switch (snapshot.state) {
    case "AWAITING_REQUIREMENT_CONFIRMATION":
      return 1;
    case "AWAITING_DISPATCH_APPROVAL":
      return 2;
    case "OFFERS_RANKED":
      return 4;
    case "ACCEPTANCE_RECORDED":
      return 6;
    default:
      return 0;
  }
}

function RequirementStage({
  snapshot,
  busy,
  disabledReason,
  competition,
  onConfirm,
}: {
  snapshot: BuyerSnapshot;
  busy: boolean;
  disabledReason?: string | undefined;
  competition: boolean;
  onConfirm: () => void;
}) {
  return (
    <div className="itaa-stack">
      <Surface raised>
        <Text role="heading" as="h2">
          Purchase Intent review
        </Text>
        <p className="itaa-text itaa-text--meta">
          {competition
            ? "These confirmed details are locked for this request. Start a revised request to change them."
            : "This seeded demonstration is read-only. Start a revised request to change the details."}
        </p>
        <dl className="itaa-fields">
          <Field
            label="Airport"
            value={competition ? snapshot.airport : `${snapshot.airport} (John F. Kennedy)`}
          />
          {competition ? null : (
            <Field label="Parking dates" value="3 Sep 2026 13:00Z to 8 Sep 2026 22:00Z" />
          )}
          {competition ? null : (
            <>
              <Field label="Vehicle class" value="standard" />
              <Field label="Covered preference" value="preferred" />
              <Field label="Shuttle preference" value="20 minutes maximum" />
              <Field label="Accessibility / add-ons" value="EV charging" />
              <Field label="Budget / currency" value="USD — precise budget withheld" />
            </>
          )}
        </dl>
      </Surface>
      <DisclosureLedger />
      <Surface>
        <Text role="heading" as="h2">
          Confirm details
        </Text>
        <p className="itaa-text itaa-text--body">
          You are confirming what ITAA should research. No supplier has been contacted yet. Next,
          you will review the minimized request before any supplier is contacted. This request
          expires {formatHumanDate(snapshot.expiresAt)}.
        </p>
        <p className="itaa-text itaa-text--meta">
          Opening this page is not approval. Confirmation is a separate action.
        </p>
        <Button
          id="a1-confirm"
          variant="consent"
          busy={busy}
          disabled={disabledReason !== undefined}
          disabledReason={disabledReason}
          onClick={onConfirm}
        >
          Confirm requirement
        </Button>
      </Surface>
    </div>
  );
}

function DisclosureStage({
  snapshot,
  busy,
  disabledReason,
  progressEvents,
  onDispatch,
  onDecline,
}: {
  snapshot: BuyerSnapshot;
  busy: boolean;
  disabledReason?: string | undefined;
  progressEvents: ProgressEventPayload[];
  onDispatch: () => void;
  onDecline: () => void;
}) {
  const lanes = progressLanes(progressEvents);
  const showLanes = busy || progressEvents.length > 0;
  return (
    <div className="itaa-stack">
      <Surface raised>
        <Text role="heading" as="h2">
          What will be shared
        </Text>
        <p className="itaa-text itaa-text--body">
          Authorize disclosure to 3 isolated simulated suppliers. This shares only the fields below.
          It does not reserve, buy, or charge anything. Suppliers cannot see competitor identities
          or offers. Buyer-owned data remains with ITAA.
        </p>
        <p className="itaa-text itaa-text--meta">
          Recipients: ParkDirect, SkyShield, and TerminalFlex. This request expires{" "}
          {formatHumanDate(snapshot.expiresAt)}.
        </p>
        <DisclosureLedger />
        <div className="itaa-actions">
          <Button
            id="a2-dispatch"
            variant="consent"
            busy={busy}
            disabled={disabledReason !== undefined}
            disabledReason={disabledReason}
            onClick={onDispatch}
          >
            Authorize disclosure to 3 suppliers
          </Button>
          <Button id="a2-decline" variant="ghost" disabled={busy} onClick={onDecline}>
            Decline disclosure
          </Button>
        </div>
        {showLanes ? (
          <ul className="itaa-lanes" aria-label="Isolated supplier progress">
            {lanes.map((lane) => (
              <li key={lane.supplierToken}>
                <Surface padding="md">
                  <Text role="label" as="p">
                    {lane.displayName}
                  </Text>
                  <StatusIndicator variant={lane.variant} label={lane.statusLabel} />
                </Surface>
              </li>
            ))}
          </ul>
        ) : null}
      </Surface>
    </div>
  );
}

function OffersStage({
  snapshot,
  selected,
  busy,
  stale,
  disabledReason,
  onSelect,
  onAccept,
  onRefresh,
  onInbox,
}: {
  snapshot: BuyerSnapshot;
  selected: RankedOffer | null;
  busy: boolean;
  stale: boolean;
  disabledReason?: string | undefined;
  onSelect: (offerId: string) => void;
  onAccept: () => void;
  onRefresh: () => void;
  onInbox: () => void;
}) {
  const lanes = supplierLanes(snapshot.supplierOutcomes);
  const cards = offerCards(snapshot.offers);
  const unavailable = allSuppliersUnavailable(snapshot);
  return (
    <div className="itaa-stack">
      <Surface>
        <Text role="heading" as="h2">
          Private supplier responses
        </Text>
        <p className="itaa-text itaa-text--body">
          Each supplier received the same minimized request. Suppliers cannot see one another or
          another offer. Live progress is operational only. The completed ranking snapshot is
          authoritative.
        </p>
        {partialSuppliers(snapshot) ? (
          <StatusIndicator variant="attention" label="Partial results" />
        ) : null}
        {unavailable ? (
          <StatusIndicator variant="denial" label="All suppliers unavailable" />
        ) : null}
        <ul className="itaa-lanes">
          {lanes.map((lane) => (
            <li key={lane.supplierToken}>
              <Surface padding="md">
                <Text role="label" as="p">
                  {lane.displayName}
                </Text>
                <StatusIndicator variant={lane.variant} label={lane.statusLabel} />
              </Surface>
            </li>
          ))}
        </ul>
      </Surface>
      <Surface raised>
        <Text role="heading" as="h2">
          Recommendation and comparison
        </Text>
        <p className="itaa-text itaa-text--body">
          ITAA recommends one offer under your stated preferences and the locked ranking policy. It
          is not claimed to be objectively best. Price is one factor among coverage, shuttle,
          distance, terms, and add-ons.
        </p>
        {snapshot.recommendedOfferId !== null ? (
          <div className="itaa-recommend">
            <StatusIndicator variant="confidence" label="Recommended" />
            <Text role="heading" as="h3">
              Why this is recommended
            </Text>
            <ul>
              {whyRecommended(snapshot).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <p className="itaa-text itaa-text--label">Weighted decision factors</p>
            <p className="itaa-text itaa-text--body">
              Coverage fit, EV add-on fit, shuttle-time fit, then all-in price. Ranking-policy
              scores are shown as evidence, not a fake percent match.
            </p>
            {downsideCopy(snapshot) !== null ? (
              <p className="itaa-text itaa-text--body">
                Material downside: {downsideCopy(snapshot)}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="itaa-text itaa-text--body">No reliable recommendation is available.</p>
        )}
        <div className="itaa-compare" role="table" aria-label="Offer comparison">
          {cards.map((card) => (
            <article
              key={card.offer.offerId}
              className="itaa-offer-card itaa-surface itaa-surface--pad-lg"
              data-recommended={card.offer.recommended ? "true" : "false"}
            >
              <header>
                <Text role="heading" as="h3">
                  {card.displayName}
                </Text>
                {card.offer.recommended ? (
                  <StatusIndicator variant="confidence" label="Recommended" />
                ) : null}
                <StatusIndicator variant="neutral" label="Private simulated offer" />
              </header>
              <dl className="itaa-fields">
                <Field label="All-in total" value={card.total} fact />
                <Field label="Ranking score" value={card.score} fact />
                <Field label="Qualitative fit" value={card.fit} />
                <Field label="Covered" value={card.catalog?.covered ?? "Not provided"} />
                <Field
                  label="Shuttle"
                  value={card.catalog ? `${card.catalog.shuttleMinutes} minutes` : "Not provided"}
                />
                <Field
                  label="Distance"
                  value={card.catalog ? `${card.catalog.distanceMeters} metres` : "Not provided"}
                />
                <Field label="Cancellation" value={card.catalog?.cancellation ?? "Not provided"} />
                <Field label="Refund" value={card.catalog?.refund ?? "Not provided"} />
                <Field
                  label="Add-ons"
                  value={
                    card.catalog === undefined
                      ? "Not provided"
                      : card.catalog.addOns.join(", ") || "None"
                  }
                />
                <Field label="Availability" value={card.catalog?.availability ?? "Not provided"} />
                <Field label="Validity" value={card.catalog?.validUntil ?? "Not provided"} />
                <Field label="Evidence" value={card.catalog?.evidenceRef ?? "Not provided"} />
              </dl>
              <Button
                id={`select-${card.offer.offerId}`}
                variant={selected?.offerId === card.offer.offerId ? "consent" : "ghost"}
                onClick={() => onSelect(card.offer.offerId)}
              >
                Select {card.displayName}
              </Button>
            </article>
          ))}
        </div>
        <Surface padding="md">
          <Text role="heading" as="h3">
            Confirm selected offer
          </Text>
          <p className="itaa-text itaa-text--body">
            Selection does not reserve or charge anything. Review the exact selected snapshot offer
            before acceptance.
          </p>
          {selected === null ? (
            <p className="itaa-text itaa-text--body">No offer is selected.</p>
          ) : (
            <A3AcceptanceDetails snapshot={snapshot} selected={selected} />
          )}
          <A3AcceptanceGate
            snapshot={snapshot}
            selected={selected}
            busy={busy}
            stale={stale}
            disabledReason={disabledReason}
            onAccept={onAccept}
            onRefresh={onRefresh}
            onInbox={onInbox}
          />
        </Surface>
      </Surface>
    </div>
  );
}

function AuthorizationStage({
  snapshot,
  busy,
  disabledReason,
  onAuthorize,
}: {
  snapshot: BuyerSnapshot;
  busy: boolean;
  disabledReason?: string | undefined;
  onAuthorize: () => void;
}) {
  const accepted = snapshot.acceptance;
  const offer = snapshot.offers.find((item) => item.offerId === accepted?.offerId);
  const money = offer === undefined ? null : offerMoney(offer);
  return (
    <div className="itaa-stack">
      <Surface raised>
        <Text role="heading" as="h2">
          Authorize simulated reservation
        </Text>
        <p className="itaa-text itaa-text--body">
          Action: reserve parking. Mode: simulated. This demonstration authorizes a simulated
          reservation only. No card will be charged and no supplier booking will be created.
        </p>
        {offer !== undefined && money !== null ? (
          <dl className="itaa-fields">
            <Field label="Supplier" value={supplierDisplayName(offer.supplierToken)} />
            <Field label="Offer version" value={String(offer.version)} />
            <Field label="Amount" value={formatMoney(money.totalMinor, money.currency)} fact />
            <Field label="Action" value="Reserve parking" />
            <Field label="Mode" value="Simulated" />
          </dl>
        ) : (
          <StatusIndicator variant="denial" label="Selected offer is no longer available" />
        )}
        <Button
          id="a4-authorize"
          variant="consent"
          busy={busy}
          disabled={offer === undefined || disabledReason !== undefined}
          disabledReason={disabledReason}
          onClick={onAuthorize}
        >
          Authorize simulated reservation
        </Button>
      </Surface>
    </div>
  );
}

function ReceiptStage({ snapshot, onInbox }: { snapshot: BuyerSnapshot; onInbox: () => void }) {
  const tx = snapshot.transaction;
  const offer = snapshot.offers.find((item) => item.offerId === snapshot.acceptance?.offerId);
  return (
    <div className="itaa-stack">
      <Surface raised>
        <Text role="display" as="h2">
          SIMULATED RECEIPT
        </Text>
        <p className="itaa-text itaa-text--body">
          No card was charged. No supplier reservation was created.
        </p>
        <dl className="itaa-fields">
          <Field label="Authorization status" value="Simulated" />
          <Field
            label="Supplier"
            value={
              offer === undefined ? "Simulated supplier" : supplierDisplayName(offer.supplierToken)
            }
          />
          <Field
            label="Amount"
            value={tx == null ? "Not provided" : formatMoney(tx.amountMinor, tx.currency)}
            fact
          />
        </dl>
        <ol className="itaa-timeline">
          <li>Details confirmed</li>
          <li>Supplier information approved</li>
          <li>Offer selected</li>
          <li>Simulated reservation authorized</li>
        </ol>
        <p className="itaa-text itaa-text--meta">
          This demonstration keeps requests in this browser session only.
        </p>
        <Button id="receipt-inbox" variant="primary" onClick={onInbox}>
          Return to Intent Inbox
        </Button>
      </Surface>
    </div>
  );
}

function DisclosureLedger() {
  return (
    <div className="itaa-ledger">
      <Surface padding="md">
        <Text role="heading" as="h3">
          Proposed for supplier disclosure
        </Text>
        <ul>
          {DISCLOSED_FIELDS.map((item) => (
            <li key={item.field}>
              <span className="itaa-text itaa-text--label">{item.field}</span>
              <span className="itaa-text itaa-text--fact"> {item.value}</span>
              <span className="itaa-text itaa-text--meta"> {item.purpose}</span>
            </li>
          ))}
        </ul>
      </Surface>
      <Surface padding="md">
        <Text role="heading" as="h3">
          Retained by the buyer agent
        </Text>
        <ul>
          {RETAINED_FIELDS.map((item) => (
            <li key={item.field}>
              <span className="itaa-text itaa-text--label">{item.field}</span>
              <span className="itaa-text itaa-text--meta"> {item.value}</span>
            </li>
          ))}
        </ul>
      </Surface>
      <Surface padding="md">
        <Text role="heading" as="h3">
          Withheld by the privacy firewall
        </Text>
        <ul>
          {WITHHELD_FIELDS.map((item) => (
            <li key={item.field}>
              <span className="itaa-text itaa-text--label">{item.field}</span>
              <span className="itaa-text itaa-text--meta"> {item.reason}</span>
            </li>
          ))}
        </ul>
      </Surface>
    </div>
  );
}

function A3AcceptanceDetails({
  snapshot,
  selected,
}: {
  snapshot: BuyerSnapshot;
  selected: RankedOffer;
}) {
  const details = a3AcceptanceView(snapshot, selected);
  return (
    <dl className="itaa-fields" aria-label="Selected offer acceptance">
      <Field label="Supplier" value={details.supplier} />
      <Field label="Offer version" value={details.version} fact />
      <Field label="Amount" value={details.amount} fact />
      <Field label="Currency" value={details.currency} fact />
      <Field label="Cancellation" value={details.cancellation} />
      <Field label="Refund" value={details.refund} />
      <Field label="Add-ons" value={details.addOns} />
      <Field label="Validity deadline" value={details.validityDeadline} fact />
      <Field label="Simulation status" value={details.simulationStatus} />
      <Field label="Simulation evaluation time" value={details.evaluationTime} fact />
    </dl>
  );
}

function A3AcceptanceGate({
  snapshot,
  selected,
  busy,
  stale,
  disabledReason,
  onAccept,
  onRefresh,
  onInbox,
}: {
  snapshot: BuyerSnapshot;
  selected: RankedOffer | null;
  busy: boolean;
  stale: boolean;
  disabledReason?: string | undefined;
  onAccept: () => void;
  onRefresh: () => void;
  onInbox: () => void;
}) {
  const gate = a3Eligibility(snapshot, selected, { stale });
  const blockedReason = !gate.eligible ? gate.reason : disabledReason;
  return (
    <div className="itaa-stack">
      {!gate.eligible ? (
        <div className="itaa-error" role="alert">
          <Text role="label" as="p">
            Acceptance is blocked
          </Text>
          <p className="itaa-text itaa-text--body">{gate.reason}</p>
          {gate.recoveryAction === "refresh" ? (
            <Button id="a3-recover-refresh" variant="ghost" onClick={onRefresh}>
              {gate.recoveryLabel}
            </Button>
          ) : null}
          {gate.recoveryAction === "inbox" ? (
            <Button id="a3-recover-inbox" variant="ghost" onClick={onInbox}>
              {gate.recoveryLabel}
            </Button>
          ) : null}
          {gate.recoveryAction === "select" ? (
            <p className="itaa-text itaa-text--body">{gate.recoveryLabel}</p>
          ) : null}
        </div>
      ) : null}
      <Button
        id="a3-accept"
        variant="consent"
        busy={busy}
        disabled={!gate.eligible || disabledReason !== undefined}
        disabledReason={blockedReason}
        onClick={onAccept}
      >
        Confirm offer selection
      </Button>
    </div>
  );
}

function Field({ label, value, fact = false }: { label: string; value: string; fact?: boolean }) {
  return (
    <div>
      <dt className="itaa-text itaa-text--meta">{label}</dt>
      <dd className={fact ? "itaa-text itaa-text--fact" : "itaa-text itaa-text--body"}>{value}</dd>
    </div>
  );
}
