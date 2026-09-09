# ADR-0002 — Cloud-neutral boundaries

- Status: Accepted
- Date: 2026-08-15
- Decision owners: Product Owner; recorded from the approved Product + Technical Specification and Engineering Kickoff Pack

## Context

ITAA must run the same governed purchase flow on Google and AWS adapters without duplicating product semantics. Models may extract or explain; code owns policy, state transitions, eligibility, ranking, approvals, money, and idempotency. If Google, AWS, FastAPI, or storage types leak into the domain, the project becomes two products instead of one core with adapters.

## Decision

- `packages/domain` and `packages/application` are the cloud-neutral core.
- Domain code has no I/O and cannot import application packages, adapters, FastAPI, ORM/database clients, Google/AWS/model SDKs, RevenueCat, or UI packages.
- Application code may depend on domain types and abstract ports. It cannot import concrete providers, FastAPI, database clients, cloud SDKs, RevenueCat, or UI packages.
- Provider integrations live only under `adapters/` or `infra/`. Google ADK/Gemini/Cloud and AWS Strands/Bedrock/AgentCore are adapters to one core, not duplicated products.
- UI consumes typed contracts and view models. `packages/ui-kit` and future apps cannot redefine domain semantics, disclosure rules, ranking, or approval policy.
- Generated transport models are mapped at boundaries; they are not domain objects.
- WP-01 enforces this with an automated import/manifest check that has both passing core scans and failing fixture cases.

## Consequences

- Later Google and AWS work packages add code under `adapters/` and `infra/` only.
- A prohibited core import is a failing quality gate, not a style comment.
- Changing this direction requires an ADR and Product Owner approval.
