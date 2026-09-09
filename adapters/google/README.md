# adapters/google

Competition-specific Google adapter around the cloud-neutral ITAA core. Models may extract airport-parking **requirement evidence** or explain an already-ranked snapshot. Code remains authoritative for ranking, eligibility, isolation, disclosure, approvals, money, state, idempotency, and simulation.

## Official versions (rechecked 2026-08-26, official Google only)

| Decision                                                                                                         | Source                                                                                                          |
| ---------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `google-adk==2.7.1`, Apache-2.0, Python ≥3.10 (repo pin 3.12)                                                    | https://pypi.org/project/google-adk/2.7.1/ accessed 2026-08-26                                                  |
| ADK agents, `LlmAgent` + Pydantic `output_schema`, Runner, `InMemorySessionService`, `runner.run_async`          | https://google.github.io/adk-docs/ and https://google.github.io/adk-docs/agents/llm-agents/ accessed 2026-08-26 |
| Do **not** combine tools + `output_schema` on Gemini 2.5                                                         | https://google.github.io/adk-docs/agents/llm-agents/ accessed 2026-08-26                                        |
| Default model `gemini-2.5-flash` via `ITAA_GEMINI_MODEL`                                                         | https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models accessed 2026-08-26                          |
| Vertex via `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `ITAA_GCP_REGION` / `GOOGLE_CLOUD_LOCATION` | https://google.github.io/adk-docs/ and Gemini / Vertex docs accessed 2026-08-26                                 |
| Cloud Run FastAPI + `PORT` / non-root                                                                            | https://docs.cloud.google.com/run/docs/tips/python accessed 2026-08-26                                          |
| Token counts from event / `LlmResponse.usage_metadata`                                                           | https://google.github.io/adk-docs/ accessed 2026-08-26                                                          |

`EXTRACT_TEMPLATE_VERSION` is `wp08.extract.v3`. Live extra is optional (`[project.optional-dependencies] live`) and locked in root `uv.lock` as an extra of `itaa-google-adapter`. `uv sync --group dev` installs that extra so non-credentialed tests can construct real ADK objects. Runtime default remains `ITAA_GOOGLE_MODEL_MODE=fake`.

`google-adk==2.7.1` (accessed 2026-08-26) declares `fastapi>=0.133`, `starlette>=1.3.1`, and `pydantic>=2.12`. Patched ADK 1.x that fits the old FastAPI 0.116.1 / Pydantic 2.11 pins is `1.20.0`, but PyPI lists CVE-2026-4810 until `1.28.1` / `2.0.0a2`. The workspace therefore pins `fastapi==0.133.0` and `pydantic==2.12.5` (Starlette resolves to ≥1.3.1; `google-genai` requires Pydantic ≥2.12.5) with **no** `override-dependencies`. The adapter uses ADK `LlmAgent` / `Runner` only, not the ADK FastAPI dev UI.

## Model mode

`ITAA_GOOGLE_MODEL_MODE=fake|live` (default **fake**). Unknown values fail closed (`model: schema_invalid`). Live requires Vertex config and does **not** fall back to `FakeModel`. `ITAA_GOOGLE_LIVE=1` is a deprecated alias that selects live only when the mode env is unset. Credentialed tests: `ITAA_GOOGLE_LIVE_TEST=1` (skipped in CI). Production Cloud Run must set `ITAA_GOOGLE_MODEL_MODE=live`.

## HTTP wrapper

`itaa_google_adapter.app:app` mounts `itaa_api.create_app()` and adds:

- `POST /v1/google/extractions` — requirement fields + `fieldAttributions` only. Never emits `intentId`, `buyerToken`, disclosure hashes, or fixture timestamps.
- `POST /v1/google/explanations`

`GET /readyz` is overridden on this wrapper only. Fake mode stays 200. Live mode without Vertex/SDK returns 503 `{status: unavailable, adapter: live, environment: local_simulation}` with no project ids or secrets. Unknown mode is 503.

CORS allowlist: `ITAA_CORS_ORIGINS` (comma-separated). Default `http://localhost:5173`. Documented Cloudflare Pages placeholder: `https://app.example.invalid`. Never Vercel.

## Behavior

- Extraction never auto-approves A1 and never calls dispatch. Missing required information stays missing. Accessibility is not silently defaulted.
- Every accepted field carries origin (`extracted` \| `user_confirmed` \| `deterministic_default`), confidence, and evidence or `noEvidence`.
- Application code — not the model or the JFK fixture — would mint PI id, buyer token, disclosure hash, and timestamps only when converting to a draft PI. Extraction HTTP does not mint them.
- Explanation cannot change scores, totals, downside, or the winner.
- Live path uses injectable `invoke` at the Google SDK boundary. Default invoke lazily imports `google.adk` in `live.py` only, runs `LlmAgent` + `Runner` + `InMemorySessionService`, and maps provider errors to closed `field: code` values.
- Telemetry records model name, adapter/template version, correlation id, latency, and token counts. It never records raw prompts or responses by default.

## Local

```text
PYTHONPATH=adapters/google/src uv run pytest adapters/google/tests
uv sync --frozen --package itaa-google-adapter --extra live
```

The live extra is installed in the dev group so tests can construct ADK objects without credentials. Set `ITAA_GOOGLE_LIVE_TEST=1` only for the strict credentialed Vertex extraction gate in `test_wp08_live_gemini.py`. Ordinary CI skips that module. The gate must not treat `ApplicationError` as success. It uses production-equivalent composition, including `ITAA_GOOGLE_TIMEOUT_MS=30000`, and requires three consecutive synthetic extractions.

ADK / `google-genai` may log an automatic-function-calling advisory on `generate_content` even though ITAA's `LlmAgent` has `output_schema` and no tools. That is a non-blocking upstream advisory; do not suppress it globally.

Live mode requires `ITAA_GOOGLE_TIMEOUT_MS` (approved competition value 30000, bounds 5000-45000). Fake mode stays at a 2000 ms overall deadline. There is one shared `ResiliencePolicy` deadline across retries.
