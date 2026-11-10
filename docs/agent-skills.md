# Agent Skills

ContextSage publishes two [Agent Skills](https://agentskills.io/specification)
for coding agents. They provide focused, source-checked guidance and do not
change the Python package's behavior.

| Skill | Purpose |
| --- | --- |
| [`contextsage`](https://github.com/smuniharish/contextsage/tree/master/contextsage-skills/skills/contextsage) | Integrate, configure and test ContextSage in an agent |
| [`contextsage-extend`](https://github.com/smuniharish/contextsage/tree/master/contextsage-skills/skills/contextsage-extend) | Implement adapters and customize ContextSage, parsefabric and agxai components |

## Install with the skills CLI

Install both:

```bash
npx skills add smuniharish/contextsage
```

Install a single skill:

```bash
npx skills add smuniharish/contextsage --skill contextsage
npx skills add smuniharish/contextsage --skill contextsage-extend
```

The CLI discovers the skills through the repository's `skills.sh.json`.
Alternatively, copy the complete skill directory, including `SKILL.md`, into
the skill location documented by your agent.

## Maintain and verify

The canonical skill sources are in
[`contextsage-skills/`](https://github.com/smuniharish/contextsage/tree/master/contextsage-skills).
Update the relevant skill
when public behavior changes, and validate it with the procedure in
[`contextsage-skills/validation/README.md`](https://github.com/smuniharish/contextsage/blob/master/contextsage-skills/validation/README.md).
