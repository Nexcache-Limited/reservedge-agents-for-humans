import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ClosedApiError } from "../api/errors.js";
import type {
  ActivityEntry,
  BuyerSnapshot,
  BuyerSessionState,
  ItaaApi,
  ProgressEventPayload,
} from "../api/types.js";
import { Button, LiveRegion } from "../components/primitives.js";
import {
  CompetitionAuthSheet,
  CompetitionOffers,
  CompetitionReceipt,
  PublicResearch,
  defaultOffersView,
  type OffersView,
} from "../reservedge/competition-offers.js";
import { STATUS_STYLE } from "../reservedge/inbox.js";
import { snapshotToRow } from "../reservedge/map-snapshot.js";
import { usePortfolio } from "../reservedge/portfolio.js";
import {
  idempotencyKeyFor,
  rememberCompetitionIntent,
  rememberSnapshot,
} from "../session/memory.js";
import {
  a3Eligibility,
  activityHeading,
  formatHumanDate,
  formatHumanDateTime,
  progressAnnouncement,
  STATE_LABEL,
} from "../view-models/workspace.js";
import { syncPlanSessionWithSnapshot } from "../intent-first/agent.js";
import { withParked } from "../reservedge/plan-inbox.js";

const TABS = ["request", "research", "offers", "activity"] as const;
type WorkspaceTab = (typeof TABS)[number];
const TAB_LABEL: Record<WorkspaceTab, string> = {
  request: "Request",
  research: "Research",
  offers: "Offers",
  activity: "Activity",
};

type DialogKind = "modify" | "cancel" | "delete" | "replace" | "auth";

