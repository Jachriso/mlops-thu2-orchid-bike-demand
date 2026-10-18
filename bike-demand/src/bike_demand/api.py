# Prediction API for the saved bike-demand baseline model
import json
import logging
import math
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
 
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
 
from bike_demand.validate import FEATURES
 
# The uvicorn logger shows INFO lines in the container output.
log = logging.getLogger("uvicorn.error")
 
DEFAULT_MODEL_PATH = "artifacts/model.joblib"
METADATA_NAME = "model-metadata.json"
 
 
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
 
 
app = FastAPI(title="Bike demand prediction API", lifespan=lifespan)
 
 
@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc: RequestValidationError):
    """422 with location, message and type only (never echo the input).
 
    Echoing the input could even break the response for values like NaN.
    """
    detail = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})
 
 
@app.get("/health")
def health():
    loaded = app.state.loaded
    if loaded is None:
        raise HTTPException(status_code=503, detail="no usable model loaded")
    return {"status": "ok", "model_version": loaded.version}
 
 
@app.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest):
    loaded = app.state.loaded
    if loaded is None:
        raise HTTPException(status_code=503, detail="no usable model loaded")
    row = pd.DataFrame([payload.model_dump()], columns=list(FEATURES))
    try:
        value = float(loaded.model.predict(row)[0])
    except Exception:
        log.exception("prediction failed")
        raise HTTPException(status_code=500, detail="prediction failed") from None
    if not math.isfinite(value) or value < 0:
        log.error("model returned an invalid prediction: %r", value)
        raise HTTPException(
            status_code=500, detail="model returned an invalid prediction"
        )
    return PredictResponse(prediction=value, model_version=loaded.version)
 