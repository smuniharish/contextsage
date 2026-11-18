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

## Skills from dependencies and integrations

These upstream skills are optional and installed independently. Installing a
skill does not install its Python package or a ContextSage extra. Review the
upstream instructions and your installed package versions before using them.
The skills CLI requires Node.js and supports interactive agent selection;
agxai documents Node.js 22.20 or newer.

| Upstream | Skills | Purpose |
| --- | --- | --- |
| [parsefabric](https://parsefabric.readthedocs.io/en/latest/agent-skills/install/) | `parsefabric`, `parsefabric-extend` | Parsing integrations and custom components |
| [agxai](https://agxai.readthedocs.io/en/latest/agent-skills/) | `agxai`, `agxai-extend` | Provenance and custom stores or integrations |
| [LangChain](https://github.com/langchain-ai/langchain-skills) | `langchain-build-agent`, `langchain-agent-tracing`, `langchain-agent-monitoring`, `langchain-eval-engineering` | Optional LangChain, LangGraph and Deep Agents workflows |
| [tree-sitter language pack](https://github.com/xberg-io/tree-sitter-language-pack/tree/main/skills) | `tree-sitter-language-pack` and focused skills | Code parsing and parser management |

The language pack's focused skills are
`tree-sitter-language-pack-chunking-for-llms`,
`tree-sitter-language-pack-detecting-languages`,
`tree-sitter-language-pack-extracting-code-structure`,
`tree-sitter-language-pack-managing-parsers`,
`tree-sitter-language-pack-parsing-source`, and
`tree-sitter-language-pack-using-the-mcp-server`. Select a skill by name using
the same CLI command shown below.

For example, install the two core dependency skill sets:

```bash
npx skills add smuniharish/parsefabric
npx skills add smuniharish/agxai
```

Install the LangChain skills only if relevant to your integration:

```bash
npx skills add langchain-ai/langchain-skills --skill '*' --yes
```

The LangChain skills-only install does not register its documentation MCP
servers. LangChain describes its skills project as early development; consult
its current documentation for updates and any additional setup.
Its recommended plugin installation also bundles documentation MCP servers;
see the [upstream instructions](https://github.com/langchain-ai/langchain-skills#installation)
for supported agents and migration from older standalone skills.

For code-detection work, install the language-pack skill separately:

```bash
npx skills add xberg-io/tree-sitter-language-pack --skill tree-sitter-language-pack
```

For development tools, [Astral's plugin](https://github.com/astral-sh/agent-plugins)
offers `uv` and `ruff` skills. Its Codex installation is:

```bash
codex plugin marketplace add astral-sh/agent-plugins
codex plugin add astral@astral-sh
```

The transitive Pydantic dependency also provides a
[Pydantic skill](https://github.com/pydantic/skills). Install its Claude Code
plugin when working directly with Pydantic:

```bash
claude plugin marketplace add pydantic/skills
claude plugin install pydantic@pydantic-skills
```

Consult each upstream for supported agents, manual installation and
prerequisites. Neither plugin is required by ContextSage.

No independently installable first-party skills were confirmed for the other
direct dependencies and example tools during this review; check their official
documentation for updates. Third-party skills are not endorsed by this list.

## Maintain and verify

The canonical skill sources are in
[`contextsage-skills/`](https://github.com/smuniharish/contextsage/tree/master/contextsage-skills).
Update the relevant skill
when public behavior changes, and validate it with the procedure in
[`contextsage-skills/validation/README.md`](https://github.com/smuniharish/contextsage/blob/master/contextsage-skills/validation/README.md).
