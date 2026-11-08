"""Candidate pipeline: train one candidate, observe evidence, ask the gate.

One command, one candidate. It never touches artifacts/ or reports/metrics.json
(train.py does) and it never decides: it observes, then hands the evidence to the
gate. Everything is built in a temporary folder and renamed at the end, so a
folder named after a run always holds a finished decision.

Exit status is the gate's: 0 accept, 1 reject, 2 blocked. Anything that is not a
decision (bad settings, unexpected crash) also exits 2, never 1.

Candidate settings (tunable and fixed) are read from the policy file, so the
allowlist lives next to the rules it belongs to.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import yaml

from bike_demand.api import ModelUnavailable, load_model
from bike_demand.gate import decide, load_policy
from bike_demand.preflight import check_snapshot, sha256
from bike_demand.split import split_data
from bike_demand.tracking import training_commit
from bike_demand.train import DEFAULT_MODEL, compare_mean, fit_evaluate
from bike_demand.validate import FEATURES, load_data

CANDIDATES = Path("bundles/candidates")  # outside Git (see .gitignore)
DECISIONS = Path("reports/lab7/decisions")  # committed records


class PipelineError(Exception):
    """The run cannot produce evidence that the gate could judge."""


def load_candidate(path: Path, settings: dict) -> dict:
    """Same contract as train.load_config, but model settings may vary.

    `settings` is the `candidate_settings` block of the policy: it holds the
    `tunable` keys with their min/max bounds and the `fixed` keys with their
    required values. The policy is required (no fallback): a missing block is
    already refused by load_policy.
    """
    tunable = settings["tunable"]
    fixed = settings["fixed"]
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"data", "features", "model"}:
        raise PipelineError("config: require data, features and model")
    if config["data"] != "data/raw/hour.csv":
        raise PipelineError("config: use the frozen data/raw/hour.csv snapshot")
    if config["features"] != list(FEATURES):
        raise PipelineError("config: require the twelve ordered contract predictors")
    model = config["model"]
    if not isinstance(model, dict) or set(model) != set(DEFAULT_MODEL):
        raise PipelineError(f"config: model needs exactly {sorted(DEFAULT_MODEL)}")
    for key, bounds in tunable.items():
        if type(model[key]) is not int:
            raise PipelineError(f"config: {key} must be an integer")
        if not (bounds["min"] <= model[key] <= bounds["max"]):
            raise PipelineError(
                f"config: {key} must be between {bounds['min']} and {bounds['max']}"
            )
    for key, value in fixed.items():
        if type(model[key]) is not int or model[key] != value:
            raise PipelineError(f"config: {key} must stay {value}")
    return config


def code_revision(root: Path) -> str:
    # The image has no .git: the commit is passed from outside.
    commit = os.environ.get("TRAINING_COMMIT") or training_commit(root)
    if commit == "unavailable":
        raise PipelineError("commit: set TRAINING_COMMIT (the image has no .git)")
    return commit


def run_identity(config: dict, data_sha256: str, commit: str) -> str:
    """Same settings + same data + same commit = same identity. No clock, no uuid."""
    payload = {"model": config["model"], "data_sha256": data_sha256, "commit": commit}
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def check_budget(root: Path, policy: dict, run_id: str) -> int:
    """Count by identity. Return this attempt number. Raise if not allowed."""
    records = sorted((root / DECISIONS).glob("*.json"))
    mine = [p for p in records if p.stem.rsplit("-", 1)[0] == run_id]
    for path in mine:
        if json.loads(path.read_text())["decision"]["outcome"] != "blocked":
            raise PipelineError(f"run {run_id} is already decided; change the settings")
    known = {p.stem.rsplit("-", 1)[0] for p in records}
    limit = policy["budget"]["max_candidates"]
    if not mine and len(known) >= limit:
        raise PipelineError(f"budget: {limit} distinct settings already evaluated")
    return len(mine) + 1


def observe_incumbent(root: Path, bundle: Path | None) -> dict:
    """Run `bundle verify` as its own process and keep only what it reported."""
    if bundle is None:
        return {}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "bike_demand.bundle",
            "verify",
            str(bundle),
            "--pointer",
            "models/accepted.json",
        ],
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    evidence = {"incumbent_verify_exit": done.returncode}
    if done.returncode == 0:
        report = json.loads(done.stdout)
        manifest = json.loads((bundle / "manifest.json").read_text())
        evidence["incumbent_mae"] = report["validation_mae"]["model"]
        evidence["incumbent_lock_sha256"] = manifest["files"]["uv.lock"]
    return evidence


def run(root: Path, config_path: Path, incumbent: Path | None) -> int:
    policy = load_policy(root / "policy/gate-policy.yaml")
    settings = policy["candidate_settings"]
    config = load_candidate(config_path, settings)
    observed_sha = check_snapshot(root)["sha256"]
    expected_sha = json.loads((root / "data/manifest.json").read_text())["sha256"]
    commit = code_revision(root)
    run_id = run_identity(config, observed_sha, commit)
    name = f"{run_id}-{check_budget(root, policy, run_id)}"
    final = root / CANDIDATES / name
    tmp = root / CANDIDATES / f".tmp-{name}"
    if final.exists():
        raise PipelineError(f"{final} already exists; runs are never overwritten")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    partitions = split_data(load_data(root / config["data"]))
    train, validation = partitions["train"], partitions["validation"]
    _, naive_mae = compare_mean(train["cnt"], validation["cnt"])
    model, _, candidate_mae = fit_evaluate(train, validation, config)

    model_path = tmp / "model.joblib"
    metadata_path = tmp / "model-metadata.json"
    joblib.dump(model, model_path)
    metadata = {
        "model_version": f"candidate-{name}",
        "features": config["features"],
        "data_sha256": observed_sha,
        "training_commit": commit,
        "config": config,
        "effective_model_settings": model.get_params(),
        "model_sha256": sha256(model_path),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, default=str) + "\n")

    # Evidence = what is observed on the files as saved, never what was intended.
    saved = json.loads(metadata_path.read_text())
    evidence = {
        "candidate_mae": candidate_mae,
        "naive_mae": naive_mae,
        "data_sha256": observed_sha,
        "manifest_sha256": expected_sha,
        "features": saved["features"],
        "validation_rows": len(validation),
        "candidate_model_sha256": sha256(model_path),
        "recorded_model_sha256": saved["model_sha256"],
        "candidate_lock_sha256": sha256(root / "uv.lock"),
        "settings": model.get_params(),
    }
    # Bytes first: the model is only loaded if its digest matches its record.
    if evidence["candidate_model_sha256"] == evidence["recorded_model_sha256"]:
        try:
            loaded = load_model(model_path, metadata_path)
            predictions = np.asarray(
                loaded.model.predict(validation.loc[:, list(FEATURES)]), dtype=float
            )
            evidence["loads_in_api"] = True
            evidence["settings"] = loaded.model.get_params()
            evidence["predictions_all_finite"] = bool(np.isfinite(predictions).all())
            if evidence["predictions_all_finite"]:
                evidence["predictions_min"] = float(predictions.min())
        except ModelUnavailable:
            evidence["loads_in_api"] = False
    evidence.update(observe_incumbent(root, incumbent and root / incumbent))

    decision = decide(evidence, policy)
    record = {
        "run": name,
        "training_commit": commit,
        "config": config,
        "evidence": evidence,
        "decision": decision,
    }
    text = json.dumps(record, indent=2, default=str) + "\n"
    (tmp / "decision.json").write_text(text)
    tmp.rename(final)  # a run folder exists only once its decision is written
    (root / DECISIONS).mkdir(parents=True, exist_ok=True)
    (root / DECISIONS / f"{name}.json").write_text(text)
    print(json.dumps(decision, indent=2))
    return decision["exit_status"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--incumbent", type=Path, help="local copy of accepted bundle")
    args = parser.parse_args(argv)
    try:
        return run(Path.cwd(), args.config, args.incumbent)
    except Exception as error:  # any crash is blocked (2), never a reject (1)
        print(f"blocked: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
