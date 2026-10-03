# Contributing to OpenRouter Pipe

Thanks for wanting to contribute! This document is intentionally opinionated: it codifies the
**deliverable-PR playbook** the maintainers use day-to-day so new contributors can ship changes
with the same cadence and quality.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting started](#getting-started)
- [Development setup](#development-setup)
- [Deliverable-PR playbook](#deliverable-pr-playbook)
- [Commit messages](#commit-messages)
- [Coding standards](#coding-standards)
- [Testing](#testing)
- [Reporting bugs](#reporting-bugs)
- [Suggesting features](#suggesting-features)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](.github/CODE_OF_CONDUCT.md).
By participating, you agree to uphold this code.

## Getting started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:

   ```bash
   git clone https://github.com/<your-username>/Open-WebUI-Pipe-OpenRouter.git
   cd Open-WebUI-Pipe-OpenRouter
   ```

3. **Install** dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. **Verify** the baseline is green before changing anything:

   ```bash
   python test_pipe.py
   ```

## Development setup

### Prerequisites

- **Python** ≥ 3.10 (CI covers 3.10–3.14).
- **`requests`** ≥ 2.32.4.
- **`pydantic`** ≥ 2.0.

### Useful commands

| Command | Description |
| --- | --- |
| `python test_pipe.py` | Run the procedural assertion suite |
| `python -m unittest -v test_maintenance` | Run cache ownership, invalidation and concurrency regressions |
| `python smoke_owui.py --base-url http://127.0.0.1:3001` | Test save/update/schema/valves on a fresh disposable OWUI instance |
| `python integration_test.py` | Run live API tests (requires `OPENROUTER_API_KEY`) |

## Deliverable-PR playbook

Every change is shipped as a **single-deliverable pull request**. One PR = one reviewable unit
of value. The playbook:

1. **Sync `main`** and create a branch with a descriptive slug:

   ```bash
   git checkout main && git pull
   git checkout -b feat/<slug>
   ```

2. **Implement** the smallest complete slice of the change. Prefer surgical edits over
   incidental refactors.

3. **Add or update tests.** A change without test coverage needs a written justification
   in the PR body. Both automated suites must pass without reducing coverage.

4. **Validate locally** using the same commands CI runs:

   ```bash
   python test_pipe.py
   python -m unittest -v test_maintenance
   python integration_test.py   # optional, requires a valid API key
   ```

5. **Update `CHANGELOG.md`.** Record user-visible changes under `## [Unreleased]`.
   If it does not exist, create that section above the latest release only when
   adding pending entries, with a compare link from the latest tag to `HEAD`.
   When publishing, move those entries into the dated version section and remove
   the empty `Unreleased` heading and its compare link.

6. **Commit with Conventional Commits** (see [Commit messages](#commit-messages)) and push:

   ```bash
   git push -u origin feat/<slug>
   ```

7. **Open the pull request** using the [PR template](.github/PULL_REQUEST_TEMPLATE.md) and
   fill every section.

8. **Verify CI** goes green. A failing test leg blocks the merge — fix forward rather than
   disabling the check.

Keep the branch focused: if the diff grows beyond ~300 lines of non-generated code, split it.

## Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`.

**Examples:**

```text
feat(routing): add PROVIDER_IGNORE valve
fix(stream): close think tag on mid-stream error
docs: update README installation steps
test: add retry exhaustion coverage
```

## Coding standards

- **PEP 8** — enforced by convention; keep line length ≤ 100 chars.
- **Type hints** on every function signature.
- **One responsibility per method** — keep functions under ~50 lines; extract helpers when they grow.
- **Docstrings** on every public method using the one-line summary style.
- **Logging** via `print(f"[OpenRouter Pipe] …")` — never log API keys or user content.
- No `any`-equivalent type erasure; use proper `dict[str, Any]` annotations.

## Testing

- **Framework:** `test_pipe.py` is a procedural assertion harness; `test_maintenance.py`
  uses Python `unittest` (stdlib) for asynchronous maintenance regressions.
- **Mock strategy:** `unittest.mock.patch` for HTTP calls and Open WebUI internals.
- **Conventions:**
  - Keep existing `_section` / `_assert` conventions in `test_pipe.py`.
  - Group maintenance regression methods by behavior; prefer ownership and
    scheduling checks over assertions that mirror private implementation details.
- **CI:** both suites run on Python 3.10–3.14 using a hashed dependency snapshot.
  Real OWUI compatibility checks cover pinned `v0.11.4-slim` and current stable
  `main-slim`. Tests and CodeQL also run weekly. Live OpenRouter API tests are
  optional and can spend credits; OWUI smoke needs no API key.

To refresh the reproducible snapshot after changing `requirements-ci.in`:

```bash
uv pip compile --python-version 3.10 --generate-hashes --no-header --output-file requirements-ci.txt requirements-ci.in
python -m pip install --require-hashes -r requirements-ci.txt
```

## Reporting bugs

When reporting a bug, open a [GitHub issue](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/issues)
using the **Bug report** template and include:

1. **Open WebUI version** (`Admin Panel → About`).
2. **Python version** (`python --version`).
3. **Steps to reproduce** the issue.
4. **Expected vs. actual behavior.**
5. **Error logs** — check the Open WebUI server logs and filter for `[OpenRouter Pipe]` messages.

**Do not** include your API key in the issue. Redact it before pasting logs.

## Suggesting features

Before opening a feature request:

1. Check the [OpenRouter API docs](https://openrouter.ai/docs) to confirm the feature exists upstream.
2. Check the [Open WebUI Pipe docs](https://docs.openwebui.com/features/extensibility/plugin/functions/pipe) for compatibility constraints.
3. Open an issue using the **Feature request** template and describe the use case and expected behavior.

---

Thanks for helping improve OpenRouter Pipe! 🚀
