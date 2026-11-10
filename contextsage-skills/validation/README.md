# Validating the ContextSage skills

The `contextsage` and `contextsage-extend` skills are checked for structure,
links and alignment with the package API.

## Automated checks

From the repository root, install all development dependencies and run:

```powershell
uv sync --locked --all-extras --all-groups
uv run pytest tests\docs\test_agent_skill.py tests\docs\test_docs.py -q --no-cov
```

The checks verify that:

- both skill directories contain a `SKILL.md`;
- frontmatter names, descriptions, license and skill version are valid;
- the skill version matches the package version;
- each skill includes its required workflow and verification guidance;
- local links resolve, and the repository manifest discovers the skills.

Use the skills reference validator for an independent format check:

```powershell
uvx --from skills-ref agentskills validate contextsage-skills\skills\contextsage
uvx --from skills-ref agentskills validate contextsage-skills\skills\contextsage-extend
```

## Source review

Validate claims against the implementation and documentation:

| Claim area | Source of truth |
| --- | --- |
| Public names and version | [`src/contextsage/__init__.py`](../../src/contextsage/__init__.py) and [`pyproject.toml`](../../pyproject.toml) |
| Engine arguments and behavior | [`src/contextsage/engine.py`](../../src/contextsage/engine.py) |
| Extension ABCs and parse options | [`src/contextsage/contracts.py`](../../src/contextsage/contracts.py) and [`src/contextsage/parsing.py`](../../src/contextsage/parsing.py) |
| Framework adapter | [`src/contextsage/integrations/langchain/__init__.py`](../../src/contextsage/integrations/langchain/__init__.py) and [`examples/custom_framework.py`](../../examples/custom_framework.py) |
| agxai components | [`src/contextsage/provenance.py`](../../src/contextsage/provenance.py) and [`examples/downstream_customization.py`](../../examples/downstream_customization.py) |
| Runnable behavior | [`examples/`](../../examples/) and [`tests/`](../../tests/) |

If a behavior is not implemented or tested, leave it out of the skills.
