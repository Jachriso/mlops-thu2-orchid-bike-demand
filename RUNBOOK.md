# RUNBOOK: bike-demand prediction service

For the next operator. It says **what to check and what to do** when the service looks
wrong. What actually happened in the Lab 8 drill is in
[`reports/lab8/incident-record.md`](reports/lab8/incident-record.md).

Author: Marie (`Leona224`), from the Lab 8 drill of 8–9 Nov 2026 (local Docker).
Tested: every step below was run in that drill, on Windows 11 with Docker Desktop.
Not tested: Cloud Run (see "Limits").

## 1. What "healthy" means

| Signal | Healthy value |
| --- | --- |
| `GET /health` | `200 {"status":"ok","model_version":"baseline-0b7ee4462ec6"}` |
| Model served | the bundle named by `bike-demand/models/accepted.json` → `current` (today `v1-d24c050e3631`, manifest `75dedf7d…`) |
| Valid `POST /predict` | `200`, finite prediction ≥ 0, same `model_version` as `/health` |
| Invalid `POST /predict` (e.g. `hum = 1.5`) | `422` (expected, **not** a failure) |
| Logs (`docker logs`) | one JSON line per request, with `status`, `duration_ms`, `model_version`; no `ERROR` line |
| Latency, valid predictions | about 10 ms median, under 25 ms p95 on a laptop (baseline 2) |

**A 200 does not prove the right model.** In the drill, every status code stayed normal
while a non-accepted model was served. Always check the **model identity**.

## 2. Symptoms and first checks

| What you see | Likely area | First check |
| --- | --- | --- |
| `/health` 200 but `model_version` is not the accepted one | **wrong model served** | section 3, then section 4 |
| `/health` 503 `no usable model loaded` | model or metadata missing / unreadable / wrong features | `docker logs <container>`: the start-up `ERROR` line names the cause (e.g. `model file not found: …`) |
| `/predict` 500 | the loaded model fails or returns an invalid value | `docker logs`: `prediction failed` or `invalid prediction` |
| `/predict` 422 on requests that should be valid | input contract or client | compare the body with the contract in the README (Lab 4); do **not** roll back the model for this |
| A new release does not build (`Training failed: config: …`) | training settings guard | nothing reached the service; the release needs a reviewed config change. **Never bypass the guard** |
| Status and identity fine, predictions look odd | not detectable by the service alone | compare one fixed request with the value recorded for the accepted model (section 5) |

## 3. Check the model identity (2 minutes)

Run from the repository root, with the service up.

```powershell
curl.exe -s http://127.0.0.1:8000/health
Get-Content bike-demand\models\accepted.json
```

Then verify the bundle the container mounts against the accepted pointer
(replace `<bundle folder>` with the folder passed to `docker run -v`):

```powershell
cd bike-demand
uv run --locked python -m bike_demand.bundle verify <bundle folder> --pointer models/accepted.json
echo "exit code: $LASTEXITCODE"
cd ..
```

- `status: ok`, exit 0 → the mounted bytes are the accepted ones; look elsewhere
  (configuration, inputs, code).
- `manifest sha256 differs from the pointer` or `model.joblib sha256 differs` →
  **a non-accepted model is mounted**: go to section 4.

On PowerShell, red `NativeCommandError` lines at the start are only `uv` progress
messages; read the JSON and the exit code.

Before changing anything, write down the time (UTC) and what you saw, and save the logs:

```powershell
(Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
docker logs <container> 2>&1 | Set-Content -Encoding utf8 reports\incident-<date>-service.log
```

## 4. Roll back to the accepted bundle (one change, no retraining)

**Do not retrain to recover.** Retraining gives a new `model_version`, and on another
platform a different `model_sha256` (Lab 2 vs Lab 3). Recover the retained bytes.

### 4.1 Get the accepted bundle

The bundle is stored outside Git. With access to the GCP project:

```powershell
cd bike-demand
gcloud storage cp -r gs://mlops-demo-512323-orchid-bike-models/bundles/v1-d24c050e3631 bundles/
```

**Access limit:** today only Jade can read the bucket (Lab 7 challenge, PR #20). If she is
not available, ask for the four bundle files by a private channel; the check in 4.2 still
proves they are the accepted bytes, whatever the transport. Never put them in Git.

To recover an older version, use the `bundle_uri` and `manifest_sha256` of its entry in
`previous` in `accepted.json`.

### 4.2 Verify the target **before** switching

```powershell
uv run --locked python -m bike_demand.bundle verify bundles/v1-d24c050e3631 --pointer models/accepted.json
echo "exit code: $LASTEXITCODE"
cd ..
```

Expected: `status: ok`, exit 0, validation MAE 86.84685685591091.
**If it does not pass, stop.** Never switch to an unverified target.

### 4.3 Switch: replace only the mounted bundle

Same image, same variables; only the folder changes.

```powershell
docker rm -f <faulty container>
$bundle = "${PWD}\bike-demand\bundles\v1-d24c050e3631:/bundle:ro"
$m = "MODEL_PATH=/bundle/model.joblib"
$meta = "METADATA_PATH=/bundle/model-metadata.json"
docker run -d --name bike-recovered -p 127.0.0.1:8000:8000 -v $bundle -e $m -e $meta <image>
```

On macOS/Linux, use `"$PWD/bike-demand/bundles/v1-d24c050e3631:/bundle:ro"`.
If a long command gets cut when pasted, keep the variables as above.

## 5. Prove the recovery with fresh evidence

A successful `docker run` proves nothing. After the switch:

1. `docker logs bike-recovered` shows `model loaded: version baseline-0b7ee4462ec6`.
2. `curl.exe -s http://127.0.0.1:8000/health` → 200, `baseline-0b7ee4462ec6`.
3. Send the same workload as the baseline (5 health, 20 valid, 5 invalid; commands in
   the incident record) and save it: expect 5/5 200, 20/20 200, 5/5 422, one identity.
4. Fixed check request (`valid.json` in the incident record: `season 1, yr 1, mnth 1,
   hr 8, …, hum 0.5`): the accepted model answers **149.53300780120094**. In the drill,
   the wrong model answered 119.18 with a 200.
5. Compare the three periods (before, during, after) in one table, with UTC windows.

## 6. What not to do

- Do not retrain, reinstall or regenerate `uv.lock` to "fix" a serving incident.
- Do not edit `models/accepted.json` during an incident: only a reviewed PR changes it.
- Do not bypass the training settings guard or disable a test to get a release through.
- Do not edit raw evidence afterwards to match the final explanation.

## 7. Limits (known gaps)

- `/health` reports `model_version` only, not `model_sha256`; `service_revision` is
  `"unknown"` in the logs. Identity must be checked with `bundle verify` (section 3).
- The service loads whatever `MODEL_PATH` points to; it does **not** check the bundle
  against `accepted.json`. Proposed fix: verify at start-up and answer 503 on mismatch.
- Bucket access is held by one member (section 4.1).
- Cloud Run: this runbook was rehearsed locally only. The Cloud Run rollback (switching
  traffic to the previous verified revision) has not been tested by the author.
- The validation MAE of a wrong model is not known from the service; the service cannot
  tell whether a prediction is good, only which model produced it.
