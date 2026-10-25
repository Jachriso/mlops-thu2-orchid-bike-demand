import json
from pathlib import Path

import pytest

from bike_demand.split import split_data
from bike_demand.train import compare_mean, fit_evaluate, load_config
from bike_demand.validate import load_data

pytestmark = pytest.mark.regression
ROOT = Path(__file__).parents[1]

# Measured variation: the seed is fixed (random_state=42, n_jobs=1) and the
# recorded readback gives reload_mae_delta = 0.0. Three recomputations on
# Windows gave a delta of exactly 0.0 for both MAEs; the CI run on
# ubuntu-24.04 is the second platform. The tolerance only absorbs float
# rounding across platforms.
TOLERANCE = 1e-6


@pytest.fixture(scope="module")
def recorded():
    return json.loads((ROOT / "reports/metrics.json").read_text())["validation_mae"]


@pytest.fixture(scope="module")
def partitions():
    config = load_config(ROOT / "configs/baseline.yaml")
    return config, split_data(load_data(ROOT / config["data"]))


def test_random_forest_validation_mae_matches_recorded(recorded, partitions):
    config, parts = partitions
    _, _, mae = fit_evaluate(parts["train"], parts["validation"], config)
    assert mae == pytest.approx(recorded["random_forest"], abs=TOLERANCE)


def test_naive_mean_validation_mae_matches_recorded(recorded, partitions):
    _, parts = partitions
    _, mae = compare_mean(parts["train"]["cnt"], parts["validation"]["cnt"])
    assert mae == pytest.approx(recorded["naive_train_mean"], abs=TOLERANCE)