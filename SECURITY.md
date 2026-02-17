# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|| 1.2.x   | Yes       || 1.1.x   | Yes       |
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public issue
2. Use [GitHub's private vulnerability reporting](https://github.com/sena-labs/OpenRouter-Pipe/security/advisories/new)
3. Include: description, steps to reproduce, and potential impact
4. You will receive a response within 48 hours

## Security Design

- API keys are never logged or included in error messages
- Pre-flight API key validation prevents requests with invalid credentials
- All HTTP requests use TLS (HTTPS)
- Open WebUI internal keys are stripped before forwarding to OpenRouter
- No user data is stored by the pipe
