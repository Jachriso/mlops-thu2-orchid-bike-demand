# Lab 8: incident record

Recorder: Marie (`Leona224`). This record says **what happened**; `RUNBOOK.md` tells the
next operator what to do. Raw evidence is kept as text next to this file and is never
edited after the fact (slide 9).

## Status
Prepared before the drill. Prerequisite not met yet: Lab 7 is not fully merged on `main`
(pipeline not connected, Cloud Run still serves a model retrained at deploy time).

## Roles 
| Role | Member | Rule |
| --- | --- | --- |
| Operator | <name> | investigates without knowing the fault |
| Injector | <name> | one reversible fault, on our own Cloud Run service only |
| Recorder | Marie | keeps the UTC timeline and the raw evidence |
| Runbook peer | Marie | follows `RUNBOOK.md` without its author narrating |

The fault is revealed only **after** the diagnosis is recorded.

## Scope and limits
- Service: our own Cloud Run service, `<service name>`, region `<region>`.
- Recovery target must be a **retained accepted bundle** (Lab 7), checked with
  `bundle verify` before switching. No retraining as recovery.
- Known access limit (Lab 7 challenge, PR #20): only Jade has access to the GCP project
  and the models bucket.

## 1. Normal, before the fault 
| Item | Value |
| --- | --- |
| Observation window (UTC) | <start> to <end> |
| Workload | <which requests, how many, from where> |
| Service revision | <Cloud Run revision> |
| Image | <image digest> |
| Model identity | `model_version` <…>, `model_sha256` <…> |
| Accepted pointer | `models/accepted.json` current: <manifest_sha256> |

### Signal definitions
| Signal | Eligible attempts | Good attempts | Unit / window | Missing data |
| --- | --- | --- | --- | --- |
| Readiness | `GET /health` calls | 200 with the expected `model_sha256` | count per window | no answer counts as not ready |
| Prediction success | valid `POST /predict` calls | 200, finite value ≥ 0 | ratio per window | <…> |
| Validation rejections | invalid `POST /predict` calls | 4xx (expected) | count | not counted as failures |
| Latency | <…> | <…> | ms, p95 | <…> |

Intentional 422 rejections are **not** failures of valid predictions.

## 2. Timeline (UTC)
| Time (UTC) | Who | What was observed or done | Evidence |
| --- | --- | --- | --- |
| <…> | | | |

## 3. First signal (slide 9)
- Signal: <…>
- Time (UTC): <…>
- Affected scope: <…>
- Revision / model observed: <…>
- Raw evidence: <link to the raw file>

## 4. Hypotheses (slide 10)
| | Hypothesis A | Hypothesis B |
| --- | --- | --- |
| Statement | <…> | <…> |
| Predicted signature | <…> | <…> |
| Discriminating check | <…> | <…> |
| Actual result | <…> | <…> |
| Kept or rejected | <…> | <…> |
| Still uncertain | <…> | <…> |

### Boundaries checked (slide 12)
| Boundary | Checked? | Observation |
| --- | --- | --- |
| Service revision and image | | |
| Model version and verified bytes | | |
| Configuration | | |
| Inputs | | |

## 5. Response and rollback target (slides 13-14)
- Why rollback fits: <…>
- Target: version <…>, `manifest_sha256` <…>, `bundle_uri` <…>
- Integrity check before switching: `bundle verify` exit <…> (raw output: <link>)
- Compatibility: code, dependencies, feature schema, configuration: <…>
- Action taken: <one controlled change>

## 6. Verification after recovery (slide 15)
| Source | Expected | Observed |
| --- | --- | --- |
| Identity (`/health`, `model_sha256`) | <…> | <…> |
| Fresh requests to the live URL | <…> | <…> |
| Post-change logs and window | <…> | <…> |

A successful command alone does not prove recovery.

## 7. Baseline, incident, recovery (slide 16)
| Period | Window (UTC) | Count | Identity | Signals |
| --- | --- | --- | --- | --- |
| Baseline | | | | |
| Incident | | | | |
| After recovery | | | | |

## 8. Observed, unknown, next action (slide 17)
- Observed: <…>
- Unknown: <…>
- Next action and owner: <…>