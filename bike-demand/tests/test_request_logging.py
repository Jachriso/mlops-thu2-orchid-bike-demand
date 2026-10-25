# Request log tests : one JSON line per request, useful and without private data


import json
import logging

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
VERSION = "test-model-0001"
REVISION = "rev-abc1234"
EXPECTED_KEYS = {
    "timestamp",
    "event",
    "request_id",
    "method",
    "path",
    "status",
    "outcome",
    "duration_ms",
    "model_version",
    "service_revision",
}


def write_artifact(folder):
    rng = np.random.default_rng(0)
    columns = {}
    for name in FEATURES:
        if name in WHOLE_RANGES:
            low, high = WHOLE_RANGES[name]
            columns[name] = rng.integers(low, high + 1, 40)
        else:
            columns[name] = rng.random(40)
    frame = pd.DataFrame(columns, columns=list(FEATURES))
    model = RandomForestRegressor(n_estimators=5, max_depth=3, random_state=0)
    model.fit(frame, rng.integers(0, 500, 40))
    joblib.dump(model, folder / "model.joblib")
    metadata = {"model_version": VERSION, "features": list(FEATURES)}
    (folder / "model-metadata.json").write_text(json.dumps(metadata))


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("SERVICE_REVISION", REVISION)
    monkeypatch.delenv("METADATA_PATH", raising=False)


@pytest.fixture
def client(tmp_path, monkeypatch):
    write_artifact(tmp_path)
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "model.joblib"))
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture
def client_without_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "absent" / "model.joblib"))
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture
def lines(caplog):
    """The raw request-log lines captured so far."""
    caplog.set_level(logging.INFO, logger="bike_demand.request")

    def read():
        return [
            record.getMessage()
            for record in caplog.records
            if record.name == "bike_demand.request"
        ]

    return read


class BrokenModel:
    def predict(self, frame):
        raise RuntimeError("secret-internal-detail")


def test_valid_predict_writes_one_complete_line(client, lines):
    response = client.post("/predict", json=VALID)
    assert response.status_code == 200
    [line] = lines()
    event = json.loads(line)
    assert set(event) == EXPECTED_KEYS
    assert event["event"] == "request"
    assert event["method"] == "POST"
    assert event["path"] == "/predict"
    assert event["status"] == 200
    assert event["outcome"] == "ok"
    assert event["model_version"] == VERSION
    assert event["service_revision"] == REVISION
    assert isinstance(event["duration_ms"], (int, float)) and event["duration_ms"] >= 0
    assert len(event["request_id"]) == 12


def test_response_header_carries_the_logged_request_id(client, lines):
    response = client.get("/health")
    [line] = lines()
    assert response.headers["X-Request-ID"] == json.loads(line)["request_id"]


def test_health_is_logged(client, lines):
    assert client.get("/health").status_code == 200
    [line] = lines()
    event = json.loads(line)
    assert (event["method"], event["path"], event["status"]) == ("GET", "/health", 200)


def test_one_line_per_request_with_distinct_ids(client, lines):
    client.get("/health")
    client.post("/predict", json=VALID)
    client.post("/predict", json={**VALID, "hum": 1.5})
    events = [json.loads(line) for line in lines()]
    assert [event["status"] for event in events] == [200, 200, 422]
    assert len({event["request_id"] for event in events}) == 3


def test_invalid_request_logs_the_field_not_the_value(client, lines):
    response = client.post("/predict", json={**VALID, "hum": 1.4321})
    assert response.status_code == 422
    [line] = lines()
    event = json.loads(line)
    assert event["status"] == 422
    assert event["outcome"] == "rejected"
    assert event["error_fields"] == ["body.hum"]
    assert "1.4321" not in line


def test_missing_model_logs_the_reason_and_no_version(client_without_model, lines):
    client_without_model.get("/health")
    client_without_model.post("/predict", json=VALID)
    events = [json.loads(line) for line in lines()]
    assert [event["status"] for event in events] == [503, 503]
    for event in events:
        assert event["outcome"] == "unavailable"
        assert event["reason"] == "no_model"
        assert event["model_version"] is None


def test_model_failure_logs_status_500_without_the_exception_text(client, lines):
    api.app.state.loaded = api.LoadedModel(model=BrokenModel(), version=VERSION)
    response = client.post("/predict", json=VALID)
    assert response.status_code == 500
    [line] = lines()
    event = json.loads(line)
    assert event["status"] == 500
    assert event["outcome"] == "error"
    assert event["reason"] == "prediction_failed"
    assert "secret-internal-detail" not in line


def test_request_body_is_not_logged(client, lines):
    client.post("/predict", json={**VALID, "temp": 0.123456789})
    [line] = lines()
    assert "0.123456789" not in line


def test_query_string_is_not_logged(client, lines):
    client.get("/health?token=SECRET123")
    [line] = lines()
    assert "SECRET123" not in line


def test_headers_are_not_logged(client, lines):
    client.get("/health", headers={"Authorization": "Bearer SECRET456"})
    [line] = lines()
    assert "SECRET456" not in line


def test_unknown_path_is_logged_without_the_client_text(client, lines):
    response = client.get("/steal-this-token-789")
    assert response.status_code == 404
    [line] = lines()
    event = json.loads(line)
    assert event["path"] == "(other)"
    assert event["status"] == 404
    assert event["outcome"] == "refused"
    assert "steal-this-token-789" not in line


def test_revision_defaults_to_unknown(client, lines, monkeypatch):
    monkeypatch.delenv("SERVICE_REVISION")
    client.get("/health")
    [line] = lines()
    assert json.loads(line)["service_revision"] == "unknown"


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (200, "ok"),
        (404, "refused"),
        (405, "refused"),
        (422, "rejected"),
        (500, "error"),
        (503, "unavailable"),
        (None, "aborted"),
    ],
)
def test_outcome_words(status, outcome):
    assert api.outcome_for(status) == outcome
