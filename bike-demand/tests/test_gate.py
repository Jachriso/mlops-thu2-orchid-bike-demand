"""Gate tests: one rule at a time, on evidence made up for the test.

No model is loaded and no candidate is evaluated here. The policy is the committed
file, so a changed margin or budget changes what these tests check.
"""

import math
from pathlib import Path

import pytest

from bike_demand.gate import decide, load_policy
from bike_demand.validate import FEATURES

ROOT = Path(__file__).parents[1]
POLICY = load_policy(ROOT / "policy" / "gate-policy.yaml")
MARGIN = POLICY["quality"]["improves_incumbent"]["improvement_margin"]
INCUMBENT = 86.84685685591091
NAIVE = 154.23179306864967
THRESHOLD = INCUMBENT * (1 - MARGIN)


def good_evidence():
    """Evidence that passes every rule."""
    return {
        "candidate_mae": 80.0,
        "naive_mae": NAIVE,
        "incumbent_mae": INCUMBENT,
        "loads_in_api": True,
        "predictions_all_finite": True,
        "predictions_min": 0.0,
        "data_sha256": "a" * 64,
        "manifest_sha256": "a" * 64,
        "features": list(FEATURES),
        "validation_rows": 4358,
        "candidate_model_sha256": "b" * 64,
        "recorded_model_sha256": "b" * 64,
        "incumbent_verify_exit": 0,
        "candidate_lock_sha256": "c" * 64,
        "incumbent_lock_sha256": "c" * 64,
        "settings": {"max_depth": 12, "random_state": 42, "n_jobs": 1},
    }


def status_of(decision, rule):
    [record] = [r for r in decision["rules"] if r["rule"] == rule]
    return record["status"]


def test_good_evidence_is_accepted():
    decision = decide(good_evidence(), POLICY)
    assert decision["outcome"] == "accept"
    assert decision["exit_status"] == POLICY["exit_status"]["accept"] == 0
    assert decision["reasons"] == []
    assert all(record["status"] == "passed" for record in decision["rules"])


def test_decision_names_the_policy_and_every_rule():
    decision = decide(good_evidence(), POLICY)
    assert set(decision) == {
        "policy_version",
        "outcome",
        "exit_status",
        "rules",
        "reasons",
    }
    assert decision["policy_version"] == POLICY["policy_version"]
    assert len(decision["rules"]) == 12
    for record in decision["rules"]:
        assert set(record) == {"family", "rule", "status", "reason"}


# Quality: a measured failure is a rejection


def test_gain_below_the_margin_is_rejected():
    evidence = {**good_evidence(), "candidate_mae": THRESHOLD + 0.01}
    decision = decide(evidence, POLICY)
    assert decision["outcome"] == "reject"
    assert decision["exit_status"] == 1
    assert status_of(decision, "improves_incumbent") == "failed"
    assert status_of(decision, "beats_naive") == "passed"


def test_gain_exactly_at_the_margin_is_accepted():
    evidence = {**good_evidence(), "candidate_mae": THRESHOLD}
    assert decide(evidence, POLICY)["outcome"] == "accept"


def test_a_model_worse_than_the_train_mean_fails_both_quality_rules():
    evidence = {**good_evidence(), "candidate_mae": NAIVE + 1}
    decision = decide(evidence, POLICY)
    assert decision["outcome"] == "reject"
    assert status_of(decision, "beats_naive") == "failed"
    assert status_of(decision, "improves_incumbent") == "failed"


# Operation: a measured failure is a rejection


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ({"loads_in_api": False}, "loads_in_the_api"),
        ({"predictions_all_finite": False}, "predictions"),
        ({"predictions_min": -0.1}, "predictions"),
    ],
)
def test_operation_failures_are_rejections(change, rule):
    decision = decide({**good_evidence(), **change}, POLICY)
    assert decision["outcome"] == "reject"
    assert status_of(decision, rule) == "failed"


# Integrity: a failure means the evidence cannot be trusted, so the run is blocked

