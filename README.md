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
## Lab 3: Docker rerun (same code, clean environment)

Team `mlops-thu2-orchid-bike-demand`. Branch `lab3-docker`, created from `main` at commit `37d5781` (merge of PR #2, Lab 2).

### Rebuild and rerun (run from the repository root)

Prerequisite: Docker Desktop is running.

    docker build -t orchid-bike:lab3 .
    docker run --name c1 orchid-bike:lab3
    docker run --rm orchid-bike:lab3 uv run --locked pytest -q
    docker cp c1:/app/reports ./out-reports
    docker rm c1

Expected result:
- 49 tests pass.
- Validation MAE: random forest 86.8469, comparator (training mean) 154.2318, the same as in Lab 2.
- Model readback: `reload_mae_delta` is 0.0.

To compare with Lab 2, open `out-reports/metrics.json` and compare it with `bike-demand/reports/metrics.json`. The `model_run_id` values differ (new run); this is expected.

### Evidence

| Item | Value |
| --- | --- |
| Base commit | `37d5781` |
| Image | `orchid-bike:lab3`, ID `sha256:15c6c02a3bd91f381596db3c4d02dea33b48a2a006a4dbfcc93c45e105139fbf` (970 MB) |
| Run in the container | `model_run_id` `b508951f7faa46c2aa82c237544b40a0` |
| Tests in the container | 49 passed |
| Raw logs | `reports/lab3/logs-build.txt`, `logs-run.txt`, `logs-tests.txt` |

The image was built from the working tree at base commit `37d5781`, plus the `Dockerfile` and `.dockerignore`, which were committed afterwards in `cd25a99`; `git diff 37d5781 cd25a99 -- bike-demand` is empty (the project code is identical).

Build and image ID:

![Build and image ID](images/lab3-build.png)

Run and tests:

![Run and tests](images/lab3-run.png)

A stale lock makes `docker build` fail at the `uv sync --locked --no-install-project` step (tested on a throwaway copy, by adding `requests>=2` to `pyproject.toml` without updating `uv.lock`; raw log: `reports/lab3/logs-stale-lock-build.txt`):

![Stale lock](images/lab3-stale-lock.png)

### Dockerfile choices

- **`python:3.12-slim`**: matches `requires-python = ">=3.12,<3.13"`.
- **uv 0.12.24** copied from the official image, compatible with `required-version = ">=0.12.19,<0.13"`.
- **`pyproject.toml` and `uv.lock` first**, then `uv sync --locked --no-install-project`: the dependencies stay cached when only the code changes. A second `uv sync --locked` installs the project itself.
- **Copied into the image**: `src/`, `configs/`, `data/` (Lab 2 snapshot), `tests/`, `README.md`, `.python-version`, `.github/` and `reports/week-01-team.md` (the `preflight` test checks that they exist).
- **Not copied** (see `.dockerignore`): `.venv`, `.git`, caches, `.env`, `artifacts/`, `tracking/`, and the Lab 2 `reports/metrics.json`, so that the rerun starts from scratch.
- **`git` installed** with `apt-get`: `tracking.py` calls `git rev-parse HEAD` and `git status`.
- **`CMD`** in exec form: `uv run --locked python -m bike_demand.train --config configs/baseline.yaml` (Lab 3 only; since Lab 4, training runs in the `trainer` build stage and the `CMD` starts the API).

### Failures met during the build

| Step | Result | Cause | Fix |
| --- | --- | --- | --- |
| First tests in the container | 45 passed, 4 failed | `preflight` could not find `README.md`, `.python-version`, `reports/week-01-team.md`, `.github/workflows/ci.yml` | files copied into the image |
| Second try | 48 passed, 1 failed | `FileNotFoundError: 'git'` (readback test) | `git` installed in the image |
| Third try | 49 passed | | |

No test was disabled or changed.

### Notes

- The container is stable: two containers started from the same image give the same `model_sha256` (`d24c050e…`) and the same MAE.
- This `model_sha256` differs from the Lab 2 one (`fd98ceaf…`, Jade's run on Windows 11). The MAE values are identical, and Python (3.12.15) and the lock are the same. The cause is not established.
- `.git` is excluded from the image: the commit is recorded outside the container with `git rev-parse HEAD`.
- These checks are local (Docker Desktop on Mac), not a remote CI.


## Lab 4: Prediction API
 
The service loads the saved baseline model at startup and answers predictions. It never trains: training happens when the image is built (`trainer` stage of the `Dockerfile`).
 
### Build, test, run (Docker)
 
```
docker build -t orchid-bike:lab4 .
docker run --rm orchid-bike:lab4 uv run --locked pytest -q
docker run --rm -p 127.0.0.1:8000:8000 orchid-bike:lab4
```
 
### Endpoints
 
- `GET /health`: `200 {"status": "ok", "model_version": "..."}` when a model is loaded, `503` otherwise.
- `POST /predict`: flat JSON object with the 12 predictors (`season` 1-4, `yr` 0-1, `mnth` 1-12, `hr` 0-23, `holiday` 0-1, `weekday` 0-6, `workingday` 0-1, `weathersit` 1-4 as JSON integers; `temp`, `atemp`, `hum`, `windspeed` as numbers in 0-1). Returns `200 {"prediction": <finite number >= 0>, "model_version": "..."}`.

| Case | Status |
| Valid request, model loaded | 200 |
| Invalid request (missing/extra field, wrong type, out of range, NaN/Infinity, malformed JSON) | 422, even if no model is loaded |
| Valid request, model missing or unusable | 503 |
| Model fails or returns a non-finite/negative value | 500 |
 
**Extra fields are rejected (422).** In particular `cnt`, `casual` and `registered` are labels, not inputs. Numbers must be real JSON numbers: `"2"`, `2.0` for an integer field, and `true` are rejected. The 422 body lists only `loc`, `msg` and `type`, never the submitted value.
 
### Configuration
 
- `MODEL_PATH` (default `artifacts/model.joblib`)
- `METADATA_PATH` (default `model-metadata.json` next to the model)

`model_version` comes from the metadata file. Only load model files you trust (joblib uses pickle).
 
### Limits
 
The model is a baseline random forest; the API checks input ranges but cannot tell whether a prediction is good. A missing model keeps the service up and answering 503; there is no reload without restart.

## Lab 5: Deploy, log and check the service

This section is one path to follow from top to bottom. It starts the Lab 4 service from its Docker image with settings passed at start-up, sends real requests to it, reads one log line per request, and checks from outside the container which model is answering.

Run every command from the repository root. Each step says which commands to use:

- **Windows (PowerShell):** commands for Windows PowerShell. Use `curl.exe`, not `curl` (in PowerShell, `curl` is `Invoke-WebRequest` and asks for a `Uri`), and `python`, not `python3` (on Windows, `python3` may open the Microsoft Store).
- **macOS / Linux (Terminal):** commands for zsh or bash. Use `curl` and `python3`.
- **Windows and macOS / Linux:** the same command works in both.

### What "deployed" means, and who checks it

**Promise: what does "deployed" promise to others?**
Choice: the container was started from these README steps; `/health` returns 200; a valid `/predict` returns 200 with a finite, non-negative prediction; an invalid input gets 422; `model_version` equals the value recorded from the image at build time; and the check script (step 7) exits 0. It does not promise model quality, code identity, CI results or load behaviour. *Rejected:* "the container is running", which does not show which model answers.

**Final check** Run by `Jachriso` on `main` after the last Lab 5 merge and before the `m3` tag, by following steps 1 to 8 below. The output is saved in `reports/lab5/lab5-final-check.txt`. Until that file exists, the service is not called "deployed". 

### Before you start

- Docker Desktop is running.
- Python 3 is installed (the check uses the standard library only).
- The working tree is clean (`git status --short` prints nothing), so the revision written in the logs is the code that was built.
- Port 8000 is free. Remove containers left from an earlier run with `docker rm -f bike bike-broken` ("No such container" is fine).

### 1. Build the image

**Windows (PowerShell):**

```powershell
$rev = git rev-parse --short HEAD
docker build --build-arg SERVICE_REVISION=$rev -t orchid-bike:lab5 .
docker image inspect --format '{{.Id}}' orchid-bike:lab5
```

**macOS / Linux (Terminal):**

```bash
rev=$(git rev-parse --short HEAD)
docker build --build-arg SERVICE_REVISION=$rev -t orchid-bike:lab5 .
docker image inspect --format '{{.Id}}' orchid-bike:lab5
```

Note the commit (`echo $rev`) and the image ID: they are the first two links of the evidence chain (commit → image → run). The model is trained during this build (`trainer` stage of the `Dockerfile`); the service never trains. Without `--build-arg`, the logs say `"service_revision":"unknown"`.

### 2. Record the expected model

**Windows (PowerShell):**

```powershell
docker run --rm orchid-bike:lab5 cat artifacts/model-metadata.json
$expected = (docker run --rm orchid-bike:lab5 cat artifacts/model-metadata.json | Out-String | ConvertFrom-Json).model_version
echo $expected
```

**macOS / Linux (Terminal):**

```bash
docker run --rm orchid-bike:lab5 cat artifacts/model-metadata.json
expected=$(docker run --rm orchid-bike:lab5 cat artifacts/model-metadata.json | python3 -c "import sys, json; print(json.load(sys.stdin)['model_version'])")
echo $expected
```

The first command shows the whole metadata (keep `model_version` and `model_sha256` for your evidence); the second stores `model_version` in `$expected` (for example `baseline-b71392fa90e5`), used in steps 7 and 8. Keep the same terminal open until step 8. The value is read from the image, before the service runs, so the check cannot validate itself (see *expected*). It changes each time the model is retrained, so read it again after every build (see *identity*).

### 3. Start the service

**Windows and macOS / Linux:**

```
docker run -d --name bike -p 127.0.0.1:8000:8000 -e MODEL_PATH=artifacts/model.joblib orchid-bike:lab5
docker ps --filter name=bike
```

`docker ps` must show `bike` as `Up` with `127.0.0.1:8000->8000/tcp`. A container in `Created` did not start (usually port 8000 is still used by another container). `-p 127.0.0.1:8000:8000` publishes the port to your own machine only. The available settings are in [Settings](#settings).

### 4. Wait until it is ready

**Windows (PowerShell):**

```powershell
curl.exe -i http://127.0.0.1:8000/health
```

**macOS / Linux (Terminal):**

```bash
curl -i http://127.0.0.1:8000/health
```

The service is ready when this answers `200 {"status":"ok","model_version":"…"}` with the version from step 2. If the connection is refused, wait a few seconds and retry.

### 5. Send a valid and an invalid request

The bodies are written to files first, which avoids quoting problems. The 12 fields are described in "Lab 4: Endpoints".

**Windows (PowerShell):**

```powershell
'{"season":3,"yr":1,"mnth":7,"hr":17,"holiday":0,"weekday":3,"workingday":1,"weathersit":1,"temp":0.7,"atemp":0.65,"hum":0.5,"windspeed":0.2}' | Out-File -Encoding ascii ok.json
'{"season":3,"yr":1,"mnth":7,"hr":17,"holiday":0,"weekday":3,"workingday":1,"weathersit":1,"temp":0.7,"atemp":0.65,"hum":1.5,"windspeed":0.2}' | Out-File -Encoding ascii bad.json
curl.exe -s -w " [%{http_code}]`n" -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data "@ok.json"
curl.exe -s -w " [%{http_code}]`n" -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data "@bad.json"
```

**macOS / Linux (Terminal):**

```bash
echo '{"season":3,"yr":1,"mnth":7,"hr":17,"holiday":0,"weekday":3,"workingday":1,"weathersit":1,"temp":0.7,"atemp":0.65,"hum":0.5,"windspeed":0.2}' > ok.json
echo '{"season":3,"yr":1,"mnth":7,"hr":17,"holiday":0,"weekday":3,"workingday":1,"weathersit":1,"temp":0.7,"atemp":0.65,"hum":1.5,"windspeed":0.2}' > bad.json
curl -s -w ' [%{http_code}]\n' -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data "@ok.json"
curl -s -w ' [%{http_code}]\n' -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data "@bad.json"
```

Expected: `{"prediction":<number >= 0>,"model_version":"…"} [200]`, then `{"detail":[{"loc":["body","hum"],…}]} [422]`. `ok.json` and `bad.json` are scratch files: do not commit them.

### 6. Read the logs

**Windows and macOS / Linux:**

```
docker logs bike
```

After the start-up lines, each request writes exactly one JSON line (steps 4 and 5 give three lines). The `uvicorn` access log is off (`--no-access-log` in the `Dockerfile`), so a request never appears twice. Example lines (Annabelle's run, commit `6b85a88`):

```
{"timestamp":"2026-10-25T13:26:40.416+00:00","event":"request","request_id":"ca7faa38cbb1","method":"POST","path":"/predict","status":200,"outcome":"ok","duration_ms":78.3,"model_version":"baseline-657f25b9a370","service_revision":"6b85a88"}
{"timestamp":"2026-10-25T13:26:54.999+00:00","event":"request","request_id":"1c6bb5cafae3","method":"POST","path":"/predict","status":422,"outcome":"rejected","duration_ms":0.7,"model_version":"baseline-657f25b9a370","service_revision":"6b85a88","error_fields":["body.hum"]}
```

Each response carries the same id in its `X-Request-ID` header, so a client can quote it to the operator.

To keep the logs as a raw file:

- **Windows (PowerShell):** `cmd /c "docker logs bike > reports\lab5\<name>.log 2>&1"`. Do not use `docker logs bike *> file`: Windows PowerShell 5.1 wraps the start-up lines as `NativeCommandError` and mixes their order.
- **macOS / Linux (Terminal):** `docker logs bike > reports/lab5/<name>.log 2>&1`

### 7. Run the check

**Windows (PowerShell):**

```powershell
python scripts/check_deployed.py $expected
echo $LASTEXITCODE
```

**macOS / Linux (Terminal):**

```bash
python3 scripts/check_deployed.py $expected
echo $?
```

The script sends real HTTP requests to `http://127.0.0.1:8000` (no `TestClient`): `GET /health`, a valid `POST /predict` and an invalid one (`hum = 1.5`). It prints one row per claim and exits 0 only if every claim matches:

```
claim                       expected                  observed                    result
health status               200                       200                         ok
health model_version        baseline-32b2127e4f74     baseline-32b2127e4f74       ok
predict valid               200 + prediction >= 0     200 149.2911970908957       ok
predict model_version       baseline-32b2127e4f74     baseline-32b2127e4f74       ok
predict invalid (hum=1.5)   422                       422                         ok
exit status 0
```

To see it fail, pass a wrong value (`python scripts/check_deployed.py wrong-version` on Windows, `python3 …` on macOS / Linux): the two `model_version` rows become `FAIL` and the exit status is 1.

### 8. Break it on purpose

Start the service with a model path that does not exist, then repeat steps 4, 5 and 7 against it:

**Windows (PowerShell):**

```powershell
docker rm -f bike
docker run -d --name bike-broken -p 127.0.0.1:8000:8000 -e MODEL_PATH=/nonexistent/model.joblib orchid-bike:lab5
curl.exe -i http://127.0.0.1:8000/health
curl.exe -s -w " [%{http_code}]`n" -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data "@ok.json"
curl.exe -s -w " [%{http_code}]`n" -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data "@bad.json"
python scripts/check_deployed.py $expected
docker logs bike-broken
```

Use PowerShell, not Git Bash: Git Bash rewrites `/nonexistent/model.joblib` to `C:/Program Files/Git/nonexistent/model.joblib` (or prefix the command with `MSYS_NO_PATHCONV=1`).

**macOS / Linux (Terminal):**

```bash
docker rm -f bike
docker run -d --name bike-broken -p 127.0.0.1:8000:8000 -e MODEL_PATH=/nonexistent/model.joblib orchid-bike:lab5
curl -i http://127.0.0.1:8000/health
curl -s -w ' [%{http_code}]\n' -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data "@ok.json"
curl -s -w ' [%{http_code}]\n' -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" --data "@bad.json"
python3 scripts/check_deployed.py $expected
docker logs bike-broken
```

| Request | Observed |
| --- | --- |
| `GET /health` | 503 `{"detail":"no usable model loaded"}` |
| `POST /predict`, valid body | 503 |
| `POST /predict`, `hum = 1.5` | 422 (validation runs before the model check) |
| check script | 4 rows `FAIL`, `predict invalid` ok, exit status 1 |

**Failure: what does it leave behind?** In `docker logs bike-broken`, one `ERROR` line at start-up names the missing file, and every 503 request line says why:

```
ERROR:    no usable model, /health and /predict answer 503: model file not found: /nonexistent/model.joblib
INFO:     Application startup complete.
{"timestamp":"2026-10-25T13:41:30.003+00:00","event":"request","request_id":"dbf8b5e13088","method":"POST","path":"/predict","status":503,"outcome":"unavailable","duration_ms":2.0,"model_version":null,"service_revision":"6b85a88","reason":"no_model"}
```

Someone who reads only the logs can find the cause. `Application startup complete` is printed even though the service is not ready, so readiness must be read from `/health`, not from that line.

### 9. Stop

**Windows and macOS / Linux:**

```
docker rm -f bike bike-broken
```

Then delete the scratch files `ok.json` and `bad.json`.

### Settings

| Variable | Default | If wrong |
| --- | --- | --- |
| `MODEL_PATH` | `artifacts/model.joblib` (inside the image) | the service stays up, `/health` and `/predict` answer 503, one `ERROR` line at start-up names the cause |
| `METADATA_PATH` | `model-metadata.json` next to the model | same as above (`metadata file not found: …`) |
| `SERVICE_REVISION` | set at build time by `--build-arg`, otherwise `unknown` | the logs say `"service_revision":"unknown"` |

### Decisions

Each answer gives our choice, the option we rejected, and why. *Promise* is at the top of this section and *failure* in step 8.

#### Start-up (Léona, PR #8)

**Settings: what changes between laptop and container?**
Only the model location is configurable, through environment variables passed with `-e` at `docker run`. The image is the same everywhere. *Rejected:* hard-coding paths in the code or baking a per-machine config file into the image, because the same image could then not run elsewhere without a rebuild.

**Model: where does it come from at start-up?**
The model is trained once at build time (`trainer` stage) and copied into the final image under `artifacts/`. The service only loads it, once, when it starts; it never trains. `MODEL_PATH` can point to another trusted file. *Rejected:* training at start-up (slow, and each start could produce a different model) and downloading the model at start-up (needs network and credentials).

**Ready: when do we call the service ready?**
When `GET /health` answers `200` with a `model_version`, which only happens after the model and its metadata were loaded and checked. *Rejected:* "the container is running" or the log line `Application startup complete`: both appear even when no model is loaded.

**Broken: what does it say if the model is missing?**
It stays up and fails closed: `/health` and a valid `/predict` answer `503 {"detail":"no usable model loaded"}`, while an invalid request still gets `422`. The start-up log names the cause in one line, and each request line says `"reason":"no_model"`. *Rejected:* crashing at start-up (the operator gets no `/health` answer to read) and answering with a default prediction (a confident wrong answer).

#### Logging (Annabelle, PR #10)

**Log line: what must one request tell an operator?**
Choice: `timestamp`, `request_id` (also returned in the `X-Request-ID` header), `method`, `path`, `status`, `outcome` (`ok`, `rejected`, `unavailable`, `error`, `refused`), `duration_ms`, `model_version` (null when no model is loaded) and `service_revision`. Two optional fields explain failures: `reason` (`no_model`, `prediction_failed`, `invalid_prediction`) and `error_fields` (for a 422, the names of the wrong fields, for example `body.hum`). An operator reading only these lines can tell which request it was, what happened, how long it took, and which model and code answered. *Rejected:* the default `uvicorn` access line (status only, no model, code, reason or request id, and it would duplicate ours); free-text messages (hard to search); logging the request body or the prediction to make debugging easier (see *secrets*).

**Secrets: what must never appear in a log?**
Choice: request bodies, query strings, headers (for example `Authorization`), environment variables, prediction values, text chosen by the client (any path other than `/health` and `/predict` is logged as `(other)`), and any metric computed on the test period. The service has no secret today, so the rule is "log metadata, not payloads". For a 422, the line lists the wrong field names, never the values sent. Tests in `bike-demand/tests/test_request_logging.py` check that a body value, a query-string value, a header value and an unknown path do not appear in the line. *Rejected:* logging the whole request for easier debugging, because a payload can carry private or sensitive data, and the same rule already keeps values out of the 422 response.

#### Identity and expected model (Hajar, PR #9)

**Identity: which id shows which model is running?**
Choice: `model_version`, returned by `/health`, `/predict` and every log line. It comes from `artifacts/model-metadata.json`, which also stores `model_sha256`. Hajar checked that `sha256sum artifacts/model.joblib` in the container gives the same value as `model_sha256` in the metadata (`d24c050e…`). The check compares `model_version` only, because `/health` does not return `model_sha256`. *Rejected:* the image tag (it can be moved and says nothing about the model inside) and the image ID (it identifies one build, not the model).

Note: `model_version` is not reproducible. `train.py` builds it with `uuid4()`, a random value drawn at each training, so each build that retrains gives a new string (we saw five different strings, with the same training code and data), while `model_sha256` stayed `d24c050e…` in the builds where we read it. The string identifies one build, which is why the expected value is read from the image after each build.

**Expected: who knows the expected model, and when?**
Choice: whoever builds the image reads the metadata from the image right after the build (step 2) and passes `model_version` to the script as an argument. *Rejected:* reading the expected value from the running service (the check would validate itself), and hard-coding it in the repository (it would fail after the next build, see the note above).

### Evidence

Each run was made by its author on their own machine; image IDs differ because each person built their own image.

| Run | Commit | Image | Result | Raw evidence |
| --- | --- | --- | --- | --- |
| Start-up (Léona, Windows 11) | `cab9507` | `sha256:76a4c875…` | health 200, predict 200, `hum = 1.5` 422; missing model 503 / 503 / 422 | PR #8 description |
| Check (Hajar, macOS) | `cab9507` | `sha256:53a5ab37…` (`bike-demand:dev`, container `c1`) | exit 0 with the right version, exit 1 with a wrong one | `reports/lab5/lab5-check-ok.txt`, `reports/lab5/lab5-check-fail.txt`, `reports/lab5/lab5-logs-raw.txt` |
| Logging (Annabelle) | `6b85a88` | `8c5567d14241` | 145 tests passed in the image; one line per request; check exit 0; missing model logged with `reason` | `reports/lab5/lab5-logging-*.txt` |
| Final check (Jade) | `main` after the last merge | — | pending | `reports/lab5/lab5-final-check.txt` |

### Limits

- The check compares `model_version` only. It does not compare `model_sha256` or `service_revision`, so code identity is visible in the logs but not verified. The model metadata has `training_commit: "unavailable"`.
- The expected value comes from the same image, so the check detects a wrong or stale container, not a bad build.
- `service_revision` is only as good as the value passed at build time: a dirty tree or a forgotten `--build-arg` gives a wrong or `"unknown"` value.
- If the model raises an unexpected error, the traceback is still written to the container log by the `uvicorn.error` logger, with the exception text. We did not review what such a text could contain.
- `uv run` re-installs the project at each container start (`Uninstalled 1 package / Installed 1 package` in the logs).
- No log retention or access control is defined; these are local logs. All runs are local; there is no CI yet (Lab 6).
