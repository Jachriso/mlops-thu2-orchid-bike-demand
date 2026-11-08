"""Pipeline tests: settings guard, identity, budget and the failure paths.

No real candidate is evaluated here. The data is made up, and nothing is read from
or written to artifacts/, tracking/ or reports/metrics.json.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from bike_demand import pipeline
from bike_demand.pipeline import (
    CANDIDATES,
    DECISIONS,
    PipelineError,
    check_budget,
    code_revision,
    load_candidate,
    main,
    run_identity,
)
from bike_demand.train import DEFAULT_MODEL
from bike_demand.validate import FEATURES

ROOT = Path(__file__).parents[1]
POLICY_FILE = ROOT / "policy" / "gate-policy.yaml"


def write_config(folder: Path, **changes) -> Path:
    config = {
        "data": "data/raw/hour.csv",
        "features": list(FEATURES),
        "model": dict(DEFAULT_MODEL),
    }
    config.update(changes)
    path = folder / "candidate.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def made_up_partitions() -> dict:
    rng = np.random.default_rng(0)

    def frame(rows: int) -> pd.DataFrame:
        data = pd.DataFrame(rng.random((rows, len(FEATURES))), columns=list(FEATURES))
        data["cnt"] = rng.random(rows) * 100
        return data

    return {"train": frame(80), "validation": frame(40)}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A throwaway project root: policy copy, data manifest, lock, made-up data."""
    (tmp_path / "policy").mkdir()
    shutil.copy(POLICY_FILE, tmp_path / "policy" / "gate-policy.yaml")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.json").write_text(json.dumps({"sha256": "a" * 64}))
    (tmp_path / "uv.lock").write_text("lock\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRAINING_COMMIT", "f" * 40)
    monkeypatch.setattr(pipeline, "check_snapshot", lambda root: {"sha256": "a" * 64})
    monkeypatch.setattr(pipeline, "load_data", lambda path: None)
    monkeypatch.setattr(pipeline, "split_data", lambda frame: made_up_partitions())
    return tmp_path


# Settings guard


def test_changed_tunable_settings_are_accepted(tmp_path):
    model = {**DEFAULT_MODEL, "n_estimators": 100, "max_depth": 6}
    config = load_candidate(write_config(tmp_path, model=model))
    assert config["model"] == model


@pytest.mark.parametrize(
    "changes",
    [
        {"n_estimators": True},
        {"n_estimators": 0},
        {"n_estimators": "50"},
        {"max_depth": 10.5},
        {"max_depth": None},
        {"random_state": 7},
        {"n_jobs": 2},
        {"min_samples_leaf": 3},
    ],
)
def test_bad_model_settings_are_refused(tmp_path, changes):
    model = {**DEFAULT_MODEL, **changes}
    with pytest.raises(PipelineError):
        load_candidate(write_config(tmp_path, model=model))


def test_a_missing_model_setting_is_refused(tmp_path):
    model = {k: v for k, v in DEFAULT_MODEL.items() if k != "n_jobs"}
    with pytest.raises(PipelineError):
        load_candidate(write_config(tmp_path, model=model))


def test_the_data_and_feature_contracts_cannot_change(tmp_path):
    with pytest.raises(PipelineError):
        load_candidate(write_config(tmp_path, data="data/raw/other.csv"))
    with pytest.raises(PipelineError):
        load_candidate(write_config(tmp_path, features=list(FEATURES)[::-1]))
    with pytest.raises(PipelineError):
        load_candidate(write_config(tmp_path, features=list(FEATURES)[:-1]))
    with pytest.raises(PipelineError):
        load_candidate(write_config(tmp_path, extra="nope"))


# Identity


def test_identity_is_stable_and_depends_on_every_input():
    base = run_identity({"model": {"max_depth": 6}}, "d" * 64, "c" * 40)
    assert base == run_identity({"model": {"max_depth": 6}}, "d" * 64, "c" * 40)
    assert len(base) == 12
    assert base != run_identity({"model": {"max_depth": 7}}, "d" * 64, "c" * 40)
    assert base != run_identity({"model": {"max_depth": 6}}, "e" * 64, "c" * 40)
    assert base != run_identity({"model": {"max_depth": 6}}, "d" * 64, "b" * 40)


