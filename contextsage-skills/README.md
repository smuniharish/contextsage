# ContextSage Agent Skills

This directory is the canonical Agent Skills distribution for ContextSage. It
contains procedural guidance for coding agents that need to integrate,
configure, test, or debug the existing ContextSage package.

It is not a Python package and does not add runtime behavior.

| Component | Location | Purpose |
| --- | --- | --- |
| ContextSage runtime | [`src/contextsage/`](https://github.com/smuniharish/contextsage/tree/master/src/contextsage) | The published Python package and its supported public API. |
| ContextSage Agent Skill | [`skills/contextsage/`](skills/contextsage/) | Canonical agent-oriented instructions and concise reference material. |
| Skill validation | [`validation/`](validation/) | Validation procedure and realistic activation/task matrix. |

## Agent Skills format

The canonical skill follows the Agent Skills `SKILL.md` format: a
directory-scoped Markdown instruction file with required `name` and
`description` YAML frontmatter. Its `name` matches its containing
directory (`contextsage`), and only the specification's required frontmatter
is used for portability.

Compatible agents should load
[`skills/contextsage/SKILL.md`](skills/contextsage/SKILL.md) when working on
ContextSage integrations, context-budget pressure, or LangGraph agent
summarization. The skill links to the repository's authoritative
[documentation](https://contextsage.readthedocs.io/en/latest/) and
[examples](https://github.com/smuniharish/contextsage/tree/master/examples)
instead of maintaining a second copy of them.

For current skills.sh, Claude Code, Codex, Cursor, GitHub Copilot, and
manual installation instructions, see
[Agent Skills - ContextSage](https://contextsage.readthedocs.io/en/latest/agent-skills/).
This repository intentionally provides no Claude, Codex, or Copilot adapter
because none is required to consume the canonical `SKILL.md`.

## Maintaining the distribution

When ContextSage's public API, supported integrations, or documented behavior
changes:

1. Update the canonical skill and only the reference material affected by
   that verified change.
2. Link to the corresponding implementation, tests, examples, or
   documentation; do not duplicate runtime logic.
3. Run the process in [`validation/README.md`](validation/README.md).
4. Do not add platform-specific copies of the skill text. Add thin metadata
   only when a host's current official documentation demonstrates it is
   required.

The distribution is covered by the repository's Apache License 2.0; see the
[repository license](https://github.com/smuniharish/contextsage/blob/master/LICENSE).
