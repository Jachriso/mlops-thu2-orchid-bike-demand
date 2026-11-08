"""Accepted-model bundles: create one, verify its bytes, recompute its evidence.

A bundle is a directory holding the exact bytes of one model version:

    model.joblib          the fitted model
    model-metadata.json   the metadata the API serves (model_version, ...)
    uv.lock               the dependency lock the model was trained with
    manifest.json         sha256 of each file above + evaluation context

The bundle itself lives outside Git (model binaries are never committed).
The pointer `models/accepted.json` is committed: it names the accepted bundle
by the sha256 of its manifest, so it names exact bytes.

Integrity comes first: no model file is loaded before every digest matches.
"""

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error

from bike_demand.preflight import check_snapshot, sha256
from bike_demand.split import split_data
from bike_demand.train import compare_mean
from bike_demand.validate import FEATURES, load_data

BUNDLE_FILES = ("model.joblib", "model-metadata.json", "uv.lock")
MANIFEST = "manifest.json"
SCHEMA = 1
# Same tolerance as the Lab 6 regression tests: the seed is fixed and the
# recomputed MAE was identical on Windows, macOS and ubuntu-24.04 runners.
MAE_TOLERANCE = 1e-6


class BundleError(ValueError):
    """The bundle cannot be trusted or does not match its recorded evidence."""


def validation_rows(root: Path):
    """The frozen validation partition (Jan-Jun 2012), after the snapshot check."""
    snapshot = check_snapshot(root)
    partitions = split_data(load_data(root / "data/raw/hour.csv"))
    return snapshot["sha256"], partitions["train"], partitions["validation"]


def evaluate_model(model_path: Path, root: Path) -> dict:
    """Validation MAE of a trusted model file and of the train-mean comparator."""
    data_sha256, train, validation = validation_rows(root)
    # Only call this on bytes whose digest was checked (or that we just trained).
    model = joblib.load(model_path)
    predictions = model.predict(validation.loc[:, list(FEATURES)])
    if not np.isfinite(predictions).all():
        raise BundleError("evaluation: predictions must be finite")
    _, naive_mae = compare_mean(train["cnt"], validation["cnt"])
    return {
        "data_sha256": data_sha256,
        "features": list(FEATURES),
        "validation_rows": len(validation),
        "validation_mae": {
            "naive_train_mean": naive_mae,
            "model": float(mean_absolute_error(validation["cnt"], predictions)),
        },
    }


def create_bundle(
    model_path: Path,
    metadata_path: Path,
    lock_path: Path,
    out_dir: Path,
    root: Path,
    source: dict,
) -> dict:
    """Copy the three files into out_dir and write their manifest."""
    if out_dir.exists() and any(out_dir.iterdir()):
        raise BundleError(f"create: {out_dir} is not empty; bundles are never edited")
    metadata = json.loads(metadata_path.read_text())
    if sha256(model_path) != metadata.get("model_sha256"):
        raise BundleError("create: model.joblib does not match its metadata")
    out_dir.mkdir(parents=True, exist_ok=True)
    for source_path, name in zip(
        (model_path, metadata_path, lock_path), BUNDLE_FILES, strict=True
    ):
        shutil.copyfile(source_path, out_dir / name)
    evaluation = evaluate_model(out_dir / "model.joblib", root)
    if evaluation["data_sha256"] != metadata.get("data_sha256"):
        raise BundleError("create: model was trained on another data snapshot")
    manifest = {
        "schema": SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "files": {name: sha256(out_dir / name) for name in BUNDLE_FILES},
        "model_sha256": metadata["model_sha256"],
        "model_version": metadata["model_version"],
        "model_settings": metadata.get("config", {}).get("model"),
        **evaluation,
        "source": source,
    }
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def check_bytes(bundle: Path, expected_manifest_sha256: str | None = None) -> dict:
    """Check every digest without loading the model. Raises BundleError."""
    manifest_path = bundle / MANIFEST
    if not manifest_path.is_file():
        raise BundleError(f"integrity: {MANIFEST} is missing")
    manifest_digest = sha256(manifest_path)
    if expected_manifest_sha256 and manifest_digest != expected_manifest_sha256:
        raise BundleError(
            "integrity: manifest sha256 differs from the pointer "
            f"({manifest_digest} != {expected_manifest_sha256})"
        )
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != SCHEMA:
        raise BundleError("integrity: unknown manifest schema")
    if set(manifest.get("files", {})) != set(BUNDLE_FILES):
        raise BundleError("integrity: manifest does not list the bundle files")
    for name, expected in manifest["files"].items():
        path = bundle / name
        if not path.is_file():
            raise BundleError(f"integrity: {name} is missing")
        if sha256(path) != expected:
            raise BundleError(f"integrity: {name} sha256 differs from the manifest")
    if manifest["files"]["model.joblib"] != manifest["model_sha256"]:
        raise BundleError("integrity: model_sha256 differs from model.joblib digest")
    metadata = json.loads((bundle / "model-metadata.json").read_text())
    for key in ("model_sha256", "model_version"):
        if metadata.get(key) != manifest[key]:
            raise BundleError(f"integrity: metadata {key} differs from the manifest")
    return {"manifest_sha256": manifest_digest, "manifest": manifest}


