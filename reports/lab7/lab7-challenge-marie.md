# Lab 7: independent challenge (Marie)

Written and committed **before** running the challenge, so the prediction cannot be
adjusted to the result.

## Claim challenged
From the README section "Recover the accepted version without retraining" (Jade, PR #17):
a member who did not build the bundle can recover the accepted version with the two
README commands only, without retraining, and `bundle verify` refuses bytes that are
not the accepted ones.

## Why this claim
`tests/test_bundle.py` already checks a changed byte on bundles created inside the
tests. It does not show that the real accepted bundle in the bucket can be recovered by
someone else, from a clean checkout, following only the README. That is what Lab 8
will rely on.

## Plan
1. Clean checkout of `main`; follow only the README recovery section.
2. Download `bundles/v1-d24c050e3631` from the bucket and run
   `bundle verify ... --pointer models/accepted.json`.
3. Copy the downloaded bundle, change one byte of `model.joblib` in the copy only,
   and run the same `verify` on the copy.
4. Compare `models/accepted.json` and the bucket listing before and after.

## Prediction
1. The downloaded bundle passes `verify` with exit 0 and the recorded validation MAE.
2. The altered copy fails with a non-zero exit, and the message names `model.joblib`.
3. The pointer and the bucket content are unchanged.

## What would count as a gap
- a README command that does not work as written for someone who did not build it;
- the altered copy passing `verify`;
- any change to the accepted state.

## Access
Read-only access (Storage Object Viewer) on the models bucket requested from Jade.
Status: **refused**. On 8 Nov, the project `mlops-demo-512323` is not visible from my
Google account ("No resources to display"), and Jade cannot grant access. Only Jade can
run the first recovery command.

![Project mlops-demo-512323 not visible from my account (8 Nov)](../../images/lab7-marie-01-no-project-access.png)

**Gap found:** the README recovery path depends on one person's cloud access. If she is
not available during the Lab 8 incident, no other member can recover the accepted
bundle. Possible repairs (team decision): ask the instructor to grant read access to the
bucket for every member, or document a second, verified copy of the accepted bundle.



## Results ( Windows 11, my machine, branch `lab-07-challenge` = `main` + this file)

Step 1 of the README (`gcloud storage cp`) was run by Jade, the only member with bucket
access; she sent me the four bundle files privately (not through Git). Transport does not
matter for this check: the pointer committed on `main` names the exact manifest digest.

| Prediction | Observed | Raw output |
| --- | --- | --- |
| 1. The real bundle passes `verify`, exit 0, recorded MAE | **Confirmed.** `status: ok`, exit 0, `manifest_sha256` `75dedf7d…`, `model_sha256` `d24c050e…`, 4,358 validation rows, MAE 86.84685685591091 (train mean 154.23179306864967) | [`lab7-marie-verify-genuine.txt`](lab7-marie-verify-genuine.txt) |
| 2. A copy with one changed byte fails and names `model.joblib` | **Confirmed.** One bit flipped at byte 1000 of the copy: `status: failed`, `integrity: model.joblib sha256 differs from the manifest`, exit 1, no MAE computed (refused before loading) | [`lab7-marie-verify-tampered.txt`](lab7-marie-verify-tampered.txt) |
| 3. Accepted state unchanged | **Confirmed locally.** `git diff main -- models/accepted.json` is empty; the original `model.joblib` still hashes to `D24C050E…`, the copy to `B2D2AC74…`. I could not list the bucket myself (no access), but nothing was uploaded. | this file |

### What this shows
- `bundle verify` does what the README claims, on the real accepted bundle and for a
  member who did not build it.
- Loading the exact bytes on Windows, without Docker, gives the recorded MAE to every
  digit, whereas retraining on Windows in Lab 2 gave another `model_sha256`. Keeping the
  bytes is what makes recovery reproducible.

### Gap (for Lab 8)
The first recovery command needs bucket access that only one member has. Recovery
during the incident must not depend on her being available. To be decided by the team
before the drill.

### Not covered by this challenge
- The second recovery case in the README (an older version from `previous`): only v1
  exists today.
- Serving: Cloud Run still serves a model retrained at deploy time (README, line 647),
  so I did not check the served identity.