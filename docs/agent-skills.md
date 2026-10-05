# Agent Skills

ContextSage publishes an [Agent Skill](https://agentskills.io/specification)
that teaches AI coding agents to integrate, configure, test and debug the
middleware: when to use it, how to replace existing summarization, which
arguments fit which need, and which shortcuts to avoid. The skill is
documentation for agents; it does not change how ContextSage is installed or
behaves.

| Component | Location |
| --- | --- |
| ContextSage library | [`src/contextsage/`](https://github.com/smuniharish/contextsage/tree/master/src/contextsage) |
| Agent Skill | [`contextsage-skills/skills/contextsage/`](https://github.com/smuniharish/contextsage/tree/master/contextsage-skills/skills/contextsage) |
| Skill instructions | [`SKILL.md`](https://github.com/smuniharish/contextsage/blob/master/contextsage-skills/skills/contextsage/SKILL.md) |

The skill uses only the standard `name` and `description` frontmatter, so one
copy works with every compatible agent.

## Install with the skills CLI

The [skills CLI](https://www.skills.sh/docs/cli) installs a skill directly
from GitHub:

```bash
npx skills add https://github.com/smuniharish/contextsage/tree/master/contextsage-skills/skills/contextsage
```

Follow the CLI's prompts to choose your agent, then check that it placed a
`contextsage` folder in that agent's skills directory.

## Install manually

Copy the complete
[`contextsage` skill directory](https://github.com/smuniharish/contextsage/tree/master/contextsage-skills/skills/contextsage),
including `SKILL.md`, into the location your agent reads.

### Claude Code

| Scope | Destination |
| --- | --- |
| Current repository | `.claude/skills/contextsage/` |
| All local projects | `~/.claude/skills/contextsage/` |

Restart Claude Code after copying the directory. Claude selects the skill when
a task matches its description, or you can invoke it with `/contextsage`. See
[Claude Code skills](https://code.claude.com/docs/en/skills).

### Codex

| Scope | Destination |
| --- | --- |
| Current repository | `.agents/skills/contextsage/` |
| All local projects | `~/.agents/skills/contextsage/` |

Codex picks up new skills automatically; restart it if the skill does not
appear. Invoke it with `$contextsage`, or list skills with `/skills`.

### Cursor

| Scope | Destination |
| --- | --- |
| Current repository | `.agents/skills/contextsage/` or `.cursor/skills/contextsage/` |
| All local projects | `~/.agents/skills/contextsage/` or `~/.cursor/skills/contextsage/` |

Restart Cursor after copying the directory. In Agent chat, type `/` and select
`contextsage`, or let Cursor activate it from its description. See
[Cursor Agent Skills](https://cursor.com/docs/skills).

### GitHub Copilot

| Scope | Destination |
| --- | --- |
| Current repository | `.agents/skills/contextsage/`, `.github/skills/contextsage/` or `.claude/skills/contextsage/` |
| All local projects | `~/.agents/skills/contextsage/` or `~/.copilot/skills/contextsage/` |

In Copilot CLI, start a new session or run `/skills reload`, then check the
skill with `/skills info contextsage`. See
[adding agent skills for GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills).

### Other agents

Copy the complete `contextsage` folder into the skills directory documented by
your agent. No adapter is needed.

## Update and verify

To update a manual installation, replace the installed `contextsage` folder
with the latest version from the repository and restart or reload the agent.

After installing, check that:

1. the directory is named `contextsage` and contains `SKILL.md`,
2. the agent lists `contextsage` among its skills, if it offers a listing, and
3. a task such as "our agent's summaries keep losing ticket IDs; fix the
   summarization" activates the skill, or that you can invoke it explicitly.

The [distribution README](https://github.com/smuniharish/contextsage/blob/master/contextsage-skills/README.md)
and the [validation process](https://github.com/smuniharish/contextsage/blob/master/contextsage-skills/validation/README.md)
describe how the skill is maintained.
