FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
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
CMD ["uv", "run", "--locked", "python", "-m", "bike_demand.train", "--config", "configs/baseline.yaml"]
