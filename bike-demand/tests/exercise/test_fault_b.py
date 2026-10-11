from pathlib import Path

import pandas as pd
import pytest

from bike_demand.validate import load_data

pytestmark = pytest.mark.exercise
FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_fault_b_weathersit_out_of_domain_is_rejected():
    control = pd.read_csv(FIXTURES / "missing-hours.csv")
    fault = pd.read_csv(FIXTURES / "weathersit-out-of-domain.csv")
    changed = control.ne(fault)
    assert list(fault.columns) == list(control.columns)
    assert changed.sum().sum() == 1 and changed.loc[0, "weathersit"]
    with pytest.raises(ValueError, match=r"weathersit: require integers in \[1, 4\]"):
        load_data(FIXTURES / "weathersit-out-of-domain.csv")
    assert len(load_data(FIXTURES / "missing-hours.csv")) == 6
