# Security Policy

OpenRouter Pipe follows a **best-effort patch policy** on the latest minor release and
critical-only fixes on the previous one.

## Supported Versions

| Version | Status              | Security fixes |
| ------- | ------------------- | -------------- |
| 1.12.x  | :white_check_mark:  | active         |
| 1.11.x  | :white_check_mark:  | critical only  |
| < 1.11  | :x:                 | end-of-life    |

## Reporting a Vulnerability

We take the security of OpenRouter Pipe seriously. If you discover a security vulnerability,
please report it responsibly.

### How to Report

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please send an email to **<contact@sena-labs.dev>** with:

1. **Description** of the vulnerability.
2. **Steps to reproduce** the issue.
3. **Impact assessment** — what an attacker could achieve.
4. **Affected versions** — which version(s) are impacted.
5. **Suggested fix** (if you have one).

Alternatively, use
[GitHub's private vulnerability reporting](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/security/advisories/new).

### What to Expect

- **Acknowledgment** within 48 hours of your report.
- **Initial assessment** within 5 business days.
- **Fix timeline** communicated within 10 business days.
- **Credit** in the release notes (unless you prefer to remain anonymous).

### Scope

The following are in scope for security reports:

- API key exposure through logs, error messages, or HTTP responses.
- Injection of arbitrary HTTP headers or request parameters via user-supplied valves.
- Unintended forwarding of sensitive Open WebUI internal data to OpenRouter.
- Dependency vulnerabilities with a known CVE affecting the production dependency closure.

### Out of Scope

- Vulnerabilities in the OpenRouter API itself (report to [OpenRouter](https://openrouter.ai)).
- Vulnerabilities in Open WebUI (report to the [Open WebUI project](https://github.com/open-webui/open-webui)).
- Denial of service via excessive `MAX_RETRIES` or `REQUEST_TIMEOUT` configuration.
- Social engineering attacks.

### Security Measures

The pipe implements the following security practices:

- **No key logging** — `OPENROUTER_API_KEY` is never written to logs or included in error messages.
- **Pre-flight validation** — invalid keys are caught at model-fetch time via the `/models` response, before any user message is sent.
- **HTTPS by default** — `OPENROUTER_BASE_URL` defaults to `https://openrouter.ai/api/v1`; custom HTTP endpoints are allowed, and non-HTTP(S) schemes are rejected.
- **Internal key stripping** — Open WebUI internal fields (`chat_id`, `title`, `task`, `metadata`, `files`, `tool_ids`, `session_id`, `message_id`) are removed from the payload before forwarding.
- **Bounded in-memory caches** — the pipe retains model metadata, authorization headers,
  credit balances and hashed TTS fingerprints. Speech-file URLs are scoped to user,
  chat, endpoint and resolved API key, expire after five minutes and are checked
  against OWUI file metadata before reuse. Generated media is stored by OWUI.
- **Key storage** — OWUI persists valves; pipe API keys are Fernet-encrypted when
  `WEBUI_SECRET_KEY` and `cryptography` are available, otherwise stored in plaintext
  with a warning. Authorization headers necessarily contain decrypted credentials
  in server memory; neither full keys nor key fragments belong in test output.
- **Media redirects rejected** — speech/video HTTP calls do not follow redirects,
  so an upstream redirect cannot bypass media URL restrictions.
- **Deep-copy payload** — `copy.deepcopy` is used on the request body to prevent mutation of Open WebUI's internal state.

### Automated Security Gates

Every push to `main`, pull request and weekly scheduled run executes:

- **Unit and regression suites** (`.github/workflows/tests.yml`) across Python 3.10–3.14,
  with pinned and hashed CI dependencies.
- **Real OWUI compatibility smoke** — create/update a function, generate valve
  schemas and persist valves on pinned and current stable disposable containers.
- **CodeQL** (`.github/workflows/codeql.yml`) — Python `security-extended` analysis.

Dependabot checks Python dependencies and GitHub Actions weekly. GitHub secret
scanning, push protection and private vulnerability reporting are enabled.

## Disclosure Policy

- We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure).
- We aim to release patches within 14 days of confirming a vulnerability.
- Security advisories are published via [GitHub Security Advisories](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/security/advisories).
