# Contributing to OpenRouter Pipe

> **Maintained by [Sena Labs](https://github.com/sena-labs)** · [GitHub](https://github.com/sena-labs/Open-Router-Pipe)

Thanks for your interest in contributing! 🎉

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/sena-labs/Open-Router-Pipe.git
cd Open-Router-Pipe

# Run the test suite
python test_pipe.py
```

## 📁 Project Structure

```
Open-Router-Pipe/
├── openrouter_pipe.py      # Main pipe source — this is what gets installed in Open WebUI
├── test_pipe.py            # Test suite (131 tests, run with: python test_pipe.py)
├── README.md               # Project documentation
├── CHANGELOG.md            # Version history (Keep a Changelog format)
├── CONTRIBUTING.md         # This file
├── LICENSE                 # MIT License
└── .gitignore              # Git ignore rules
```

## 🔧 Development

### Prerequisites

- Python 3.10+
- `requests` library
- `pydantic` library

### Running Tests

```bash
python test_pipe.py
```

All 131 tests should pass. If adding new functionality, add corresponding tests.

### Code Style

- Follow PEP 8 conventions
- Use type hints for all function signatures
- Keep methods focused — one responsibility per method
- Add docstrings for public methods
- Use `print(f"[OpenRouter Pipe] ...")` for debug logging

## 🔀 Pull Request Process

1. **Fork** the repository
2. Create a **feature branch** (`git checkout -b feature/my-feature`)
3. Make your changes
4. **Run the test suite** and ensure all tests pass
5. Update `CHANGELOG.md` with your changes under `[Unreleased]`
6. Commit with a clear message (`git commit -m "feat: add XYZ support"`)
7. Push to your fork and **open a Pull Request**

### Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Usage |
|--------|-------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code restructuring |
| `test:` | Adding or updating tests |
| `chore:` | Maintenance tasks |

### PR Checklist

- [ ] Tests pass (`python test_pipe.py` → 0 failures)
- [ ] New features have corresponding tests
- [ ] `CHANGELOG.md` updated
- [ ] Code follows existing style conventions
- [ ] No OpenRouter API keys or secrets committed

## 🐛 Reporting Issues

When reporting a bug, please include:

1. **Open WebUI version** you're running
2. **Python version** (`python --version`)
3. **Steps to reproduce** the issue
4. **Expected vs actual behavior**
5. **Error logs** (check Open WebUI server logs for `[OpenRouter Pipe]` messages)

## 📋 Feature Requests

Before requesting a feature:

1. Check [OpenRouter API docs](https://openrouter.ai/docs) to confirm the feature exists upstream
2. Check [Open WebUI Pipe docs](https://docs.openwebui.com/features/plugin/functions/pipe) for compatibility
3. Open an issue describing the feature and its use case

## 📄 License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