def test_commit_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TRAINING_COMMIT", "f" * 40)
    assert code_revision(tmp_path) == "f" * 40


def test_an_unknown_commit_is_refused(monkeypatch, tmp_path):
    monkeypatch.delenv("TRAINING_COMMIT", raising=False)
    monkeypatch.setattr(pipeline, "training_commit", lambda root: "unavailable")
    with pytest.raises(PipelineError):
        code_revision(tmp_path)


# Budget: counted by identity, a blocked run may be retried


POLICY = {"budget": {"max_candidates": 2}}


def write_record(root: Path, name: str, outcome: str) -> None:
    folder = root / DECISIONS
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps({"decision": {"outcome": outcome}}))


def test_first_attempt_is_number_one(tmp_path):
    assert check_budget(tmp_path, POLICY, "aaa") == 1


def test_a_blocked_run_can_be_retried(tmp_path):
    write_record(tmp_path, "aaa-1", "blocked")
    assert check_budget(tmp_path, POLICY, "aaa") == 2


@pytest.mark.parametrize("outcome", ["accept", "reject"])
def test_a_decided_run_cannot_be_rerun(tmp_path, outcome):
    write_record(tmp_path, "aaa-1", outcome)
    with pytest.raises(PipelineError):
        check_budget(tmp_path, POLICY, "aaa")


def test_a_new_setting_beyond_the_budget_is_refused(tmp_path):
    write_record(tmp_path, "aaa-1", "reject")
    write_record(tmp_path, "bbb-1", "accept")
    with pytest.raises(PipelineError):
        check_budget(tmp_path, POLICY, "ccc")


def test_a_blocked_retry_does_not_use_new_budget(tmp_path):
    write_record(tmp_path, "aaa-1", "reject")
    write_record(tmp_path, "bbb-1", "blocked")
    assert check_budget(tmp_path, POLICY, "bbb") == 2


# Failure paths


def test_bad_settings_exit_2_not_1(workspace, capsys):
    config = write_config(workspace, model={**DEFAULT_MODEL, "random_state": 7})
    assert main(["--config", str(config)]) == 2
    assert "blocked" in capsys.readouterr().err
    assert not (workspace / CANDIDATES).exists()


def test_a_run_without_incumbent_is_blocked_and_touches_no_other_state(workspace):
    config = write_config(workspace)
    assert main(["--config", str(config)]) == 2
    [final] = list((workspace / CANDIDATES).iterdir())
    assert not final.name.startswith(".tmp-")
    assert (final / "decision.json").is_file()
    assert (final / "model.joblib").is_file()
    [record_path] = list((workspace / DECISIONS).glob("*.json"))
    decision = json.loads(record_path.read_text())["decision"]
    assert decision["outcome"] == "blocked"
    assert decision["exit_status"] == 2
    beats_naive = next(r for r in decision["rules"] if r["rule"] == "beats_naive")
    assert beats_naive["status"] == "passed"
    assert not (workspace / "artifacts").exists()
    assert not (workspace / "reports" / "metrics.json").exists()


def test_a_crash_exits_2_and_leaves_no_finished_run(workspace, monkeypatch, capsys):
    real = pipeline.fit_evaluate

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    config = write_config(workspace)
    monkeypatch.setattr(pipeline, "fit_evaluate", boom)
    assert main(["--config", str(config)]) == 2
    assert "boom" in capsys.readouterr().err
    folders = list((workspace / CANDIDATES).iterdir())
    assert all(p.name.startswith(".tmp-") for p in folders)
    assert not list((workspace / DECISIONS).glob("*.json"))

    monkeypatch.setattr(pipeline, "fit_evaluate", real)
    assert main(["--config", str(config)]) == 2  # blocked: no incumbent, but decided
    names = [p.name for p in (workspace / CANDIDATES).iterdir()]
    assert any(not name.startswith(".tmp-") for name in names)


def test_a_blocked_run_is_retried_as_a_new_attempt(workspace):
    config = write_config(workspace)
    assert main(["--config", str(config)]) == 2
    assert main(["--config", str(config)]) == 2
    names = sorted(p.name for p in (workspace / CANDIDATES).iterdir())
    assert [name.rsplit("-", 1)[1] for name in names] == ["1", "2"]
    assert len({name.rsplit("-", 1)[0] for name in names}) == 1