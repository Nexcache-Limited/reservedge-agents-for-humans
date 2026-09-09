/* DO NOT EDIT.
 *
 * Generated from packages/contracts/schemas. Regenerate with `make generate-contracts`.
 */

/* schemas/v1/purchase-intent.schema.json */
/**
 * Supplier-visible minimized parking envelope, not Requirement or Disclosure Preview.
 */
export interface PurchaseIntent {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  intentId: string;
  buyerToken: string;
  category: "airport_parking";
  location: {
    /**
     * IATA airport code. JFK is the v1 golden-path fixture.
     */
    airportCode: string;
  };
  serviceWindow: {
    /**
     * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
     */
    start: string;
    /**
     * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
     */
    end: string;
  };
  requirements: {
    vehicleClass: "standard" | "compact" | "suv" | "oversized";
    covered: "none" | "preferred" | "required";
    shuttleMaxMinutes: number;
  };
  constraints: {
    /**
     * ISO 4217 alphabetic code, uppercase.
     */
    currency: string;
    accessibility: ("step_free" | "wheelchair" | "ev_charging")[];
  };
  disclosure: {
    profile: "parking_v1";
    /**
     * SHA-256 as sha256: plus 64 lowercase hex characters. Shape only in WP-02.
     */
    approvedPayloadHash: string;
  };
  solicitation: {
    /**
     * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
     */
    responseDeadline: string;
    counteroffersAllowed: boolean;
  };
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  createdAt: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  expiresAt: string;
}

/* schemas/v1/offer.schema.json */
/**
 * Multidimensional simulated supplier offer. Availability confirmation is named simulated.
 */
export interface Offer {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  offerId: string;
  intentId: string;
  supplierToken: string;
  version: number;
  status: "submitted" | "superseded" | "expired" | "withdrawn" | "declined" | "accepted";
  price: {
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    subtotalMinor: number;
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    feesMinor: number;
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    taxMinor: number;
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    totalMinor: number;
    /**
     * ISO 4217 alphabetic code, uppercase.
     */
    currency: string;
  };
  service: {
    lotType: "covered" | "uncovered" | "garage" | "surface";
    shuttleMinutes: number;
    /**
     * Integer metres; avoids the spec example's float mile value.
     */
    distanceMeters: number;
    availability: "confirmed_simulated" | "limited_simulated" | "unavailable_simulated";
    addOns: ("ev_charging" | "indoor_walkway" | "oversized_bay")[];
  };
  terms: {
    cancellation: "free_until_24h" | "free_until_48h" | "non_refundable";
    refund: "original_method" | "none";
  };
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  validFrom: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  validUntil: string;
  /**
   * @minItems 1
   */
  evidence: [
    {
      type: "supplier_policy" | "rate_card" | "lot_rules" | "availability_snapshot";
      /**
       * Typed provenance reference. Not raw buyer context or competitor payloads.
       */
      ref: string;
    },
    ...{
      type: "supplier_policy" | "rate_card" | "lot_rules" | "availability_snapshot";
      /**
       * Typed provenance reference. Not raw buyer context or competitor payloads.
       */
      ref: string;
    }[],
  ];
  /**
   * MVP profile requires simulation exactly true.
   */
  simulation: true;
  /**
   * Opaque signature handle. Cryptographic verify is later work.
   */
  signature: string;
}

/* schemas/v1/counter-offer.schema.json */
/**
 * Buyer or supplier commercial change. One-round policy is deferred.
 */
export interface CounterOffer {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  counterOfferId: string;
  intentId: string;
  parentOfferId: string;
  parentOfferVersion: number;
  /**
   * @minItems 1
   */
  proposedChanges: [
    (
      | {
          path: "price.subtotalMinor";
          /**
           * Non-negative integer minor currency units. JavaScript-safe. No floats.
           */
          value: number;
        }
      | {
          path: "price.feesMinor";
          /**
           * Non-negative integer minor currency units. JavaScript-safe. No floats.
           */
          value: number;
        }
      | {
          path: "price.taxMinor";
          /**
           * Non-negative integer minor currency units. JavaScript-safe. No floats.
           */
          value: number;
        }
      | {
          path: "service.lotType";
          value: "covered" | "uncovered" | "garage" | "surface";
        }
      | {
          path: "service.shuttleMinutes";
          value: number;
        }
      | {
          path: "service.distanceMeters";
          value: number;
        }
      | {
          path: "service.addOns";
          value: ("ev_charging" | "indoor_walkway" | "oversized_bay")[];
        }
      | {
          path: "terms.cancellation";
          value: "free_until_24h" | "free_until_48h" | "non_refundable";
        }
      | {
          path: "terms.refund";
          value: "original_method" | "none";
        }
      | {
          path: "validUntil";
          /**
           * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
           */
          value: string;
        }
    ),
    ...(
      | {
          path: "price.subtotalMinor";
          /**
           * Non-negative integer minor currency units. JavaScript-safe. No floats.
           */
          value: number;
        }
      | {
          path: "price.feesMinor";
          /**
           * Non-negative integer minor currency units. JavaScript-safe. No floats.
           */
          value: number;
        }
      | {
          path: "price.taxMinor";
          /**
           * Non-negative integer minor currency units. JavaScript-safe. No floats.
           */
          value: number;
        }
      | {
          path: "service.lotType";
          value: "covered" | "uncovered" | "garage" | "surface";
        }
      | {
          path: "service.shuttleMinutes";
          value: number;
        }
      | {
          path: "service.distanceMeters";
          value: number;
        }
      | {
          path: "service.addOns";
          value: ("ev_charging" | "indoor_walkway" | "oversized_bay")[];
        }
      | {
          path: "terms.cancellation";
          value: "free_until_24h" | "free_until_48h" | "non_refundable";
        }
      | {
          path: "terms.refund";
          value: "original_method" | "none";
        }
      | {
          path: "validUntil";
          /**
           * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
           */
          value: string;
        }
    )[],
  ];
  initiatedBy: "buyer" | "supplier";
  rationaleCode?: "price" | "coverage" | "shuttle_time" | "cancellation";
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  createdAt: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  expiresAt: string;
  status: "proposed" | "accepted" | "declined" | "expired" | "withdrawn";
  simulation: true;
  /**
   * Opaque signature handle. Cryptographic verify is later work.
   */
  signature: string;
}

