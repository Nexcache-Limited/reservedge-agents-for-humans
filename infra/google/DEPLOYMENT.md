# Google adapter deployment evidence (WP-08-R5)

This file is **owner-approved deployment evidence**. It locks future Google
resource names for the owner-supplied project. Generic templates
(`env.example`, `cloudrun.yaml`, `Dockerfile`) must not embed the project id.

**Do not apply this document from an agent.** Do not run `gcloud`, create
Artifact Registry repositories, submit Cloud Build jobs, deploy Cloud Run, alter
IAM, create API keys, or download service-account keys.

## Locked names

| Resource                      | Value                                                         |
| ----------------------------- | ------------------------------------------------------------- |
| Project                       | owner-supplied `itaa-g1-dev`                                  |
| Region                        | `us-central1`                                                 |
| Artifact Registry repository  | `itaa-containers`                                             |
| Image                         | `google-adapter`                                              |
| Cloud Run service             | `itaa-google-adapter`                                         |
| Runtime identity              | `itaa-g1-runtime@itaa-g1-dev.iam.gserviceaccount.com`         |
| Model                         | `gemini-2.5-flash`                                            |
| Live overall deadline         | `ITAA_GOOGLE_TIMEOUT_MS=30000` (bounds 5000-45000)            |
| Cloud Run request timeout     | 60s; the model deadline must stay below this                  |
| Initial access                | private / authenticated                                       |
| Public unauthenticated access | prohibited until the Cloudflare security boundary is approved |

Unused duplicate (do **not** use, modify, disable, or delete in this package):

`itaa-google-runtime@itaa-g1-dev.iam.gserviceaccount.com`

## Image identity

Production rollouts must use an immutable digest or a commit-derived tag:

```text
us-central1-docker.pkg.dev/itaa-g1-dev/itaa-containers/google-adapter@sha256:<digest>
us-central1-docker.pkg.dev/itaa-g1-dev/itaa-containers/google-adapter:<git-sha>
```

Do **not** treat `:latest` as deployment evidence.

## Authentication

Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`) with Application Default
Credentials. No API key. No downloaded service-account JSON in the image or
repository.

## Credentialed gate

Ordinary CI skips `adapters/google/tests/test_wp08_live_gemini.py` unless
`ITAA_GOOGLE_LIVE_TEST=1`. That opt-in test must invoke real `LiveModel`
extraction through Vertex using production-equivalent composition
(`ITAA_GOOGLE_TIMEOUT_MS=30000`, no test-only deadline override), fail closed
on any `ApplicationError` / timeout / quota / refusal / schema / missing SDK /
missing proposal / fake-mode path, require three consecutive synthetic
extractions, and print only sanitized metadata (`LIVE_VERTEX_OK`, model, task,
proposal present, latency_ms).

Fake composition keeps `ResiliencePolicy.timeout_ms=2000`. Live composition
reads `ITAA_GOOGLE_TIMEOUT_MS` and fails closed when it is missing, non-integer,
zero, negative, below 5000, or above 45000. There is one overall deadline shared
across retries. `/readyz` does not expose the deadline value or project id.

The opt-in module also ignores upstream `DeprecationWarning` from ADK / aiohttp
so the repository's pytest `-W error` setting cannot abort a real Vertex call.
The AFC advisory is a log warning, not a `DeprecationWarning`, and is not
suppressed globally.

## ADK advisory (non-blocking)

`google-genai` logs that automatic function calling (AFC) is enabled by default
when `GenerateContentConfig.automatic_function_calling.disable` is unset, and
warns against direct `AsyncModels.generate_content` / `Models.generate_content`
AFC. ITAA constructs `LlmAgent` with `output_schema`, `generate_content_config`
for low-variance structured output, and an empty tools list. The extraction
agent cannot invoke facade tools or business actions. This is an upstream
advisory from ADK / `google-genai`; do not suppress it globally and do not
migrate APIs solely to silence it.
