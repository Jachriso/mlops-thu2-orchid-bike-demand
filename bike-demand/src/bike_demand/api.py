# Prediction API for the saved bike-demand baseline model

import json
import logging
import math
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from bike_demand.validate import FEATURES

# The uvicorn logger shows INFO lines in the container output.
log = logging.getLogger("uvicorn.error")

# One JSON line per request goes to stdout, so 'docker logs' shows it.
request_log = logging.getLogger("bike_demand.request")
request_log.setLevel(logging.INFO)
if not request_log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    request_log.addHandler(_handler)

DEFAULT_MODEL_PATH = "artifacts/model.joblib"
METADATA_NAME = "model-metadata.json"
# Only these paths are logged as they are; any other path is logged as "(other)".
KNOWN_PATHS = {"/health", "/predict"}
MAX_LOGGED_FIELDS = 12


class ModelUnavailable(Exception):
    """Raised when the saved model cannot be used for predictions."""


@dataclass(frozen=True)
class LoadedModel:
    model: object
    version: str


def _whole(low: int, high: int):
    """Integer field: JSON integers only (no strings, floats or booleans)."""
    return Field(strict=True, ge=low, le=high)


def _unit():
    """Normalised weather value: a finite number in 0..1 (no strings)."""
    return Field(strict=True, ge=0, le=1, allow_inf_nan=False)


class PredictRequest(BaseModel):
    """The twelve training predictors, as one flat JSON object."""

    model_config = ConfigDict(extra="forbid")

    season: int = _whole(1, 4)
    yr: int = _whole(0, 1)
    mnth: int = _whole(1, 12)
    hr: int = _whole(0, 23)
    holiday: int = _whole(0, 1)
    weekday: int = _whole(0, 6)
    workingday: int = _whole(0, 1)
    weathersit: int = _whole(1, 4)
    temp: float = _unit()
    atemp: float = _unit()
    hum: float = _unit()
    windspeed: float = _unit()


class PredictResponse(BaseModel):
    prediction: float
    model_version: str


def load_model(model_path: Path, metadata_path: Path) -> LoadedModel:
    """Load the trusted local artifact or raise ``ModelUnavailable``."""
    if not model_path.is_file():
        raise ModelUnavailable(f"model file not found: {model_path}")
    if not metadata_path.is_file():
        raise ModelUnavailable(f"metadata file not found: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ModelUnavailable(f"metadata unreadable: {error}") from error
    if not isinstance(metadata, dict):
        raise ModelUnavailable("metadata is not a JSON object")
    version = metadata.get("model_version")
    if not isinstance(version, str) or not version:
        raise ModelUnavailable("metadata has no model_version")
    if metadata.get("features") != list(FEATURES):
        raise ModelUnavailable("metadata features differ from the API contract")
    try:
        model = joblib.load(model_path)
    except Exception as error:  # corrupt or incompatible file
        raise ModelUnavailable(f"model unreadable: {error}") from error
    if not callable(getattr(model, "predict", None)):
        raise ModelUnavailable("loaded object has no predict method")
    return LoadedModel(model=model, version=version)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model once at startup; stay up (and answer 503) if unusable."""
    app.state.loaded = None
    model_path = Path(os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH))
    metadata_path = Path(
        os.environ.get("METADATA_PATH", str(model_path.with_name(METADATA_NAME)))
    )
    try:
        app.state.loaded = load_model(model_path, metadata_path)
        log.info("model loaded: version %s", app.state.loaded.version)
    except ModelUnavailable as error:
        log.error("no usable model, /health and /predict answer 503: %s", error)
    yield


def outcome_for(status: int | None) -> str:
    """Short word for what happened to a request, from its status code."""
    if status is None:
        return "aborted"
    if 200 <= status < 300:
        return "ok"
    if status == 422:
        return "rejected"
    if status == 503:
        return "unavailable"
    if status >= 500:
        return "error"
    return "refused"


def request_event(
    *,
    request_id: str,
    method: str,
    path: str,
    status: int | None,
    duration_ms: float,
    model_version: str | None,
    service_revision: str,
    reason: str | None = None,
    error_fields: list[str] | None = None,
) -> dict:
    """Build the one event logged for a request.

    Only metadata: no request body, no query string, no header, no prediction
    value, no environment variable, no path chosen by the client.
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": "request",
        "request_id": request_id,
        "method": method,
        "path": path if path in KNOWN_PATHS else "(other)",
        "status": status,
        "outcome": outcome_for(status),
        "duration_ms": duration_ms,
        "model_version": model_version,
        "service_revision": service_revision,
    }
    if reason:
        event["reason"] = reason
    if error_fields:
        event["error_fields"] = error_fields[:MAX_LOGGED_FIELDS]
    return event


app = FastAPI(title="Bike demand prediction API", lifespan=lifespan)


@app.middleware("http")
async def log_request(request: Request, call_next):
    """Write one JSON line per request, whatever its outcome."""
    request_id = uuid.uuid4().hex[:12]
    start = time.perf_counter()
    status = None
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        status = 500
        raise
    finally:
        loaded = getattr(request.app.state, "loaded", None)
        event = request_event(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=status,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            model_version=loaded.version if loaded else None,
            service_revision=os.environ.get("SERVICE_REVISION", "unknown"),
            reason=getattr(request.state, "reason", None),
            error_fields=getattr(request.state, "error_fields", None),
        )
        request_log.info(json.dumps(event, separators=(",", ":")))


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    """422 with location, message and type only (never echo the input).

    Echoing the input could even break the response for values like NaN.
    The log line gets the field locations only, never the values.
    """
    errors = exc.errors()
    request.state.error_fields = [
        ".".join(str(part) for part in err["loc"]) for err in errors
    ]
    detail = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
        for err in errors
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


@app.get("/health")
def health(request: Request):
    loaded = app.state.loaded
    if loaded is None:
        request.state.reason = "no_model"
        raise HTTPException(status_code=503, detail="no usable model loaded")
    return {"status": "ok", "model_version": loaded.version}


@app.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest, request: Request):
    loaded = app.state.loaded
    if loaded is None:
        request.state.reason = "no_model"
        raise HTTPException(status_code=503, detail="no usable model loaded")
    row = pd.DataFrame([payload.model_dump()], columns=list(FEATURES))
    try:
        value = float(loaded.model.predict(row)[0])
    except Exception:
        log.exception("prediction failed")
        request.state.reason = "prediction_failed"
        raise HTTPException(status_code=500, detail="prediction failed") from None
    if not math.isfinite(value) or value < 0:
        log.error("model returned an invalid prediction: %r", value)
        request.state.reason = "invalid_prediction"
        raise HTTPException(
            status_code=500, detail="model returned an invalid prediction"
        )
    return PredictResponse(prediction=value, model_version=loaded.version)
