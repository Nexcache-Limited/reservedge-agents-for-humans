export function GlobalActivity() {
  return (
    <div className="re-fade">
      <h2 className="re-h2">Activity</h2>
      <p className="re-lead">Across every intent and domain. Each entry names what was shared.</p>
      <div className="re-card">
        <div className="re-audit">
          <span className="re-mono re-muted">14:12</span>
          <span className="re-code">Pk</span>
          <div>
            <div style={{ fontWeight: 600 }}>You authorized $71.40 · simulated</div>
            <div className="re-muted">Why · you accepted the recommended offer</div>
          </div>
          <span className="re-muted">Shared: name, plate</span>
        </div>
        <div className="re-audit">
          <span className="re-mono re-muted">13:40</span>
          <span className="re-code">Rc</span>
          <div>
            <div style={{ fontWeight: 600 }}>3 rental offers received · 1 incomplete</div>
            <div className="re-muted">Why · CityDrive did not state its deposit hold</div>
          </div>
          <span className="re-muted">Received only</span>
        </div>
        <div className="re-audit">
          <span className="re-mono re-muted">13:31</span>
          <span className="re-code">Rc</span>
          <div>
            <div style={{ fontWeight: 600 }}>You approved a tier 2 disclosure</div>
            <div className="re-muted">
              Why · rental suppliers cannot price without age band and licence class
            </div>
          </div>
          <span className="re-muted">6 sent, 6 withheld</span>
        </div>
      </div>
    </div>
  );
}

export function PrefsScreen() {
  return (
    <div className="re-fade">
      <h2 className="re-h2">Preferences</h2>
      <p className="re-lead">
        What Reservedge believes about you, and why. Global preferences apply everywhere; domain
        ones only where they make sense.
      </p>
      <div className="re-two">
        <div className="re-card">
          <div className="re-eyebrow">GLOBAL</div>
          <div style={{ fontWeight: 650, marginTop: 5 }}>
            Free cancellation matters more than price
          </div>
          <p className="re-muted">
            Evidence · two cancellations last year, refundable picked 4 times out of 5. Applied in
            parking and rental.
          </p>
        </div>
        <div className="re-card">
          <div className="re-eyebrow">PARKING</div>
          <div style={{ fontWeight: 650, marginTop: 5 }}>Prefers covered parking</div>
          <p className="re-muted">
            Evidence · one covered booking in March, during a snow warning. Weak signal.
          </p>
        </div>
        <div className="re-spa">
          Preferences only rank offers you already received. They are never sent to a supplier — no
          supplier can learn that you are price-sensitive.
        </div>
      </div>
    </div>
  );
}

export function DataScreen() {
  return (
    <div className="re-fade">
      <h2 className="re-h2">Your data</h2>
      <p className="re-lead">
        Everything Reservedge holds, and every disclosure it has ever made, by domain.
      </p>
      <div className="re-card re-card-flush">
        <div className="re-req-confirmed">
          <div>
            <div style={{ fontWeight: 600 }}>Identity</div>
            <div className="re-muted">Name, plate, licence — withheld until you authorize</div>
          </div>
        </div>
        <div className="re-req-confirmed">
          <div>
            <div style={{ fontWeight: 600 }}>Preference history</div>
            <div className="re-muted">14 signals · 9 global, 5 domain-scoped</div>
          </div>
        </div>
        <div className="re-req-confirmed" style={{ borderBottom: 0 }}>
          <div>
            <div style={{ fontWeight: 600 }}>Disclosure log</div>
            <div className="re-muted">
              7 minimized requests · 1 identity disclosure · 2 tier 2 attribute disclosures
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function PlanScreen() {
  return (
    <div className="re-fade">
      <div className="re-warn" style={{ marginBottom: 16 }}>
        <b>Simulation only.</b> No subscription is charged in this competition cut.
      </div>
      <h2 className="re-h2">Reservedge Plus</h2>
      <p className="re-lead">
        Unlimited intents across every domain, more suppliers per request, and offer monitoring
        until you decide.
      </p>
      <div className="re-plan-grid">
        <div className="re-plan-card is-featured">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontWeight: 650 }}>Yearly</div>
            <span
              className="re-pill"
              style={{ background: "var(--ws-accent-soft)", color: "var(--ws-accent-d)" }}
            >
              Save 37%
            </span>
          </div>
          <div className="re-mono" style={{ fontSize: 24, fontWeight: 600, marginTop: 8 }}>
            $59.99
          </div>
          <div className="re-muted" style={{ marginTop: 2, fontSize: 12.5 }}>
            per year · $5.00 per month
          </div>
        </div>
        <div className="re-plan-card">
          <div style={{ fontWeight: 650 }}>Monthly</div>
          <div className="re-mono" style={{ fontSize: 24, fontWeight: 600, marginTop: 8 }}>
            $7.99
          </div>
          <div className="re-muted" style={{ marginTop: 2, fontSize: 12.5 }}>
            per month
          </div>
        </div>
      </div>
    </div>
  );
}
