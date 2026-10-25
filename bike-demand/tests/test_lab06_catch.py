import json
from pathlib import Path

from bike_demand.data import load_data, split_data
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error


def test_baseline_recompute_metric_with_tolerance():
    """
    Lab 6 - Catch test:
    Strictly reads recorded metrics, re-runs the model pipeline using project code,
    and verifies that recomputed MAE matches the recorded baseline within strict tolerance.
    """
    # 1. Strict read of metrics.json
    base_dir = Path(__file__).resolve().parent.parent
    metrics_path = base_dir / "reports" / "metrics.json"
    with open(metrics_path, "r") as f:
        metrics = json.load(f)

    recorded_rf_mae = metrics["validation_mae"]["random_forest"]

    # 2. Recompute validation MAE using project data and model configuration (random_state=42)
    # Ensuring data path resolves correctly in CI and locally
    data_path = base_dir / "data" / "bike_sharing_demand.csv"
    if not data_path.exists():
        data_path = base_dir.parent / "data" / "bike_sharing_demand.csv"

    df = load_data(str(data_path) if data_path.exists() else None)
    X_train, X_val, y_train, y_val = split_data(df)

    model = RandomForestRegressor(random_state=42)
    model.fit(X_train, y_train)
    preds = model.predict(X_val)
    recomputed_mae = mean_absolute_error(y_val, preds)

    # 3. Tolerance justified by metrics.json reload_mae_delta = 0.0 with fixed seed
    tolerance = 1e-5

    assert abs(recomputed_mae - recorded_rf_mae) <= tolerance, (
        f"Recomputed MAE ({recomputed_mae}) diverged from recorded baseline ({recorded_rf_mae})"
    )
