"""Gate: apply the committed policy to observed evidence and decide.

The gate never reads a model and never trains anything. It receives the evidence
that the pipeline observed (numbers, digests, exit codes) and the policy file, and
it returns one decision with a reason for every rule:

- accept:  every required rule passed;
- reject:  the evidence is valid and complete, and a quality or operation rule
           failed;
- blocked: an integrity rule did not pass, or a required piece of evidence is
           missing or invalid. Blocked wins over reject: numbers that cannot be
           trusted are not judged.

A rule that did not run is never a passed rule, and a better MAE never replaces
a missing check.
"""

from math import isfinite
from pathlib import Path

import yaml

from bike_demand.validate import FEATURES

POLICY_PATH = Path("policy/gate-policy.yaml")
POLICY_SECTIONS = (
    "protocol",
    "quality",
    "operation",
    "integrity",
    "outcomes",
    "exit_status",
    "budget",
)
PASSED, FAILED, MISSING, INVALID = "passed", "failed", "missing", "invalid"


def load_policy(path: Path = POLICY_PATH) -> dict:
    """Read the policy file; a policy that cannot be read decides nothing."""
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError("policy: the file is not a mapping")
    absent = [name for name in POLICY_SECTIONS if name not in policy]
    if absent:
        raise ValueError(f"policy: missing sections {absent}")
    if set(policy["exit_status"]) != {"accept", "reject", "blocked"}:
        raise ValueError("policy: exit_status must name accept, reject and blocked")
    return policy


def finite_number(value) -> bool:
    """True for a real, finite int or float (numpy floats included); not a
    boolean, a string, NaN or inf."""
    try:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
        )
    except OverflowError:
        return False


def describe(value) -> str:
    """Short text for a bad value; never echoes arbitrary text."""
    return repr(value) if type(value) in (int, float, bool) else type(value).__name__


def read_mae(evidence: dict, key: str):
    """Return (value, None), or (None, (status, reason)) for a bad MAE."""
    if key not in evidence:
        return None, (MISSING, f"{key} is missing")
    value = evidence[key]
    if not finite_number(value) or value < 0:
        return None, (
            INVALID,
            f"{key} must be a finite number >= 0, got {describe(value)}",
        )
    return float(value), None


def read_text(evidence: dict, key: str):
    """Return (value, None), or (None, (status, reason)) for a bad text value."""
    if key not in evidence:
        return None, (MISSING, f"{key} is missing")
    value = evidence[key]
    if not isinstance(value, str) or not value:
        return None, (INVALID, f"{key} must be a non-empty text, got {describe(value)}")
    return value, None


def beats_naive(evidence: dict):
    candidate, problem = read_mae(evidence, "candidate_mae")
    naive, other = read_mae(evidence, "naive_mae")
    if problem or other:
        return problem or other
    if candidate < naive:
        return PASSED, f"candidate MAE {candidate} is below the train-mean MAE {naive}"
    return FAILED, f"candidate MAE {candidate} is not below the train-mean MAE {naive}"


def improves_incumbent(evidence: dict, margin: float):
    candidate, problem = read_mae(evidence, "candidate_mae")
    incumbent, other = read_mae(evidence, "incumbent_mae")
    if problem or other:
        return problem or other
    threshold = incumbent * (1 - margin)
    if candidate <= threshold:
        return (
            PASSED,
            f"candidate MAE {candidate} <= {threshold} (incumbent {incumbent}, margin {margin})",
        )
    return (
        FAILED,
        f"candidate MAE {candidate} > {threshold} (incumbent {incumbent}, margin {margin})",
    )


def loads_in_the_api(evidence: dict):
    if "loads_in_api" not in evidence:
        return MISSING, "loads_in_api is missing"
    value = evidence["loads_in_api"]
    if type(value) is not bool:
        return INVALID, f"loads_in_api must be true or false, got {describe(value)}"
    if value:
        return PASSED, "the API loader accepted the candidate"
    return FAILED, "the API loader refused the candidate"


def predictions_rule(evidence: dict):
    if evidence.get("loads_in_api") is False:
        return FAILED, "no predictions: the API loader refused the candidate"
    if "predictions_all_finite" not in evidence:
        return MISSING, "predictions_all_finite is missing"
    finite = evidence["predictions_all_finite"]
    if type(finite) is not bool:
        return (
            INVALID,
            f"predictions_all_finite must be true or false, got {describe(finite)}",
        )
    if not finite:
        return FAILED, "some predictions are not finite"
    if "predictions_min" not in evidence:
        return MISSING, "predictions_min is missing"
    minimum = evidence["predictions_min"]
    if not finite_number(minimum):
        return (
            INVALID,
            f"predictions_min must be a finite number, got {describe(minimum)}",
        )
    if minimum < 0:
        return FAILED, f"a prediction is negative ({minimum})"
    return PASSED, "all predictions are finite and non-negative"


