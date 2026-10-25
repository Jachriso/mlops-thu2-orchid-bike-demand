FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /bin/
COPY bike-demand/pyproject.toml bike-demand/uv.lock ./
RUN uv sync --locked --no-install-project
COPY bike-demand/src ./src
COPY bike-demand/configs ./configs
COPY bike-demand/data ./data
COPY bike-demand/tests ./tests
COPY bike-demand/README.md bike-demand/.python-version ./
COPY bike-demand/.github ./.github
COPY bike-demand/reports/week-01-team.md ./reports/week-01-team.md
RUN uv sync --locked
RUN mkdir -p reports artifacts tracking
 
# Training happens here, at build time. The service never trains.
FROM base AS trainer
RUN uv run --locked python -m bike_demand.train --config configs/baseline.yaml
 
# Final image: code + tests + only the trained artifacts.
FROM base
COPY --from=trainer /app/artifacts ./artifacts
# Code revision, passed at build time (the image has no .git): the service writes
# it in every log line. Without --build-arg it stays "unknown".
ARG SERVICE_REVISION=unknown
ENV SERVICE_REVISION=$SERVICE_REVISION
EXPOSE 8000
# The service writes its own one-line-per-request log; uvicorn's access log is off.
CMD ["uv", "run", "--locked", "uvicorn", "bike_demand.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]