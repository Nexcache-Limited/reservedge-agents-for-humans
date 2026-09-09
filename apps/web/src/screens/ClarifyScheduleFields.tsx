import type { ExtractedFacts, PlanAnswers } from "../intent-first/plan.js";
import { localityForFacts, parkingNeedsTimes } from "../intent-first/plan.js";
import {
  formatHumanRange,
  periodLabel,
  rangeError,
  resolvedEndDate,
  type DayPart,
} from "../intent-first/schedule.js";

const PERIODS: ReadonlyArray<{ id: DayPart; label: string }> = [
  { id: "morning", label: "Morning" },
  { id: "afternoon", label: "Afternoon" },
  { id: "evening", label: "Evening" },
  { id: "anytime", label: "Anytime / Flexible" },
];

export function ClarifyScheduleFields({
  answers,
  facts,
  onChange,
}: {
  answers: PlanAnswers;
  facts: ExtractedFacts;
  onChange: (patch: Partial<PlanAnswers>) => void;
}) {
  const error = rangeError(answers);
  const locality = localityForFacts(facts);
  const showTimes = parkingNeedsTimes(facts);
  const mentioned = !facts.hasExactDates && facts.dates !== "";
  const structured = answers.dateInputMode === "structured";
  const selectedLabel = formatHumanRange(answers.startDate, resolvedEndDate(answers));

  return (
    <div className="re-clarify-schedule">
      <div className="re-clarify-schedule-toolbar">
        <button
          type="button"
          className="re-clarify-mode itaa-focus-ring"
          onClick={() =>
            onChange({
              dateInputMode: structured ? "text" : "structured",
            })
          }
        >
          {structured ? "Type dates instead" : "Use calendar instead"}
        </button>
      </div>
      {structured ? (
        <fieldset className="re-clarify-fieldset">
          <legend className="re-clarify-legend">Exact dates</legend>
          {mentioned ? (
            <p className="re-clarify-hint">
              You mentioned {facts.dates}. That is not an exact calendar date yet. Pick the date
              {facts.tripLike ? "s" : ""} below.
            </p>
          ) : null}
          <label className="re-clarify-check">
            <input
              type="checkbox"
              checked={answers.oneDay}
              onChange={(event) => onChange({ oneDay: event.target.checked })}
            />
            One day only
          </label>
          <div className={`re-clarify-dates${answers.oneDay ? " is-one" : ""}`}>
            <div className="re-clarify-field">
              <label className="re-clarify-label" htmlFor="clarify-start-date">
                Start date
              </label>
              <input
                id="clarify-start-date"
                className="re-clarify-text itaa-focus-ring"
                type="date"
                value={answers.startDate}
                onChange={(event) => onChange({ startDate: event.target.value })}
              />
            </div>
            {answers.oneDay ? null : (
              <div className="re-clarify-field">
                <label className="re-clarify-label" htmlFor="clarify-end-date">
                  End date
                </label>
                <input
                  id="clarify-end-date"
                  className="re-clarify-text itaa-focus-ring"
                  type="date"
                  value={answers.endDate}
                  aria-invalid={error !== ""}
                  aria-describedby={error !== "" ? "clarify-date-error" : undefined}
                  onChange={(event) => onChange({ endDate: event.target.value })}
                />
              </div>
            )}
          </div>
          {selectedLabel !== "" ? (
            <p className="re-clarify-selected" aria-live="polite">
              Selected {selectedLabel}
            </p>
          ) : null}
          {error !== "" ? (
            <p id="clarify-date-error" className="re-clarify-error" role="alert">
              {error}
            </p>
          ) : null}
        </fieldset>
      ) : (
        <div className="re-clarify-field">
          <label className="re-clarify-label" htmlFor="clarify-dates">
            Dates in your own words
          </label>
          <input
            id="clarify-dates"
            className="re-clarify-text itaa-focus-ring"
            value={answers.dates}
            placeholder="14–19 October, or next Thursday evening"
            onChange={(event) => onChange({ dates: event.target.value, dateInputMode: "text" })}
          />
          <p className="re-clarify-why">
            Ambiguous wording stays unresolved. “Next Thursday” is not turned into a calendar date
            unless you pick one.
          </p>
        </div>
      )}
      {showTimes ? (
        <fieldset className="re-clarify-fieldset">
          <legend className="re-clarify-legend">Times (optional)</legend>
          <p className="re-clarify-hint">
            Exact clock time is optional.
            {locality !== "" ? ` Local time at ${locality}.` : " Use local time."} Morning,
            afternoon, evening and flexible are not HH:MM values.
          </p>
          <div className={`re-clarify-dates${answers.oneDay ? " is-one" : ""}`}>
            <div className="re-clarify-field">
              <label className="re-clarify-label" htmlFor="clarify-start-time">
                Arrival / start time
              </label>
              <input
                id="clarify-start-time"
                className="re-clarify-text itaa-focus-ring"
                type="time"
                value={answers.startTime}
                onChange={(event) =>
                  onChange({
                    startTime: event.target.value,
                    startPeriod: "",
                    endPeriod: "",
                    timeFlexible: false,
                  })
                }
              />
            </div>
            {answers.oneDay ? null : (
              <div className="re-clarify-field">
                <label className="re-clarify-label" htmlFor="clarify-end-time">
                  Departure / end time
                </label>
                <input
                  id="clarify-end-time"
                  className="re-clarify-text itaa-focus-ring"
                  type="time"
                  value={answers.endTime}
                  onChange={(event) =>
                    onChange({
                      endTime: event.target.value,
                      startPeriod: "",
                      endPeriod: "",
                      timeFlexible: false,
                    })
                  }
                />
              </div>
            )}
          </div>
          <div className="re-clarify-choices" role="group" aria-label="Flexible time of day">
            {PERIODS.map((period) => {
              const pressed = isPeriodOn(period.id, answers);
              return (
                <button
                  key={period.id}
                  type="button"
                  className={`re-clarify-choice itaa-focus-ring${pressed ? " is-on" : ""}`}
                  aria-pressed={pressed}
                  onClick={() => selectPeriod(period.id, answers, onChange)}
                >
                  {period.label}
                </button>
              );
            })}
          </div>
          <p className="re-clarify-why">{timeStatus(answers)}</p>
        </fieldset>
      ) : null}
    </div>
  );
}

