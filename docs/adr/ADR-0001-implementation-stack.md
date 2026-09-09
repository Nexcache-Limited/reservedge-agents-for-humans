# ADR-0001 — Implementation stack

- Status: Accepted
- Date: 2026-08-15
- Decision owners: Product Owner; recorded from the approved Engineering Kickoff Pack

## Context

ITAA v1 needs one repository that can host a cloud-neutral backend/core, typed web and mobile clients, provider adapters, local infrastructure, tests, and evidence. The first competition gate is Google All Things Agentic on 31 August 2026, followed by AWS and mobile gates. The stack must stay small enough for a six-week path and must not bake a cloud vendor into the domain.

## Decision

Use the already-approved implementation direction:

- Python 3.12 is the canonical backend and core runtime.
- FastAPI and Pydantic v2 are the approved API/application direction. They are not introduced as dependencies in WP-01 and must not be imported by `packages/domain`.
- TypeScript is the client/workspace language for future React web and React Native mobile applications. Web and mobile build/runtime choices (including Vite or Expo) remain deferred.
- PostgreSQL is the local development database, started through Docker Compose. Cloud datastores remain future adapters. WP-01 does not create product schemas, migrations, or ORM models.
- Canonical contracts will use JSON Schema 2020-12 and OpenAPI 3.1. Generated Python and TypeScript types follow in WP-02.
- Foundation toolchain selected in WP-01:
  - Python workspace: `uv` for environment and lockfile management, `ruff` for lint/format, `mypy` in strict mode, `pytest` with coverage and warnings-as-errors.
  - TypeScript workspace: `pnpm` workspaces, TypeScript strict mode, ESLint, Prettier, and Node's built-in test runner via `tsx`.
  - Local database: Docker Compose and PostgreSQL 16, published on localhost:5433 to avoid colliding with an existing PostgreSQL on 5432.
  - CI: GitHub Actions running the same quality gate as `make check`.
- Shared UI belongs in `packages/ui-kit`. Tokens and components are UI-00 work, not this ADR.

## Consequences

- Contributors install Python 3.12, `uv`, Node.js 22+, `pnpm`, and Docker Desktop/Engine.
- Provider SDKs, agent frameworks, React application tooling, and ORMs stay out of the core until a later accepted work package.
- Changing the backend language, introducing a second domain stack, or selecting a production cloud database requires a superseding ADR.
