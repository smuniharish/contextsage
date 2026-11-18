# Contributing

Thank you for helping improve ContextSage. Bug reports, documentation fixes,
content recognition and performance work are welcome. Follow the
[code of conduct](https://github.com/smuniharish/contextsage/blob/master/CODE_OF_CONDUCT.md) in all project spaces.

## Report an issue

Open an [issue](https://github.com/smuniharish/contextsage/issues/new/choose)
with a minimal reproduction and the expected behavior. For runtime issues,
include the ContextSage, Python and relevant integration versions. Prefer a
scripted model over a real provider call. Do not include API keys or private
conversation content. Report security issues through the
[security policy](https://github.com/smuniharish/contextsage/blob/master/SECURITY.md).

## Set up the project

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/smuniharish/contextsage.git
cd contextsage
uv sync --locked --all-extras --all-groups
```

This installs the core, optional integrations, tests, tooling and example
dependencies. To run the pre-commit hooks locally, use `uvx pre-commit
install`.

## Run checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check --min-severity warn
uv run pytest --cov=contextsage --cov-branch --cov-report=term-missing:skip-covered
uv run pytest tests\examples tests\docs\test_examples.py `
  -m "examples or not examples" --no-cov
uv run python examples\verify_examples.py
uv run python benchmarks\bench_middleware.py --smoke
uv run python scripts\generate_api_reference.py --check
uv run --only-group docs zensical build --strict
uv build
uvx twine check --strict dist/*
```

The project requires 100% line and branch coverage. The standard pytest
configuration excludes `live` and `examples` tests; the second test command
runs the offline examples. Live model calls require explicit provider
configuration.

## Project conventions

- Keep the core asynchronous and framework-neutral. Put framework-specific
  behavior in an optional integration.
- Use abstract base classes for extension points.
- Keep public API names in module `__all__` and document them in the
  generated reference.
- Add tests for behavior changes and maintain complete package coverage.
- Keep events and logs free of conversation content and credentials.
- Update examples, documentation, Agent Skills and the changelog with
  behavior changes.
- Document public interfaces, integration boundaries and operational behavior.
  Keep diagrams conceptual where implementation detail is not needed, and
  raise potentially sensitive disclosures for maintainer review. Public source
  and Git history remain accessible even when documentation is simplified.

## Tests and documentation

Tests live under `tests/`: `unit`, `property`, `integration`, `examples`,
`docs` and optional `live` tests. See the
[testing guide](https://contextsage.readthedocs.io/en/latest/development/testing/).

Documentation in `docs/` is built with Zensical. Preview it with:

```powershell
uv run --only-group docs zensical serve
```

The [API reference](https://contextsage.readthedocs.io/en/latest/reference/)
is generated from the source docstrings. After changing a public signature or
docstring, regenerate it and commit the result:

```powershell
uv run python scripts\generate_api_reference.py
```

The documentation test suite compiles code snippets, runs snippets with
documented output, validates local links and checks the skill distribution.
Examples are embedded from `examples/` and their recorded output fixtures.
Edit Mermaid sources in `diagrams/`, render them with
`node scripts/render_diagrams.mjs`, and commit their PNGs and manifest.

## Pull requests

1. Branch from `master` and keep the change focused.
2. Update relevant tests, examples, documentation and the unreleased
   [changelog](https://github.com/smuniharish/contextsage/blob/master/CHANGELOG.md) entry.
3. Run the applicable checks above and describe the results in the pull
   request.

## Release

Releases are performed manually by a maintainer. Update the version in
`pyproject.toml` and the skill metadata, and record the actual changes in
`CHANGELOG.md`. Review the release commit and run the applicable checks
before publishing.

Build both the source distribution and wheel into an empty `dist` directory:

```powershell
uv build --no-sources
uvx twine check --strict dist/*
```

Inspect the filenames and contents before uploading. For example, with the
intended version substituted for `VERSION`:

```powershell
python -m zipfile -l dist\contextsage-VERSION-py3-none-any.whl
python -m tarfile -l dist\contextsage-VERSION.tar.gz
python -c "import zipfile; z=zipfile.ZipFile(r'dist\contextsage-VERSION-py3-none-any.whl'); print(z.read(next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))).decode())"
```

Once the maintainer has approved the artifacts, publish them explicitly with
`uvx twine upload dist/*` using PyPI's supported credentials. Keep credentials
out of the repository and shell history. Create the corresponding tag and
GitHub release manually after verifying the published version; no workflow
publishes packages or creates releases automatically.
