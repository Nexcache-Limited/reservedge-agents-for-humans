import type { BuyerSnapshot, ProgressEventPayload, RankedOffer } from "../api/types.js";
import { Button } from "../components/primitives.js";
import {
  DISCLOSED_FIELDS,
  WITHHELD_FIELDS,
  formatMoney,
  supplierDisplayName,
} from "../fixtures/golden.js";
import {
  a3AcceptanceView,
  a3Eligibility,
  addOnEvidenceCopy,
  allSuppliersUnavailable,
  downsideCopy,
  offerCards,
  offerMoney,
  partialSuppliers,
  priceOnlyLeaderCopy,
  progressLanes,
  supplierLanes,
  whyRecommended,
  type OfferCardView,
} from "../view-models/workspace.js";

export type OffersView = "gate" | "record" | "progress" | "reco" | "compare";

const OVS: Array<{ key: OffersView; label: string }> = [
  { key: "record", label: "Disclosure record" },
  { key: "reco", label: "Recommendation" },
  { key: "compare", label: "Compare offers" },
];

const AVATAR = ["var(--grad-indigo)", "var(--grad-green)", "var(--grad-violet)"] as const;

export function defaultOffersView(state: BuyerSnapshot["state"], busy: boolean): OffersView {
  if (state === "AWAITING_DISPATCH_APPROVAL") {
    return busy ? "progress" : "gate";
  }
  return "reco";
}

export function CompetitionOffers({
  snapshot,
  selected,
  busy,
  stale,
  disabledReason,
  ov,
  progressEvents,
  onView,
  onSelect,
  onAccept,
  onRefresh,
  onInbox,
  onDispatch,
  onPending,
  onTake,
  onAuthorize,
}: {
  snapshot: BuyerSnapshot;
  selected: RankedOffer | null;
  busy: boolean;
  stale: boolean;
  disabledReason?: string | undefined;
  ov: OffersView;
  progressEvents: ProgressEventPayload[];
  onView: (next: OffersView) => void;
  onSelect: (offerId: string) => void;
  onAccept: () => void;
  onRefresh: () => void;
  onInbox: () => void;
  onDispatch: () => void;
  onPending: () => void;
  onTake: () => void;
  onAuthorize: () => void;
}) {
  if (snapshot.state === "AWAITING_DISPATCH_APPROVAL") {
    if (ov === "progress" || busy) {
      return (
        <SupplierProgress
          snapshot={snapshot}
          progressEvents={progressEvents}
          onSee={() => onView("reco")}
        />
      );
    }
    return (
      <DisclosureGate snapshot={snapshot} busy={busy} onHold={onDispatch} onPending={onPending} />
    );
  }
  if (ov === "progress") {
    return (
      <SupplierProgress
        snapshot={snapshot}
        progressEvents={progressEvents}
        onSee={() => onView("reco")}
      />
    );
  }
  if (ov === "record") {
    return (
      <>
        <OfferPills ov={ov} onView={onView} />
        <DisclosureRecord />
      </>
    );
  }
  if (ov === "compare") {
    return (
      <>
        <OfferPills ov={ov} onView={onView} />
        <CompareGrid snapshot={snapshot} />
        {snapshot.state === "OFFERS_RANKED" ? (
          <AcceptanceBlock
            snapshot={snapshot}
            selected={selected}
            busy={busy}
            stale={stale}
            disabledReason={disabledReason}
            onSelect={onSelect}
            onAccept={onAccept}
            onRefresh={onRefresh}
            onInbox={onInbox}
          />
        ) : snapshot.state === "ACCEPTANCE_RECORDED" ? (
          <button type="button" className="re-primary itaa-focus-ring" onClick={onAuthorize}>
            Continue to authorization
          </button>
        ) : null}
      </>
    );
  }
  return (
    <>
      <OfferPills ov={ov} onView={onView} />
      {partialSuppliers(snapshot) ? <p className="re-path-flag">Partial results</p> : null}
      {allSuppliersUnavailable(snapshot) ? (
        <p className="re-fail">All suppliers unavailable</p>
      ) : null}
      <Recommendation snapshot={snapshot} onTake={onTake} onCompare={() => onView("compare")} />
      <SupplierStrip snapshot={snapshot} />
      {snapshot.state === "OFFERS_RANKED" ? (
        <AcceptanceBlock
          snapshot={snapshot}
          selected={selected}
          busy={busy}
          stale={stale}
          disabledReason={disabledReason}
          onSelect={onSelect}
          onAccept={onAccept}
          onRefresh={onRefresh}
          onInbox={onInbox}
        />
      ) : null}
      {snapshot.state === "ACCEPTANCE_RECORDED" ? (
        <button type="button" className="re-primary itaa-focus-ring" onClick={onAuthorize}>
          Continue to authorization
        </button>
      ) : null}
    </>
  );
}