def verify_bundle(
    bundle: Path, root: Path, expected_manifest_sha256: str | None = None
) -> dict:
    """Bytes first, then recompute the recorded validation evidence."""
    checked = check_bytes(bundle, expected_manifest_sha256)
    manifest = checked["manifest"]
    evaluation = evaluate_model(bundle / "model.joblib", root)
    if evaluation["data_sha256"] != manifest["data_sha256"]:
        raise BundleError("evidence: data snapshot differs from the manifest")
    if evaluation["features"] != manifest["features"]:
        raise BundleError("evidence: feature order differs from the manifest")
    if evaluation["validation_rows"] != manifest["validation_rows"]:
        raise BundleError("evidence: validation rows differ from the manifest")
    for label, recorded in manifest["validation_mae"].items():
        observed = evaluation["validation_mae"][label]
        if abs(observed - recorded) > MAE_TOLERANCE:
            raise BundleError(
                f"evidence: {label} validation MAE {observed} != recorded {recorded}"
            )
    return {
        "status": "ok",
        "manifest_sha256": checked["manifest_sha256"],
        "model_sha256": manifest["model_sha256"],
        "model_version": manifest["model_version"],
        "validation_rows": evaluation["validation_rows"],
        "validation_mae": evaluation["validation_mae"],
    }


def read_pointer(path: Path) -> dict:
    pointer = json.loads(path.read_text())
    current = pointer.get("current")
    if not isinstance(current, dict) or not current.get("manifest_sha256"):
        raise BundleError("pointer: no current accepted version")
    return pointer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="build a bundle from trained files")
    create.add_argument("--model", type=Path, required=True)
    create.add_argument("--metadata", type=Path, required=True)
    create.add_argument("--lock", type=Path, default=Path("uv.lock"))
    create.add_argument("--out", type=Path, required=True)
    create.add_argument("--commit", required=True, help="commit the model came from")
    create.add_argument("--built-by", required=True, help="command that trained it")
    verify = commands.add_parser("verify", help="check bytes, then recompute MAE")
    verify.add_argument("bundle", type=Path)
    verify.add_argument(
        "--pointer",
        type=Path,
        help="models/accepted.json: also require the manifest it names",
    )
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        if args.command == "create":
            source = {"commit": args.commit, "built_by": args.built_by}
            result = create_bundle(
                args.model, args.metadata, args.lock, args.out, root, source
            )
        else:
            expected = None
            if args.pointer:
                expected = read_pointer(args.pointer)["current"]["manifest_sha256"]
            result = verify_bundle(args.bundle, root, expected)
    except (BundleError, OSError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
