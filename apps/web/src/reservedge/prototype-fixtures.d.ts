import type { DomainId } from "./inbox.js";

export interface DomainQuestion {
  id: string;
  label: string;
  text: string;
  why: string;
  chips: string[];
  required?: boolean;
}

export interface DomainSpec {
  code: string;
  name: string;
  tier: string;
  tierBg: string;
  tierFg: string;
  tierNote: string;
  typed: string;
  questions: DomainQuestion[];
  extraRows: Array<{ label: string; value: string; note: string }>;
  reqRows: Array<{
    label: string;
    value?: string;
    note?: string;
    kind?: string;
    fix?: boolean;
    tags?: string[];
  }>;
  sideEyebrow: string;
  sideTier: string;
  sideTierBg: string;
  sideTierFg: string;
  sideBody: string;
  sideBtn: string;
  sideNote: string;
}

export const DOMAINS: Record<DomainId, DomainSpec>;

export const REQ_KIND: Record<
  string,
  { pill: string; bg: string; fg: string; note: string; row: string }
>;

export interface OfferFixture {
  recoName: string;
  recoTotal: string;
  recoValid: string;
  recoWhy: string;
  recoBreak: string;
  dims: Array<{ label: string; value: string; color: string }>;
  plus: string;
  minus: string;
  gap: string;
  reasons: Array<{ head: string; body: string }>;
  recoSwitch: string;
  cols: string[];
  rows: Array<{
    label: string;
    a: string;
    b: string;
    c: string;
    pub: string;
    ca?: string;
    cb?: string;
    cc?: string;
  }>;
  incomplete: { name: string; why: string } | null;
  authWhat: string;
  authDoes: string;
  receiptRef: string;
  receiptShared: string;
  resLine1: string;
  resLine2: string;
  range: string;
  rangeNote: string;
  fail: string;
  gateIntro: string;
  gatePurpose: string;
  gateTier: string;
  sent: Array<{ label: string; why: string }>;
  held: Array<{ label: string }>;
  suppliers: Array<{ code: string; name: string; grad: string; state: string }>;
  audit: Array<{ t: string; what: string; why: string; shared: string }>;
  reaskSent?: Array<{ label: string; why: string }>;
  reaskHeld?: Array<{ label: string }>;
  reaskResult?: string;
}

export const OFFERS: Record<DomainId, OfferFixture>;