export function CompetitionAuthSheet({
  snapshot,
  busy,
  disabledReason,
  onAuthorize,
  onClose,
}: {
  snapshot: BuyerSnapshot;
  busy: boolean;
  disabledReason?: string | undefined;
  onAuthorize: () => void;
  onClose: () => void;
}) {
  const accepted = snapshot.acceptance;
  const offer = snapshot.offers.find((item) => item.offerId === accepted?.offerId);
  const money = offer === undefined ? null : offerMoney(offer);
  const amount = money === null ? "" : formatMoney(money.totalMinor, money.currency);
  const name =
    offer === undefined ? "Simulated supplier" : supplierDisplayName(offer.supplierToken);
  return (
    <>
      <div className="re-sim-strip">
        <b>SIMULATION</b>
        <br />
        No card is charged and no reservation is made in this build.
      </div>
      <div className="re-eyebrow">APPROVAL 2 OF 2 · TRANSACTION</div>
      <h2 id="confirm-title" className="re-h3">
        Authorize this purchase
      </h2>
      <p className="re-lead">A separate decision from the disclosure you approved earlier.</p>
      <div className="re-kv">
        <div>
          <span>Supplier</span>
          <b>{name}</b>
        </div>
        <div>
          <span>What</span>
          <b>Simulated airport parking reservation</b>
        </div>
        <div>
          <span>Amount</span>
          <b className="re-mono">{amount || "Not provided"}</b>
        </div>
      </div>
      <div className="re-muted-card">
        <b>This authorizes:</b> one simulated reservation with {name}
        {amount !== "" ? ` at ${amount}` : ""}, and sharing your name and plate with that supplier
        only.
        <br />
        <b>It does not authorize:</b> recurring bookings, price changes, or contact with the other
        suppliers.
      </div>
      <button
        type="button"
        className="re-primary itaa-focus-ring"
        id="a4-authorize"
        disabled={offer === undefined || busy || disabledReason !== undefined}
        style={{ width: "100%", marginTop: 18 }}
        onClick={onAuthorize}
      >
        Authorize {amount}
      </button>
      <div style={{ textAlign: "center" }}>
        <button type="button" className="re-text-btn itaa-focus-ring" onClick={onClose}>
          Not now
        </button>
      </div>
    </>
  );
}

