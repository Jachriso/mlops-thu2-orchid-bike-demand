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
## Lab 3: Docker rerun (même code, environnement propre)

Équipe `mlops-thu2-orchid-bike-demand`. Branche `lab3-docker`, créée depuis `main` au commit `37d5781` (merge de la PR #2, Lab 2).

### Rebuild et rerun (à suivre depuis la racine du dépôt)

Prérequis : Docker Desktop lancé.

    docker build -t orchid-bike:lab3 .
    docker run --name c1 orchid-bike:lab3
    docker run --rm orchid-bike:lab3 uv run --locked pytest -q
    docker cp c1:/app/reports ./out-reports
    docker rm c1

Résultat attendu :
- 49 tests passent.
- MAE de validation : random forest 86.8469, comparateur (moyenne d'entraînement) 154.2318, identiques au Lab 2.
- Readback du modèle : `reload_mae_delta` à 0.0.

Pour comparer avec le Lab 2, ouvrir `out-reports/metrics.json` et le comparer à `bike-demand/reports/metrics.json`. Les `model_run_id` sont différents (nouveau run), c'est normal.

### Preuves

| Élément | Valeur |
| --- | --- |
| Commit de base | `37d5781` |
| Image | `orchid-bike:lab3`, ID `sha256:15c6c02a3bd91f381596db3c4d02dea33b48a2a006a4dbfcc93c45e105139fbf` (970 MB) |
| Run dans le conteneur | `model_run_id` `b508951f7faa46c2aa82c237544b40a0` |
| Tests dans le conteneur | 49 passed |
| Logs bruts | `reports/lab3/logs-build.txt`, `logs-run.txt`, `logs-tests.txt` |

L'image a été construite depuis le dossier de travail au commit de base `37d5781`, plus le `Dockerfile` et le `.dockerignore`, commités ensuite dans `cd25a99` ; `git diff 37d5781 cd25a99 -- bike-demand` est vide (le code du projet est identique).

Build et image ID :

![Build et image ID](images/lab3-build.png)

Run et tests :

![Run et tests](images/lab3-run.png)

Un lock périmé fait échouer `docker build` à l'étape `uv sync --locked --no-install-project` (testé sur une copie jetable, en ajoutant `requests>=2` à `pyproject.toml` sans mettre à jour `uv.lock` ; log brut : `reports/lab3/logs-stale-lock-build.txt`) :

![Lock périmé](images/lab3-stale-lock.png)

### Choix du Dockerfile

- **`python:3.12-slim`** : correspond à `requires-python = ">=3.12,<3.13"`.
- **uv 0.12.24** copié depuis l'image officielle, compatible avec `required-version = ">=0.12.19,<0.13"`.
- **`pyproject.toml` et `uv.lock` d'abord**, puis `uv sync --locked --no-install-project` : les dépendances restent en cache quand seul le code change. Un second `uv sync --locked` installe le projet lui-même.
- **Copiés dans l'image** : `src/`, `configs/`, `data/` (snapshot du Lab 2), `tests/`, `README.md`, `.python-version`, `.github/` et `reports/week-01-team.md` (le test `preflight` vérifie leur présence).
- **Non copiés** (voir `.dockerignore`) : `.venv`, `.git`, caches, `.env`, `artifacts/`, `tracking/`, ainsi que `reports/metrics.json` du Lab 2, pour que la rerun reparte de zéro.
- **`git` installé** avec `apt-get` : `tracking.py` appelle `git rev-parse HEAD` et `git status`.
- **`CMD`** en exec form : `uv run --locked python -m bike_demand.train --config configs/baseline.yaml`.

### Échecs rencontrés pendant le build

| Étape | Résultat | Cause | Correction |
| --- | --- | --- | --- |
| Premiers tests dans le conteneur | 45 passed, 4 failed | `preflight` ne trouvait pas `README.md`, `.python-version`, `reports/week-01-team.md`, `.github/workflows/ci.yml` | fichiers copiés dans l'image |
| Deuxième essai | 48 passed, 1 failed | `FileNotFoundError: 'git'` (test de readback) | `git` installé dans l'image |
| Troisième essai | 49 passed | | |

Aucun test n'a été désactivé ni modifié.

### Notes

- Le conteneur est stable : deux conteneurs lancés depuis la même image donnent le même `model_sha256` (`d24c050e…`) et les mêmes MAE.
- Ce `model_sha256` diffère de celui du Lab 2 (`fd98ceaf…`, run de Jade sous Windows 11). Les MAE sont identiques, Python est le même (3.12.15) et le lock aussi. La cause n'est pas établie.
- `.git` est exclu de l'image : le commit se note à l'extérieur du conteneur avec `git rev-parse HEAD`.
- Ces vérifications sont locales (Docker Desktop sur Mac), pas une CI distante.


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
 
  and the model beats the baseline.



## Lab 5: Deploy

Run the Lab 4 service from its image, with settings passed in at start-up. These are the only steps needed to start it.

### Start it

```
docker build -t orchid-bike:lab5 .
docker run -d --name bike -p 127.0.0.1:8000:8000 -e MODEL_PATH=artifacts/model.joblib orchid-bike:lab5
curl -i http://127.0.0.1:8000/health
```

- `-p 127.0.0.1:8000:8000` publishes the port to your own machine only.
- On Windows PowerShell, use `curl.exe` instead of `curl`. If a long command gets cut when pasted, put the setting in a variable first: `$m = "MODEL_PATH=artifacts/model.joblib"`, then `-e $m`.
- Read what the service says with `docker logs bike`. Stop it with `docker rm -f bike`.

### Settings

| Variable | Default | If wrong |
| --- | --- | --- |
| `MODEL_PATH` | `artifacts/model.joblib` (inside the image) | service stays up, `/health` and `/predict` answer 503, one `ERROR` line at start-up names the cause |
| `METADATA_PATH` | `model-metadata.json` next to the model | same as above |

### Start-up decisions

**Settings: what changes between laptop and container?**
Only the model location is configurable, through environment variables passed with `-e` at `docker run`. The image is the same everywhere. *Rejected:* hard-coding paths in the code or baking a per-machine config file into the image, because the same image could then not run elsewhere without a rebuild.

**Model: where does it come from at start-up?**
The model is trained once at build time (`trainer` stage) and copied into the final image under `artifacts/`. The service only loads it, once, when it starts; it never trains. `MODEL_PATH` can point to another trusted file. *Rejected:* training at start-up (slow, and each start could produce a different model) and downloading the model at start-up (needs network and credentials).

**Ready: when do we call the service ready?**
When `GET /health` answers `200` with a `model_version`, which only happens after the model and its metadata were loaded and checked. *Rejected:* "the container is running" or the log line `Application startup complete`: both appear even when no model is loaded.

**Broken: what does it say if the model is missing?**
It stays up and fails closed: `/health` and a valid `/predict` answer `503 {"detail":"no usable model loaded"}`, while an invalid request still gets `422` (validation runs before the model check). The start-up log names the cause in one line. *Rejected:* crashing at start-up (the operator gets no `/health` answer to read) and answering with a default prediction (a confident wrong answer).

### Break it on purpose

Start it with a model path that does not exist:

```
docker run -d --name bike-broken -p 127.0.0.1:8000:8000 -e MODEL_PATH=/nonexistent/model.joblib orchid-bike:lab5
```

Observed (commit `cab9507`, image `sha256:76a4c875…`):

| Request | Status |
| --- | --- |
| `GET /health` | 503 `no usable model loaded` |
| `POST /predict`, valid body | 503 |
| `POST /predict`, `hum = 1.5` | 422 |

What it leaves behind in `docker logs bike-broken`:

```
ERROR:    no usable model, /health and /predict answer 503: model file not found: /nonexistent/model.joblib
INFO:     Application startup complete.
```

Someone can find the cause from this one `ERROR` line. Two limits: the cause appears only at start-up, so the per-request lines show `503` without the reason; and `Application startup complete` is printed even though the service is not ready, so readiness must be read from `/health`, not from that line.
## Lab 5: Check (identity, expected, promise)

### How to run the check

1. Build and start the container exactly as in "Lab 5: Deploy / Start it" above
   (image `orchid-bike:lab5`, container `bike`).
2. Record the expected values from the image, not from the running service:
   `docker run --rm orchid-bike:lab5 cat artifacts/model-metadata.json`
   and note `model_version` and `model_sha256`.
3. From another terminal, at the repository root (Python 3, standard library only):
   `python3 scripts/check_deployed.py <expected_model_version>`
   Exit status 0 means every claim matched; 1 means at least one FAIL line.

The script calls the running container over HTTP (no TestClient): GET /health,
a valid POST /predict, and an invalid POST /predict (hum = 1.5, expected 422).
It expects the service on http://127.0.0.1:8000.

### identity: which id shows which model is running?

Choice: `model_version`, returned by /health and /predict. It comes from
`artifacts/model-metadata.json`, which also stores `model_sha256`. I checked that
`sha256sum artifacts/model.joblib` in the container gives the same value as
`model_sha256` in the metadata (d24c050e...). The check compares `model_version`
only, because /health does not return `model_sha256`.

Rejected: the image tag can be moved and says nothing about the model inside; the
image ID identifies one build, not the model.

### expected: who knows the expected model, and when?

Choice: whoever builds the image reads the metadata from the image right after the
build (step 2) and passes `model_version` to the script as an argument.

Rejected: reading the expected value from the running service (the check would
validate itself), and hard-coding it in the repository. On the same commit
(cab9507), my build gave `baseline-32b2127e4f74` and PR #8 reports
`baseline-42b3b51f3431`; I do not know why they differ, so a fixed value in the
repo would fail.

Limits: the expected value comes from the same image, so the check detects a wrong
or stale container, not a bad build. The metadata has `training_commit:
"unavailable"`, so this check does NOT verify which code is running.

### promise: what does "deployed" promise to others?

Choice: the container started from the README steps; /health returns 200; a valid
/predict returns 200 with a finite, non-negative prediction; an invalid input gets
422; and `model_version` equals the value recorded at build time. The check exits 0.

It does not promise model quality, code identity, CI results or load behaviour.

Rejected: "the container is running", which does not show which model answers.

### Evidence (this run)

My run used `docker build -t bike-demand:dev .` and a container named `c1`
(`docker run --rm --name c1 -p 127.0.0.1:8000:8000 -e MODEL_PATH=artifacts/model.joblib bike-demand:dev`);
otherwise it follows "Start it".

- Commit: cab9507b000c6c7ce408eadfc618526eb6e92bc7
- Image: sha256:53a5ab37451b4017b93c7d05665768bf9f2190a403feb0a5b14877f2b3ac95e4
- Run: `evidence/lab5-check-ok.txt` (exit 0), `evidence/lab5-check-fail.txt`
  (wrong expected version, exit 1), `evidence/lab5-logs-raw.txt`.
