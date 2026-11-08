# Lab 8: incident record

Recorder: Marie (`Leona224`). This record says **what happened**; `RUNBOOK.md` tells the
next operator what to do. Raw evidence is kept as text next to this file and is never
edited after the fact (slide 9).

## Status
- Baseline 1 measured on the old `main` (`d312a24`); `main` then moved to `7e42d3f`
  (Lab 7 pipeline, aligned `uv.lock`), so **baseline 2** was measured on the new code.
  Baseline 2 is the reference for the drill.
- Fault attempt 1 (`lab-08-injector`, `119820f`): **refused at build time** by the
  training settings guard; no image was produced and serving was not affected. A fault
  that reaches the service has been requested from the injector.
- Diagnosis, rollback and recovery: not done yet.

The drill runs **locally with Docker**, as allowed by slide 17, because the operator has
no access to the GCP project (see "Scope and limits").

## Roles
| Role | Member | Rule |
| --- | --- | --- |
| Operator | Marie | investigates without knowing the fault |
| Injector | Hajar | prepares one reversible fault on a branch, does not reveal it |
| Recorder | Marie | keeps the UTC timeline and the raw evidence |
| Runbook author | Marie | writes `RUNBOOK.md` from this drill |
| Runbook peer | TBD (not Marie) | follows `RUNBOOK.md` without its author narrating |

The fault is revealed only **after** the diagnosis is recorded. The operator and the
recorder are the same person; every observation is therefore written down with its raw
evidence when it is made, not reconstructed afterwards.

## Scope and limits
- Service: the Lab 4-7 API, run locally from its Docker image (`docker run`, port
  published to `127.0.0.1` only). The injector's faulty release is built from her branch
  and run the same way.
- Recovery target: a **retained accepted bundle** (Lab 7), checked with `bundle verify`
  before switching. No retraining as recovery.