export function CompetitionReceipt({
  snapshot,
  onActivity,
  onInbox,
}: {
  snapshot: BuyerSnapshot;
  onActivity: () => void;
  onInbox: () => void;
}) {
  const tx = snapshot.transaction;
  const offer = snapshot.offers.find((item) => item.offerId === snapshot.acceptance?.offerId);
  const name =
    offer === undefined ? "Simulated supplier" : supplierDisplayName(offer.supplierToken);
  const amount = tx == null ? "Not provided" : formatMoney(tx.amountMinor, tx.currency);
  return (
    <div className="re-receipt">
      <div className="re-receipt-head">
        <span className="re-check-disc" aria-hidden>
          ✓
        </span>
        <div>
          <h3 className="re-h3">Authorization recorded</h3>
          <p className="re-muted">Simulated. No card charged, nothing reserved.</p>
        </div>
      </div>
      <div className="re-receipt-card">
        <div className="re-stamp">SIMULATED</div>
        <div className="re-eyebrow">SIMULATED RECEIPT</div>
        <p className="re-lead">This demonstration keeps requests in this browser session only.</p>
        <div className="re-dims" style={{ marginTop: 16 }}>
          <div>
            <div className="re-muted">Supplier</div>
            <div style={{ fontWeight: 600 }}>{name}</div>
          </div>
          <div>
            <div className="re-muted">Amount</div>
            <div className="re-mono" style={{ fontWeight: 600 }}>
              {amount}
            </div>
          </div>
          <div>
            <div className="re-muted">Authorized</div>
            <div>Simulated reservation</div>
          </div>
          <div>
            <div className="re-muted">Newly shared</div>
            <div>Name and plate with {name} only</div>
          </div>
        </div>
      </div>
      <div className="re-composer-actions" style={{ marginTop: 16 }}>
        <button type="button" className="re-ghost itaa-focus-ring" onClick={onActivity}>
          View this intent&apos;s activity
        </button>
        <button type="button" className="re-primary itaa-focus-ring" onClick={onInbox}>
          Back to intents
        </button>
      </div>
    </div>
  );
}

export function PublicResearch({ onOffers }: { onOffers: () => void }) {
  return (
    <div className="re-two">
      <div className="re-card re-stack">
        <div className="re-eyebrow">PUBLIC RESEARCH · AUTONOMOUS</div>
        <div className="re-check">
          <span className="re-dot re-dot-ok">✓</span>
          Published JFK parking rates and access notes
        </div>
        <div className="re-check">
          <span className="re-dot re-dot-ok">✓</span>
          Cancellation and shuttle policies from public sources
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
          <p className="re-muted">
            Buyer-only research. Isolated suppliers are contacted only after you approve disclosure.
          </p>
        </div>
        <button type="button" className="re-primary itaa-focus-ring" onClick={onOffers}>
          Continue to the offers tab
        </button>
      </div>
    </div>
  );
}

