# Project scope

**User and goal**
The user is a bike-sharing operator who needs to anticipate demand.
Goal: estimate the total number of bike rentals for a given hour,
and expose this estimate through a prediction API.

**Input**
Calendar and weather information supplied for one hour:
hour, weekday, season, and weather conditions.

**Output**
- `prediction`: estimated hourly rentals
- `model_version`: identity of the loaded model

**In scope**
A prediction service (model + API + Docker), with tests, CI,
and evidence that it works and can be recovered.

**Non-goals**
- No real-time data collection, no user interface, no dashboard.
- Lab 1 does not train a model: it only sets up the team workflow
  and repairs the `normalize_team_slug` helper.

**How success is checked**
- Lab 1: `ruff`, `pytest -m infra` and `pytest -m lab1` pass on the merged commit.
- Later: the API returns a valid prediction and the model version,
  and the model beats the baseline.
## Lab 3: Docker rerun

**Goal** Run the Lab 2 baseline in a clean container, from the locked dependencies.

**How to rebuild** (from the repository root, Docker Desktop running)

    docker build -t orchid-bike:lab3 .
    docker run --name c1 orchid-bike:lab3
    docker run --rm orchid-bike:lab3 uv run --locked pytest -q
    docker cp c1:/app/reports ./out-reports
    docker rm c1

**How success is checked**

* 49 tests pass in the container.
* Validation MAE matches Lab 2: random forest 86.8469, train-mean comparator 154.2318.
* A stale `uv.lock` makes `docker build` fail at `uv sync --locked --no-install-project`.

**Notes**

* Evidence (logs, screenshots) is in `reports/lab3/` and `images/lab3-*.png`. Details are in `reports/week-2.md`.
* `.git` is not in the image, so the metrics record `training_commit: "unavailable"`.
