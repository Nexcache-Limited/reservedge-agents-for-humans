import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ClosedApiError } from "../api/errors.js";
import type { IntakeExtraction, ItaaApi } from "../api/types.js";
import { Button, LiveRegion, StatusIndicator, Surface, Text } from "../components/primitives.js";
import { createSeededPurchaseIntent } from "../fixtures/golden.js";
import {
  ACCESS,
  COVERED,
  EMPTY_PARKING_DRAFT,
  SAMPLE_JFK_TEXT,
  VEHICLE,
  draftFromExtraction,
  toConfirmedFields,
  type ParkingDraft,
} from "../reservedge/parking-intake.js";
import { rememberCompetitionIntent, rememberSnapshot } from "../session/memory.js";

export { SAMPLE_JFK_TEXT };

type IntakePhase = "compose" | "analysing" | "failed" | "missing" | "ambiguous" | "review";

type DraftFields = ParkingDraft;
const EMPTY_DRAFT = EMPTY_PARKING_DRAFT;

function phaseFor(extraction: IntakeExtraction): IntakePhase {
  if (extraction.missingFields.length > 0) {
    return "missing";
  }
  if (extraction.ambiguousFields.length > 0) {
    return "ambiguous";
  }
  return "review";
}

export function NewIntentScreen({ api }: { api: ItaaApi }) {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<IntakePhase>("compose");
  const [extraction, setExtraction] = useState<IntakeExtraction | null>(null);
  const [draft, setDraft] = useState<DraftFields>(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState("");

  const analysing = phase === "analysing";
  const reviewing = phase === "missing" || phase === "ambiguous" || phase === "review";

  async function analyse() {
    if (busy || text.trim() === "") {
      return;
    }
    setBusy(true);
    setError(null);
    setPhase("analysing");
    setLive("Analysing the parking requirement.");
    try {
      const next = await api.extractIntake(text, "airport_parking");
      setExtraction(next);
      setDraft(draftFromExtraction(next));
      const nextPhase = phaseFor(next);
      setPhase(nextPhase);
      setLive(
        nextPhase === "missing"
          ? "Missing information needs to be completed."
          : nextPhase === "ambiguous"
            ? "Ambiguous information needs to be confirmed."
            : "Review the extracted parking fields.",
      );
    } catch (caught) {
      setPhase("failed");
      setLive("Extraction failed.");
      setError(
        caught instanceof ClosedApiError
          ? caught.message
          : "The parking requirement could not be analysed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmDraft() {
    if (busy || extraction === null) {
      return;
    }
    const fields = toConfirmedFields(extraction.intakeId, draft);
    if (fields === null) {
      setError("Complete the required parking fields before confirming.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const snapshot = await api.confirmIntakeIntent(fields);
      rememberCompetitionIntent(snapshot.intentId);
      rememberSnapshot(snapshot);
      navigate(`/intents/${snapshot.intentId}`);
    } catch (caught) {
      setError(
        caught instanceof ClosedApiError
          ? caught.message
          : "The confirmed requirement could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  function declineConfirmation() {
    setExtraction(null);
    setDraft(EMPTY_DRAFT);
    setPhase("compose");
    setError(null);
    setLive("Confirmation declined. Describe the parking requirement again.");
  }

  async function startDemo() {
    if (busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const snapshot = await api.createIntent(createSeededPurchaseIntent());
      rememberSnapshot(snapshot);
      navigate(`/intents/${snapshot.intentId}`);
    } catch (caught) {
      setError(
        caught instanceof ClosedApiError ? caught.message : "Could not start the demonstration.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="itaa-text itaa-text--display">New airport-parking intent</h1>
      <LiveRegion
        message={live || error || ""}
        politeness={error !== null ? "assertive" : "polite"}
      />
      <Surface raised>
        <Text role="heading" as="h2">
          Describe the parking requirement
        </Text>
        <p className="itaa-text itaa-text--body">
          Write the parking need in your own words. ITAA extracts fields for your review. It does
          not invent an airport or dates, and it does not contact real suppliers.
        </p>
        <label className="itaa-field-label itaa-text itaa-text--label" htmlFor="intake-text">
          Parking requirement
        </label>
        <textarea
          id="intake-text"
          className="itaa-textarea itaa-focus-ring"
          value={text}
          placeholder={SAMPLE_JFK_TEXT}
          disabled={analysing}
          onChange={(event) => setText(event.target.value)}
        />
        <div className="itaa-actions">
          <Button
            id="use-sample-jfk"
            variant="ghost"
            disabled={analysing}
            onClick={() => setText(SAMPLE_JFK_TEXT)}
          >
            Use sample JFK text
          </Button>
          <Button
            id="analyse-intake"
            variant="consent"
            busy={analysing}
            disabled={text.trim() === "" || analysing}
            onClick={() => void analyse()}
          >
            Analyse requirement
          </Button>
        </div>
      </Surface>
      {analysing ? (
        <Surface>
          <StatusIndicator variant="working" label="Analysing" />
          <p className="itaa-text itaa-text--body">
            Extracting the parking fields for your review.
          </p>
        </Surface>
      ) : null}
      {phase === "failed" ? (
        <Surface>
          <StatusIndicator variant="denial" label="Extraction failed" />
          <p className="itaa-error" role="alert">
            {error ?? "The parking requirement could not be analysed."}
          </p>
          <Button id="retry-intake" variant="primary" onClick={() => void analyse()}>
            Retry
          </Button>
        </Surface>
      ) : null}
      {reviewing && extraction !== null ? (
        <IntakeReview
          phase={phase}
          extraction={extraction}
          draft={draft}
          text={text}
          busy={busy}
          error={error}
          onDraft={setDraft}
          onConfirm={() => void confirmDraft()}
          onDecline={declineConfirmation}
        />
      ) : null}
      <Surface>
        <Text role="heading" as="h2">
          Seeded JFK demonstration
        </Text>
        <p className="itaa-text itaa-text--body">
          This creates a local simulated Purchase Intent for JFK parking, 3–8 September 2026,
          standard vehicle, covered preferred, 20-minute shuttle, EV charging. It does not monitor
          email, ingest live context, or contact real suppliers.
        </p>
        {error !== null && !reviewing && phase !== "failed" ? (
          <p className="itaa-error" role="alert">
            {error}
          </p>
        ) : null}
        <Button id="start-demo" variant="consent" busy={busy} onClick={() => void startDemo()}>
          Start seeded demonstration
        </Button>
      </Surface>
    </>
  );
}

function IntakeReview({
  phase,
  extraction,
  draft,
  text,
  busy,
  error,
  onDraft,
  onConfirm,
  onDecline,
}: {
  phase: IntakePhase;
  extraction: IntakeExtraction;
  draft: DraftFields;
  text: string;
  busy: boolean;
  error: string | null;
  onDraft: (next: DraftFields) => void;
  onConfirm: () => void;
  onDecline: () => void;
}) {
  const ready = toConfirmedFields(extraction.intakeId, draft) !== null;
  return (
    <Surface raised>
      {phase === "missing" ? (
        <>
          <StatusIndicator variant="attention" label="Missing information" />
          <Text role="heading" as="h2">
            Missing information
          </Text>
          <ul>
            {extraction.missingFields.map((field) => (
              <li key={field}>{field}</li>
            ))}
          </ul>
        </>
      ) : null}
      {phase === "ambiguous" ? (
        <>
          <StatusIndicator variant="attention" label="Ambiguous information" />
          <Text role="heading" as="h2">
            Ambiguous information
          </Text>
          <ul>
            {extraction.ambiguousFields.map((field) => (
              <li key={field}>{field}</li>
            ))}
          </ul>
        </>
      ) : null}
      {phase === "review" ? (
        <Text role="heading" as="h2">
          Confirm extracted fields
        </Text>
      ) : null}
      <p className="itaa-text itaa-text--body">
        Edit the fields ITAA should research. Confirmation creates the Purchase Intent. Raw text
        stays with you and is not stored on the intent.
      </p>
      <IntakeFields draft={draft} onDraft={onDraft} />
      <EvidencePanel extraction={extraction} text={text} />
      {error !== null ? (
        <p className="itaa-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="itaa-actions">
        <Button
          id="confirm-intake"
          variant="consent"
          busy={busy}
          disabled={!ready || busy}
          disabledReason={!ready ? "Complete the required parking fields." : undefined}
          onClick={onConfirm}
        >
          Confirm parking requirement
        </Button>
        <Button id="decline-intake" variant="ghost" disabled={busy} onClick={onDecline}>
          Decline confirmation
        </Button>
      </div>
    </Surface>
  );
}

function IntakeFields({
  draft,
  onDraft,
}: {
  draft: DraftFields;
  onDraft: (next: DraftFields) => void;
}) {
  return (
    <div className="itaa-fields">
      <LabeledInput
        id="intake-airport"
        label="Airport"
        value={draft.airportCode}
        onChange={(airportCode) => onDraft({ ...draft, airportCode: airportCode.toUpperCase() })}
      />
      <LabeledInput
        id="intake-start"
        label="Start"
        value={draft.start}
        onChange={(start) => onDraft({ ...draft, start })}
      />
      <LabeledInput
        id="intake-end"
        label="End"
        value={draft.end}
        onChange={(end) => onDraft({ ...draft, end })}
      />
      <label className="itaa-field-label itaa-text itaa-text--label" htmlFor="intake-vehicle">
        Vehicle class
      </label>
      <select
        id="intake-vehicle"
        className="itaa-select itaa-focus-ring"
        value={draft.vehicleClass}
        onChange={(event) => onDraft({ ...draft, vehicleClass: event.target.value })}
      >
        <option value="">Select vehicle class</option>
        {VEHICLE.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      <label className="itaa-field-label itaa-text itaa-text--label" htmlFor="intake-covered">
        Covered
      </label>
      <select
        id="intake-covered"
        className="itaa-select itaa-focus-ring"
        value={draft.covered}
        onChange={(event) => onDraft({ ...draft, covered: event.target.value })}
      >
        <option value="">Select covered preference</option>
        {COVERED.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      <LabeledInput
        id="intake-shuttle"
        label="Shuttle max minutes"
        value={draft.shuttleMaxMinutes}
        onChange={(shuttleMaxMinutes) => onDraft({ ...draft, shuttleMaxMinutes })}
      />
      <LabeledInput
        id="intake-currency"
        label="Currency"
        value={draft.currency}
        onChange={(currency) => onDraft({ ...draft, currency: currency.toUpperCase() })}
      />
      <fieldset>
        <legend className="itaa-text itaa-text--label">Accessibility</legend>
        {ACCESS.map((item) => (
          <label key={item} className="itaa-text itaa-text--body">
            <input
              type="checkbox"
              checked={draft.accessibility.includes(item)}
              onChange={(event) => {
                const next = event.target.checked
                  ? [...draft.accessibility, item]
                  : draft.accessibility.filter((value) => value !== item);
                onDraft({ ...draft, accessibility: next });
              }}
            />{" "}
            {item}
          </label>
        ))}
      </fieldset>
    </div>
  );
}

function EvidencePanel({ extraction, text }: { extraction: IntakeExtraction; text: string }) {
  const items = useMemo(() => {
    return extraction.evidenceSpans.map((span) => ({
      ...span,
      quote: text.slice(span.start, span.end),
      confidence: extraction.fieldConfidence[span.field],
    }));
  }, [extraction, text]);
  if (items.length === 0 && Object.keys(extraction.fieldConfidence).length === 0) {
    return null;
  }
  return (
    <div>
      <Text role="heading" as="h3">
        Evidence and confidence
      </Text>
      <p className="itaa-text itaa-text--meta">Buyer-only field evidence. No model reasoning.</p>
      <ul>
        {items.map((item) => (
          <li key={`${item.field}-${item.start}-${item.end}`}>
            <span className="itaa-text itaa-text--label">{item.field}</span>
            {item.quote !== "" ? (
              <span className="itaa-text itaa-text--fact"> “{item.quote}”</span>
            ) : null}
            {item.confidence !== undefined ? (
              <span className="itaa-text itaa-text--meta">
                {" "}
                confidence {item.confidence.toFixed(2)}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LabeledInput({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="itaa-field-label itaa-text itaa-text--label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="itaa-input itaa-focus-ring"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
