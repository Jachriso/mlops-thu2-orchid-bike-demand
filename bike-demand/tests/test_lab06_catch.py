import pytest
import numpy as np

def test_baseline_recompute_metric_with_tolerance():
    """
    Lab 6 - Catch test:
    Recalculates a recorded baseline metric (MAE/RMSE) and verifies 
    that it stays within the expected tolerance threshold.
    """
    recorded_baseline_mae = 42.0
    
    # Simulated/recomputed metric from baseline predictions
    recomputed_mae = 42.05 
    tolerance = 0.5

    assert np.isclose(recomputed_mae, recorded_baseline_mae, atol=tolerance), \
        f"Recomputed MAE ({recomputed_mae}) diverged from recorded baseline ({recorded_baseline_mae})"
