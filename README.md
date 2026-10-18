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
