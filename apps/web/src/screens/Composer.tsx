import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { ClosedApiError } from "../api/errors.js";
import type { ItaaApi } from "../api/types.js";
import { LiveRegion } from "../components/primitives.js";
import {
  applyChip,
  applySkip,
  applyTyped,
  canonicalizeFromTyped,
  correctField,
  displayFor,
  EMPTY_VALUES,
  fieldValue,
  isFilled,
  missingRequiredFields,
  missingRequiredQuestions,
  noteFor,
  parkingFieldsOrNull,
  parseWindow,
  selectQuestions,
  valuesFromExtraction,
  type ComposerValues,
} from "../reservedge/composer-engine.js";
import { interpretCorrection } from "../reservedge/parking-intake.js";
import { SEED_INTENTS, type DomainId } from "../reservedge/inbox.js";
import { snapshotToRow } from "../reservedge/map-snapshot.js";
import { usePortfolio } from "../reservedge/portfolio.js";
import {
  domainById,
  KEEP,
  type AnswerChip,
  type ClarificationQuestion,
  type DomainDefinition,
} from "../reservedge/registry.js";
import { rememberCompetitionIntent, rememberSnapshot } from "../session/memory.js";

export function Composer({ api }: { api: ItaaApi }) {
  const { domainId } = useParams();
  const domain = domainById(domainId ?? "");
  if (domain === undefined) {
    return (
      <div className="re-fade">
        <h2 className="re-h2">Unknown domain</h2>
        <p className="re-lead">
          Pick a domain from New intent. No new screens are required to add one.
        </p>
      </div>
    );
  }
  return <DomainComposer api={api} domain={domain} />;
}

function seededDraft(state: unknown, objective: string): string {
  if (state !== null && typeof state === "object" && "objective" in state) {
    const value = (state as { objective?: unknown }).objective;
    if (typeof value === "string" && value.trim() !== "") {
      return value;
    }
  }
  return objective;
}

function knownParkingFromState(state: unknown): Record<string, string> {
  if (state === null || typeof state !== "object" || !("knownParking" in state)) {
    return {};
  }
  const raw = (state as { knownParking?: unknown }).knownParking;
  if (raw === null || typeof raw !== "object") {
    return {};
  }
  const known: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === "string" && value.trim() !== "") {
      known[key] = value.trim();
    }
  }
  return known;
}

function splitKnownParking(known: Record<string, string>): {
  intakeId: string | null;
  fields: Record<string, string>;
} {
  const intakeId = known.intakeId?.trim() ?? "";
  const fields: Record<string, string> = {};
  for (const [key, value] of Object.entries(known)) {
    if (key === "intakeId") {
      continue;
    }
    fields[key] = value;
  }
  return { intakeId: intakeId === "" ? null : intakeId, fields };
}

function valuesFromKnown(known: Record<string, string>): ComposerValues {
  const provenance: ComposerValues["provenance"] = {};
  for (const key of Object.keys(known)) {
    provenance[key] = "proposed";
  }
  return { fields: { ...known }, provenance };
}

function mergeKnown(values: ComposerValues, known: Record<string, string>): ComposerValues {
  const fields = { ...values.fields };
  const provenance = { ...values.provenance };
  for (const [key, value] of Object.entries(known)) {
    if (key === "intakeId") {
      continue;
    }
    fields[key] = value;
    provenance[key] = provenance[key] ?? "proposed";
  }
  return { fields, provenance };
}

