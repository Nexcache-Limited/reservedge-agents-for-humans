import type { IntakeExtraction, IntakeIntentFields } from "../api/types.js";

export const SAMPLE_JFK_TEXT =
  "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes.";

export const VEHICLE = ["standard", "compact", "suv", "oversized"] as const;
export const COVERED = ["none", "preferred", "required"] as const;
export const ACCESS = ["step_free", "wheelchair", "ev_charging"] as const;
export const ACCESS_NONE = "none";

export const FIELD_CHOICES: Record<string, readonly string[]> = {
  vehicleClass: VEHICLE,
  covered: COVERED,
  accessibility: [...ACCESS, ACCESS_NONE],
};

export interface ParkingDraft {
  airportCode: string;
  start: string;
  end: string;
  vehicleClass: string;
  covered: string;
  shuttleMaxMinutes: string;
  currency: string;
  accessibility: string[];
}

export const EMPTY_PARKING_DRAFT: ParkingDraft = {
  airportCode: "",
  start: "",
  end: "",
  vehicleClass: "",
  covered: "",
  shuttleMaxMinutes: "",
  currency: "",
  accessibility: [],
};

export function draftFromExtraction(extraction: IntakeExtraction): ParkingDraft {
  const proposal = extraction.proposal;
  return {
    airportCode: proposal?.location?.airportCode ?? "",
    start: proposal?.serviceWindow?.start ?? "",
    end: proposal?.serviceWindow?.end ?? "",
    vehicleClass: proposal?.requirements?.vehicleClass ?? "",
    covered: proposal?.requirements?.covered ?? "",
    shuttleMaxMinutes:
      proposal?.requirements?.shuttleMaxMinutes === null ||
      proposal?.requirements?.shuttleMaxMinutes === undefined
        ? ""
        : String(proposal.requirements.shuttleMaxMinutes),
    currency: proposal?.constraints?.currency ?? "",
    accessibility: [...(proposal?.constraints?.accessibility ?? [])],
  };
}

export function toConfirmedFields(
  intakeId: string,
  draft: ParkingDraft,
): IntakeIntentFields | null {
  const shuttle = Number(draft.shuttleMaxMinutes);
  if (
    draft.airportCode === "" ||
    draft.start === "" ||
    draft.end === "" ||
    draft.vehicleClass === "" ||
    draft.covered === "" ||
    draft.currency === "" ||
    !Number.isInteger(shuttle)
  ) {
    return null;
  }
  if (!VEHICLE.includes(draft.vehicleClass as (typeof VEHICLE)[number])) {
    return null;
  }
  if (!COVERED.includes(draft.covered as (typeof COVERED)[number])) {
    return null;
  }
  return {
    intakeId,
    airportCode: draft.airportCode,
    start: draft.start,
    end: draft.end,
    vehicleClass: draft.vehicleClass as IntakeIntentFields["vehicleClass"],
    covered: draft.covered as IntakeIntentFields["covered"],
    shuttleMaxMinutes: shuttle,
    currency: draft.currency,
    accessibility: draft.accessibility.filter(
      (item): item is IntakeIntentFields["accessibility"][number] =>
        ACCESS.includes(item as (typeof ACCESS)[number]),
    ),
  };
}

