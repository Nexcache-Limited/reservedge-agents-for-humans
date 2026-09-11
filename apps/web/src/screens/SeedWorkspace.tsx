import { useEffect, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { STATUS_STYLE, type DomainId, type IntentRow } from "../reservedge/inbox.js";
import { landingTab, usePortfolio } from "../reservedge/portfolio.js";
import { DOMAINS, OFFERS, REQ_KIND } from "../reservedge/prototype-fixtures.js";

const TABS = ["request", "research", "offers", "activity"] as const;
const TAB_LABEL = {
  request: "Request",
  research: "Research",
  offers: "Offers",
  activity: "Activity",
};
const OVS = [
  { key: "gate", label: "Disclosure record" },
  { key: "reco", label: "Recommendation" },
  { key: "compare", label: "Compare offers" },
] as const;

type PrototypeDomainId = Exclude<DomainId, "stay">;

function isPrototypeDomain(id: DomainId): id is PrototypeDomainId {
  return id === "parking" || id === "rental" || id === "ents";
}

export function SeedWorkspace({ selected }: { selected: IntentRow | null }) {
  const navigate = useNavigate();
  const { setIntents } = usePortfolio();
  const [tab, setTab] = useState<(typeof TABS)[number]>("offers");
  const [ov, setOv] = useState("reco");
  const [dlg, setDlg] = useState<null | "auth" | "reask" | "modify" | "cancel">(null);
  const [reasked, setReasked] = useState(false);

  useEffect(() => {
    setTab(landingTab(selected));
    setOv(selected?.stage === "gate" ? "gate" : "reco");
    setDlg(null);
  }, [selected?.id]);

  if (selected === null) {
    return (
      <div className="re-welcome">
        <div className="re-eyebrow">COMPETITION START</div>
        <h2 className="re-h2">Start a new parking request</h2>
        <p>
          This session opens on a blank request, not a sample recommendation. Create an airport
          parking intent, or pick a saved sample from the list when you want the prototype.
        </p>
        <button
          type="button"
          className="re-primary itaa-focus-ring"
          onClick={() => navigate("/intents/new")}
        >
          New intent
        </button>
      </div>
    );
  }

  const domainId = selected.domain;
  if (!isPrototypeDomain(domainId)) {
    return (
      <div className="re-welcome">
        <div className="re-eyebrow">CONVERSATION</div>
        <h2 className="re-h2">Continue in the running workspace</h2>
        <p>
          Stay, parking, and rental cards live in the conversational workspace, not this seed view.
        </p>
        <button
          type="button"
          className="re-primary itaa-focus-ring"
          onClick={() => navigate("/intents/clarify")}
        >
          Open conversation
        </button>
      </div>
    );
  }

  const domain = DOMAINS[domainId];
  const offers = OFFERS[domainId];
  const style = STATUS_STYLE[selected.status];
  const live = selected.status !== "done" && selected.status !== "cancelled";
  const pending = selected.status === "pending" || selected.status === "draft";
  const showReco =
    tab === "offers" && ov === "reco" && selected.stage !== "gate" && selected.status !== "done";
  const showReceipt = tab === "offers" && selected.status === "done" && ov === "reco";
  const showGate = tab === "offers" && selected.stage === "gate";
  const showRecord = tab === "offers" && selected.stage !== "gate" && ov === "gate";
  const showCompare = tab === "offers" && ov === "compare" && selected.stage !== "gate";
  const showProgress = tab === "offers" && ov === "progress";
  const showReask = tab === "offers" && ov === "reask";
  const incomplete = Boolean(offers.incomplete) && !reasked && selected.domain === "rental";
  const demo = selected.domain !== "parking";
  const intent = selected;

  function patch(fields: Partial<IntentRow>) {
    setIntents((current) =>
      current.map((row) => (row.id === intent.id ? { ...row, ...fields } : row)),
    );
  }

  function remove() {
    setIntents((current) => current.filter((row) => row.id !== intent.id));
    setDlg(null);
    navigate("/");
  }

  return (
    <div className="re-fade">
      {demo ? (
        <p className="re-demo-flag re-demo-flag--inline">
          Simulated demonstration — not a real supplier, booking, or payment.
        </p>
      ) : null}
      <div className="re-status-card">
        <div className="re-status-id">
          <span className="re-code">{domain.code}</span>
          <span className="re-pill" style={{ background: style.bg, color: style.fg }}>
            {style.label}
          </span>
        </div>
        <span className="re-status-step">{selected.step}</span>
        <div className="re-status-actions">
          {pending ? (
            <button
              type="button"
              className="re-ghost re-ghost-fill itaa-focus-ring"
              onClick={() =>
                patch({
                  status: selected.stage === "offers" ? "decision" : "running",
                  step: `Resumed · ${selected.stage} tab`,
                  sub: "Resumed just now.",
                })
              }
            >
              Resume
            </button>
          ) : null}
          {live ? (
            <>
              <button
                type="button"
                className="re-ghost itaa-focus-ring"
                onClick={() =>
                  patch({
                    status: "pending",
                    step: `Paused by you at ${selected.stage}`,
                    sub: "Paused. Nothing further was shared.",
                  })
                }
              >
                Keep pending
              </button>
              <button
                type="button"
                className="re-ghost itaa-focus-ring"
                onClick={() => setDlg("modify")}
              >
                Modify intent
              </button>
              <button
                type="button"
                className="re-ghost re-ghost-danger itaa-focus-ring"
                onClick={() => setDlg("cancel")}
              >
                Cancel intent
              </button>
            </>
          ) : (
            <span className="re-status-note">Kept in history · read-only</span>
          )}
        </div>
      </div>

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

      {tab === "request" ? <RequestPane domain={domainId} /> : null}
      {tab === "research" ? (
        <ResearchPane
          offers={offers}
          onOffers={() => {
            setTab("offers");
            setOv(selected.stage === "gate" ? "gate" : "reco");
          }}
        />
      ) : null}
      {showGate ? (
        <GatePane
          offers={offers}
          onHold={() => {
            patch({
              stage: "offers",
              status: "decision",
              step: "Decision ready · offers tab",
              sub: "Offers received. A decision is waiting.",
            });
            setOv("progress");
          }}
          onPending={() =>
            patch({
              status: "pending",
              step: "Paused by you at gate",
              sub: "Paused. Nothing further was shared.",
            })
          }
        />
      ) : null}
      {showRecord ? (
        <RecordPane
          offers={offers}
          when={selected.domain === "rental" ? "29 Aug · 13:31" : "29 Aug · 14:06"}
          ov={ov}
          setOv={setOv}
        />
      ) : null}
      {showProgress ? <ProgressPane offers={offers} onSee={() => setOv("reco")} /> : null}
      {showReco ? (
        <RecoPane
          offers={offers}
          ov={ov}
          setOv={setOv}
          onAuth={() => setDlg("auth")}
          onCompare={() => setOv("compare")}
        />
      ) : null}
      {showCompare ? (
        <ComparePane
          offers={offers}
          reasked={reasked && selected.domain === "rental"}
          incomplete={incomplete}
          ov={ov}
          setOv={setOv}
          onReask={() => setDlg("reask")}
        />
      ) : null}
      {showReask ? (
        <ReaskPane
          offers={offers}
          onSend={() => {
            patch({
              step: "Decision ready · all three offers complete",
              sub: `3 offers · complete · recommended ${offers.recoTotal}`,
            });
            setReasked(true);
            setOv("compare");
          }}
          onLeave={() => setOv("compare")}
        />
      ) : null}
      {showReceipt ? (
        <ReceiptPane
          offers={selected.id === "jfkjul" ? jfkJulReceipt(offers) : offers}
          onActivity={() => setTab("activity")}
        />
      ) : null}
      {tab === "activity" ? (
        <ActivityPane offers={offers} reasked={reasked && selected.domain === "rental"} />
      ) : null}

      {dlg === "auth" ? (
        <Overlay onClose={() => setDlg(null)}>
          <div className="re-sim-strip">
            <b>SIMULATION</b>
            <br />
            No card is charged and no reservation is made in this build.
          </div>
          <div className="re-eyebrow">APPROVAL 2 OF 2 · TRANSACTION</div>
          <h3 className="re-h3">Authorize this purchase</h3>
          <p className="re-lead">A separate decision from the disclosure you approved earlier.</p>
          <div className="re-kv">
            <div>
              <span>Supplier</span>
              <b>{offers.recoName}</b>
            </div>
            <div>
              <span>What</span>
              <b>{offers.authWhat}</b>
            </div>
            <div>
              <span>Amount</span>
              <b className="re-mono">{offers.recoTotal}</b>
            </div>
          </div>
          <div className="re-muted-card">
            <b>This authorizes:</b> {offers.authDoes}
            <br />
            <b>It does not authorize:</b> recurring bookings, price changes, or contact with the
            other suppliers.
          </div>
          <button
            type="button"
            className="re-primary itaa-focus-ring"
            style={{ width: "100%", marginTop: 18 }}
            onClick={() => {
              patch({
                status: "done",
                stage: "done",
                step: "Completed · simulated receipt",
                sub: `${offers.recoTotal} · ref ${offers.receiptRef}`,
                canDelete: false,
              });
              setDlg(null);
              setOv("reco");
            }}
          >
            Authorize {offers.recoTotal}
          </button>
          <div style={{ textAlign: "center" }}>
            <button
              type="button"
              className="re-text-btn itaa-focus-ring"
              onClick={() => setDlg(null)}
            >
              Not now
            </button>
          </div>
        </Overlay>
      ) : null}

      {dlg === "modify" ? (
        <Overlay onClose={() => setDlg(null)}>
          <h3 className="re-h3">Modify this intent?</h3>
          <p className="re-lead">
            Small corrections are better made in the Request tab — the requirement stays editable
            there for the intent&apos;s whole life. Starting fresh deletes the requirement, research
            and offers for <b>{selected.title}</b>.
          </p>
          <div className="re-stack">
            <button
              type="button"
              className="re-ghost-fill itaa-focus-ring"
              onClick={() => {
                setTab("request");
                setDlg(null);
              }}
            >
              Edit the requirement instead
            </button>
            <button
              type="button"
              className="re-primary itaa-focus-ring"
              onClick={() => {
                remove();
                navigate(`/intents/new/${selected.domain}`);
              }}
            >
              Discard this one and start fresh
            </button>
            <button
              type="button"
              className="re-ghost itaa-focus-ring"
              onClick={() => {
                patch({
                  status: "pending",
                  step: "Kept pending by you",
                  sub: "Kept pending while you work on something else.",
                });
                setDlg(null);
                navigate("/intents/new");
              }}
            >
              Keep it pending and start a new one
            </button>
            <button
              type="button"
              className="re-text-btn itaa-focus-ring"
              onClick={() => setDlg(null)}
            >
              Never mind
            </button>
          </div>
        </Overlay>
      ) : null}

      {dlg === "cancel" ? (
        <Overlay onClose={() => setDlg(null)}>
          <h3 className="re-h3">Delete this intent?</h3>
          <p className="re-lead">
            <b>{selected.title}</b> and everything Reservedge researched for it are removed.
            Suppliers are not contacted again, and any offers they made simply expire.
          </p>
          <p className="re-cap">
            Completed intents stay in history. Deleted ones do not — the audit trail keeps a single
            &quot;intent deleted&quot; entry.
          </p>
          <div className="re-row-btns">
            <button type="button" className="re-danger itaa-focus-ring" onClick={remove}>
              Delete intent
            </button>
            <button type="button" className="re-ghost itaa-focus-ring" onClick={() => setDlg(null)}>
              Keep it
            </button>
          </div>
        </Overlay>
      ) : null}

      {dlg === "reask" ? (
        <Overlay onClose={() => setDlg(null)}>
          <h3 className="re-h3">Answer and re-ask?</h3>
          <p className="re-lead">
            {offers.incomplete?.name} needs one more thing to complete its offer. Answering adds a
            field to the request, so this counts as a new disclosure and needs your approval again.
          </p>
          <div className="re-muted-card">
            <b>Would send:</b> payment method type (card or debit), so a deposit hold can be quoted.
            <br />
            <b>Still withheld:</b> card number, name, licence number.
          </div>
          <div className="re-stack" style={{ marginTop: 16 }}>
            <button
              type="button"
              className="re-primary itaa-focus-ring"
              onClick={() => {
                setDlg(null);
                setOv("reask");
              }}
            >
              Review the new disclosure
            </button>
            <button type="button" className="re-ghost itaa-focus-ring" onClick={() => setDlg(null)}>
              Leave it incomplete
            </button>
          </div>
        </Overlay>
      ) : null}
    </div>
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
      <div className="re-modal" role="dialog" aria-modal="true">
        {children}
      </div>
    </div>,
    document.body,
  );
}

function jfkJulReceipt(offers: (typeof OFFERS)["parking"]) {
  return {
    ...offers,
    recoTotal: "$44.10",
    receiptRef: "SIM-3B77",
  };
}

function OfferPills({ ov, setOv }: { ov: string; setOv: (key: string) => void }) {
  return (
    <div className="re-ov">
      {OVS.map((item) => (
        <button
          key={item.key}
          type="button"
          className={`re-ov-btn itaa-focus-ring${ov === item.key ? " is-on" : ""}`}
          onClick={() => setOv(item.key)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

const DEFAULT_KIND = {
  pill: "High",
  bg: "var(--green-soft)",
  fg: "var(--green)",
  note: "var(--ws-ink-2)",
  row: "transparent",
};

function RequestPane({ domain }: { domain: PrototypeDomainId }) {
  const spec = DOMAINS[domain];
  return (
    <div className="re-req-grid">
      <div className="re-card re-card-flush">
        <div className="re-req-head">
          <div className="re-eyebrow">REQUIREMENT · CONFIRMED BY YOU</div>
          <span>Editable</span>
        </div>
        {spec.reqRows.map((row, index) => {
          const kind = REQ_KIND[row.kind || "ok"] ?? DEFAULT_KIND;
          const last = index === spec.reqRows.length - 1;
          return (
            <div
              key={row.label}
              className="re-req-confirmed"
              style={{
                background: kind.row,
                borderBottom: last ? "0" : "1px solid var(--ws-border-2)",
              }}
            >
              <div>
                <div className="re-eyebrow">{row.label}</div>
                {row.tags ? (
                  <div className="re-tags">
                    {row.tags.map((tag) => (
                      <span key={tag} className="re-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : (
                  <>
                    <div className="re-req-strong">{row.value}</div>
                    <div className="re-req-note" style={{ color: kind.note }}>
                      {row.note}
                    </div>
                    {row.fix ? (
                      <div className="re-chips" style={{ marginTop: 9 }}>
                        <button type="button" className="re-ghost-fill itaa-focus-ring">
                          Correct
                        </button>
                        <button type="button" className="re-ghost itaa-focus-ring">
                          It&apos;s right
                        </button>
                      </div>
                    ) : null}
                  </>
                )}
              </div>
              {row.tags ? null : (
                <span className="re-pill" style={{ background: kind.bg, color: kind.fg }}>
                  {kind.pill}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="re-stack">
        <div className="re-card">
          <div className="re-eyebrow">{spec.sideEyebrow}</div>
          {spec.sideTier ? (
            <div
              className="re-pill"
              style={{ background: spec.sideTierBg, color: spec.sideTierFg, marginTop: 10 }}
            >
              {spec.sideTier}
            </div>
          ) : null}
          <p className="re-muted">{spec.sideBody}</p>
          {spec.sideBtn ? (
            <button type="button" className="re-chip-btn itaa-focus-ring" style={{ marginTop: 10 }}>
              {spec.sideBtn}
            </button>
          ) : null}
        </div>
        {spec.sideNote ? <div className="re-muted-card">{spec.sideNote}</div> : null}
        <div className="re-warn">
          <b>Editing after dispatch has a consequence.</b> Change a field now and the offers you
          have received stop applying — suppliers would need a fresh, re-approved request.
        </div>
      </div>
    </div>
  );
}

function ResearchPane({
  offers,
  onOffers,
}: {
  offers: (typeof OFFERS)["parking"];
  onOffers: () => void;
}) {
  return (
    <div className="re-two">
      <div className="re-card re-stack">
        <div className="re-eyebrow">PUBLIC RESEARCH · AUTONOMOUS</div>
        <div className="re-check">
          <span className="re-dot re-dot-ok">✓</span>
          {offers.resLine1}
        </div>
        <div className="re-check">
          <span className="re-dot re-dot-ok">✓</span>
          {offers.resLine2}
        </div>
        <div className="re-check">
          <span className="re-dot re-dot-info">•</span>Normalising taxes and fees
        </div>
        <div className="re-check re-muted">
          <span className="re-dot">–</span>Cancellation terms
        </div>
        <p className="re-cap">
          Nothing here involves a supplier. This is public information, gathered so private offers
          have something to be judged against.
        </p>
      </div>
      <div className="re-stack">
        <div className="re-card">
          <div className="re-eyebrow">PUBLIC MARKET</div>
          <div className="re-range">
            <span className="re-mono re-range-num">{offers.range}</span>
            <span className="re-muted">{offers.rangeNote}</span>
          </div>
          <div className="re-track">
            <div className="re-track-fill" />
          </div>
        </div>
        <div className="re-fail">
          <div>One source didn&apos;t respond</div>
          <div className="re-muted">{offers.fail}</div>
        </div>
        <button type="button" className="re-primary itaa-focus-ring" onClick={onOffers}>
          Continue to the offers tab
        </button>
      </div>
    </div>
  );
}

function GatePane({
  offers,
  onHold,
  onPending,
}: {
  offers: (typeof OFFERS)["parking"];
  onHold: () => void;
  onPending: () => void;
}) {
  return (
    <div>
      <div className="re-dark-block">
        <div className="re-eyebrow">APPROVAL 1 OF 2 · DISCLOSURE</div>
        <h3 className="re-h3">What suppliers will see</h3>
        <p>{offers.gateIntro}</p>
      </div>
      <SentHeld offers={offers} />
      <div className="re-meta-strip">
        <div>
          <div>Purpose</div>
          <b>{offers.gatePurpose}</b>
        </div>
        <div>
          <div>Recipients</div>
          <b>3 suppliers, isolated from each other</b>
        </div>
        <div>
          <div>Expires</div>
          <b>In 30 minutes</b>
        </div>
        <div>
          <div>Tier</div>
          <b>{offers.gateTier}</b>
        </div>
      </div>
      <div className="re-composer-actions" style={{ marginTop: 16 }}>
        <button type="button" className="re-primary itaa-focus-ring" onClick={onHold}>
          Send this request
        </button>
        <button type="button" className="re-ghost itaa-focus-ring" onClick={onPending}>
          Not now — keep pending
        </button>
      </div>
    </div>
  );
}

function RecordPane({
  offers,
  when,
  ov,
  setOv,
}: {
  offers: (typeof OFFERS)["parking"];
  when: string;
  ov: string;
  setOv: (key: string) => void;
}) {
  return (
    <div>
      <OfferPills ov={ov} setOv={setOv} />
      <div className="re-record-intro">
        <div className="re-eyebrow" style={{ color: "var(--green)" }}>
          DISCLOSURE APPROVED BY YOU · {when}
        </div>
        <h3 className="re-h3">What was sent, and what was not</h3>
        <p className="re-lead">
          A record, not an action. This approval has already been used; asking these suppliers
          anything further needs a new one.
        </p>
      </div>
      <SentHeld offers={offers} />
    </div>
  );
}

function SentHeld({ offers }: { offers: (typeof OFFERS)["parking"] }) {
  return (
    <div className="re-two">
      <div className="re-card">
        <div className="re-eyebrow" style={{ color: "var(--green)", marginBottom: 12 }}>
          SENT · {offers.sent.length} FIELDS
        </div>
        <div className="re-stack">
          {offers.sent.map((row) => (
            <div key={row.label} className="re-sent">
              <span style={{ color: "var(--green)" }}>✓</span>
              <div>
                <b>{row.label}</b>
                <div className="re-muted">{row.why}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="re-card">
        <div className="re-eyebrow" style={{ marginBottom: 12 }}>
          WITHHELD · {offers.held.length} FIELDS
        </div>
        <div className="re-stack re-muted">
          {offers.held.map((row) => (
            <div key={row.label} className="re-sent">
              <span>✕</span>
              {row.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ProgressPane({
  offers,
  onSee,
}: {
  offers: (typeof OFFERS)["parking"];
  onSee: () => void;
}) {
  return (
    <div>
      <h3 className="re-h3">Suppliers are answering</h3>
      <p className="re-lead">Each one answers alone. None of them can see the others, or you.</p>
      <div className="re-three">
        {offers.suppliers.map((supplier) => (
          <div key={supplier.code} className="re-card">
            <span className="re-avatar" style={{ background: supplier.grad }}>
              {supplier.code}
            </span>
            <div className="re-supplier-name">{supplier.name}</div>
            <div className="re-muted">{supplier.state}</div>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="re-primary itaa-focus-ring"
        style={{ marginTop: 16 }}
        onClick={onSee}
      >
        See the recommendation
      </button>
    </div>
  );
}

function RecoPane({
  offers,
  ov,
  setOv,
  onAuth,
  onCompare,
}: {
  offers: (typeof OFFERS)["parking"];
  ov: string;
  setOv: (key: string) => void;
  onAuth: () => void;
  onCompare: () => void;
}) {
  return (
    <div>
      <OfferPills ov={ov} setOv={setOv} />
      <div className="re-reco">
        <div className="re-reco-main">
          <div className="re-reco-top">
            <span
              className="re-pill"
              style={{ background: "var(--ws-accent-soft)", color: "var(--ws-accent-d)" }}
            >
              Recommended
            </span>
            <span className="re-mono re-muted">valid {offers.recoValid}</span>
          </div>
          <h3 className="re-h3" style={{ fontSize: 23, margin: "11px 0 5px" }}>
            {offers.recoName}
          </h3>
          <p className="re-lead">{offers.recoWhy}</p>
          <div className="re-price">
            <span className="re-mono re-price-num">{offers.recoTotal}</span>
            <span className="re-muted">total, taxes and fees included</span>
          </div>
          <div className="re-muted">{offers.recoBreak}</div>
          <hr className="re-hr" />
          <div className="re-dims">
            {offers.dims.map((dim) => (
              <div key={dim.label}>
                <div className="re-muted">{dim.label}</div>
                <div style={{ fontWeight: 600, color: dim.color }}>{dim.value}</div>
              </div>
            ))}
          </div>
          <hr className="re-hr" />
          <div className="re-stack">
            <div>
              <span style={{ color: "var(--green)" }}>+ </span>
              {offers.plus}
            </div>
            <div>
              <span style={{ color: "var(--amber)" }}>– </span>
              {offers.minus}
            </div>
            <div>
              <span className="re-muted">? </span>
              {offers.gap}
            </div>
          </div>
          <div className="re-composer-actions" style={{ marginTop: 20 }}>
            <button type="button" className="re-primary itaa-focus-ring" onClick={onAuth}>
              Take this one
            </button>
            <button type="button" className="re-ghost itaa-focus-ring" onClick={onCompare}>
              Compare all three
            </button>
          </div>
        </div>
        <div className="re-stack">
          <div className="re-card">
            <div className="re-eyebrow">WHY THIS ONE</div>
            <div className="re-stack" style={{ marginTop: 11 }}>
              {offers.reasons.map((reason) => (
                <div key={reason.head}>
                  <b>{reason.head}</b> <span className="re-muted">{reason.body}</span>
                </div>
              ))}
            </div>
            <hr className="re-hr" />
            <div className="re-muted">{offers.recoSwitch}</div>
          </div>
          <div className="re-muted-card">
            Reservedge&apos;s opinion on the offers received, not a rating or a financial score.
            Check the terms before authorizing.
          </div>
        </div>
      </div>
    </div>
  );
}

function ComparePane({
  offers,
  reasked,
  incomplete,
  ov,
  setOv,
  onReask,
}: {
  offers: (typeof OFFERS)["parking"];
  reasked: boolean;
  incomplete: boolean;
  ov: string;
  setOv: (key: string) => void;
  onReask: () => void;
}) {
  const rows = reasked
    ? offers.rows.map((row) =>
        row.label === "Deposit hold"
          ? { ...row, c: "$400 · credit only", cc: "var(--ws-ink)" }
          : row.label === "Evidence checked"
            ? { ...row, c: "●●●○○ 3 of 5" }
            : row,
      )
    : offers.rows;
  return (
    <div>
      <OfferPills ov={ov} setOv={setOv} />
      <p className="re-lead">
        Public market for the same window: {offers.range}. Suppliers cannot see this table or each
        other.
      </p>
      <div className="re-grid-wrap">
        <div className="re-cmp">
          <div className="re-cmp-head">
            <div>DIMENSION</div>
            <div>
              {offers.cols[0]} <span>· recommended</span>
            </div>
            <div>{offers.cols[1]}</div>
            <div>{offers.cols[2]}</div>
            <div>Public market</div>
          </div>
          {rows.map((row) => (
            <div key={row.label} className="re-cmp-row">
              <div>{row.label}</div>
              <div style={{ color: row.ca, fontWeight: row.label === "Total, all in" ? 600 : 400 }}>
                {row.a}
              </div>
              <div style={{ color: row.cb }}>{row.b}</div>
              <div style={{ color: row.cc }}>{row.c}</div>
              <div>{row.pub}</div>
            </div>
          ))}
        </div>
      </div>
      {reasked ? (
        <div className="re-ready" style={{ marginTop: 14 }}>
          <b>The added field was sent to CityDrive only.</b> {offers.reaskResult}
        </div>
      ) : null}
      {incomplete && offers.incomplete ? (
        <div
          className="re-warn"
          style={{ marginTop: 14, display: "flex", gap: 14, alignItems: "center" }}
        >
          <div style={{ flex: 1 }}>
            <div>
              <b>{offers.incomplete.name}</b> couldn&apos;t answer one dimension
            </div>
            <div className="re-muted">
              {offers.incomplete.why} The offer is marked incomplete rather than guessed at, and it
              can&apos;t be recommended while a must-have is unanswered.
            </div>
          </div>
          <button type="button" className="re-ghost-fill itaa-focus-ring" onClick={onReask}>
            Answer and re-ask
          </button>
        </div>
      ) : null}
    </div>
  );
}

function ReaskPane({
  offers,
  onSend,
  onLeave,
}: {
  offers: (typeof OFFERS)["parking"];
  onSend: () => void;
  onLeave: () => void;
}) {
  return (
    <div>
      <div className="re-dark-block">
        <div className="re-eyebrow">ADDED DISCLOSURE · 1 FIELD</div>
        <h3 className="re-h3">One more field, one more approval</h3>
        <p>
          The approval you already gave has been used. Adding a field to the request is a new
          disclosure, so it is asked separately — and it goes to one supplier, not all three.
        </p>
      </div>
      <div className="re-two">
        <div className="re-card">
          <div className="re-eyebrow" style={{ color: "var(--green)" }}>
            SENT · 1 FIELD
          </div>
          {(offers.reaskSent || []).map((row) => (
            <div key={row.label} className="re-sent">
              <span style={{ color: "var(--green)" }}>✓</span>
              <div>
                <b>{row.label}</b>
                <div className="re-muted">{row.why}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="re-card">
          <div className="re-eyebrow">
            STILL WITHHELD · {(offers.reaskHeld || []).length} FIELDS
          </div>
          {(offers.reaskHeld || []).map((row) => (
            <div key={row.label} className="re-sent re-muted">
              <span>✕</span>
              {row.label}
            </div>
          ))}
        </div>
      </div>
      <div className="re-stack" style={{ marginTop: 14 }}>
        <button type="button" className="re-primary itaa-focus-ring" onClick={onSend}>
          Send this one field
        </button>
        <button type="button" className="re-ghost itaa-focus-ring" onClick={onLeave}>
          Leave it incomplete
        </button>
      </div>
    </div>
  );
}

function ReceiptPane({
  offers,
  onActivity,
}: {
  offers: (typeof OFFERS)["parking"];
  onActivity: () => void;
}) {
  return (
    <div className="re-receipt">
      <div className="re-receipt-head">
        <span className="re-check-disc">✓</span>
        <div>
          <h3 className="re-h3" style={{ margin: 0 }}>
            Authorization recorded
          </h3>
          <p className="re-muted">Simulated. No card charged, nothing reserved.</p>
        </div>
      </div>
      <div className="re-receipt-card">
        <div className="re-stamp">SIMULATED</div>
        <div className="re-eyebrow">REFERENCE</div>
        <div className="re-mono" style={{ fontSize: 16, marginTop: 4 }}>
          {offers.receiptRef}
        </div>
        <hr className="re-hr" />
        <div className="re-dims">
          <div>
            <div className="re-muted">Supplier</div>
            <b>{offers.recoName}</b>
          </div>
          <div>
            <div className="re-muted">Amount</div>
            <b className="re-mono">{offers.recoTotal}</b>
          </div>
          <div>
            <div className="re-muted">Authorized</div>
            <span className="re-mono">29 Aug · 14:12</span>
          </div>
          <div>
            <div className="re-muted">Newly shared</div>
            <b>{offers.receiptShared}</b>
          </div>
        </div>
      </div>
      <button
        type="button"
        className="re-ghost itaa-focus-ring"
        style={{ marginTop: 14 }}
        onClick={onActivity}
      >
        View this intent&apos;s activity
      </button>
    </div>
  );
}

function ActivityPane({
  offers,
  reasked,
}: {
  offers: (typeof OFFERS)["parking"];
  reasked: boolean;
}) {
  const extra = reasked
    ? [
        {
          t: "13:52",
          what: "You approved a single added field",
          why: "Why · CityDrive could not quote a deposit hold without the payment method type",
          shared: "1 sent, 1 recipient",
        },
      ]
    : [];
  return (
    <div className="re-card">
      {[...extra, ...offers.audit].map((row) => (
        <div key={`${row.t}-${row.what}`} className="re-audit">
          <span className="re-mono re-muted">{row.t}</span>
          <div>
            <div style={{ fontWeight: 600 }}>{row.what}</div>
            <div className="re-muted">{row.why}</div>
          </div>
          <span className="re-muted">{row.shared}</span>
        </div>
      ))}
    </div>
  );
}