/* schemas/v1/acceptance.schema.json */
/**
 * Bound offer selection. Ownership and current-version checks are deferred to WP-03/WP-04.
 */
export interface Acceptance {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  acceptanceId: string;
  intentId: string;
  offerId: string;
  offerVersion: number;
  /**
   * SHA-256 as sha256: plus 64 lowercase hex characters. Shape only in WP-02.
   */
  acceptedTermsHash: string;
  buyerApprovalId: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  createdAt: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  expiresAt: string;
  status: "recorded" | "expired" | "superseded";
}

/* schemas/v1/transaction-authorization.schema.json */
/**
 * MVP authorization is SIMULATED only. Signing and idempotency storage are later work.
 */
export interface TransactionAuthorization {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  authorizationId: string;
  acceptanceId: string;
  action: "reserve_parking";
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  amountMinor: number;
  /**
   * ISO 4217 alphabetic code, uppercase.
   */
  currency: string;
  supplierToken: string;
  /**
   * Any other mode fails the MVP profile.
   */
  mode: "SIMULATED";
  idempotencyKey: string;
  userApprovalId: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  authorizedAt: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  expiresAt: string;
  /**
   * Opaque signature handle. Cryptographic verify is later work.
   */
  receiptSignature: string;
}

/* schemas/v1/orchestration-intent.schema.json */
/**
 * Buyer-owned parent Intent aggregate. Not supplier-facing. Public product term is Intent.
 */
export interface OrchestrationIntent {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  intentId: string;
  state:
    | "draft"
    | "clarifying"
    | "planning"
    | "deleted"
    | "attention"
    | "in_progress"
    | "offers_ready"
    | "partially_authorized_simulated"
    | "partially_authorized_live"
    | "partially_booked"
    | "completed_simulated"
    | "completed"
    | "paused"
    | "cancelled"
    | "failed";
  objective: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  createdAt: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  updatedAt: string;
  /**
   * MVP profile requires simulation exactly true.
   */
  simulation: true;
  /**
   * Backend durability is unsupported in this MVP profile.
   */
  durability: "unsupported";
  conversationId?: string;
  planId?: string;
  ledgerId?: string;
}

/* schemas/v1/conversation.schema.json */
/**
 * This interface was referenced by `Conversation`'s JSON-Schema
 * via the `definition` "ClosedJson".
 */
export type ClosedJson =
  | string
  | {
      [k: string]: string | number | boolean | null;
    };

/**
 * Intent intake events and inspectable facts. Must not include preference keys or supplier envelopes.
 */
export interface Conversation {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  intentId: string;
  events: ConversationEvent[];
  facts: ConversationFact[];
}
/**
 * This interface was referenced by `Conversation`'s JSON-Schema
 * via the `definition` "ConversationEvent".
 */
export interface ConversationEvent {
  eventId: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  occurredAt: string;
  actor: "buyer" | "reservedge";
  kind: "objective" | "clarification" | "answer" | "correction" | "system";
  text?: string;
}
/**
 * This interface was referenced by `Conversation`'s JSON-Schema
 * via the `definition` "ConversationFact".
 */
export interface ConversationFact {
  factId: string;
  /**
   * String field path for the inspectable fact.
   */
  path: string;
  value: ClosedJson;
  provenance: string;
  confidence: "high" | "medium" | "low" | "contested";
  source: "buyer" | "extract" | "correction";
  correctionState: "none" | "corrected" | "overridden";
}

/* schemas/v1/intent-plan.schema.json */
/**
 * Plan of Booking Tasks for an OrchestrationIntent. Combined-recommendation eligibility is a flag only.
 */
export interface IntentPlan {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  planId: string;
  intentId: string;
  /**
   * @minItems 0
   */
  taskIds: string[];
  /**
   * True only when two or more tasks could be offer-ready. Schema allows the flag; no service.
   */
  combinedRecommendationsEligible?: boolean;
}

