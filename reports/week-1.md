# Week 1, Labs 1–2: shared repository, workflow, validated tracked baseline

## Status
**Lab 1:** Done and described below.
**Lab 2:** Done by Anna and Jade.

## Student / team
**Student:** Benlemqadem Hajar, GitHub: `Hajarblmq`
**Team:** `mlops-thu2-orchid-bike-demand`

---

## Lab 1: Shared Repository, Workflow & Code Quality Checks

### Roles & Contributions
**Lab 1 Roles:** Leona224 was the lead author, I (`Hajarblmq`) was the reviewer.
**My Contribution:** I was the reviewer for Lab 1. I set up the project on my machine, checked out Leona's branch, ran the checks myself, read the diff, and ran the tests against the old `team.py` to see whether her added test was useful. I wrote the review comments, checked the new commit, approved the PR and merged it.

### Links to Code and Pull Requests
**Team repository:** https://github.com/Jachriso/mlops-thu2-orchid-bike-demand
**Pull request #1 (merged):** https://github.com/Jachriso/mlops-thu2-orchid-bike-demand/pull/1
**First commit I checked:** `8eea469`
**Final commit I checked and approved:** `9677616` (branch `lab-01-fix-slug`)
**My review comments:** [LINK TO COMMENT 1] and [LINK TO COMMENT 2]

### Test and Execution Results
All commands were run by me on my Mac (arm64), from the `bike-demand/` folder.

#### Commit `8eea469` (first version of the PR)
`uv run --locked pytest -q -m lab1` -> `4 passed, 44 deselected`
`uv run --locked ruff check .` -> `All checks passed`
`uv run --locked ruff format --check .` -> `10 files already formatted`
`uv run --locked pytest -q` -> `20 passed, 28 failed` (the 28 are the expected Lab 2 NotImplementedError TODOs)
Old `team.py` (`git checkout origin/main -- src/bike_demand/team.py`), then `pytest -q tests/lab1/test_team.py` -> `1 failed, 3 passed`
*Note: The last line is the important one: the test added in this first version also passed on the old code, so it did not protect the fix.*

#### Commit `9677616` (final version of the PR)
`git rev-parse --short HEAD` -> `9677616`
`uv run --locked pytest -q -m lab1` -> `4 passed, 44 deselected`
`uv run --locked ruff check .` -> `All checks passed`
Old `team.py`, then `pytest -q tests/lab1/test_team.py` -> `2 failed, 2 passed`
*Note: On the old code, both `test_joins_whitespace_with_hyphens` (supplied) and `test_joins_newlines_with_hyphens` (added) fail, so the added test now catches the bug.*

On `9677616` I did not re-run `ruff format --check`, `pytest -m infra` and the full suite myself. The results for those on `9677616` come from the PR description written by Leona and I have not independently verified them.

No GitHub check ran on the pull request (Checks: 0), so my local results are my evidence. After each check I restored `team.py` and `git status --short` was empty.

### Decisions and Rationale
The fix `"-".join(team_name.lower().split())` follows the contract: it trims, lowercases, joins any whitespace with one hyphen, and the blank-name check still raises `ValueError`.
I asked for a different added test. The first one (a name made only of tabs and newlines) passed on the old code too, because `strip()` already treats tabs and newlines as blank. A useful test must fail on the old code, so I suggested `"Team\nBlue North"` → `"team-blue-north"`.
I approved only after re-running the checks on the new commit (`9677616`).

### Review and Response
**My finding (on `8eea469`):** the added test also passed on the old `team.py`; I asked for one that fails on the old code, e.g. `"Team\nBlue North"` → `"team-blue-north"`.
**Response:** Leona replaced the test with `test_joins_newlines_with_hyphens` (commits `9cddb2c` and `9677616`) and confirmed it to me by WhatsApp message. She did not reply in writing on GitHub, so the reply is not visible on the PR.
**My follow-up (on `9677616`):** `lab1` 4 passed, `ruff check` OK, the new test fails on the old code and passes on the fix.
**Result:** I approved on `9677616` and the PR was merged into `main`.

### Screenshots
**Local checks on commit `9677616`:**
   ![Local checks on commit 9677616](./images/lab1-9677616.png)

2. **Tests run against the old `team.py` code (showing the new test fails as expected):**
   ![Tests run against old team.py](./images/old-code-9677616.jpg)

---

##  General Notes, Blockers & Acknowledgements

### Blockers / Missing Evidence
My first install failed: the disk was full, and then my Intel (x86_64) `uv` on an arm64 Mac tried to compile `cryptography`. I freed disk space, installed a native `uv` 0.12.24 and an arm64 Python 3.12, and ran `uv sync --locked`. I did not touch `uv.lock`.
No remote CI result exists for this PR.
Leona's reply is only on WhatsApp, not on GitHub.
I have no saved screenshot of the first old-code run (1 failed, 3 passed on `8eea469`); I only have its terminal output in my notes.
Lab 2 is not done yet.

### Assistance and Recovery Acknowledgement
Starter code and tests were supplied by the course.







