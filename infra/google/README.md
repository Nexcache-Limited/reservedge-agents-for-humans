# infra/google

Documented G1 backend deployment plan for the Google adapter FastAPI wrapper. **Do not apply this directory.** Do not run `gcloud`, create projects, mutate DNS, or deploy from an agent. Local `docker build` and a container smoke of `/healthz` and `/readyz` are authorized.

## Official sources (rechecked 2026-08-26)

| Topic                                    | URL                                                                                               |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Cloud Run FastAPI                        | https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-fastapi-service |
| Cloud Run Python tips (`PORT`, non-root) | https://docs.cloud.google.com/run/docs/tips/python                                                |
| ADK 2.7.1                                | https://pypi.org/project/google-adk/2.7.1/                                                        |
| ADK docs / Cloud Run                     | https://google.github.io/adk-docs/ and https://google.github.io/adk-docs/deploy/cloud-run/        |
| Vertex / Gemini models                   | https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models                                |
| Gemini terms / ZDR                       | https://ai.google.dev/gemini-api/terms and https://ai.google.dev/gemini-api/docs/zdr              |

## Service

- Image: `infra/google/Dockerfile` (Python 3.12-slim, non-root, no secrets). Installs `uv sync --frozen --package itaa-google-adapter --extra live` so the production image contains `google-adk==2.7.1`.
- Entrypoint: `/app/.venv/bin/uvicorn itaa_google_adapter.app:app --host 0.0.0.0 --port $PORT` from the frozen virtualenv. Container start does not invoke `uv run`, resolve dependencies, or install packages.
- Default process env in the image is `ITAA_GOOGLE_MODEL_MODE=fake` so the container starts without credentials.
- Documented Cloud Run shape (`cloudrun.yaml`, not applied): `ITAA_GOOGLE_MODEL_MODE=live`, Vertex true, region `us-central1`, 1 vCPU, 512Mi, concurrency 40, timeout 60s, min instances 0, max instances 3.

## Owner inputs (not executed)

The owner must supply, out of band:

- GCP project id (`GOOGLE_CLOUD_PROJECT`)
- Artifact Registry or Cloud Run image path
- Dedicated runtime service account
- Cloudflare Pages origin replacing `https://app.example.invalid`

Owner-approved locked names, digest/commit-tag rules, private access, and the
credentialed Vertex gate are in [`DEPLOYMENT.md`](DEPLOYMENT.md). That file is
deployment evidence. Do not copy the owner project id into `env.example` or
`cloudrun.yaml`.

Exact commands for the owner. **Do not run these from this worktree.** Replace
`PROJECT_ID` at apply time. Use a digest or `<git-sha>` tag, never `latest`:

```text
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com aiplatform.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories create itaa-containers --repository-format=docker --location=us-central1
docker build -f infra/google/Dockerfile -t us-central1-docker.pkg.dev/PROJECT_ID/itaa-containers/google-adapter:<git-sha> .
docker push us-central1-docker.pkg.dev/PROJECT_ID/itaa-containers/google-adapter:<git-sha>
gcloud run services replace infra/google/cloudrun.yaml --region=us-central1
gcloud run services update itaa-google-adapter --region=us-central1 --set-env-vars=GOOGLE_CLOUD_PROJECT=PROJECT_ID,ITAA_GOOGLE_MODEL_MODE=live,GOOGLE_GENAI_USE_VERTEXAI=true,ITAA_GCP_REGION=us-central1,GOOGLE_CLOUD_LOCATION=us-central1,ITAA_GEMINI_MODEL=gemini-2.5-flash,ITAA_GOOGLE_TIMEOUT_MS=30000
```

Wait for owner authorization before any of the above. Public unauthenticated
access is prohibited until the Cloudflare security boundary is approved.

## Least-privilege service account

Create a dedicated runtime SA (plan only). Suggested roles, nothing broader:

- `roles/run.invoker` on callers that must hit the service, not on the runtime SA itself unless another service calls it.
- `roles/aiplatform.user` when Vertex is enabled.
- `roles/secretmanager.secretAccessor` on named secrets only.
- No `roles/owner`, `roles/editor`, or project-wide secret admin.

Workload identity / ADC on Cloud Run. Do not bake a JSON key into the image.

## Secret Manager

Production must use Vertex (`GOOGLE_GENAI_USE_VERTEXAI=true`) and ADC. Do not commit `GOOGLE_CLOUD_PROJECT` values or keys. ZDR for the Gemini Developer API is a Google-approved project request and is not enabled here.

## Cloudflare origin

Public web origin is Cloudflare (Pages or equivalent static host). Placeholder: `https://app.example.invalid`. Add that origin to `ITAA_CORS_ORIGINS` on the Cloud Run service. This directory does not deploy Workers, does not mutate DNS, and does not use Vercel.

## Rollback

Plan only: Cloud Run revisions stay immutable. Roll back by shifting traffic to the previous revision. Do not execute `gcloud run services update-traffic`.

## Cost and quota

- Default model `gemini-2.5-flash` — fail closed on quota (`model: quota_exceeded`).
- Cloud Run min instances 0 to avoid idle spend; concurrency 40.
- Live misconfiguration refuses readiness (503) and never falls back to `FakeModel`.
- Timeouts return a manual structured-input fallback for extraction and a deterministic explanation for ranking facts.

## Local container smoke

```text
docker build -f infra/google/Dockerfile -t itaa-google-adapter:local .
docker run --rm -e PORT=8080 -e ITAA_GOOGLE_MODEL_MODE=fake -p 8080:8080 itaa-google-adapter:local
```

Then `GET /healthz` and `GET /readyz` (200 in fake mode). Live mode without Vertex env returns `/readyz` 503. No credentials required for fake mode.
