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