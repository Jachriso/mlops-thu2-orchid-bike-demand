"""Accepted bundles: integrity is checked before loading, evidence is recomputed."""

import json
from pathlib import Path

import joblib
import pytest
from sklearn.dummy import DummyRegressor

from bike_demand import bundle as bundle_module
from bike_demand.bundle import (
    BundleError,
    check_bytes,
    create_bundle,
    main,
    read_pointer,
    validation_rows,
    verify_bundle,
)
from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    """A small trusted model (train mean) with metadata, like train.py writes."""
    folder = tmp_path_factory.mktemp("trained")
    data_sha256, train, _ = validation_rows(ROOT)
    model = DummyRegressor(strategy="mean").fit(
        train.loc[:, list(FEATURES)], train["cnt"]
    )
    model_path = folder / "model.joblib"
    joblib.dump(model, model_path)
    metadata = {
        "model_version": "baseline-test",
        "model_sha256": sha256(model_path),
        "data_sha256": data_sha256,
        "config": {"model": {"strategy": "mean"}},
    }
    metadata_path = folder / "model-metadata.json"
    metadata_path.write_text(json.dumps(metadata))
    return model_path, metadata_path


@pytest.fixture
def bundle(trained, tmp_path):
    model_path, metadata_path = trained
    out = tmp_path / "bundle"
    create_bundle(
        model_path,
        metadata_path,
        ROOT / "uv.lock",
        out,
        ROOT,
        {"commit": "test", "built_by": "pytest"},
    )
    return out


def manifest_digest(folder: Path) -> str:
    return sha256(folder / "manifest.json")


def test_created_bundle_verifies_and_reproduces_its_mae(bundle):
    result = verify_bundle(bundle, ROOT, manifest_digest(bundle))
    assert result["status"] == "ok"
    assert result["validation_rows"] == 4358
    # A train-mean model must score exactly the train-mean comparator.
    mae = result["validation_mae"]
    assert mae["model"] == pytest.approx(mae["naive_train_mean"], abs=1e-9)


def test_tampered_model_is_rejected_before_it_is_loaded(bundle, monkeypatch):
    with (bundle / "model.joblib").open("ab") as stream:
        stream.write(b"\0")

    def never_load(*_args, **_kwargs):
        raise AssertionError("a model with a wrong digest must not be loaded")

    monkeypatch.setattr(bundle_module.joblib, "load", never_load)
    with pytest.raises(BundleError, match="model.joblib sha256 differs"):
        verify_bundle(bundle, ROOT)


def test_pointer_must_name_this_exact_manifest(bundle):
    with pytest.raises(BundleError, match="differs from the pointer"):
        check_bytes(bundle, "0" * 64)


def test_missing_file_is_not_a_pass(bundle):
    (bundle / "uv.lock").unlink()
    with pytest.raises(BundleError, match="uv.lock is missing"):
        check_bytes(bundle)


def test_recorded_mae_that_cannot_be_reproduced_fails(bundle):
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["validation_mae"]["model"] -= 1.0
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match="model validation MAE"):
        verify_bundle(bundle, ROOT, manifest_digest(bundle))


def test_metadata_must_match_the_manifest(bundle):
    metadata_path = bundle / "model-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["model_version"] = "baseline-other"
    metadata_path.write_text(json.dumps(metadata))
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["model-metadata.json"] = sha256(metadata_path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match="metadata model_version"):
        check_bytes(bundle)


def test_existing_bundle_is_never_overwritten(trained, bundle):
    model_path, metadata_path = trained
    with pytest.raises(BundleError, match="never edited"):
        create_bundle(model_path, metadata_path, ROOT / "uv.lock", bundle, ROOT, {})


def test_committed_pointer_names_the_recorded_reference():
    pointer = read_pointer(ROOT / "models/accepted.json")
    current = pointer["current"]
    for key in ("manifest_sha256", "model_sha256"):
        assert len(current[key]) == 64 and int(current[key], 16) >= 0
    assert current["bundle_uri"].startswith("gs://")
    assert current["bundle_uri"].endswith("/")
    recorded = json.loads((ROOT / "reports/metrics.json").read_text())
    assert current["validation_mae"] == {
        "naive_train_mean": recorded["validation_mae"]["naive_train_mean"],
        "model": recorded["validation_mae"]["random_forest"],
    }
    assert isinstance(pointer["previous"], list)


def test_cli_exit_status(bundle, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    pointer = tmp_path / "accepted.json"
    pointer.write_text(
        json.dumps({"current": {"manifest_sha256": manifest_digest(bundle)}})
    )
    assert main(["verify", str(bundle), "--pointer", str(pointer)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    pointer.write_text(json.dumps({"current": {"manifest_sha256": "0" * 64}}))
    assert main(["verify", str(bundle), "--pointer", str(pointer)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