INTEGRITY_BREAKS = [
    ("snapshot", {"data_sha256": "f" * 64}),
    ("features", {"features": list(reversed(FEATURES))}),
    ("validation_rows", {"validation_rows": 4357}),
    ("candidate_bytes", {"candidate_model_sha256": "f" * 64}),
    ("incumbent", {"incumbent_verify_exit": 1}),
    ("lock", {"candidate_lock_sha256": "f" * 64}),
    ("settings", {"settings": {"random_state": 43, "n_jobs": 1}}),
    ("settings", {"settings": {"random_state": 42, "n_jobs": 2}}),
]


@pytest.mark.parametrize(("rule", "change"), INTEGRITY_BREAKS)
def test_integrity_failures_block_the_run(rule, change):
    decision = decide({**good_evidence(), **change}, POLICY)
    assert decision["outcome"] == "blocked"
    assert decision["exit_status"] == 2
    assert status_of(decision, rule) == "failed"


def test_blocked_wins_over_reject():
    evidence = {
        **good_evidence(),
        "candidate_mae": NAIVE + 1,
        "features": list(reversed(FEATURES)),
    }
    decision = decide(evidence, POLICY)
    assert status_of(decision, "improves_incumbent") == "failed"
    assert decision["outcome"] == "blocked"


# Missing and invalid evidence is never a pass


@pytest.mark.parametrize("key", sorted(good_evidence()))
def test_missing_evidence_blocks_the_run(key):
    evidence = good_evidence()
    del evidence[key]
    decision = decide(evidence, POLICY)
    assert decision["outcome"] == "blocked"
    assert any(record["status"] == "missing" for record in decision["rules"])


def test_a_better_mae_does_not_replace_a_missing_check():
    evidence = good_evidence()
    evidence["candidate_mae"] = 1.0
    del evidence["features"]
    assert decide(evidence, POLICY)["outcome"] == "blocked"


@pytest.mark.parametrize(
    "value", [math.nan, math.inf, -math.inf, True, "86.8", -1.0, None, [80.0]]
)
def test_invalid_mae_blocks_the_run(value):
    decision = decide({**good_evidence(), "candidate_mae": value}, POLICY)
    assert decision["outcome"] == "blocked"
    assert status_of(decision, "improves_incumbent") == "invalid"
    assert status_of(decision, "evidence_values") == "invalid"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("validation_rows", 4358.0),
        ("validation_rows", True),
        ("loads_in_api", 1),
        ("predictions_all_finite", "yes"),
        ("predictions_min", math.nan),
        ("incumbent_verify_exit", False),
        ("features", "season"),
        ("settings", ["random_state"]),
        ("data_sha256", 12345),
    ],
)
def test_wrongly_typed_evidence_blocks_the_run(key, value):
    decision = decide({**good_evidence(), key: value}, POLICY)
    assert decision["outcome"] == "blocked"
    assert any(record["status"] == "invalid" for record in decision["rules"])


@pytest.mark.parametrize("evidence", [None, [], "accept", 3])
def test_evidence_that_is_not_a_mapping_blocks_the_run(evidence):
    decision = decide(evidence, POLICY)
    assert decision["outcome"] == "blocked"
    assert all(record["status"] == "missing" for record in decision["rules"][:-1])


def test_reasons_name_every_rule_that_did_not_pass():
    evidence = {**good_evidence(), "loads_in_api": False, "candidate_mae": NAIVE + 1}
    reasons = decide(evidence, POLICY)["reasons"]
    assert len(reasons) == 3
    assert any(
        reason.startswith("operation.loads_in_the_api: failed") for reason in reasons
    )
    assert any(reason.startswith("quality.beats_naive: failed") for reason in reasons)


# The policy file itself


def test_policy_without_a_section_is_refused(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("policy_version: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing sections"):
        load_policy(path)


def test_policy_must_name_the_three_outcomes(tmp_path):
    text = (ROOT / "policy" / "gate-policy.yaml").read_text(encoding="utf-8")
    path = tmp_path / "policy.yaml"
    path.write_text(text.replace("blocked: 2}", "stuck: 2}"), encoding="utf-8")
    with pytest.raises(ValueError, match="exit_status"):
        load_policy(path)
