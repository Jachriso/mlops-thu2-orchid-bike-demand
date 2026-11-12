# Lab 8: incident record

Recorder: Marie (`Leona224`). This record says **what happened**; `RUNBOOK.md` tells the
next operator what to do. Raw evidence is kept as text next to this file and is never
edited after the fact (slide 9).

## Status
- Baseline 1 measured on the old `main` (`d312a24`); `main` then moved to `7e42d3f`, so
  **baseline 2** was measured on the new code and is the reference for the drill.
- Fault attempt 1 (`lab-08-injector`, `119820f`): refused at build time by the training
  settings guard; serving not affected.
- Fault attempt 2 (`release-2`): **diagnosed and recovered** on 9 Nov. A non-accepted
  model was served with normal status codes; rollback to the verified accepted bundle v1
  restored the expected identity and behaviour.
- Fault revealed by the injector: TBD (asked after the diagnosis and recovery were
  committed).
- `RUNBOOK.md`: written from this drill; to be followed by a peer without its author.

The drill runs **locally with Docker**, because the operator has
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
| 2026-11-08T23:53:38Z | Marie | release-2 deployed (container `bike-release2`, same image, bundle `release-2`) | `incident-service.log` |
| 2026-11-08T23:54:43Z | Marie | incident workload started (same as baseline 2) | [`incident-requests.txt`](incident-requests.txt) |
| 2026-11-08T23:54:51Z | Marie | **first signal**: `model_version` `candidate-0e02f6bbae83-1`, all status codes normal | [`incident-service.log`](incident-service.log) |
| 2026-11-08T23:55:18Z | Marie | incident workload ended | [`incident-requests.txt`](incident-requests.txt) |
| 2026-11-08T23:56Z | Marie | hypotheses A and B written before running any check | this file |
| 2026-11-09T00:01Z | Marie | model sha256 compared: release-2 `BBAE6BC8…` ≠ v1 `D24C050E…` → hypothesis B rejected | [`incident-hashes.txt`](incident-hashes.txt) |
| 2026-11-09T00:02Z | Marie | `bundle verify release-2 --pointer`: manifest differs from the pointer, exit 1 → hypothesis A kept | [`incident-verify-release2.txt`](incident-verify-release2.txt) |
| 2026-11-09T00:07Z | Marie | `bundle verify` of v1 against the pointer right before the switch: `status: ok`, exit 0 | [`rollback-verify-v1.txt`](rollback-verify-v1.txt) |
| 2026-11-09T00:08:04Z | Marie | incident logs saved, container `bike-release2` removed, `bike-recovered` started with bundle v1 (same image, same variables) | [`incident-service-final.log`](incident-service-final.log), [`recovery-service.log`](recovery-service.log) |
| 2026-11-09T00:08:47Z | Marie | recovery workload started (same as baseline 2) | [`recovery-requests.txt`](recovery-requests.txt) |
| 2026-11-09T00:09:33Z | Marie | recovery workload ended: health 5/5 200, valid 20/20 200, invalid 5/5 422, all `baseline-0b7ee4462ec6` | [`recovery-requests.txt`](recovery-requests.txt) |
| 2026-11-09T00:10:44Z | Marie | same valid request: prediction 149.53300780120094 (incident: 119.18025683402225) | terminal output |

## 3. First signal 
- Signal: unexpected model identity. `/health` and every `/predict` answer
  `model_version` `candidate-0e02f6bbae83-1` instead of `baseline-0b7ee4462ec6`.
  Status codes are unchanged (health 5/5 200, valid 20/20 200, invalid 5/5 422):
  **a silent fault**, invisible to a status-code check.
- Time (UTC): 2026-11-08T23:54:51Z (first request of the window); already in the
  start-up line `model loaded: version candidate-0e02f6bbae83-1`.
- Affected scope: every request served by the release (container `bike-release2`).
- Image and model observed: image `97e4f5be…` (unchanged), bundle `release-2`
  mounted with the same `MODEL_PATH` / `METADATA_PATH` as baseline 2.
- Note: the per-request log lines carry `model_version`, which made the signal
  visible in logs; `service_revision` is `"unknown"`.
- Raw evidence: [`incident-requests.txt`](incident-requests.txt),
  [`incident-service.log`](incident-service.log)

## 4. Hypotheses 
Written before running the checks.

| | Hypothesis A | Hypothesis B |
| --- | --- | --- |
| Statement | the release serves another model, not the accepted one | the release serves the accepted model; only its metadata (label) changed |
| Predicted signature | `model.joblib` sha256 ≠ `d24c050e…`; `bundle verify release-2 --pointer models/accepted.json` fails | `model.joblib` sha256 = `d24c050e…`; only `model-metadata.json` differs |
| Discriminating check | sha256 of both `model.joblib`; `bundle verify` of release-2 against the pointer | same checks |
| Actual result | **confirmed**: `model.joblib` sha256 `BBAE6BC8…` ≠ `D24C050E…` (4,145 bytes vs 5,243,633); `bundle verify` fails: `manifest sha256 differs from the pointer (feee47b9… != 75dedf7d…)`, exit 1 | **rejected**: the model file itself differs, not only the metadata |
| Kept or rejected | **kept** | **rejected** |
| Still uncertain | whether the candidate predicts worse (its validation MAE was not measured); how it was built (a model ~1,000 times smaller suggests a much simpler forest, not proven) | — |

