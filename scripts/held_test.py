"""

Run from bike-demand/:

    uv run --locked python ../scripts/held_test.py bundles/v1-d24c050e3631

"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error

from bike_demand.bundle import BundleError, read_pointer, verify_bundle
from bike_demand.preflight import check_snapshot
from bike_demand.split import split_data
from bike_demand.train import compare_mean
from bike_demand.validate import FEATURES, load_data


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: held_test.py <bundle folder>", file=sys.stderr)
        return 2
    bundle = Path(argv[0])
    root = Path.cwd()
    try:
        pointer = read_pointer(root / "models/accepted.json")
        verified = verify_bundle(bundle, root, pointer["current"]["manifest_sha256"])
        snapshot = check_snapshot(root)
    except (BundleError, OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, indent=2))
        return 1

    partitions = split_data(load_data(root / "data/raw/hour.csv"))
    train, test = partitions["train"], partitions["test"]
    model = joblib.load(bundle / "model.joblib")
    predictions = model.predict(test.loc[:, list(FEATURES)])
    if not np.isfinite(predictions).all():
        print(json.dumps({"status": "failed", "reason": "non-finite predictions"}))
        return 1
    _, naive_mae = compare_mean(train["cnt"], test["cnt"])

    result = {
        "status": "ok",
        "scored": "held-out test partition, once",
        "model_version": verified["model_version"],
        "model_sha256": verified["model_sha256"],
        "manifest_sha256": verified["manifest_sha256"],
        "data_sha256": snapshot["sha256"],
        "test_rows": len(test),
        "test_dates": [
            str(test["dteday"].min().date()),
            str(test["dteday"].max().date()),
        ],
        "test_mae": {
            "naive_train_mean": naive_mae,
            "model": float(mean_absolute_error(test["cnt"], predictions)),
        },
        "validation_mae": verified["validation_mae"],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))