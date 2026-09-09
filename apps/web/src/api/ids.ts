const CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz";

export function opaqueId(prefix: string): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let body = "";
  for (let index = 0; index < 26; index += 1) {
    const byte = bytes[index % bytes.length] ?? 0;
    body += CROCKFORD[(byte + index) % CROCKFORD.length];
  }
  return `${prefix}${body}`;
}

export const SIMULATION_ISSUED_AT = "2026-08-20T15:00:00Z";
export const SIMULATION_EXPIRES_AT = "2026-08-22T15:00:00Z";

export function governanceIds(actorId: string, ownerId: string) {
  return {
    actorId,
    ownerId,
    approvalId: opaqueId("ap_"),
    correlationId: opaqueId("cr_"),
    issuedAt: SIMULATION_ISSUED_AT,
    expiresAt: SIMULATION_EXPIRES_AT,
  };
}
