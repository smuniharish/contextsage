# Testing

The test suite uses pytest and Hypothesis. The package is measured with
branch coverage and the project requires 100% line and branch coverage.

## Test areas

| Directory | Coverage |
| --- | --- |
| `tests/unit` | Budgeting, parsing, compaction, preservation, validation, recovery, provenance and configuration |
| `tests/property` | Properties over generated message histories |
| `tests/integration` | LangChain and LangGraph adapter behavior |
| `tests/examples` | Offline example scripts and service-backed example behavior |
| `tests/docs` | Documentation examples, local links and Agent Skills structure |
| `tests/live` | Optional real-provider calls |

## Run core tests

Install the project's dependencies:

```powershell
uv sync --locked --all-extras --all-groups
```

Run the default suite with branch coverage:

```powershell
uv run pytest --cov=contextsage --cov-branch --cov-report=term-missing:skip-covered
```

The default pytest configuration excludes tests marked `live` and `examples`.
Use an explicit selector to run examples:

```powershell
uv run pytest tests\examples tests\docs\test_examples.py `
  -m "examples or not examples" --no-cov
```

Hypothesis uses its CI profile in continuous integration:

```powershell
$env:HYPOTHESIS_PROFILE = "ci"
uv run pytest tests\property
```

## Live tests

Tests that call a real model are marked `live`. Configure
`CONTEXTSAGE_LLM_API_KEY` and, optionally,
`CONTEXTSAGE_LLM_BASE_URL` and `CONTEXTSAGE_LLM_MODEL` before running them:

```powershell
uv run pytest tests\live -m live
```

They are excluded from routine runs and do not run without an explicitly
configured provider.

## Examples and benchmarks

```powershell
uv run python examples\verify_examples.py
uv run python benchmarks\bench_middleware.py --smoke
```

The verifier compares each offline example with its recorded output. After
an intentional change, use `--update` and review every updated fixture.
