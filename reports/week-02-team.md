# Week 2, Lab 3: same code, clean environment (locked dependencies, container, rerun)

## Status
- **Lab 3:** Lead author Hajar Benlemqadem (`Hajarblmq`); reviewer Marie Léona (`Leona224`). TODO: add who owns which area for Annabelle and Jade, if they took part.

## Student / team
- **Team:** `mlops-thu2-orchid-bike-demand`
- **Students:** Benlemqadem Hajar (`Hajarblmq`), Marie Léona (`Leona224`), Fautrad Annabelle (`annaftrd`), Parrilla Jade (`Jachriso`)

---

## Roles & Contributions
- **Hajar (lead author):** wrote `Dockerfile` and `.dockerignore`, built the image, ran the baseline and the tests in the container, compared with Lab 2, proved that a stale lock fails, wrote the README section.
- **Marie (reviewer):** TODO (she writes her own section below).
- TODO: Annabelle / Jade, if they own an area.

## Links to Code and Pull Requests
- **Branch:** `lab3-docker` (from `main` at `37d5781`, the merge of PR #2)
- **Pull request:** https://github.com/Jachriso/mlops-thu2-orchid-bike-demand/pull/3
- **Commit packaged:** `cd25a99` (on top of `37d5781`, Lab 2 merged)
- **Review / approval:** TODO: link to Marie's review

## Locked
- Lockfile: `bike-demand/uv.lock`, committed and unchanged by this PR.
- Local check on the host: `uv run --locked pytest -q` -> `49 passed`.
- **A stale lock stops the build.** On a throwaway copy (`/tmp/test-lock`), I added `requests>=2` to `pyproject.toml` without updating the lock, then ran `uv sync --locked`:
  `error: The lockfile at uv.lock needs to be updated, but --locked was provided.`
  The lock was not regenerated. My branch was not touched.
  ![Stale lock fails](../images/lab3-stale-lock.png)

## Packaged
- Files at the repository root: `Dockerfile`, `.dockerignore`, `README.md` (new section "Lab 3").
- Image: `orchid-bike:lab3`, ID `sha256:15c6c02a3bd91f381596db3c4d02dea33b48a2a006a4dbfcc93c45e105139fbf` (970 MB).
  ![Build and image ID](../images/lab3-build.png)
- Raw logs: `reports/lab3/logs-build.txt`, `logs-run.txt`, `logs-tests.txt`.

### Dockerfile decisions
- **Base `python:3.12-slim`:** matches `requires-python = ">=3.12,<3.13"`.
- **uv 0.12.24 copied from the official image:** respects `required-version = ">=0.12.19,<0.13"`.
- **`pyproject.toml` and `uv.lock` first, then `uv sync --locked --no-install-project`:** the dependency layer stays cached when only code changes. A second `uv sync --locked` installs the project itself (build backend `uv_build`, needs `src/`).
- **Copied into the image:** `src/`, `configs/`, `data/` (the Lab 2 snapshot), `tests/`, plus `README.md`, `.python-version`, `.github/` and `reports/week-01-team.md`, because the preflight test checks that they exist.
- **Not copied:** `.venv`, `.git`, caches, `.env`, `artifacts/`, `tracking/` and the Lab 2 `reports/metrics.json`, so the rerun starts from zero and cannot reuse earlier outputs.
- **`git` installed with `apt-get`:** `tracking.py` runs `git rev-parse HEAD` and `git status`.
- **`CMD`:** `uv run --locked python -m bike_demand.train --config configs/baseline.yaml` (exec form), the command from the Lab 2 README.

### Failures observed while building (not hidden)
| Step | Result | Cause | Fix |
| --- | --- | --- | --- |
| First test run in the container | 45 passed, 4 failed | preflight reported missing `README.md`, `.python-version`, `reports/week-01-team.md`, `.github/workflows/ci.yml`; the package test and the readback test also failed | copied those files into the image |
| Second run | 48 passed, 1 failed | `FileNotFoundError: 'git'` in the readback test | installed `git` in the image |
| Third run | **49 passed** | | |

No test was deselected or edited.

## Rerun
Inputs unchanged from Lab 2: same data snapshot, same `configs/baseline.yaml`, same split. No tuning, API, cloud or test-set scoring.

| Item | Lab 2 (Jade, Windows 11) | Container (this lab) |
| --- | --- | --- |
| Validation MAE, random forest | 86.84685685591091 | 86.84685685591091 |
| Validation MAE, train-mean comparator | 154.23179306864967 | 154.23179306864967 |
| Train mean | 143.794 | 143.79444765760556 |
| Readback delta | 0.0 | 0.0 |
| `model_run_id` | `0656443c0a4c4ce8a907b8d367515b42` | `b508951f7faa46c2aa82c237544b40a0` |
| `model_sha256` | `fd98ceaf…c304` | `d24c050e…8c07` |

- 49 tests pass in the container; the baseline `CMD` completes and the readback matches.
  ![Run and tests](../images/lab3-run.png)
- **Run IDs differ:** expected, each run creates new MLflow runs.
- **MAE identical to every printed digit.**
- **`model_sha256` differs from Lab 2.** Two containers started from the same image gave the same hash (`d24c050e…`), so the container rerun is stable. Python is the same on the host and in the container (3.12.15) and the packages come from the same `uv.lock`. The Lab 2 model was produced on Windows 11, so a platform effect is plausible, but **we did not establish the cause**. A rerun on a Mac outside Docker was started and not completed, so it is not evidence.
- The `model_version` string also changed between our container runs (`baseline-e09ff6eeb7fc`, `baseline-264a4ea24207`) while the model hash did not. We did not look at how it is computed.
- **Commit tracking differs from Lab 2.** In the container, `metrics.json` records `training_commit: "unavailable"` and `working_tree_dirty: null`, because `.git` is excluded from the image and `tracking.py` falls back to these values when git has no repository. Lab 2 recorded commit `61c2ade…` with `working_tree_dirty: false`. The commit is therefore tracked outside the container (`git rev-parse HEAD`, here `cd25a99`).

## Revision, image, run
| Link | Value |
| --- | --- |
| Revision | `cd25a99` + `uv.lock` |
| Image | `sha256:15c6c02a3bd9…` (build log in `reports/lab3/logs-build.txt`) |
| Run | `model_run_id` `b508951f7faa46c2aa82c237544b40a0`, MAE 86.847 |

## Decisions and Rationale
- The lock drives the install; a stale lock must stop the build, never be repaired to get green.
- `.git` stays out of the build context so the image does not depend on the laptop.
- The image carries only the files the tests and baseline need; outputs of earlier runs stay out.

## Review and Response

### Reviewer's reproduction (Marie)
TODO: Marie writes this section: clean clone of `lab3-docker`, README only, her build, run and test results, her image ID and `model_sha256`, her finding(s), and the approval commit.

## Local vs remote checks
All runs above are local (Docker Desktop on a Mac). No GitHub CI check was used as evidence for this lab.

## Blockers / Missing Evidence
- The cause of the different `model_sha256` is not established (see Rerun).
- TODO: add anything Marie could not reproduce.

## Screenshots
1. Build and image ID: ![build](../images/lab3-build.png)
2. Run and tests: ![run](../images/lab3-run.png)
3. Stale lock fails: ![stale lock](../images/lab3-stale-lock.png)
