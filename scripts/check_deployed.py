import json
import math
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
VALID = {"season": 1, "yr": 0, "mnth": 1, "hr": 12, "holiday": 0,
         "weekday": 1, "workingday": 1, "weathersit": 1,
         "temp": 0.5, "atemp": 0.5, "hum": 0.5, "windspeed": 0.2}
INVALID = dict(VALID, hum=1.5)


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}


def main():
    if len(sys.argv) != 2:
        print("usage: python3 scripts/check_deployed.py <expected_model_version>")
        return 2
    expected = sys.argv[1]
    rows = []

    s, h = call("GET", "/health")
    rows.append(("health status", "200", str(s), s == 200))
    rows.append(("health model_version", expected,
                 str(h.get("model_version")), h.get("model_version") == expected))

    s, p = call("POST", "/predict", VALID)
    pred = p.get("prediction")
    good = (s == 200 and isinstance(pred, (int, float))
            and math.isfinite(pred) and pred >= 0)
    rows.append(("predict valid", "200 + prediction >= 0", f"{s} {pred}", good))
    rows.append(("predict model_version", expected,
                 str(p.get("model_version")), p.get("model_version") == expected))

    s, _ = call("POST", "/predict", INVALID)
    rows.append(("predict invalid (hum=1.5)", "422", str(s), s == 422))

    print(f"{'claim':<28}{'expected':<26}{'observed':<28}result")
    failed = False
    for claim, exp, obs, ok in rows:
        failed = failed or not ok
        print(f"{claim:<28}{exp:<26}{obs:<28}{'ok' if ok else 'FAIL'}")
    print("exit status", 1 if failed else 0)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