function OfferPills({ ov, onView }: { ov: OffersView; onView: (next: OffersView) => void }) {
  return (
    <div className="re-ov" role="tablist" aria-label="Offers views">
      {OVS.map((item) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={ov === item.key}
          className={`re-ov-btn itaa-focus-ring${ov === item.key ? " is-on" : ""}`}
          onClick={() => onView(item.key)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function DisclosureGate({
  snapshot,
  busy,
  onHold,
  onPending,
}: {
  snapshot: BuyerSnapshot;
  busy: boolean;
  onHold: () => void;
  onPending: () => void;
}) {
  return (
    <div>
      <div className="re-dark-block">
        <div className="re-eyebrow">APPROVAL 1 OF 2 · DISCLOSURE</div>
        <h3 className="re-h3">What suppliers will see</h3>
        <p>
          Approving here sends a request for offers to three parking suppliers. It does not buy
          anything, and it contains nothing that identifies you. Recipients: ParkDirect, SkyShield,
          and TerminalFlex — isolated from each other.
        </p>
      </div>
      <SentHeld />
      <div className="re-meta-strip">
        <div>
          <div>Purpose</div>
          <b>Get parking offers</b>
        </div>
        <div>
          <div>Recipients</div>
          <b>3 suppliers, isolated from each other</b>
        </div>
        <div>
          <div>Expires</div>
          <b>{snapshot.expiresAt.slice(0, 10)}</b>
        </div>
        <div>
          <div>Tier</div>
          <b>Tier 1 · anonymous</b>
        </div>
      </div>
      <div className="re-composer-actions" style={{ marginTop: 16 }}>
        <button
          type="button"
          className="re-primary itaa-focus-ring"
          id="a2-dispatch"
          disabled={busy}
          onClick={onHold}
        >
          Send this request
        </button>
        <button
          type="button"
          className="re-ghost itaa-focus-ring"
          disabled={busy}
          onClick={onPending}
        >
          Not now — keep pending
        </button>
      </div>
    </div>
  );
}

function DisclosureRecord() {
  return (
    <div>
      <div className="re-record-intro">
        <div className="re-eyebrow" style={{ color: "var(--green)" }}>
          DISCLOSURE APPROVED BY YOU
        </div>
        <h3 className="re-h3">What was sent, and what was not</h3>
        <p className="re-lead">
          A record, not an action. This approval has already been used; asking these suppliers
          anything further needs a new one.
        </p>
      </div>
      <SentHeld />
    </div>
  );
}

function SentHeld() {
  return (
    <div className="re-two">
      <div className="re-card">
        <div className="re-eyebrow" style={{ color: "var(--green)", marginBottom: 12 }}>
          SENT · {DISCLOSED_FIELDS.length} FIELDS
        </div>
        <div className="re-stack">
          {DISCLOSED_FIELDS.map((row) => (
            <div key={row.field} className="re-sent">
              <span style={{ color: "var(--green)" }}>✓</span>
              <div>
                <b>{row.field}</b>
                <div className="re-muted">{row.purpose}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="re-card">
        <div className="re-eyebrow" style={{ marginBottom: 12 }}>
          WITHHELD · {WITHHELD_FIELDS.length} FIELDS
        </div>
        <div className="re-stack re-muted">
          {WITHHELD_FIELDS.map((row) => (
            <div key={row.field} className="re-sent">
              <span>✕</span>
              {row.field}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SupplierProgress({
  snapshot,
  progressEvents,
  onSee,
}: {
  snapshot: BuyerSnapshot;
  progressEvents: ProgressEventPayload[];
  onSee: () => void;
}) {
  const live = progressLanes(progressEvents);
  const settled = supplierLanes(snapshot.supplierOutcomes);
  const lanes = snapshot.supplierOutcomes.length > 0 ? settled : live;
  const ranked = snapshot.state === "OFFERS_RANKED";
  return (
    <div>
      <h3 className="re-h3">{ranked ? "Suppliers answered" : "Suppliers are answering"}</h3>
      <p className="re-lead">Each one answers alone. None of them can see the others, or you.</p>
      {partialSuppliers(snapshot) ? <p className="re-path-flag">Partial results</p> : null}
      {allSuppliersUnavailable(snapshot) ? (
        <p className="re-fail">All suppliers unavailable</p>
      ) : null}
      <div className="re-three">
        {lanes.map((lane, index) => (
          <div key={lane.supplierToken} className="re-card">
            <span className="re-avatar" style={{ background: AVATAR[index % AVATAR.length] }}>
              {codeFor(lane.displayName)}
            </span>
            <div className="re-supplier-name">{lane.displayName}</div>
            <div className="re-muted">{lane.statusLabel}</div>
          </div>
        ))}
      </div>
      {ranked ? (
        <button
          type="button"
          className="re-primary itaa-focus-ring"
          style={{ marginTop: 16 }}
          onClick={onSee}
        >
          See the recommendation
        </button>
      ) : null}
    </div>
  );
}

function SupplierStrip({ snapshot }: { snapshot: BuyerSnapshot }) {
  const lanes = supplierLanes(snapshot.supplierOutcomes);
  if (lanes.length === 0) {
    return null;
  }
  return (
    <ul className="re-live-lanes" aria-label="Isolated supplier progress">
      {lanes.map((lane) => (
        <li key={lane.supplierToken}>
          <b>{lane.displayName}</b>
          <span className="re-muted"> {lane.statusLabel}</span>
        </li>
      ))}
    </ul>
  );
}

function Recommendation({
  snapshot,
  onTake,
  onCompare,
}: {
  snapshot: BuyerSnapshot;
  onTake: () => void;
  onCompare: () => void;
}) {
  const cards = offerCards(snapshot.offers);
  const recommended = cards.find((card) => card.offer.recommended) ?? cards[0];
  if (recommended === undefined) {
    return <p className="re-muted">No reliable recommendation is available.</p>;
  }
  const catalog = recommended.catalog;
  const downside = downsideCopy(snapshot);
  const reasons = whyRecommended(snapshot);
  const priceLeader = priceOnlyLeaderCopy(snapshot);
  const addOnLine = addOnEvidenceCopy(snapshot);
  return (
    <div className="re-reco">
      <div className="re-reco-main">
        <div className="re-reco-top">
          <span
            className="re-pill"
            style={{ background: "var(--ws-accent-soft)", color: "var(--ws-accent-d)" }}
          >
            Recommended
          </span>
          {recommended.score !== "" ? (
            <span className="re-mono re-muted">score {recommended.score}</span>
          ) : (
            <span className="re-mono re-muted">{recommended.fit}</span>
          )}
        </div>
        <h3 className="re-h3" style={{ fontSize: 23, margin: "11px 0 5px" }}>
          {recommended.displayName}
        </h3>
        <p className="re-lead">{reasons[0]}</p>
        <div className="re-price">
          <span className="re-mono re-price-num">{recommended.total}</span>
          <span className="re-muted">total, taxes and fees included</span>
        </div>
        <div className="re-muted">
          {recommended.score !== ""
            ? `Ranking-policy score ${recommended.score} · ${recommended.fit}`
            : recommended.fit}
        </div>
        <hr className="re-hr" />
        <div className="re-dims">
          <div>
            <div className="re-muted">Cover</div>
            <div style={{ fontWeight: 600 }}>{catalog?.covered ?? "Not provided"}</div>
          </div>
          <div>
            <div className="re-muted">Shuttle</div>
            <div style={{ fontWeight: 600 }}>
              {catalog ? `${catalog.shuttleMinutes} min` : "Not provided"}
            </div>
          </div>
          <div>
            <div className="re-muted">Distance</div>
            <div style={{ fontWeight: 600 }}>
              {catalog ? `${catalog.distanceMeters} m` : "Not provided"}
            </div>
          </div>
          <div>
            <div className="re-muted">Cancellation</div>
            <div style={{ fontWeight: 600, color: "var(--green)" }}>
              {catalog?.cancellation ?? "Not provided"}
            </div>
          </div>
        </div>
        <hr className="re-hr" />
        <div className="re-stack">
          <div>
            <span style={{ color: "var(--green)" }}>+ </span>
            {catalog?.addOns.join(", ") || addOnLine}
          </div>
          <div>
            <span style={{ color: "var(--amber)" }}>– </span>
            {downside ?? "No material downside recorded on this snapshot."}
          </div>
          <div>
            <span className="re-muted">? </span>
            Ranking scores are evidence, not a percent match.
          </div>
        </div>
        <div className="re-composer-actions" style={{ marginTop: 20 }}>
          <button type="button" className="re-primary itaa-focus-ring" onClick={onTake}>
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
          <h3 className="re-h3">Why this is recommended</h3>
          <div className="re-stack" style={{ marginTop: 11 }}>
            {reasons.map((reason) => (
              <div key={reason}>{reason}</div>
            ))}
          </div>
          <hr className="re-hr" />
          <div className="re-muted">{priceLeader}</div>
        </div>
        <div className="re-muted-card">
          Reservedge&apos;s opinion on the offers received, not a rating or a financial score. Check
          the terms before authorizing.
        </div>
      </div>
    </div>
  );
}

function CompareGrid({ snapshot }: { snapshot: BuyerSnapshot }) {
  const cards = offerCards(snapshot.offers);
  const recommended = cards.find((card) => card.offer.recommended) ?? cards[0];
  const ordered = recommended
    ? [recommended, ...cards.filter((card) => card.offer.offerId !== recommended.offer.offerId)]
    : cards;
  const rows = compareRows(ordered);
  return (
    <div>
      <p className="re-lead">
        Each supplier received the same minimized request. Suppliers cannot see this table or each
        other. Totals and scores come from the owned ranking snapshot.
      </p>
      {partialSuppliers(snapshot) ? <p className="re-path-flag">Partial results</p> : null}
      <div className="re-grid-wrap">
        <div className="re-cmp" role="table" aria-label="Offer comparison">
          <div className="re-cmp-head">
            <div>DIMENSION</div>
            {ordered.map((card) => (
              <div key={card.offer.offerId}>
                {card.displayName}
                {card.offer.recommended ? <span> · recommended</span> : null}
              </div>
            ))}
            <div>Public market</div>
          </div>
          {rows.map((row) => (
            <div key={row.label} className="re-cmp-row">
              <div>{row.label}</div>
              {row.values.map((value, index) => (
                <div key={`${row.label}-${ordered[index]?.offer.offerId ?? index}`}>{value}</div>
              ))}
              <div className="re-muted">—</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function compareRows(cards: OfferCardView[]): Array<{ label: string; values: string[] }> {
  return [
    { label: "Total, all in", values: cards.map((card) => card.total) },
    { label: "Ranking score", values: cards.map((card) => card.score) },
    { label: "Qualitative fit", values: cards.map((card) => card.fit) },
    { label: "Cover", values: cards.map((card) => card.catalog?.covered ?? "Not provided") },
    {
      label: "Shuttle",
      values: cards.map((card) =>
        card.catalog ? `${card.catalog.shuttleMinutes} min` : "Not provided",
      ),
    },
    {
      label: "Distance",
      values: cards.map((card) =>
        card.catalog ? `${card.catalog.distanceMeters} m` : "Not provided",
      ),
    },
    {
      label: "Cancellation",
      values: cards.map((card) => card.catalog?.cancellation ?? "Not provided"),
    },
    {
      label: "Add-ons",
      values: cards.map((card) =>
        card.catalog === undefined ? "Not provided" : card.catalog.addOns.join(", ") || "None",
      ),
    },
  ];
}

function AcceptanceBlock({
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
  const cards = offerCards(snapshot.offers);
  const gate = a3Eligibility(snapshot, selected, { stale });
  const details = selected === null ? null : a3AcceptanceView(snapshot, selected);
  return (
    <div className="re-card" style={{ marginTop: 14 }}>
      <h3 className="re-h3">Confirm selected offer</h3>
      <p className="re-muted">Selection does not reserve or charge anything.</p>
      <div className="re-chips" style={{ marginBottom: 12 }}>
        {cards.map((card) => (
          <button
            key={card.offer.offerId}
            type="button"
            className={`re-ghost itaa-focus-ring${selected?.offerId === card.offer.offerId ? " re-ghost-fill" : ""}`}
            onClick={() => onSelect(card.offer.offerId)}
          >
            Select {card.displayName}
          </button>
        ))}
      </div>
      {details === null ? (
        <p className="re-lead">No offer is selected.</p>
      ) : (
        <dl className="re-live-fields" aria-label="Selected offer acceptance">
          <div>
            <dt className="re-muted">Supplier</dt>
            <dd>{details.supplier}</dd>
          </div>
          <div>
            <dt className="re-muted">Amount</dt>
            <dd>{details.amount}</dd>
          </div>
          <div>
            <dt className="re-muted">Simulation status</dt>
            <dd>{details.simulationStatus}</dd>
          </div>
        </dl>
      )}
      {!gate.eligible ? (
        <div className="re-fail" role="alert">
          <p>Acceptance is blocked</p>
          <p>{gate.reason}</p>
          {gate.recoveryAction === "refresh" ? (
            <button type="button" className="re-ghost itaa-focus-ring" onClick={onRefresh}>
              {gate.recoveryLabel}
            </button>
          ) : null}
          {gate.recoveryAction === "inbox" ? (
            <button type="button" className="re-ghost itaa-focus-ring" onClick={onInbox}>
              Back to intents
            </button>
          ) : null}
          {gate.recoveryAction === "select" ? <p>{gate.recoveryLabel}</p> : null}
        </div>
      ) : null}
      <Button
        id="a3-accept"
        variant="consent"
        busy={busy}
        disabled={!gate.eligible || disabledReason !== undefined}
        disabledReason={!gate.eligible ? gate.reason : disabledReason}
        onClick={onAccept}
      >
        Confirm offer selection
      </Button>
    </div>
  );
}

function codeFor(name: string): string {
  if (name === "ParkDirect") {
    return "PD";
  }
  if (name === "SkyShield") {
    return "SS";
  }
  if (name === "TerminalFlex") {
    return "TF";
  }
  return name.slice(0, 2).toUpperCase();
}
