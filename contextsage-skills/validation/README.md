# ContextSage Agent Skill validation

This directory documents the repeatable validation process for the canonical
skill. It is intentionally not a second runtime test suite and does not
provide a host-specific package.

The Agent Skills specification was checked at
[agentskills.io/specification](https://agentskills.io/specification). It
defines `name` and `description` as the required frontmatter. No official
validator is specified there, so validation combines structural checks with
source-backed content review.

## Structural validation

For every change:

1. Confirm [`../skills/contextsage/SKILL.md`](../skills/contextsage/SKILL.md)
   exists and starts with YAML frontmatter.
2. Confirm `name` is exactly `contextsage` (the directory name), contains
   only lowercase letters and hyphens, and is at most 64 characters.
3. Confirm `description` is non-empty, at most 1024 characters, and states
   both the capability and when to activate it.
4. Confirm only `name` and `description` appear in frontmatter unless the
   current specification and a demonstrated host requirement justify more.
5. Resolve every relative Markdown target in the skill, its references, and
   this directory; no target may point at a deleted file.
6. Confirm the distribution contains one `skills/contextsage/` canonical
   knowledge source and no Claude/Codex/Copilot duplicate.
7. Search the distribution for `agloom`, stale package names, invented CLI
   commands, credentials, and unrelated projects.

## Source-accuracy review

Review every code snippet and factual claim against its source:

| Claim area | Source of truth |
| --- | --- |
| Public import and package version | [`src/contextsage/__init__.py`](https://github.com/smuniharish/contextsage/blob/master/src/contextsage/__init__.py) |
| Constructor signature and middleware hooks | [`src/contextsage/middleware/summarization.py`](https://github.com/smuniharish/contextsage/blob/master/src/contextsage/middleware/summarization.py) |
| Dependencies and supported Python/LangChain/LangGraph floors | [`pyproject.toml`](https://github.com/smuniharish/contextsage/blob/master/pyproject.toml) |
| Public API and configuration | [API Reference - ContextSage](https://contextsage.readthedocs.io/en/latest/api-reference/), [Configuration - ContextSage](https://contextsage.readthedocs.io/en/latest/configuration/) |
| Processing and ownership boundaries | [Architecture - ContextSage](https://contextsage.readthedocs.io/en/latest/architecture/), [Migration Guide - ContextSage](https://contextsage.readthedocs.io/en/latest/migration/) |
| Observability and provenance | [Observability - ContextSage](https://contextsage.readthedocs.io/en/latest/observability/), [Provenance - ContextSage](https://contextsage.readthedocs.io/en/latest/provenance/) |
| Executable workflows | [Examples](https://github.com/smuniharish/contextsage/tree/master/examples) and [tests](https://github.com/smuniharish/contextsage/tree/master/tests) |

If a behavior lacks an implementation, test, or authoritative document, omit
it from the skill rather than infer an API.

## Agent-task matrix

The following matrix was reviewed against the canonical
[`SKILL.md`](../skills/contextsage/SKILL.md), its references, the runtime
implementation, and the linked examples/tests.

| Task | Activates | Grounded route | Avoids |
| --- | --- | --- | --- |
| “Add ContextSage summarization to my LangGraph agent.” | Yes | `references/integration.md` → `create_agent` example and supported public import. | Invented integration API or a second summarizer. |
| “My MCP tool sometimes returns 100K tokens. Help me handle it.” | Yes | Mixed/large tool-output guidance and existing mixed-content examples. | Blind slicing or treating all output as text. |
| “Context is exceeding the model's context window.” | Yes | Budget, trigger, `keep`, and production configuration guidance. | Guessing from characters or ignoring reserved output. |
| “Why did my tool output disappear after summarization?” | Yes | Debug sequence, tool-pairing tests, validation/recovery diagnostics. | Deleting tool messages or speculative changes. |
| “Integrate ContextSage into this existing LangGraph application.” | Yes | Existing middleware-order inspection and verified `create_agent` pattern. | Silent ordering changes. |
| “Debug why ContextSage isn't summarizing.” | Yes | Trigger/budget-first troubleshooting flow and observability events. | Unsupported diagnostics or CLI commands. |
| “Add tests for large mixed tool output.” | Yes | Existing integration/unit tests plus mixed-output examples. | Duplicate runtime parsing/summarization logic. |
| “Configure ContextSage for production.” | Yes | Configuration decision table, validation/recovery, observability, and provenance references. | Undocumented settings or secrets. |

## Repository validation

Skill-only work should at least run the structural/link/source review above and
review the resulting Git diff. If runtime files change, run the CI-equivalent
checks documented in
[CONTRIBUTING.md](https://github.com/smuniharish/contextsage/blob/master/CONTRIBUTING.md).
This distribution must not require a ContextSage runtime change.
