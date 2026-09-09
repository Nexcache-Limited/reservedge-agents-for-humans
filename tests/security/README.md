# tests/security

Architecture-boundary, secret-hygiene, and dependency-direction checks.

WP-01 implements the initial core-to-provider boundary tests and supporting fixtures.
WP-04 extends the scans to `packages/policy` (domain + stdlib only) and
`packages/observability` (domain + stdlib only). Application may depend on
domain, policy, and observability, but not generated contracts or providers.
