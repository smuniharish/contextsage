# Contributing to ContextSage

Thanks for your interest in contributing! ContextSage is a focused,
production-grade package. Every change is expected to preserve its
architectural contract (in particular: no public plugin architecture, no
forced heavyweight dependencies, and no new top-level product surface beyond
`IntelligentSummarizationMiddleware`). See
[`ARCHITECTURE_INTERNALS.md`](ARCHITECTURE_INTERNALS.md) for a guided tour
of the internal pipeline engines (`ContextDecomposer`, `ImportanceEngine`,
`SummarizationPlanner`, etc.) if you're extending or debugging one of them.

## Getting started

```bash
git clone https://github.com/smuniharish/contextsage.git
cd contextsage
pip install -e ".[dev,examples]"
pre-commit install
```

## Development workflow

Before opening a pull request, run the same checks CI runs
(`.github/workflows/ci.yml`):

```bash
ruff check src tests examples
ruff format --check src tests examples
pyrefly check
pytest tests -q
mkdocs build --strict
```

`pre-commit run --all-files` runs the lint/format checks automatically on
every commit once installed.

## Making changes

- **Tests are required** for any behavioral change. Unit tests live in
  `tests/unit/` (one file per engine), integration tests in
  `tests/integration/`, and failure-injection tests in `tests/failure/`.
- **Public API changes** (anything on `IntelligentSummarizationMiddleware`'s
  constructor) must update `docs/api-reference.md` and
  `docs/configuration.md`, and should extend `examples/all_parameters.py`
  to exercise the new parameter against a real LLM call.
- **New default values or hardcoded patterns/thresholds** should be
  exposed as overridable constructor keyword arguments, following the
  `DEFAULT_*` module-constant convention used throughout `src/contextsage/`.
- Update `CHANGELOG.md` under `[Unreleased]` for any user-facing change.

## Reporting bugs / requesting features

Open a GitHub issue with a minimal reproduction (a message list and the
`IntelligentSummarizationMiddleware` constructor arguments used) where
possible.

## Security issues

Do not open a public issue for a security vulnerability — see
[SECURITY.md](SECURITY.md).

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