export function parkingDraftFromValues(fields: Record<string, string>): ParkingDraft {
  const accessibility = (fields.accessibility ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return {
    airportCode: fields.airportCode ?? "",
    start: fields.start ?? "",
    end: fields.end ?? "",
    vehicleClass: fields.vehicleClass ?? "",
    covered: fields.covered ?? "",
    shuttleMaxMinutes: fields.shuttleMaxMinutes ?? "",
    currency: fields.currency ?? "",
    accessibility,
  };
}

export function valuesFromParkingDraft(draft: ParkingDraft): Record<string, string> {
  return {
    airportCode: draft.airportCode,
    start: draft.start,
    end: draft.end,
    vehicleClass: draft.vehicleClass,
    covered: draft.covered,
    shuttleMaxMinutes: draft.shuttleMaxMinutes,
    currency: draft.currency,
    accessibility: draft.accessibility.join(","),
  };
}

export function canonicalizeAccessibility(raw: string): string | null {
  const tokens = raw
    .split(",")
    .map((item) => item.trim().toLowerCase().replace(/\s+/g, " "))
    .filter(Boolean);
  if (tokens.length === 0) {
    return null;
  }
  const mapped: string[] = [];
  for (const token of tokens) {
    if (token === ACCESS_NONE || token === "no extra access needs" || token === "not needed") {
      if (!mapped.includes(ACCESS_NONE)) {
        mapped.push(ACCESS_NONE);
      }
      continue;
    }
    if ((ACCESS as readonly string[]).includes(token)) {
      if (!mapped.includes(token)) {
        mapped.push(token);
      }
      continue;
    }
    if (
      /\bev[_\s-]?charging\b|\belectric vehicle\b|\belectric car\b|\belectric\b|\bev\b/.test(token)
    ) {
      if (!mapped.includes("ev_charging")) {
        mapped.push("ev_charging");
      }
      continue;
    }
    if (/\bstep[- ]?free\b/.test(token)) {
      if (!mapped.includes("step_free")) {
        mapped.push("step_free");
      }
      continue;
    }
    if (/\bwheelchair\b/.test(token)) {
      if (!mapped.includes("wheelchair")) {
        mapped.push("wheelchair");
      }
    }
  }
  if (mapped.length === 0) {
    return null;
  }
  if (mapped.includes(ACCESS_NONE) && mapped.length === 1) {
    return ACCESS_NONE;
  }
  return mapped.filter((item) => item !== ACCESS_NONE).join(",");
}

export function interpretCorrection(
  fieldId: string,
  raw: string,
): { ok: true; value: string } | { ok: false; message: string } {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: false, message: "Enter a value to correct this field." };
  }
  if (fieldId === "vehicleClass") {
    const lower = trimmed.toLowerCase();
    if ((VEHICLE as readonly string[]).includes(lower)) {
      return { ok: true, value: lower };
    }
    return {
      ok: false,
      message: "Vehicle class must be one of: standard, compact, suv, oversized.",
    };
  }
  if (fieldId === "covered") {
    const lower = trimmed.toLowerCase();
    if ((COVERED as readonly string[]).includes(lower)) {
      return { ok: true, value: lower };
    }
    return { ok: false, message: "Covered preference must be one of: none, preferred, required." };
  }
  if (fieldId === "accessibility") {
    const canonical = canonicalizeAccessibility(trimmed);
    if (canonical === null) {
      return {
        ok: false,
        message: "Accessibility must be one of: EV charging, step-free, wheelchair, or none.",
      };
    }
    return { ok: true, value: canonical };
  }
  if (fieldId === "currency") {
    const upper = trimmed.toUpperCase();
    if (/^[A-Z]{3}$/.test(upper)) {
      return { ok: true, value: upper };
    }
    return { ok: false, message: "Currency must be a three-letter code such as USD." };
  }
  if (fieldId === "shuttleMaxMinutes") {
    const minutes = Number(trimmed);
    if (Number.isInteger(minutes) && minutes >= 0 && minutes <= 180) {
      return { ok: true, value: String(minutes) };
    }
    return {
      ok: false,
      message: "Shuttle maximum must be a whole number of minutes from 0 to 180.",
    };
  }
  if (fieldId === "airportCode") {
    const upper = trimmed.toUpperCase();
    if (/^[A-Z]{3}$/.test(upper)) {
      return { ok: true, value: upper };
    }
    return { ok: false, message: "Airport must be a three-letter code such as JFK." };
  }
  return { ok: true, value: trimmed };
}

export function hintsFromRequirementText(text: string): Record<string, string> {
  const lower = text.toLowerCase();
  const hints: Record<string, string> = {};
  const airport =
    text.toUpperCase().match(/\bJFK\b/)?.[0] ?? text.toUpperCase().match(/\b[A-Z]{3}\b/)?.[0];
  if (airport !== undefined && airport !== "USD" && airport !== "THE" && airport !== "AND") {
    hints.airportCode = airport;
  }
  if (/\bsuv\b/.test(lower)) {
    hints.vehicleClass = "suv";
  } else if (/\bcompact\b/.test(lower)) {
    hints.vehicleClass = "compact";
  } else if (/\boversized\b/.test(lower)) {
    hints.vehicleClass = "oversized";
  } else if (/\bstandard\b/.test(lower)) {
    hints.vehicleClass = "standard";
  }
  if (/\brequired\b/.test(lower) && /\bcover/.test(lower)) {
    hints.covered = "required";
  } else if (/\bprefer/.test(lower) && /\bcover/.test(lower)) {
    hints.covered = "preferred";
  } else if (/\buncovered\b/.test(lower)) {
    hints.covered = "none";
  }
  if (/\bshuttle\b/.test(lower)) {
    const minutes = text.match(/(\d+)\s*minutes?/i);
    if (minutes?.[1] !== undefined) {
      hints.shuttleMaxMinutes = minutes[1];
    }
  }
  if (/\busd\b/.test(lower)) {
    hints.currency = "USD";
  }
  const access = canonicalizeAccessibility(text);
  if (access !== null && access !== ACCESS_NONE) {
    hints.accessibility = access;
  }
  return hints;
}
