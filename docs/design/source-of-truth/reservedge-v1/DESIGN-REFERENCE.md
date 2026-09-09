# Reservedge v1 — design references, not production code

Reservedge is the public product identity. ITAA remains the internal technical namespace during the competition cut.

The files in this directory are the COMP-G1-05 visual source of truth. They are **design references**. Do not copy their prototyping runtime into `apps/web`.

## Not production code

- `Reservedge Web.dc.html`
- `Reservedge Mobile.dc.html`
- `Reservedge Logo.dc.html`
- `support.js`
- `tokens/fonts.css` (Google Fonts `@import` — production self-hosts Schibsted Grotesk and JetBrains Mono)

## Production mapping

Exact colour, type, spacing, and radius values are mapped into `packages/ui-kit` semantic tokens. `apps/web` consumes those tokens only. Do not introduce a second token system.

Package namespaces, API paths, schema IDs, opaque identifier prefixes, environment variables, audit event names, and deployed Google resource names stay `itaa_*` / existing.

Do not configure `reservedge.com`, DNS, Cloudflare, or Google Cloud from this package.
