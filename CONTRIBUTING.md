# Contributing

## Branches and commits
- Branch: `lab-<number>-<short-description>` (e.g. `lab-01-workflow`)
- Commit messages: short, imperative (e.g. "Normalize team labels")
- One small change per branch; stage only intended files.

## Local checks
`uv run --locked ruff check .`

`uv run --locked ruff format --check .`

`uv run --locked pytest -q -m infra`

`uv run --locked pytest -q -m lab1`

`uv run --locked pytest -q`

## Pull requests and review
- Every change goes through a PR into `main`; no direct push to `main`.
- The PR author is the lab lead; the reviewer is another member (never the author).
- The reviewer reads the diff and the test, leaves a finding, and approves
  only when the checks passed on the current revision.
- The author replies to the review and rechecks after any change.

## Merge
- The lab lead merges, only after approval and passing checks on the revision being merged.
- If a check cannot run, record why in the PR; do not claim it passed.
- Never commit secrets, environments or generated artifacts.

## Roles
Lead and reviewer rotate each lab; the current assignment is recorded
in `reports/lab-XX.md`.