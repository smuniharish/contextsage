# Testing

The test suite runs with [pytest](https://docs.pytest.org/) and
[Hypothesis](https://hypothesis.readthedocs.io/), with 100% line and branch
coverage of the package and every warning treated as an error.

## Layout

| Directory | What it tests |
| --- | --- |
| `tests/unit` | Each stage on its own: budget and trigger, parsing, content units, importance, conflicts, preservation, compaction, validation, recovery, provenance and configuration |
| `tests/property` | Hypothesis properties over generated histories: units tile messages exactly, compaction never grows content or loses a fact, restated facts always satisfy validation, fallback windows are always valid |
| `tests/integration` | The middleware inside `create_agent` agents, with checkpointers, async calls and streaming |
| `tests/failure` | Failing summary models, provenance stores, hooks and analysis |
| `tests/docs` | Documentation snippets and links, rendered diagrams, the examples and the Agent Skill |
| `tests/live` | Real models; deselected by default |

## Run the tests

```bash
uv run coverage run -m pytest
uv run coverage report
```

`coverage report` fails below 100%. Code that no test can reach is removed
rather than excluded.

Hypothesis runs 60 examples per property by default. Continuous integration
runs 200 with the `ci` profile:

```bash
HYPOTHESIS_PROFILE=ci uv run pytest tests/property
```

## Markers

| Marker | Meaning |
| --- | --- |
| `live` | Calls a real model. Deselected by default; run with `uv run pytest -m live` |
| `code_detection` | Needs the tree-sitter grammars, which are downloaded on first use |

The live tests read `CONTEXTSAGE_LLM_API_KEY`, and optionally
`CONTEXTSAGE_LLM_BASE_URL` and `CONTEXTSAGE_LLM_MODEL`, from the environment or
a `.env` file, and are skipped without them.

## Examples and benchmarks

```bash
uv run python examples/verify_examples.py
uv run python benchmarks/bench_middleware.py --smoke
```

`verify_examples.py` runs every offline example and compares its output with
the recording in `examples/expected/`; after an intended change, re-record
with `--update` and review the diff. The benchmark smoke run checks that every
benchmark case still works.
