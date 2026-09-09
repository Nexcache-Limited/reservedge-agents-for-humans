# Documented Cloud Run image. Do not deploy from this file.
# Sources accessed 2026-08-26:
# https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-fastapi-service
# https://docs.cloud.google.com/run/docs/tips/python
# https://google.github.io/adk-docs/
FROM python:3.12-slim

RUN useradd --create-home --uid 10001 nonroot
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/supplier-simulator ./apps/supplier-simulator
COPY adapters/google ./adapters/google
COPY tools ./tools

# Production image includes the adapter live extra. CI remains fake-capable.
# The frozen virtualenv is the runtime; container start must not invoke uv.
RUN uv sync --frozen --package itaa-google-adapter --extra live \
    && chown -R nonroot:nonroot /app

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONPATH=/app/adapters/google/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
ENV ITAA_GOOGLE_MODEL_MODE=fake
USER nonroot
EXPOSE 8080
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn itaa_google_adapter.app:app --host 0.0.0.0 --port ${PORT}"]
