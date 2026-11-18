# OpenRouter Pipe contributor instructions

Use English for code, tests, issue responses, commit messages, and pull requests. Read CONTRIBUTING.md and TESTING.md before changing behavior.

## Verification

Use the Python versions listed in .github/workflows/tests.yml. Install CI dependencies with `python -m pip install --require-hashes -r requirements-ci.txt`. For a bug, capture the failure on the base revision and rerun the same regression after the fix. Run `python test_pipe.py` and `python -m unittest -v test_maintenance test_alignment test_regressions`. Check `ruff check .` and `mypy` for code changes. Exercise both streaming and non-streaming code paths when shared behavior changes. Use mock provider data in automated tests. Live-provider checks consume credits and need an explicit assignment.

## Delivery

Keep each pull request focused on one deliverable. Include the affected behavior, the regression evidence, the CI results, and any checks that still need a real Open WebUI instance. For repository-maintainer assignments, use one draft PR per issue and leave the final merge and release to the owner.
