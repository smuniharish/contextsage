# ContextSage Agent Skills

This directory distributes two skills for the ContextSage Python package.
Skills give coding agents procedural guidance; they do not add runtime
behavior.

| Skill | Use |
| --- | --- |
| [`contextsage`](skills/contextsage/SKILL.md) | Integrate, configure, test and debug ContextSage in an agent |
| [`contextsage-extend`](skills/contextsage-extend/SKILL.md) | Implement a framework adapter or customize ContextSage and downstream ABCs |

Both use the [Agent Skills specification](https://agentskills.io/specification)
and are discoverable from the repository's `skills.sh.json`.

## Install

Install both skills with the [skills CLI](https://www.skills.sh/docs/cli):

```bash
npx skills add smuniharish/contextsage
```

Install one skill at a time:

```bash
npx skills add smuniharish/contextsage --skill contextsage
npx skills add smuniharish/contextsage --skill contextsage-extend
```

To install manually, copy the selected skill directory, including
`SKILL.md`, into the skills location used by your agent.

## Maintaining the skills

When the public API or documented behavior changes:

1. Update the skill that covers the affected task.
2. Verify every API claim and code example against source, tests and docs.
3. Keep the two skill descriptions routed to the correct task.
4. Run the validation steps in [`validation/README.md`](validation/README.md).

Do not add host-specific copies; compatible agents should read the same
canonical skill files. The distribution is covered by the Apache License 2.0;
see [`LICENSE`](../LICENSE).
