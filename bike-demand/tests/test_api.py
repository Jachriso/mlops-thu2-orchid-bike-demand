# API tests: normal, invalid and missing-model cases

import json
import math

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import RandomForestRegressor

from bike_demand import api
from bike_demand.validate import FEATURES

VALID = {
    "season": 1,
    "yr": 1,
    "mnth": 6,
    "hr": 8,
    "holiday": 0,
    "weekday": 2,
    "workingday": 1,
    "weathersit": 1,
    "temp": 0.5,
    "atemp": 0.5,
    "hum": 0.6,
    "windspeed": 0.2,
}
WHOLE_RANGES = {
    "season": (1, 4),
    "yr": (0, 1),
    "mnth": (1, 12),
    "hr": (0, 23),
    "holiday": (0, 1),
    "weekday": (0, 6),
    "workingday": (0, 1),
    "weathersit": (1, 4),
}
UNIT_FIELDS = ("temp", "atemp", "hum", "windspeed")
VERSION = "test-model-0001"


def write_artifact(folder, version=VERSION):
    """Save a tiny trained model and its metadata, like 'train' does."""
    rng = np.random.default_rng(0)
    columns = {}
    for name in FEATURES:
        if name in WHOLE_RANGES:
            low, high = WHOLE_RANGES[name]
            columns[name] = rng.integers(low, high + 1, 40)
        else:
            columns[name] = rng.random(40)
    frame = pd.DataFrame(columns, columns=list(FEATURES))
    target = rng.integers(0, 500, 40)
    model = RandomForestRegressor(n_estimators=5, max_depth=3, random_state=0)
    model.fit(frame, target)
    joblib.dump(model, folder / "model.joblib")
    metadata = {"model_version": version, "features": list(FEATURES)}
    (folder / "model-metadata.json").write_text(json.dumps(metadata))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App started with a usable model."""
    write_artifact(tmp_path)
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "model.joblib"))
    monkeypatch.delenv("METADATA_PATH", raising=False)
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture
def client_without_model(tmp_path, monkeypatch):
    """App started when the model file does not exist."""
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "absent" / "model.joblib"))
    monkeypatch.delenv("METADATA_PATH", raising=False)
    with TestClient(api.app) as test_client:
        yield test_client


class ConstantModel:
    def __init__(self, value):
        self.value = value

    def predict(self, frame):
        return np.array([self.value])


class ForbiddenModel:
    def predict(self, frame):
        raise AssertionError("the model must not run for an invalid request")


def with_changes(**changes):
    return {**VALID, **changes}


def without(name):
    return {key: value for key, value in VALID.items() if key != name}


# Normal cases


def test_health_ok_reports_loaded_version(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_version": VERSION}


def test_predict_valid_returns_finite_nonnegative_value_and_version(client):
    response = client.post("/predict", json=VALID)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"prediction", "model_version"}
    assert body["model_version"] == VERSION
    assert math.isfinite(body["prediction"]) and body["prediction"] >= 0


def test_version_comes_from_metadata_not_from_code(tmp_path, monkeypatch):
    write_artifact(tmp_path, version="other-version-xyz")
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "model.joblib"))
    monkeypatch.delenv("METADATA_PATH", raising=False)
    with TestClient(api.app) as test_client:
        assert test_client.get("/health").json()["model_version"] == "other-version-xyz"
        predicted = test_client.post("/predict", json=VALID).json()
        assert predicted["model_version"] == "other-version-xyz"


def test_predict_is_repeatable(client):
    first = client.post("/predict", json=VALID).json()
    second = client.post("/predict", json=VALID).json()
    assert first == second


def test_predict_accepts_boundary_values(client):
    low = {name: WHOLE_RANGES[name][0] for name in WHOLE_RANGES}
    high = {name: WHOLE_RANGES[name][1] for name in WHOLE_RANGES}
    for whole in (low, high):
        for unit in (0.0, 1.0):
            payload = {**whole, **{name: unit for name in UNIT_FIELDS}}
            assert client.post("/predict", json=payload).status_code == 200


# Invalid input: always 4xx (422), and the model never runs

INVALID_BODIES = (
    [pytest.param(without(name), id=f"missing-{name}") for name in FEATURES]
    + [
        pytest.param(with_changes(season="2"), id="string-for-int"),
        pytest.param(with_changes(season=2.5), id="fraction-for-int"),
        pytest.param(with_changes(season=2.0), id="float-for-int"),
        pytest.param(with_changes(season=True), id="bool-for-int"),
        pytest.param(with_changes(season=None), id="null-for-int"),
        pytest.param(with_changes(season="abc"), id="text-for-int"),
        pytest.param(with_changes(temp="0.5"), id="string-for-float"),
        pytest.param(with_changes(temp=True), id="bool-for-float"),
        pytest.param(with_changes(temp=None), id="null-for-float"),
        pytest.param(with_changes(temp=[0.5]), id="list-for-float"),
        pytest.param(with_changes(hum=1.5), id="hum-1.5"),
        pytest.param({**VALID, "cnt": 100}, id="extra-cnt"),
        pytest.param({**VALID, "casual": 10}, id="extra-casual"),
        pytest.param({**VALID, "registered": 90}, id="extra-registered"),
        pytest.param({**VALID, "unknown": 1}, id="extra-unknown"),
        pytest.param({}, id="empty-object"),
        pytest.param([], id="list-instead-of-object"),
    ]
    + [
        pytest.param(with_changes(**{name: low - 1}), id=f"{name}-below-{low}")
        for name, (low, high) in WHOLE_RANGES.items()
    ]
    + [
        pytest.param(with_changes(**{name: high + 1}), id=f"{name}-above-{high}")
        for name, (low, high) in WHOLE_RANGES.items()
    ]
    + [
        pytest.param(with_changes(**{name: -0.01}), id=f"{name}-below-0")
        for name in UNIT_FIELDS
    ]
    + [
        pytest.param(with_changes(**{name: 1.01}), id=f"{name}-above-1")
        for name in UNIT_FIELDS
    ]
)


@pytest.mark.parametrize("payload", INVALID_BODIES)
def test_invalid_body_is_rejected_before_the_model_runs(client, payload):
    api.app.state.loaded = api.LoadedModel(model=ForbiddenModel(), version=VERSION)
    response = client.post("/predict", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_infinity_are_rejected_with_422(client, value):
    # json.dumps writes NaN / Infinity, which Python's JSON parser accepts.
    content = json.dumps(with_changes(temp=value))
    response = client.post(
        "/predict", content=content, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("content", ["", "not json", "{"])
def test_malformed_json_is_rejected_with_422(client, content):
    response = client.post(
        "/predict", content=content, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


def test_error_detail_does_not_echo_the_input(client):
    response = client.post("/predict", json=with_changes(hum=1.5))
    assert response.status_code == 422
    entry = response.json()["detail"][0]
    assert set(entry) == {"loc", "msg", "type"}
    assert entry["loc"] == ["body", "hum"]


# Honest failures of the model itself


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_invalid_model_output_is_a_server_error(client, value):
    api.app.state.loaded = api.LoadedModel(model=ConstantModel(value), version=VERSION)
    response = client.post("/predict", json=VALID)
    assert response.status_code == 500


def test_model_exception_is_a_server_error(client):
    api.app.state.loaded = api.LoadedModel(model=ForbiddenModel(), version=VERSION)
    response = client.post("/predict", json=VALID)
    assert response.status_code == 500
    assert "AssertionError" not in response.text


# Missing or unusable model: the service stays up and answers 503


def test_health_is_503_without_a_model(client_without_model):
    assert client_without_model.get("/health").status_code == 503


def test_valid_predict_is_503_without_a_model(client_without_model):
    assert client_without_model.post("/predict", json=VALID).status_code == 503


def test_invalid_predict_is_still_4xx_without_a_model(client_without_model):
    response = client_without_model.post("/predict", json=with_changes(hum=1.5))
    assert response.status_code == 422


def break_artifact(folder, how):
    write_artifact(folder)
    if how == "no-metadata":
        (folder / "model-metadata.json").unlink()
    elif how == "corrupt-model":
        (folder / "model.joblib").write_bytes(b"this is not a joblib file")
    elif how == "no-version":
        (folder / "model-metadata.json").write_text(
            json.dumps({"features": list(FEATURES)})
        )
    elif how == "bad-json":
        (folder / "model-metadata.json").write_text("{")
    elif how == "wrong-features":
        metadata = {"model_version": VERSION, "features": list(FEATURES)[::-1]}
        (folder / "model-metadata.json").write_text(json.dumps(metadata))


@pytest.mark.parametrize(
    "how", ["no-metadata", "corrupt-model", "no-version", "bad-json", "wrong-features"]
)
def test_unusable_artifact_gives_503(tmp_path, monkeypatch, how):
    break_artifact(tmp_path, how)
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "model.joblib"))
    monkeypatch.delenv("METADATA_PATH", raising=False)
    with TestClient(api.app) as test_client:
        assert test_client.get("/health").status_code == 503
        assert test_client.post("/predict", json=VALID).status_code == 503
