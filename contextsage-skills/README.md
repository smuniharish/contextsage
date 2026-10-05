# contextsage Agent Skills

This directory is the canonical Agent Skills distribution for `contextsage`.
It contains procedural guidance for coding agents that integrate, configure,
test or debug the existing `contextsage` package.

It is not a Python package and does not add runtime behavior.

| Component | Location | Purpose |
| --- | --- | --- |
| contextsage library | [`src/contextsage/`](../src/contextsage/) | The published Python package and its public API |
| contextsage Agent Skill | [`skills/contextsage/`](skills/contextsage/) | Canonical guidance for integrating and operating the library |
| Skill validation | [`validation/`](validation/) | Validation procedure and agent-task matrix |

## Agent Skills format

The skill follows the
[Agent Skills specification](https://agentskills.io/specification): a
directory with a `SKILL.md` file whose YAML frontmatter holds the required
`name` and `description`. The `name`, `contextsage`, matches the directory
name, and only the required frontmatter fields are used, for portability.

Compatible agents load [`skills/contextsage/SKILL.md`](skills/contextsage/SKILL.md)
when a task involves summarizing a LangChain agent's history with ContextSage.
The skill links to the authoritative documentation and examples instead of
keeping a second copy of them.

There are no host-specific copies of the skill; every compatible host reads
the same `SKILL.md`. Installation instructions for Claude Code, Codex, Cursor,
GitHub Copilot and other hosts are in the
[Agent Skills guide](https://contextsage.readthedocs.io/en/latest/agent-skills/).

## Maintaining the distribution

When the public API, the supported workflows or documented behavior change:

1. Update the skill, limited to the verified change.
2. Link to the corresponding documentation, examples or tests instead of
   duplicating them.
3. Run the process in [`validation/README.md`](validation/README.md).
4. Do not add host-specific copies of the skill text.

The distribution is covered by the repository's Apache License 2.0; see
[LICENSE](../LICENSE).