| Boundary | Checked? | Observation |
| --- | --- | --- |
| Code and image | yes | same image `97e4f5be…`, same commit `ccabd24` as baseline 2: unchanged |
| Model version and verified bytes | yes | **changed**: `candidate-0e02f6bbae83-1`, model sha256 `BBAE6BC8…`, manifest `feee47b9…`, not the pointer's `75dedf7d…` ([`incident-verify-release2.txt`](incident-verify-release2.txt), [`incident-hashes.txt`](incident-hashes.txt)) |
| Configuration (environment variables) | yes | same `MODEL_PATH` and `METADATA_PATH`; only the mounted folder changed |
| Inputs | yes | same request bodies as baseline 2; invalid requests still rejected with 422 |

## 5. Response and rollback target 
- Why rollback fits: the fault is a wrong model, not a code, dependency or input
  problem; the image, configuration and inputs are unchanged. Switching back to the
  accepted bundle removes the cause in one controlled change, without retraining.
- Target: version `v1-d24c050e3631`, `manifest_sha256` `75dedf7d…`, named by
  `models/accepted.json` `current`.
- Integrity check before switching: `bundle verify` `status: ok`, exit 0, MAE
  86.84685685591091 ([`rollback-verify-v1.txt`](rollback-verify-v1.txt)).
- Compatibility: same image and code (`ccabd24`); `uv.lock` of `main` = bundle's
  `uv.lock` (`955FD4FD…`); feature order and validation rows checked by `verify`.
- Action taken: one change only, at 2026-11-09T00:08:04Z: the mounted folder went from
  `release-2` back to `v1-d24c050e3631` (container `bike-release2` replaced by
  `bike-recovered`, same image, same `MODEL_PATH` and `METADATA_PATH`).
- Gap found: the service loads whatever `MODEL_PATH` points to; nothing checks the
  bundle against the accepted pointer before it is served.

## 6. Verification after recovery 
| Source | Expected | Observed |
| --- | --- | --- |
| Identity (`/health`, `model_version`) | `baseline-0b7ee4462ec6` | `baseline-0b7ee4462ec6` on every request; start-up line `model loaded: version baseline-0b7ee4462ec6` |
| Verified bytes | accepted bundle v1 | `bundle verify` ok on the mounted folder just before the switch |
| Fresh requests (same workload as baseline 2) | health 5/5 → 200, valid 20/20 → 200, invalid 5/5 → 422 | health 5/5 → 200, valid 20/20 → 200, invalid 5/5 → 422 |
| Same valid request | v1 behaviour | prediction 149.53300780120094 (incident model: 119.18025683402225) |
| Post-change logs and window | no error line, one log line per request | no `ERROR` line; one JSON line per request with `model_version` `baseline-0b7ee4462ec6`; the only matches for "error" are the `error_fields` of the 5 expected 422 rejections |

A successful command alone does not prove recovery: recovery is shown by the identity
and by fresh requests after the change.

## 7. Baseline, incident, recovery 
| Period | Window (UTC) | Count | Identity | Signals |
| --- | --- | --- | --- | --- |
| Baseline 2 | 2026-11-08 23:27:32Z to 23:28:03Z | 30 requests | `baseline-0b7ee4462ec6` | health 5/5 200, valid 20/20 200, invalid 5/5 422; latency median 9.4 ms, p95 11.9 ms |
| Incident | 2026-11-08 23:54:43Z to 23:55:18Z | 30 requests | **`candidate-0e02f6bbae83-1`** | health 5/5 200, valid 20/20 200, invalid 5/5 422; latency median 11.1 ms, p95 13.4 ms; same request predicted 119.18 |
| After recovery | 2026-11-09 00:08:47Z to 00:09:33Z | 30 requests | `baseline-0b7ee4462ec6` | health 5/5 200, valid 20/20 200, invalid 5/5 422; latency median 9.6 ms, p95 13.9 ms; same request predicted 149.53 |

Status codes and latency stayed in the same range in all three periods. **Only the
model identity and the prediction values revealed the incident.**

## 8. Observed, unknown, next action 
- Observed:
  - release-2 served a model that is not the accepted one (model sha256 `BBAE6BC8…`,
    manifest `feee47b9…` ≠ pointer `75dedf7d…`), with normal status codes;
  - the per-request logs (Lab 5) made it visible, because every line carries
    `model_version`;
  - the rollback to the verified bundle v1 restored the expected identity, status codes
    and prediction, with no retraining;
  - fault attempt 1 (training configuration) was stopped earlier by the settings guard.
- Unknown:
  - whether the candidate model is worse on validation (its MAE was not measured);
  - how it was produced (a file ~1,000 times smaller suggests a much simpler forest,
    not proven);
  - whether the same procedure works on Cloud Run (no access).
  - Limit of this drill: the operator knew in advance that the fault was one of two
    types proposed by the injector; the observed fault was neither of them.
- Next actions and owners:
  - Hajar reveals the fault; Marie compares it with this diagnosis (TBD).
  - Marie writes `RUNBOOK.md` from this drill; a peer (TBD) follows it without help.
  - Team decision: check the mounted bundle against `models/accepted.json` before
    serving (for example, run `bundle verify` at start-up and answer 503 on a mismatch),
    and add `model_sha256` to `/health`, so that a wrong model is refused instead of
    served.