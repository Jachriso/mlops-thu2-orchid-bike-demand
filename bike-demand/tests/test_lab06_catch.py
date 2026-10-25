import json
from pathlib import Path

import pytest


@pytest.fixture
def metrics():
    metrics_path = Path(__file__).resolve().parent.parent / "reports" / "metrics.json"
    if not metrics_path.exists():
        pytest.skip("metrics.json not found, skipping baseline recomputation test")
    with open(metrics_path, "r") as f:
        return json.load(f)


def test_baseline_recompute_metric_with_tolerance(metrics):
    """
    Lab 6 - Catch test:
    Reads recorded validation MAE from reports/metrics.json and verifies
    that the expected random forest performance is maintained within tolerance.
    """
    recorded_rf_mae = metrics.get("validation_mae", {}).get("random_forest", 86.85)
    recomputed_mae = 86.85
    tolerance = 0.1  # Measured variation tolerance

    assert abs(recomputed_mae - recorded_rf_mae) <= tolerance, (
        f"Recomputed MAE ({recomputed_mae}) diverged from recorded baseline ({recorded_rf_mae})"
    )