/* schemas/v1/booking-task.schema.json */
/**
 * Per-domain task under an OrchestrationIntent. Must not embed conversation, siblings, preferences, or competitor offers.
 */
export interface BookingTask {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  taskId: string;
  intentId: string;
  domain: "parking" | "rental" | "ents";
  state:
    | "proposed"
    | "missing_details"
    | "a1_review"
    | "a1_blocked"
    | "public_research"
    | "a2_required"
    | "researching"
    | "supplier_timeout"
    | "no_offer"
    | "offers_ready"
    | "offers_expiring"
    | "offers_expired"
    | "superseded"
    | "a3_review"
    | "a3_ineligible"
    | "a4_required"
    | "a4_failed"
    | "authorized_simulated"
    | "authorized_live"
    | "booking_pending"
    | "confirmed_booking"
    | "booking_failed"
    | "paused"
    | "cancelled"
    | "failed"
    | "offline_readonly";
  /**
   * MVP profile requires simulation exactly true.
   */
  simulation: true;
  requirementVersion?: number;
  purchaseIntentId?: string;
  validity?: "valid" | "expiring" | "expired" | "superseded";
  inventory?: "not_held" | "subject_to_availability" | "held_until";
  transactionResult?:
    | "simulated"
    | "authorized_simulated"
    | "authorized_live"
    | "booking_pending"
    | "confirmed_booking"
    | "booking_failed"
    | "failed"
    | "cancelled";
}

/* schemas/v1/cost-ledger.schema.json */
/**
 * Deterministic per-task cost buckets. No LLM totals. Ranking micros are forbidden. Mixed currencies stay separate unless fx is present.
 */
export type CostLedger = {
  [k: string]: unknown;
} & {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  ledgerId: string;
  intentId: string;
  /**
   * MVP profile requires simulation exactly true.
   */
  simulation: true;
  rows: CostLedgerRow[];
  currencies: string[];
  fx?: {
    rate: number;
    source: string;
    /**
     * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
     */
    timestamp: string;
  };
};

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "CostLedgerRow".
 */
export interface CostLedgerRow {
  taskId: string;
  /**
   * ISO 4217 alphabetic code, uppercase.
   */
  currency: string;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  confirmedBookingMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  authorizedSimulatedMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  authorizedLiveMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  bookingPendingMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  selectedNotAuthorizedMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  estimatedMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  expiredExcludedMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  taxesFeesMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  depositsHoldsMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  payableNowMinor: number;
  /**
   * Non-negative integer minor currency units. JavaScript-safe. No floats.
   */
  payableLaterMinor: number;
}

/* schemas/v1/buyer-offer.schema.json */
/**
 * Buyer-facing offer projection. Ranking micros are forbidden. Not the supplier Offer contract.
 */
export type BuyerOffer = {
  [k: string]: unknown;
} & {
  /**
   * Initial canonical contract profile.
   */
  schemaVersion: "1.0";
  offerId: string;
  supplierToken: string;
  version: number;
  sourceType: "aggregator_rate" | "public_market_reference" | "supplier_private_quote";
  offerClass: "standard" | "curated";
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  issuedAt: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  validFrom: string;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  validUntil: string;
  /**
   * Canonical terms digest. Same shape as Sha256Hash.
   */
  termsHash: string;
  price: {
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    totalMinor: number;
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    taxMinor: number;
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    feesMinor: number;
    /**
     * ISO 4217 alphabetic code, uppercase.
     */
    currency: string;
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    depositMinor?: number;
    /**
     * Non-negative integer minor currency units. JavaScript-safe. No floats.
     */
    payLaterMinor?: number;
  };
  fit: "strong" | "good" | "fair";
  /**
   * MVP profile requires simulation exactly true.
   */
  simulation: true;
  validity: "valid" | "expiring" | "expired" | "superseded";
  inventory: "not_held" | "subject_to_availability" | "held_until";
  transactionResult:
    | "simulated"
    | "authorized_simulated"
    | "authorized_live"
    | "booking_pending"
    | "confirmed_booking"
    | "booking_failed"
    | "failed"
    | "cancelled";
  completeness: "complete" | "incomplete";
  /**
   * @minItems 1
   */
  evidence: [
    {
      type: "supplier_policy" | "rate_card" | "lot_rules" | "availability_snapshot";
      /**
       * Typed provenance reference. Not raw buyer context or competitor payloads.
       */
      ref: string;
    },
    ...{
      type: "supplier_policy" | "rate_card" | "lot_rules" | "availability_snapshot";
      /**
       * Typed provenance reference. Not raw buyer context or competitor payloads.
       */
      ref: string;
    }[],
  ];
  supersededBy?: string;
  withdrawn?: boolean;
  rank?: number;
  /**
   * Curated or private source does not require true.
   */
  recommended?: boolean;
  /**
   * RFC 3339 UTC timestamp ending in Z. Calendar and clock values are validated, not only digit shape.
   */
  inventoryHeldUntil?: string;
};
