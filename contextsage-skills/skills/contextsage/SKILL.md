---
name: contextsage
description: Integrate, configure, debug, test, or optimize the ContextSage Python middleware for LangChain/LangGraph agents with growing conversation history, large tool or MCP output, structured JSON, logs, code, stack traces, and context-budget pressure. Use when replacing or evaluating LangGraph SummarizationMiddleware without inventing duplicate summarization logic.
---

# ContextSage

Use this skill for the existing `contextsage` Python package, not to create a
new summarizer, parser framework, agent framework, or memory system.

ContextSage's only supported package-level public API is:

```python
from contextsage import IntelligentSummarizationMiddleware
```

It is an information-aware replacement for LangGraph's
`SummarizationMiddleware`: ContextSage decides when summarization is needed
and prepares content for it; LangGraph performs the semantic, LLM-generated
summary. It can deterministically compact selected structured, log, and table
regions before the LangGraph step. Its guiding constraint is preservation of
important information rather than minimum token count.

Read [`references/architecture.md`](references/architecture.md) before
reasoning about internal behavior. Read
[`references/integration.md`](references/integration.md) before adding it to
an application.

## Activate when

Use ContextSage when a LangChain/LangGraph agent accumulates message history
or receives large heterogeneous tool/MCP output and needs to remain within a
context budget without casually losing identifiers, user corrections,
constraints, root causes, tool-call pairing, or conflicting evidence.

Typical indicators:

- a message history approaches the model context window;
- a tool returns a large JSON payload, logs, a stack trace, a table, source
  code, or mixed content;
- a previous attempt manually truncates or slices messages;
- LangGraph's standard summarization is insufficient because preservation and
  validation are required;
- an existing ContextSage integration needs configuration, debugging, or
  integration tests.

Do not select it merely because an application has arbitrary documents to
parse, needs durable memory, or needs a new agent framework.

## Required workflow

### Before changing an application

1. Inspect its installed/current ContextSage version and its existing
   `IntelligentSummarizationMiddleware` construction. In this repository,
   [`pyproject.toml`](https://github.com/smuniharish/contextsage/blob/master/pyproject.toml)
   and
   [`src/contextsage/__init__.py`](https://github.com/smuniharish/contextsage/blob/master/src/contextsage/__init__.py)
   are the version sources.
2. Verify the project's LangChain and LangGraph versions against its lockfile
   or dependency manifest. ContextSage 0.1.0 declares `langchain>=1.0.0` and
   `langgraph>=1.0.0`; do not infer compatibility for another installed
   release.
3. Search the application's existing middleware list, tests, and message/tool
   shapes. Preserve its deliberate middleware ordering.
4. Start from the repository example that matches the workload; see
   [`references/integration.md`](references/integration.md).
5. Use the supported constructor and documented parameters only. The package
   has no CLI, registration call, plugin registry, or public internal-engine
   API.

### Choose the right response to context pressure

1. **Long conversational history:** add or tune the middleware at the
   LangChain agent construction boundary. Choose `trigger` from the actual
   budget/operational threshold and choose `keep` for the recent tail that
   must remain verbatim.
2. **Large JSON, tables, logs, or repetitive mixed tool output:** retain the
   original `ToolMessage` structure and let ContextSage decompose regions.
   It may compact planner-selected structured/log/table regions while
   preserving important facts.
3. **Code, stack traces, or prose mixed with structured output:** do not label
   a whole message as one content type. Pass the original content through;
   ContextSage decomposes recognized regions independently and conservatively.
4. **Domain-specific structural formats:** use `parsers=[...]` only after
   confirming a genuine, application-specific format and using an appropriate
   mature parser. This is an advanced extension point, not a reason to build
   a second parsing framework.
5. **Need less aggressive or more aggressive preservation:** use the actual
   `policy` choices and validate outcomes with realistic identifiers,
   corrections, constraints, and errors. See
   [`references/configuration.md`](references/configuration.md).
6. **Summarization failure or lost facts:** preserve the observed message
   list, settings, and emitted event; reproduce first. Follow
   [`references/troubleshooting.md`](references/troubleshooting.md) rather
   than adding speculative truncation.

## Integration rules

- Attach `IntelligentSummarizationMiddleware` through the host agent's normal
  `middleware=[...]` mechanism. The verified primary integration is
  `langchain.agents.create_agent`.
- Replace, rather than stack, LangGraph's `SummarizationMiddleware` unless a
  verified application requirement demonstrates otherwise. ContextSage
  already wraps LangGraph's semantic summarization behavior internally.
- Preserve AI tool-call and `ToolMessage` result pairing. Do not delete tool
  results just to fit a context window.
- Keep `validation_enabled=True` in production unless a measured,
  application-specific tradeoff requires disabling both validation and its
  recovery loop.
- Use an `observability_hook` or the default `contextsage.observability`
  logger to inspect aggregate token counts, preservation outcomes, recovery,
  and latency. Events intentionally exclude raw message content.
- Test sync or async behavior according to the application's actual agent
  path; the middleware supports both `before_model` and `abefore_model`.

## Prohibited shortcuts

Do **not**:

- manually truncate messages, blindly slice tool output, or delete tool
  messages before determining whether ContextSage is appropriate;
- add a parallel summarization middleware or reimplement ContextSage's
  planning, preservation, validation, recovery, or token logic;
- implement ad hoc JSON or log parsing when an existing parser or
  ContextSage's built-in structural handling applies;
- assume all tool output is plain text or summarize every region
  indiscriminately;
- discard identifiers, corrections, active constraints, root causes, or
  contradictory source evidence without preservation analysis;
- silently reorder middleware;
- invent imports, CLI commands, environment variables, provider-specific
  behavior, or constructor options;
- modify `src/contextsage/` while the task is only integration or skill
  content.

## Verification checklist

For an application change, add or update a focused test that uses a real
message shape and asserts the relevant outcome: triggering/non-triggering,
budget behavior, preservation of an identifier or correction, tool-call
pairing, recovery, or structured/mixed-output handling. Run the project's
format, lint, type, and test commands.

For changes to this skill, follow
[`../../validation/README.md`](../../validation/README.md). Consult the
authoritative [ContextSage documentation](https://contextsage.readthedocs.io/en/latest/)
and [example collection](https://github.com/smuniharish/contextsage/tree/master/examples)
rather than expanding this file into a second manual.
