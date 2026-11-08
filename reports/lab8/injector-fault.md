# Injector fault (do not show to the operator before diagnosis)

- Fault: `bike-demand/configs/baseline.yaml` has `n_estimators: 3` and `max_depth: 2` (under-trained model).
- Expected symptom: validation MAE around 130-150 instead of 86.85.
- Revert: `git checkout main -- bike-demand/configs/baseline.yaml`.
- Prepared on: 2026-11-08.