export function LiveParkingWorkspace({
  api,
  confirmationRoute = false,
  intentId: intentIdProp,
}: {
  api: ItaaApi;
  confirmationRoute?: boolean;
  intentId?: string;
}) {
  const params = useParams();
  const intentId = intentIdProp ?? params.intentId ?? "";
  const navigate = useNavigate();
  const {
    setIntents,
    setSelectedId,
    planSession,
    setPlanSession,
    setParkedSessions,
    setObjective,
  } = usePortfolio();
  const [snapshot, setSnapshot] = useState<BuyerSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState("");
  const [tab, setTab] = useState<WorkspaceTab>("request");
  const [ov, setOv] = useState<OffersView>("reco");
  const [selectedOfferId, setSelectedOfferId] = useState<string | null>(null);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [dlg, setDlg] = useState<DialogKind | null>(null);
  const [progressEvents, setProgressEvents] = useState<ProgressEventPayload[]>([]);
  const inflight = useRef(false);
  const progressRef = useRef<{ close: () => void } | null>(null);
  const pulledWorkspace = useRef("");

  const applySnapshot = useCallback(
    (next: BuyerSnapshot, syncInbox = true) => {
      setSnapshot(next);
      rememberSnapshot(next);
      rememberCompetitionIntent(next.intentId);
      setSelectedOfferId((current) => current ?? next.recommendedOfferId);
      setSelectedId(next.intentId);
      setPlanSession((current) =>
        current == null ? current : syncPlanSessionWithSnapshot(current, next),
      );
      if (!syncInbox) {
        return;
      }
      setIntents((current) => {
        const row = snapshotToRow(next);
        const rest = current.filter((item) => item.id !== row.id);
        return [row, ...rest];
      });
    },
    [setIntents, setPlanSession, setSelectedId],
  );

  const load = useCallback(async () => {
    if (intentId === "") {
      setLoading(false);
      setSnapshot(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const next = await api.getOwnedIntent(intentId);
      applySnapshot(next, false);
      setNeedsRefresh(false);
      setTab(tabFor(next.state));
      setOv(defaultOffersView(next.state, false));
      setLive(`Intent is ${STATE_LABEL[next.state]}.`);
    } catch (caught) {
      setError(caught instanceof ClosedApiError ? caught.message : "Unable to load this intent.");
      setSnapshot(null);
    } finally {
      setLoading(false);
    }
  }, [api, applySnapshot, intentId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (snapshot === null) {
      return;
    }
    const parking = planSession?.agent?.domains?.parking;
    if (parking?.intentId !== snapshot.intentId) {
      return;
    }
    const key = `${snapshot.intentId}:${parking.completeness}:${snapshot.state}`;
    if (pulledWorkspace.current === key) {
      return;
    }
    if (parking.completeness === "accepted" && snapshot.state === "OFFERS_RANKED") {
      pulledWorkspace.current = key;
      void api.getOwnedIntent(snapshot.intentId).then((next) => {
        applySnapshot(next);
        if (next.state === "ACCEPTANCE_RECORDED") {
          setDlg("auth");
        }
      });
    }
    if (
      parking.completeness === "authorized" &&
      snapshot.state !== "TRANSACTION_AUTHORIZED_SIMULATED"
    ) {
      pulledWorkspace.current = key;
      void api.getOwnedIntent(snapshot.intentId).then((next) => {
        applySnapshot(next);
        if (next.state === "TRANSACTION_AUTHORIZED_SIMULATED") {
          navigate(`/intents/${next.intentId}/confirmation`);
        }
      });
    }
  }, [api, applySnapshot, navigate, planSession?.agent?.domains?.parking, snapshot]);

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
    async (action: () => Promise<BuyerSnapshot>) => {
      if (inflight.current || busy) {
        return;
      }
      inflight.current = true;
      setBusy(true);
      setError(null);
      try {
        const next = await action();
        applySnapshot(next);
        setNeedsRefresh(false);
        setTab(tabFor(next.state));
        setOv((current) =>
          next.state === "OFFERS_RANKED" && current === "progress"
            ? "progress"
            : defaultOffersView(next.state, false),
        );
        setLive(`Updated to ${STATE_LABEL[next.state]}.`);
        if (next.state === "ACCEPTANCE_RECORDED") {
          setDlg("auth");
        }
        if (next.state === "TRANSACTION_AUTHORIZED_SIMULATED") {
          navigate(`/intents/${next.intentId}/confirmation`);
        }
      } catch (caught) {
        if (caught instanceof ClosedApiError && caught.ambiguous) {
          setNeedsRefresh(true);
          setError(caught.message);
          try {
            applySnapshot(await api.getOwnedIntent(intentId));
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
    [api, applySnapshot, busy, intentId, navigate],
  );

  function backToIntents() {
    setParkedSessions((current) => withParked(current, planSession));
    setPlanSession(null);
    setSelectedId(null);
    setObjective("");
    navigate("/intents/new");
  }

  if (loading) {
    return (
      <div className="re-fade">
        <LiveRegion message="Loading intent." />
        <p className="re-muted">Loading this parking request.</p>
      </div>
    );
  }

  if (snapshot === null) {
    return (
      <div className="re-fade">
        <LiveRegion message={error ?? "Intent not found."} politeness="assertive" />
        <div className="re-card">
          <div className="re-eyebrow">UNKNOWN REQUEST</div>
          <h2 className="re-h2">Unknown intent</h2>
          <p className="re-lead">
            {error ?? "This request is not available in this browser session."}
          </p>
          <button
            type="button"
            className="re-primary itaa-focus-ring"
            onClick={() => navigate("/")}
          >
            Back to intents
          </button>
        </div>
      </div>
    );
  }

  if (confirmationRoute && snapshot.state !== "TRANSACTION_AUTHORIZED_SIMULATED") {
    return <Navigate to={`/intents/${snapshot.intentId}`} replace />;
  }

  const style = STATUS_STYLE[snapshotToRow(snapshot).status];
  const terminal =
    snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED" ||
    snapshot.state === "CANCELLED" ||
    snapshot.state === "SUPERSEDED";
  const cleanDraft = snapshot.state === "AWAITING_REQUIREMENT_CONFIRMATION";
  const pending = snapshot.saved === true && !terminal;
  const liveIntent = !terminal;
  const selected = snapshot.offers.find((item) => item.offerId === selectedOfferId) ?? null;
  const disabledReason = busy
    ? "A request is already in progress."
    : needsRefresh
      ? "Refresh status before another consequential action."
      : undefined;
  const showReceipt = snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED" && tab !== "activity";

  return (
    <div className="re-fade">
      <LiveRegion
        message={live || error || ""}
        politeness={error !== null ? "assertive" : "polite"}
      />
      <p className="re-path-flag re-path-flag--inline">Live competition path</p>
      <div className="re-status-card">
        <div className="re-status-id">
          <span className="re-code">Pk</span>
          <span className="re-pill" style={{ background: style.bg, color: style.fg }}>
            {style.label}
          </span>
        </div>
        <span className="re-status-step">{STATE_LABEL[snapshot.state]}</span>
        <div className="re-status-actions">
          {pending ? (
            <button
              type="button"
              className="re-ghost re-ghost-fill itaa-focus-ring"
              disabled={busy}
              onClick={() => void runMutation(() => api.unsaveIntent(snapshot.intentId))}
            >
              Resume
            </button>
          ) : null}
          {liveIntent ? (
            <>
              <button
                type="button"
                className="re-ghost itaa-focus-ring"
                disabled={busy || snapshot.saved === true}
                onClick={() => void runMutation(() => api.saveIntent(snapshot.intentId))}
              >
                Keep pending
              </button>
              <button
                type="button"
                className="re-ghost itaa-focus-ring"
                disabled={busy}
                onClick={() => setDlg("modify")}
              >
                Modify intent
              </button>
              <button
                type="button"
                className="re-ghost re-ghost-danger itaa-focus-ring"
                disabled={busy}
                onClick={() => setDlg(cleanDraft ? "delete" : "cancel")}
              >
                {cleanDraft ? "Cancel intent" : "Cancel intent"}
              </button>
            </>
          ) : (
            <span className="re-status-note">Kept in history · read-only</span>
          )}
        </div>
      </div>

      {error !== null ? <div className="re-fail">{error}</div> : null}
      {needsRefresh ? (
        <button type="button" className="re-ghost itaa-focus-ring" onClick={() => void load()}>
          Refresh status
        </button>
      ) : null}

      <div className="re-intent-tabs" role="tablist" aria-label="Intent workspace">
        {TABS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={`re-intent-tab itaa-focus-ring${tab === key ? " is-on" : ""}`}
            onClick={() => setTab(key)}
          >
            {TAB_LABEL[key]}
          </button>
        ))}
      </div>

      {tab === "request" && !showReceipt ? (
        <RequestPane
          snapshot={snapshot}
          busy={busy}
          disabledReason={disabledReason}
          onConfirm={() => void runMutation(() => api.intakeConfirm(snapshot.intentId))}
        />
      ) : null}
      {tab === "research" && !showReceipt ? (
        <PublicResearch
          onOffers={() => {
            setTab("offers");
            setOv(snapshot.state === "AWAITING_DISPATCH_APPROVAL" ? "gate" : "reco");
          }}
        />
      ) : null}
      {showReceipt ? (
        <CompetitionReceipt
          snapshot={snapshot}
          onActivity={() => setTab("activity")}
          onInbox={backToIntents}
        />
      ) : null}
      {tab === "offers" && !showReceipt ? (
        <CompetitionOffers
          snapshot={snapshot}
          selected={selected}
          busy={busy}
          stale={needsRefresh}
          disabledReason={disabledReason}
          ov={ov}
          progressEvents={progressEvents}
          onView={setOv}
          onSelect={setSelectedOfferId}
          onRefresh={() => void load()}
          onInbox={backToIntents}
          onPending={() => void runMutation(() => api.saveIntent(snapshot.intentId))}
          onDispatch={() => {
            progressRef.current?.close();
            setProgressEvents([]);
            setOv("progress");
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
            void runMutation(() => api.intakeDispatch(snapshot.intentId));
          }}
          onAccept={() => {
            if (snapshot.state === "ACCEPTANCE_RECORDED") {
              setDlg("auth");
              return;
            }
            if (selected === null) {
              return;
            }
            const gate = a3Eligibility(snapshot, selected, { stale: needsRefresh });
            if (!gate.eligible) {
              return;
            }
            void runMutation(() =>
              api.intakeAccept(snapshot.intentId, {
                offerId: selected.offerId,
                offerVersion: selected.version,
              }),
            );
          }}
          onTake={() => {
            if (snapshot.state === "ACCEPTANCE_RECORDED") {
              setDlg("auth");
              return;
            }
            const recommended =
              snapshot.offers.find((item) => item.offerId === snapshot.recommendedOfferId) ??
              snapshot.offers.find((item) => item.recommended) ??
              selected;
            if (recommended === null || recommended === undefined) {
              return;
            }
            setSelectedOfferId(recommended.offerId);
            const gate = a3Eligibility(snapshot, recommended, { stale: needsRefresh });
            if (!gate.eligible) {
              return;
            }
            void runMutation(() =>
              api.intakeAccept(snapshot.intentId, {
                offerId: recommended.offerId,
                offerVersion: recommended.version,
              }),
            );
          }}
          onAuthorize={() => {
            setDlg("auth");
          }}
        />
      ) : null}
      {tab === "activity" ? <ActivityPane activity={activity} snapshot={snapshot} /> : null}

      {tab !== "activity" ? <ActivityPane activity={activity} snapshot={snapshot} compact /> : null}

      {dlg !== null ? (
        <Overlay onClose={() => setDlg(null)}>
          {dlg === "auth" ? (
            <CompetitionAuthSheet
              snapshot={snapshot}
              busy={busy}
              disabledReason={disabledReason}
              onAuthorize={() => {
                setDlg(null);
                void runMutation(() => api.intakeAuthorize(snapshot.intentId));
              }}
              onClose={() => setDlg(null)}
            />
          ) : null}
          {dlg === "modify" ? (
            <ModifyDialog
              busy={busy}
              title={`Airport parking · ${snapshot.airport}`}
              onEdit={() => {
                setTab("request");
                setDlg(null);
              }}
              onReplace={() => setDlg("replace")}
              onKeepPending={() => {
                setDlg(null);
                void runMutation(async () => {
                  const saved = await api.saveIntent(snapshot.intentId);
                  navigate("/intents/new");
                  return saved;
                });
              }}
              onDiscard={() => {
                setDlg(null);
                if (cleanDraft) {
                  void api.deleteDraft(snapshot.intentId).then(
                    () => {
                      setIntents((current) =>
                        current.filter((item) => item.id !== snapshot.intentId),
                      );
                      navigate("/intents/new/parking");
                    },
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
                void runMutation(async () => {
                  const cancelled = await api.cancelIntent(snapshot.intentId);
                  navigate("/intents/new/parking");
                  return cancelled;
                });
              }}
              onClose={() => setDlg(null)}
            />
          ) : null}
          {dlg === "replace" ? (
            <ConfirmDialog
              title="Start a revised request?"
              body="The original request will be closed and a new draft will be created from the same details. Offers and approvals are not reused."
              confirmLabel="Start revised request"
              busy={busy}
              onConfirm={() => {
                setDlg(null);
                void runMutation(async () => {
                  const result = await api.replaceIntent(
                    snapshot.intentId,
                    idempotencyKeyFor(`replace:${snapshot.intentId}`),
                  );
                  rememberCompetitionIntent(result.draft.intentId);
                  navigate(`/intents/${result.draft.intentId}`);
                  return result.draft;
                });
              }}
              onClose={() => setDlg(null)}
            />
          ) : null}
          {dlg === "delete" ? (
            <ConfirmDialog
              title="Delete this draft?"
              body="This removes the unpublished draft. It cannot be undone. Cancelled requests stay in history; deleted drafts do not."
              confirmLabel="Delete draft"
              busy={busy}
              onConfirm={() => {
                setDlg(null);
                void api.deleteDraft(snapshot.intentId).then(
                  () => {
                    setIntents((current) =>
                      current.filter((item) => item.id !== snapshot.intentId),
                    );
                    navigate("/");
                  },
                  (caught: unknown) => {
                    setError(
                      caught instanceof ClosedApiError
                        ? caught.message
                        : "This draft could not be deleted. Cancel the request instead.",
                    );
                  },
                );
              }}
              onClose={() => setDlg(null)}
            />
          ) : null}
          {dlg === "cancel" ? (
            <ConfirmDialog
              title="Cancel this request?"
              body="Suppliers will not be contacted further. This cannot be undone. The cancelled request stays in history."
              confirmLabel="Cancel request"
              busy={busy}
              onConfirm={() => {
                setDlg(null);
                void runMutation(() => api.cancelIntent(snapshot.intentId));
              }}
              onClose={() => setDlg(null)}
            />
          ) : null}
        </Overlay>
      ) : null}
    </div>
  );
}

function tabFor(state: BuyerSessionState): WorkspaceTab {
  if (
    state === "OFFERS_RANKED" ||
    state === "ACCEPTANCE_RECORDED" ||
    state === "TRANSACTION_AUTHORIZED_SIMULATED"
  ) {
    return "offers";
  }
  if (state === "AWAITING_DISPATCH_APPROVAL") {
    return "offers";
  }
  return "request";
}

function RequestPane({
  snapshot,
  busy,
  disabledReason,
  onConfirm,
}: {
  snapshot: BuyerSnapshot;
  busy: boolean;
  disabledReason?: string | undefined;
  onConfirm: () => void;
}) {
  const awaiting = snapshot.state === "AWAITING_REQUIREMENT_CONFIRMATION";
  return (
    <div className="re-card">
      <div className="re-eyebrow">REQUEST · CONFIRMED FIELDS</div>
      <h3 className="re-h3">Airport parking details</h3>
      <p className="re-muted">
        These confirmed details are locked for this request. Start a revised request to change them.
        The original intake paragraph is not stored on the request.
      </p>
      <dl className="re-live-fields">
        <Field label="Airport" value={snapshot.airport} />
        <Field
          label="Window start"
          value={
            snapshot.windowStart ? formatHumanDate(snapshot.windowStart) : "Not on this snapshot"
          }
        />
        <Field
          label="Window end"
          value={snapshot.windowEnd ? formatHumanDate(snapshot.windowEnd) : "Not on this snapshot"}
        />
        <Field label="Category" value="Airport parking" />
        <Field label="Expires" value={formatHumanDate(snapshot.expiresAt)} />
      </dl>
      {snapshot.state === "CANCELLED" || snapshot.state === "SUPERSEDED" ? (
        <p className="re-lead">
          {snapshot.state === "SUPERSEDED"
            ? "This request was replaced with a revised request."
            : "This request was cancelled. Start a new demonstration if you still need parking."}
        </p>
      ) : null}
      {awaiting ? (
        <>
          <p className="re-lead">
            You are confirming what Reservedge should research. No supplier has been contacted yet.
            Opening this page is not approval.
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
        </>
      ) : null}
    </div>
  );
}

function ActivityPane({
  activity,
  snapshot,
  compact = false,
}: {
  activity: ActivityEntry[];
  snapshot: BuyerSnapshot;
  compact?: boolean;
}) {
  if (activity.length === 0) {
    return compact ? null : (
      <div className="re-card">
        <div className="re-eyebrow">ACTIVITY</div>
        <p className="re-muted">No activity recorded for this request yet.</p>
      </div>
    );
  }
  return (
    <div className={compact ? "re-live-activity-strip" : "re-card"}>
      {compact ? (
        <div className="re-eyebrow">LATEST ACTIVITY</div>
      ) : (
        <div className="re-eyebrow">ACTIVITY</div>
      )}
      <ol className="re-timeline">
        {activity.map((entry) => (
          <li key={`${entry.occurredAt}-${entry.label}`}>
            <span className="re-muted">{formatHumanDateTime(entry.occurredAt)}</span>
            <span> {activityHeading(entry.label, snapshot)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ModifyDialog({
  title,
  busy,
  onEdit,
  onReplace,
  onKeepPending,
  onDiscard,
  onClose,
}: {
  title: string;
  busy: boolean;
  onEdit: () => void;
  onReplace: () => void;
  onKeepPending: () => void;
  onDiscard: () => void;
  onClose: () => void;
}) {
  return (
    <>
      <h2 id="confirm-title" className="re-h3">
        Modify this intent?
      </h2>
      <p className="re-lead">
        Confirmed parking fields are locked. Starting a revised request closes this one and mints a
        fresh draft from the same details, without copying offers. Keep it pending if you only want
        to start something else. Discarding a draft deletes it; a disclosed request is cancelled
        into history instead.
      </p>
      <p className="re-cap">{title}</p>
      <div className="re-stack">
        <button
          type="button"
          className="re-ghost-fill itaa-focus-ring"
          disabled={busy}
          onClick={onEdit}
        >
          Review the requirement instead
        </button>
        <button
          type="button"
          className="re-primary itaa-focus-ring"
          disabled={busy}
          onClick={onReplace}
        >
          Start a revised request
        </button>
        <button
          type="button"
          className="re-ghost itaa-focus-ring"
          disabled={busy}
          onClick={onKeepPending}
        >
          Keep it pending and start a new one
        </button>
        <button
          type="button"
          className="re-ghost re-ghost-danger itaa-focus-ring"
          disabled={busy}
          onClick={onDiscard}
        >
          Discard this one and start fresh
        </button>
        <button type="button" className="re-text-btn itaa-focus-ring" onClick={onClose}>
          Never mind
        </button>
      </div>
    </>
  );
}

function ConfirmDialog({
  title,
  body,
  confirmLabel,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <>
      <h2 id="confirm-title" className="re-h3">
        {title}
      </h2>
      <p className="re-lead">{body}</p>
      <div className="re-row-btns">
        <button
          type="button"
          className="re-danger itaa-focus-ring"
          disabled={busy}
          onClick={onConfirm}
        >
          {confirmLabel}
        </button>
        <button type="button" className="re-ghost itaa-focus-ring" onClick={onClose}>
          Keep request
        </button>
      </div>
    </>
  );
}

function Overlay({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  function onBackdrop(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }
  function onKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      onClose();
    }
  }
  return createPortal(
    <div className="re-overlay" role="presentation" onClick={onBackdrop} onKeyDown={onKey}>
      <div className="re-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        {children}
      </div>
    </div>,
    document.body,
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="re-muted">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
