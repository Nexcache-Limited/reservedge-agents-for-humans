import { useNavigate } from "react-router-dom";
import { listDomains } from "../reservedge/registry.js";

export function DomainPicker() {
  const navigate = useNavigate();
  const domains = listDomains();
  return (
    <div className="re-fade">
      <h2 className="re-h2">What do you need?</h2>
      <p className="re-lead">
        Pick the kind of thing you&apos;re buying. Each one tells you up front what suppliers will
        need before they can price it.
      </p>
      <div className="re-domain-grid">
        {domains.map((domain) => (
          <button
            key={domain.id}
            type="button"
            className="re-domain-card itaa-focus-ring"
            onClick={() => navigate(`/intents/new/${domain.id}`)}
          >
            <span className="re-code">{domain.code}</span>
            <div className="re-domain-card-name">{domain.name}</div>
            <div
              className="re-pill"
              style={{ background: domain.disclosureTier.bg, color: domain.disclosureTier.fg }}
            >
              {domain.disclosureTier.label}
            </div>
            <p>{domain.pickerBody}</p>
            <div className="re-domain-meta">{domain.pickerNeeds}</div>
            <div
              className={domain.simulation === "design_fixture" ? "re-demo-flag" : "re-path-flag"}
            >
              {domain.capabilityNote}
            </div>
          </button>
        ))}
      </div>
      <div className="re-spa">
        Adding a domain means declaring its requirement fields, disclosure tier, and up to six offer
        dimensions — no new screens.
      </div>
    </div>
  );
}