- **Cloud Run blocker:** only Jade has access to the GCP project and the models bucket
  (Lab 7 challenge, PR #20). The drill is therefore not run on Cloud Run; replaying the
  rollback on Cloud Run from `RUNBOOK.md` is proposed to Jade as a next step.
- The image still retrains a model at build time (`trainer` stage). To serve the accepted
  model, the bundle is mounted read-only and selected with `MODEL_PATH` and
  `METADATA_PATH`.

## 1. Normal, before the fault 

### Baseline 2 (reference for the drill)
| Item | Value |
| --- | --- |
| Observation window (UTC) | 2026-11-08T23:27:32Z to 2026-11-08T23:28:03Z |
| Workload | 5 `GET /health`, 20 valid `POST /predict` (same body), 5 invalid `POST /predict` (`hum = 1.5`), sent with `curl` from the same machine |
| Where | local Docker, Windows 11, port published to `127.0.0.1` only |
| Code | commit `ccabd24` (branch `lab-08-incident-record` = `main` `7e42d3f` + this record) |
| Image | `sha256:97e4f5be60201bba58e50237a1f22bd775ec67ea37d29c2e9840fc63f5123bc5` |
| Model served | accepted bundle `v1-d24c050e3631`, mounted read-only with `MODEL_PATH` and `METADATA_PATH` |
| Model identity seen by `/health` | `model_version` `baseline-0b7ee4462ec6` (same as `bundle verify` on v1); `/health` does not report `model_sha256` |
| Dependencies | `uv.lock` of `main` identical to the bundle's `uv.lock` (sha256 `955FD4FD…`) |
| Accepted pointer | `models/accepted.json` current: `75dedf7d…` (manifest of v1) |
| Results | health 5/5 → 200; valid 20/20 → 200; invalid 5/5 → 422 |
| Latency, valid predictions (n = 20) | median 9.4 ms, p95 11.9 ms (nearest rank, `curl` `time_total`) |
| Raw evidence | [`baseline2-requests.txt`](baseline2-requests.txt), [`baseline2-service.log`](baseline2-service.log) |

### Baseline 1 (old `main`, kept for the record)
| Item | Value |
| --- | --- |
| Observation window (UTC) | 2026-11-08T22:30:24Z to 2026-11-08T22:31:00Z |
| Code / image | `a58f051` (`main` `d312a24`) / `sha256:099e606f936b36cbfd1c75d95eb644ef85dbb7ac21ef30c8c5408900c81ae929` |
| Model | bundle v1, `model_version` `baseline-0b7ee4462ec6` |
| Results | health 5/5 → 200; valid 20/20 → 200; invalid 5/5 → 422 |
| Latency (n = 20) | median 13.5 ms, p95 22.0 ms |
| Note | the `uv.lock` of `d312a24` differed from the bundle's `uv.lock`; the bundle loaded and served anyway |
| Raw evidence | [`baseline-requests.txt`](baseline-requests.txt), [`baseline-service.log`](baseline-service.log) |

The two baselines agree on every count and on the model identity. The latency difference
comes from 20 samples on a laptop and is not interpreted.

### Signal definitions 
| Signal | Eligible attempts | Good attempts | Unit / window | Missing data |
| --- | --- | --- | --- | --- |
| Readiness | `GET /health` calls | 200 with the expected `model_version` | count per window | no answer counts as not ready |
| Prediction success | valid `POST /predict` calls | 200, finite value ≥ 0, expected `model_version` | ratio per window | no answer counts as a failure |
| Validation rejections | invalid `POST /predict` calls | 4xx (expected) | count per window | not counted as failures |
| Latency | valid `POST /predict` calls answered | time measured by `curl` (`time_total`) | ms, median and p95 (nearest rank) | unanswered calls are reported separately, not as a latency |
| Release build | build of a new release | image produced | pass / fail | a refused build means nothing new is served |

Intentional 422 rejections are **not** failures of valid predictions. The expected
identity is `model_version` because `/health` does not report `model_sha256`.

## 2. Timeline (UTC)
| Time (UTC) | Who | What was observed or done | Evidence |
| --- | --- | --- | --- |
| 2026-11-08T22:28:38Z | Marie | service started from image `099e606f…` with bundle v1 | [`baseline-service.log`](baseline-service.log) |
| 2026-11-08T22:28:49Z | Marie | `/health` → 200, `model_version` `baseline-0b7ee4462ec6` | terminal output |
| 2026-11-08T22:30:24Z | Marie | baseline 1 workload started | [`baseline-requests.txt`](baseline-requests.txt) |
| 2026-11-08T22:31:00Z | Marie | baseline 1 workload ended: no failure | [`baseline-requests.txt`](baseline-requests.txt) |
| 2026-11-08T23:05Z | Hajar | announced a faulty release on branch `lab-08-injector` (`119820f`). Her message included a hint about the fault area; the investigation deliberately starts from the symptoms | team chat |
| 2026-11-08T23:06Z | Marie | release `119820f` checked out in a separate worktree; its commit message reads "under-trained model fault (config)". Treated as release metadata to verify, not as the conclusion | `git log` |
| 2026-11-08T23:09Z | Marie | build of release `119820f` refused at the `trainer` stage: "config: use the Week 1 RF preset; settings changes need review". No image produced; serving state unchanged | [`release-build-refused.txt`](release-build-refused.txt) |
| 2026-11-08T23:12Z | Marie | build rerun with full output saved as raw evidence; same refusal | [`release-build-refused.txt`](release-build-refused.txt) |
| 2026-11-08T23:15Z | Marie | asked the injector for a fault that reaches the service, without bypassing the guard | team chat |
| 2026-11-08T23:17Z | Marie | found that `main` moved from `d312a24` to `7e42d3f` (Lab 7 pipeline, `uv.lock` changed) | `git log`, `git diff --stat` |
| 2026-11-08T23:20Z | Marie | merged `main` into this branch (`ccabd24`); `uv.lock` of `main` identical to the bundle's (`955FD4FD…`) | `Get-FileHash` |
| 2026-11-08T23:23Z | Marie | `bundle verify` on v1 with the new `main`: `status: ok`, MAE 86.84685685591091, exit 0 | terminal output |
| 2026-11-08T23:26:27Z | Marie | service started from image `97e4f5be…` with bundle v1; `/health` → 200, `baseline-0b7ee4462ec6` | [`baseline2-service.log`](baseline2-service.log) |
| 2026-11-08T23:27:32Z | Marie | baseline 2 workload started | [`baseline2-requests.txt`](baseline2-requests.txt) |
| 2026-11-08T23:28:03Z | Marie | baseline 2 workload ended: no failure | [`baseline2-requests.txt`](baseline2-requests.txt) |
| TBD | | | |

## 3. First signal 
- Signal: TBD (attempt 2)
- Time (UTC): TBD
- Affected scope: TBD
- Image and model observed: TBD
- Raw evidence: TBD

## 4. Hypotheses 
| | Hypothesis A | Hypothesis B |
| --- | --- | --- |
| Statement | TBD | TBD |
| Predicted signature | TBD | TBD |
| Discriminating check | TBD | TBD |
| Actual result | TBD | TBD |
| Kept or rejected | TBD | TBD |
| Still uncertain | TBD | TBD |

### Boundaries checked 
| Boundary | Checked? | Observation |
| --- | --- | --- |
| Code and image | TBD | TBD |
| Model version and verified bytes | TBD | TBD |
| Configuration (environment variables and training config) | TBD | TBD |
| Inputs | TBD | TBD |

## 5. Response and rollback target 
- Why rollback fits: TBD
- Target: version `v1-d24c050e3631`, `manifest_sha256` `75dedf7d…`, bundle URI from
  `models/accepted.json`
- Integrity check before switching: `bundle verify` exit 0 on the new `main` at
  2026-11-08T23:23Z (to be run again right before the switch)
- Compatibility: dependencies checked (`uv.lock` of `main` = bundle's `uv.lock`); feature
  order and validation rows checked by `bundle verify`; configuration: TBD
- Action taken: TBD

## 6. Verification after recovery 
| Source | Expected | Observed |
| --- | --- | --- |
| Identity (`/health`, `model_version`) | `baseline-0b7ee4462ec6` | TBD |
| Fresh requests (same workload as baseline 2) | health 5/5 → 200, valid 20/20 → 200, invalid 5/5 → 422 | TBD |
| Post-change logs and window | no error line, one log line per request | TBD |

A successful command alone does not prove recovery.

## 7. Baseline, incident, recovery 
| Period | Window (UTC) | Count | Identity | Signals |
| --- | --- | --- | --- | --- |
| Baseline 2 | 23:27:32Z to 23:28:03Z | 30 requests | `baseline-0b7ee4462ec6` | health 5/5 200, valid 20/20 200, invalid 5/5 422; latency median 9.4 ms, p95 11.9 ms |
| Incident | TBD | TBD | TBD | TBD |
| After recovery | TBD | TBD | TBD | TBD |

## 8. Observed, unknown, next action 
- Observed:
  - the service serves the accepted bundle v1 on both the old and the new `main`, when
    the bundle is mounted and selected with `MODEL_PATH` and `METADATA_PATH`;
  - the new `main` uses exactly the bundle's `uv.lock`, and v1 still passes
    `bundle verify`, so v1 is a compatible rollback target;
  - fault attempt 1 (a training configuration change) never reached the service: the
    training settings guard refused it at build time. The guard was not bypassed.
- Unknown:
  - the symptoms of a fault that does reach the service (attempt 2 pending);
  - whether the procedure works on Cloud Run (no access).
- Next action and owner: Hajar prepares a fault that reaches the service and can be
  reversed with the retained bundle v1; Marie runs it with the baseline 2 workload.