function isPeriodOn(period: DayPart, answers: PlanAnswers): boolean {
  if (period === "anytime") {
    return (
      answers.startPeriod === "anytime" || (answers.timeFlexible && answers.startPeriod === "")
    );
  }
  return answers.startPeriod === period;
}

function selectPeriod(
  period: DayPart,
  answers: PlanAnswers,
  onChange: (patch: Partial<PlanAnswers>) => void,
) {
  if (period === "anytime") {
    const on = !isPeriodOn("anytime", answers);
    onChange({
      startPeriod: on ? "anytime" : "",
      endPeriod: on ? "anytime" : "",
      timeFlexible: on,
      startTime: "",
      endTime: "",
    });
    return;
  }
  const clearing = answers.startPeriod === period;
  onChange({
    startPeriod: clearing ? "" : period,
    endPeriod: clearing ? "" : period,
    timeFlexible: clearing ? false : answers.timeFlexible && period === "evening",
    startTime: "",
    endTime: "",
  });
}

function timeStatus(answers: PlanAnswers): string {
  if (answers.startTime !== "" || answers.endTime !== "") {
    return `Exact clock time selected${answers.startTime ? `: ${answers.startTime}` : ""}${
      answers.endTime ? `–${answers.endTime}` : ""
    }.`;
  }
  if (answers.startPeriod === "anytime" || (answers.timeFlexible && answers.startPeriod === "")) {
    return "Anytime / Flexible — not an exact HH:MM.";
  }
  if (answers.startPeriod !== "") {
    return `${periodLabel(answers.startPeriod)}${
      answers.timeFlexible ? ", flexible" : ""
    } — not an exact HH:MM.`;
  }
  return "Leave blank if you do not need a clock time yet.";
}