def same_text(evidence: dict, observed_key: str, expected_key: str):
    observed, problem = read_text(evidence, observed_key)
    expected, other = read_text(evidence, expected_key)
    if problem or other:
        return problem or other
    if observed == expected:
        return PASSED, f"{observed_key} equals {expected_key}"
    return FAILED, f"{observed_key} differs from {expected_key}"


def features_rule(evidence: dict):
    if "features" not in evidence:
        return MISSING, "features is missing"
    value = evidence["features"]
    if not isinstance(value, list):
        return INVALID, f"features must be a list, got {describe(value)}"
    if value == list(FEATURES):
        return PASSED, "the twelve predictors, in order"
    return FAILED, "the features differ from the twelve ordered predictors"


def rows_rule(evidence: dict, expected: int):
    if "validation_rows" not in evidence:
        return MISSING, "validation_rows is missing"
    value = evidence["validation_rows"]
    if type(value) is not int:
        return INVALID, f"validation_rows must be an integer, got {describe(value)}"
    if value == expected:
        return PASSED, f"{expected} validation rows"
    return FAILED, f"{value} validation rows, expected {expected}"


def incumbent_rule(evidence: dict):
    if "incumbent_verify_exit" not in evidence:
        return MISSING, "incumbent_verify_exit is missing"
    value = evidence["incumbent_verify_exit"]
    if type(value) is not int:
        return (
            INVALID,
            f"incumbent_verify_exit must be an integer, got {describe(value)}",
        )
    if value == 0:
        return PASSED, "bundle verify of the incumbent exited 0"
    return FAILED, f"bundle verify of the incumbent exited {value}"


def settings_rule(evidence: dict):
    if "settings" not in evidence:
        return MISSING, "settings is missing"
    value = evidence["settings"]
    if not isinstance(value, dict):
        return INVALID, f"settings must be a mapping, got {describe(value)}"
    if type(value.get("random_state")) is not int or value["random_state"] != 42:
        return FAILED, "random_state must stay 42"
    if type(value.get("n_jobs")) is not int or value["n_jobs"] != 1:
        return FAILED, "n_jobs must stay 1"
    return PASSED, "random_state 42 and n_jobs 1 are unchanged"


def decide(evidence, policy: dict) -> dict:
    """Apply every rule of the policy to the evidence and return the decision."""
    if not isinstance(evidence, dict):
        evidence = {}
    margin = policy["quality"]["improves_incumbent"]["improvement_margin"]
    expected_rows = policy["integrity"]["validation_rows"]
    results = [
        (
            "integrity",
            "snapshot",
            same_text(evidence, "data_sha256", "manifest_sha256"),
        ),
        ("integrity", "features", features_rule(evidence)),
        ("integrity", "validation_rows", rows_rule(evidence, expected_rows)),
        (
            "integrity",
            "candidate_bytes",
            same_text(evidence, "candidate_model_sha256", "recorded_model_sha256"),
        ),
        ("integrity", "incumbent", incumbent_rule(evidence)),
        (
            "integrity",
            "lock",
            same_text(evidence, "candidate_lock_sha256", "incumbent_lock_sha256"),
        ),
        ("integrity", "settings", settings_rule(evidence)),
        ("quality", "beats_naive", beats_naive(evidence)),
        ("quality", "improves_incumbent", improves_incumbent(evidence, margin)),
        ("operation", "loads_in_the_api", loads_in_the_api(evidence)),
        ("operation", "predictions", predictions_rule(evidence)),
    ]
    invalid = [name for _, name, (status, _) in results if status == INVALID]
    if invalid:
        values = (INVALID, f"invalid evidence in: {', '.join(invalid)}")
    else:
        values = (PASSED, "every number is finite, typed and in range")
    results.append(("integrity", "evidence_values", values))

    records = [
        {"family": family, "rule": name, "status": status, "reason": reason}
        for family, name, (status, reason) in results
    ]
    untrusted = any(
        record["status"] in (MISSING, INVALID)
        or (record["family"] == "integrity" and record["status"] != PASSED)
        for record in records
    )
    if untrusted:
        outcome = "blocked"
    elif any(record["status"] == FAILED for record in records):
        outcome = "reject"
    else:
        outcome = "accept"
    return {
        "policy_version": policy["policy_version"],
        "outcome": outcome,
        "exit_status": policy["exit_status"][outcome],
        "rules": records,
        "reasons": [
            f"{record['family']}.{record['rule']}: {record['status']}: {record['reason']}"
            for record in records
            if record["status"] != PASSED
        ],
    }
