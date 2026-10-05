# contextsage Agent Skill validation

This directory documents how the canonical skill is validated. It is not a
second test suite for the library.

The [Agent Skills specification](https://agentskills.io/specification)
defines the required frontmatter. Validation combines automated structural
checks with a review of every claim against its source.

## Automated checks

`tests/docs/test_agent_skill.py` runs with the test suite and checks that:

1. [`../skills/contextsage/SKILL.md`](../skills/contextsage/SKILL.md) exists
   and starts with YAML frontmatter that contains only `name` and
   `description`.
2. `name` is exactly `contextsage`, the directory name, and satisfies the
   specification: 1 to 64 lowercase letters, digits and single hyphens, not
   starting or ending with a hyphen.
3. `description` is 1 to 1,024 characters long and says both what the skill
   does and when to use it.
4. The skill body stays under 500 lines, as the specification recommends, and
   has the activation, workflow, rules, shortcuts and verification sections.
5. The distribution contains exactly one skill directory.

`tests/docs/test_docs.py` also runs the Python example in `SKILL.md`, compares
its output with the documented output, and checks that every link in this
distribution resolves.

The reference validator from the specification gives an independent check. It
is installed from its repository:

```bash
uvx --from "git+https://github.com/agentskills/agentskills#subdirectory=skills-ref" \
  skills-ref validate contextsage-skills/skills/contextsage
```

## Source review

Review every code snippet and factual claim against its source:

| Claim area | Source of truth |
| --- | --- |
| Public imports and version | [`src/contextsage/__init__.py`](../../src/contextsage/__init__.py) and [`pyproject.toml`](../../pyproject.toml) |
| Arguments, defaults and errors | [`src/contextsage/middleware.py`](../../src/contextsage/middleware.py) and [`src/contextsage/errors.py`](../../src/contextsage/errors.py) |
| Events and statuses | [`src/contextsage/events.py`](../../src/contextsage/events.py) |
| Integrations with Deep Agents and LangGraph Swarm | [`examples/deep_agent.py`](../../examples/deep_agent.py) and [`examples/swarm.py`](../../examples/swarm.py) |
| Executable workflows | [`examples/`](../../examples/) and [`tests/`](../../tests/) |

If a behavior has no implementation, test or documentation, leave it out of
the skill rather than infer an API.

## Agent-task matrix

Review the skill against these tasks after every change:

| Task | Activates | Grounded route | Avoids |
| --- | --- | --- | --- |
| "Our agent hits the context limit; add summarization." | Yes | `IntelligentSummarizationMiddleware` in `create_agent(middleware=[...])` | Writing a custom summarizer |
| "Replace SummarizationMiddleware in our agent." | Yes | Same arguments on `IntelligentSummarizationMiddleware` | Running both middleware |
| "Summaries keep losing our ticket IDs." | Yes | `identifier_patterns=[*DEFAULT_IDENTIFIER_PATTERNS, ...]` with validation on | Turning validation off |
| "Our deep agent's summaries drop the error details." | Yes | Exclude Deep Agents' `SummarizationMiddleware` with a harness profile, then add ContextSage | Stacking two summarizers |
| "Alert when summarization fails in production." | Yes | `observability_hook` with status-labelled metrics | Logging message content |
| "Trace which messages a summary came from." | Yes | `provenance_store` and `alineage` | Rebuilding lineage by hand |
| "Search our past conversations." | No | Explain that ContextSage summarizes an agent's live history; it is not a memory or retrieval system | Inventing memory APIs |

## Repository checks

Skill-only changes should pass the automated checks above and a review of the
diff. If library code changes too, run the checks in
[CONTRIBUTING.md](../../CONTRIBUTING.md).