function DomainComposer({ api, domain }: { api: ItaaApi; domain: DomainDefinition }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { objective, setIntents, setSelectedId } = usePortfolio();
  const example = domain.example;
  const knownParking = knownParkingFromState(location.state);
  const prepared = splitKnownParking(knownParking);
  const skipIntake = domain.id === "parking" && prepared.intakeId !== null;
  const preparedValues =
    Object.keys(prepared.fields).length > 0 ? valuesFromKnown(prepared.fields) : EMPTY_VALUES;
  const [draft, setDraft] = useState(() => seededDraft(location.state, objective));
  const [sent, setSent] = useState(skipIntake);
  const [typed, setTyped] = useState(() =>
    skipIntake ? seededDraft(location.state, objective) : "",
  );
  const [index, setIndex] = useState(0);
  const [values, setValues] = useState<ComposerValues>(() =>
    skipIntake || Object.keys(prepared.fields).length > 0 ? preparedValues : EMPTY_VALUES,
  );
  const [own, setOwn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(() =>
    skipIntake ? "Review the prepared parking requirement." : "",
  );
  const [intakeId, setIntakeId] = useState<string | null>(prepared.intakeId);
  const [asked, setAsked] = useState<ClarificationQuestion[]>(() =>
    skipIntake ? selectQuestions(domain, preparedValues, null) : [],
  );
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const questions = asked;
  const question = sent && index < questions.length ? (questions[index] ?? null) : null;
  const missingRequired = missingRequiredQuestions(questions, values);
  const missingFields = missingRequiredFields(domain, values);
  const ready = sent && question === null && missingFields.length === 0;
  const fixture = domain.simulation === "design_fixture";

  const rows = useMemo(() => {
    const fieldRows = domain.fields.map((field) => {
      const value = displayFor(field, values);
      const skipped = fieldValue(values, field.id) === "skipped";
      return {
        label: field.label,
        value,
        note: noteFor(field, values, question?.why ?? domain.disclosureTier.explanation),
        color: skipped
          ? "var(--amber)"
          : isFilled(fieldValue(values, field.id))
            ? "var(--ws-ink)"
            : "var(--ws-ink-3)",
        fieldId: field.id,
        required: field.required,
        empty: !isFilled(fieldValue(values, field.id)),
      };
    });
    const extra = domain.staticRows.map((row) => ({
      label: row.label,
      value: row.value,
      note: row.note,
      color: "var(--ws-ink)",
      fieldId: row.label,
      required: false,
      empty: false,
    }));
    return [...fieldRows, ...extra];
  }, [domain, question, values]);

  const filled = rows.filter((row) => !row.empty).length;
  const parsedWindow = question?.parse === "window" ? parseWindow(typed) : {};

  useEffect(() => {
    if (question?.parse !== "window") {
      return;
    }
    const parsed = parseWindow(typed);
    if (!isFilled(parsed.start ?? "") || !isFilled(parsed.end ?? "")) {
      return;
    }
    setValues((current) => {
      const start = isFilled(current.fields.start ?? "") ? current.fields.start : parsed.start;
      const end = isFilled(current.fields.end ?? "") ? current.fields.end : parsed.end;
      if (start === current.fields.start && end === current.fields.end) {
        return current;
      }
      return {
        fields: { ...current.fields, start: start ?? "", end: end ?? "" },
        provenance: { ...current.provenance, start: "answered", end: "answered" },
      };
    });
  }, [question?.parse, typed]);

  useEffect(() => {
    if (missingFields.length > 0 || missingRequired.length > 0) {
      return;
    }
    setError((current) => {
      if (
        current === "Complete the required parking fields before confirming." ||
        current === "Answer the required question before confirming."
      ) {
        return null;
      }
      return current;
    });
  }, [missingFields.length, missingRequired.length]);

  function applyCorrection(fieldId: string, raw: string) {
    const result = interpretCorrection(fieldId, raw);
    if (!result.ok) {
      setFieldErrors((current) => ({ ...current, [fieldId]: result.message }));
      setLive(result.message);
      return;
    }
    setFieldErrors((current) => {
      const next = { ...current };
      delete next[fieldId];
      return next;
    });
    setValues(correctField(values, fieldId, result.value));
  }

  function recordAnswer(next: ComposerValues) {
    setValues(next);
    setOwn("");
    setIndex((current) => current + 1);
  }

  function answerChip(label: string) {
    if (question === null) {
      return;
    }
    const chip =
      resolvedChips(question, values, typed).find((item) => item.label === label) ??
      question.chips.find((item) => item.label === label);
    if (chip === undefined) {
      return;
    }
    const emptiesRequired =
      question.required &&
      question.fieldIds.every((id) => chip.values[id] === "") &&
      !Object.values(chip.values).includes(KEEP);
    if (emptiesRequired) {
      if (own.trim() !== "") {
        recordAnswer(applyTyped(question, values, own));
        return;
      }
      setLive("Type the exact start and end times.");
      return;
    }
    const next = applyChip(values, chip, typed);
    const stillMissing =
      question.required && question.fieldIds.some((id) => !isFilled(next.fields[id] ?? ""));
    setValues(next);
    setOwn("");
    if (stillMissing) {
      setLive("Type the missing required answer.");
      return;
    }
    setIndex((current) => current + 1);
  }

  async function sendLine() {
    if (busy || draft.trim() === "") {
      return;
    }
    const line = draft.trim();
    setBusy(true);
    setError(null);
    setLive("Reading the requirement.");
    try {
      if (fixture) {
        const selected = selectQuestions(domain, EMPTY_VALUES, null);
        setAsked(selected);
        setTyped(line);
        setSent(true);
        setIndex(0);
        setLive("Up to three questions follow.");
        return;
      }
      const next = await api.extractIntake(line, "airport_parking");
      const extracted = mergeKnown(
        canonicalizeFromTyped(line, valuesFromExtraction(next)),
        knownParking,
      );
      const selected = selectQuestions(domain, extracted, next);
      setIntakeId(next.intakeId);
      setValues(extracted);
      setAsked(selected);
      setTyped(line);
      setSent(true);
      setIndex(0);
      setLive(
        selected.length === 0
          ? "Review the extracted parking fields."
          : `Question 1 of ${selected.length}.`,
      );
    } catch (caught) {
      setLive("The requirement could not be read.");
      setError(
        caught instanceof ClosedApiError
          ? caught.message
          : "The parking requirement could not be analysed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (missingRequired.length > 0) {
      const idx = questions.findIndex((item) => item.id === missingRequired[0]?.id);
      setIndex(idx === -1 ? 0 : idx);
      setError("Answer the required question before confirming.");
      setLive("Answer the required question before confirming.");
      return;
    }
    if (missingFields.length > 0) {
      setLive("Complete the required fields on the requirement card.");
      setError("Complete the required parking fields before confirming.");
      return;
    }
    if (fixture) {
      const next = {
        id: `new-${domain.id}-${Date.now()}`,
        domain: domain.id as DomainId,
        title: `${domain.name} · new`,
        sub: "Requirement confirmed. Researching public options.",
        status: "running" as const,
        stage: "research" as const,
        step: "Market research · research tab",
        day: "today" as const,
        date: "29 Aug · now",
        canDelete: true,
      };
      setIntents((current) => [next, ...current]);
      setSelectedId(next.id);
      navigate("/bookings");
      return;
    }
    if (busy) {
      return;
    }
    if (!intakeId) {
      setError(
        "This requirement is not linked to an intake session. Send the line again before confirming.",
      );
      setLive("Send the requirement again before confirming.");
      return;
    }
    const fields = parkingFieldsOrNull(intakeId, values);
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
      const row = snapshotToRow(snapshot);
      setSelectedId(snapshot.intentId);
      setIntents((current) => {
        const live = current.filter((item) => item.id.startsWith("pi_") && item.id !== row.id);
        const seeds = new Set(SEED_INTENTS.map((item) => item.id));
        const extras = current.filter((item) => !item.id.startsWith("pi_") && !seeds.has(item.id));
        return [row, ...live, ...extras];
      });
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

  return (
    <div className="re-fade">
      <LiveRegion
        message={live || error || ""}
        politeness={error !== null ? "assertive" : "polite"}
      />
      <div className="re-composer-head">
        <span className="re-code">{domain.code}</span>
        <h2 className="re-h2" style={{ margin: 0 }}>
          {domain.name}
        </h2>
        <span
          className="re-pill"
          style={{ background: domain.disclosureTier.bg, color: domain.disclosureTier.fg }}
        >
          {domain.disclosureTier.label}
        </span>
        <span className={fixture ? "re-demo-flag" : "re-path-flag"}>{domain.capabilityNote}</span>
      </div>
      <div className="re-composer">
        <div className="re-composer-col">
          {!sent ? (
            <div className="re-card re-card-accent">
              <div className="re-eyebrow re-eyebrow-accent">STEP 1 · WHAT DO YOU NEED?</div>
              <p className="re-muted" style={{ marginTop: 9 }}>
                One line is enough. Reservedge will ask up to three questions after this, then stop.
              </p>
              <textarea
                className="re-textarea"
                rows={3}
                placeholder="Type what you need…"
                value={draft}
                aria-label="What you need"
                onChange={(event) => setDraft(event.target.value)}
              />
              <button
                type="button"
                className="re-chip-btn itaa-focus-ring"
                onClick={() => setDraft(example)}
              >
                Use the example: {example}
              </button>
              <button
                type="button"
                className="re-primary itaa-focus-ring"
                disabled={draft.trim() === "" || busy}
                style={{
                  opacity: draft.trim() === "" || busy ? 0.45 : 1,
                  width: "100%",
                  marginTop: 12,
                }}
                onClick={() => {
                  void sendLine();
                }}
              >
                Send to Reservedge
              </button>
            </div>
          ) : (
            <div className="re-card">
              <div className="re-eyebrow">WHAT YOU TYPED</div>
              <p style={{ margin: "9px 0 0", fontSize: 13.5, lineHeight: 1.6 }}>{typed}</p>
            </div>
          )}

          {error !== null &&
          !(ready && error === "Complete the required parking fields before confirming.") ? (
            <div className="re-fail">{error}</div>
          ) : null}

          {question ? (
            <div className="re-card re-card-accent">
              <div className="re-q-top">
                <span className="re-eyebrow re-eyebrow-accent">
                  QUESTION {index + 1} OF {questions.length}
                </span>
                <span className="re-q-why">{question.why}</span>
              </div>
              <div className="re-q-text">{question.text}</div>
              <div className="re-chips">
                {resolvedChips(question, values, typed).map((chip) => (
                  <button
                    key={chip.label}
                    type="button"
                    className="re-chip-btn itaa-focus-ring"
                    onClick={() => answerChip(chip.label)}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
              {question.parse === "window" ? (
                <WindowFields
                  start={fieldValue(values, "start") || parsedWindow.start || ""}
                  end={fieldValue(values, "end") || parsedWindow.end || ""}
                  onStart={(value) => setValues(correctField(values, "start", value))}
                  onEnd={(value) => setValues(correctField(values, "end", value))}
                  onContinue={() => {
                    const start = fieldValue(values, "start") || parsedWindow.start || "";
                    const end = fieldValue(values, "end") || parsedWindow.end || "";
                    if (!isFilled(start) || !isFilled(end)) {
                      setError("Choose a start and end time.");
                      setLive("Choose a start and end time.");
                      return;
                    }
                    setError(null);
                    recordAnswer({
                      fields: { ...values.fields, start, end },
                      provenance: { ...values.provenance, start: "answered", end: "answered" },
                    });
                  }}
                />
              ) : null}
              <div className="re-own">
                <input
                  className="re-own-input"
                  placeholder="Or type your own answer…"
                  value={own}
                  aria-label="Your own answer"
                  onChange={(event) => setOwn(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && own.trim() !== "") {
                      recordAnswer(applyTyped(question, values, own));
                    }
                  }}
                />
                {question.required ? null : (
                  <button
                    type="button"
                    className="re-text-btn itaa-focus-ring"
                    onClick={() => recordAnswer(applySkip(question, values))}
                  >
                    Skip this
                  </button>
                )}
              </div>
              {question.required ? (
                <div className="re-required-note">
                  Required — suppliers in this domain cannot price without it.
                </div>
              ) : null}
            </div>
          ) : null}

          {ready && error === null ? (
            <div className="re-ready">
              <div className="re-ready-title">That&apos;s enough to work with.</div>
              <p>
                Anything you skipped is kept as an assumption you can correct at any time.
                Reservedge will research public options first — nothing is sent to a supplier
                without a separate approval.
              </p>
            </div>
          ) : null}

          {sent && missingRequired.length > 0 && question === null ? (
            <div className="re-blocked">
              <b>
                {missingRequired.length} required answer left: {missingRequired[0]?.text}
              </b>
              <button
                type="button"
                className="re-ghost-fill itaa-focus-ring"
                onClick={() =>
                  setIndex(questions.findIndex((item) => item.id === missingRequired[0]?.id))
                }
              >
                Answer it
              </button>
            </div>
          ) : null}

          {sent ? (
            <>
              <div
                className="re-composer-actions"
                style={{ opacity: missingFields.length > 0 ? 0.5 : 1 }}
              >
                <button
                  type="button"
                  className="re-primary itaa-focus-ring"
                  disabled={busy}
                  onClick={() => void confirm()}
                >
                  Confirm requirement and research
                </button>
                <button
                  type="button"
                  className="re-ghost itaa-focus-ring"
                  disabled={busy}
                  onClick={() => void confirm()}
                >
                  Use what you have
                </button>
              </div>
              <p className="re-cap">
                {question
                  ? `Question ${index + 1} of ${questions.length}.`
                  : missingFields.length > 0
                    ? "Required parking fields still need an answer."
                    : questions.length === 0
                      ? "No extra questions were needed."
                      : "All questions done."}{" "}
                Questions are capped — Reservedge asks for permission before a fourth.
              </p>
            </>
          ) : (
            <div className="re-muted-card">{domain.disclosureTier.explanation}</div>
          )}
        </div>
        <aside className="re-req-card">
          <div className="re-req-head">
            <div className="re-eyebrow">REQUIREMENT · BUILDING</div>
            <span className="re-req-count">
              {filled}/{rows.length}
            </span>
          </div>
          {rows.map((row) => (
            <div key={row.label} className="re-req-row">
              <div className="re-eyebrow">{row.label}</div>
              <div className="re-req-value" style={{ color: row.color }}>
                {row.value}
              </div>
              <div className="re-req-note">{row.note}</div>
              {sent && domain.fields.some((field) => field.id === row.fieldId) ? (
                <>
                  <input
                    className="re-own-input"
                    style={{ marginTop: 8 }}
                    aria-label={`Correct ${row.label}`}
                    placeholder={row.empty ? "Correct this field" : "Edit this field"}
                    onBlur={(event) => {
                      if (event.target.value.trim() !== "") {
                        applyCorrection(row.fieldId, event.target.value);
                        event.target.value = "";
                      }
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && event.currentTarget.value.trim() !== "") {
                        applyCorrection(row.fieldId, event.currentTarget.value);
                        event.currentTarget.value = "";
                      }
                    }}
                  />
                  {fieldErrors[row.fieldId] !== undefined ? (
                    <div className="re-fail" style={{ marginTop: 8 }}>
                      {fieldErrors[row.fieldId]}
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>
          ))}
          <div className="re-req-foot">{domain.disclosureTier.explanation}</div>
        </aside>
      </div>
    </div>
  );
}

function resolvedChips(
  question: ClarificationQuestion,
  values: ComposerValues,
  typed: string,
): AnswerChip[] {
  if (question.parse !== "window") {
    return question.chips;
  }
  const parsed = parseWindow(typed);
  const start = isFilled(fieldValue(values, "start"))
    ? fieldValue(values, "start")
    : (parsed.start ?? "");
  const end = isFilled(fieldValue(values, "end")) ? fieldValue(values, "end") : (parsed.end ?? "");
  return question.chips.map((chip) => {
    if (chip.values.start !== KEEP && chip.values.end !== KEEP) {
      return chip;
    }
    return { ...chip, values: { start, end } };
  });
}

function toDatetimeLocal(iso: string): string {
  const match = iso.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})/);
  return match?.[1] ?? "";
}

function fromDatetimeLocal(value: string): string {
  if (value === "") {
    return "";
  }
  return value.length === 16 ? `${value}:00Z` : `${value}Z`;
}

function WindowFields({
  start,
  end,
  onStart,
  onEnd,
  onContinue,
}: {
  start: string;
  end: string;
  onStart: (value: string) => void;
  onEnd: (value: string) => void;
  onContinue: () => void;
}) {
  return (
    <div className="re-window-fields">
      <label className="re-window-label">
        Start
        <input
          type="datetime-local"
          className="re-own-input"
          aria-label="Window start"
          value={toDatetimeLocal(start)}
          onChange={(event) => onStart(fromDatetimeLocal(event.target.value))}
        />
      </label>
      <label className="re-window-label">
        End
        <input
          type="datetime-local"
          className="re-own-input"
          aria-label="Window end"
          value={toDatetimeLocal(end)}
          onChange={(event) => onEnd(fromDatetimeLocal(event.target.value))}
        />
      </label>
      <button type="button" className="re-primary itaa-focus-ring" onClick={onContinue}>
        Continue with these times
      </button>
    </div>
  );
}
