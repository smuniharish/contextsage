# ContextSage

[![PyPI](https://img.shields.io/pypi/v/contextsage)](https://pypi.org/project/contextsage/)
[![Python](https://img.shields.io/pypi/pyversions/contextsage)](https://pypi.org/project/contextsage/)
[![CI](https://github.com/smuniharish/contextsage/actions/workflows/ci.yml/badge.svg)](https://github.com/smuniharish/contextsage/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/readthedocs/contextsage)](https://contextsage.readthedocs.io/en/latest/)
[![License](https://img.shields.io/pypi/l/contextsage)](https://github.com/smuniharish/contextsage/blob/master/LICENSE)

**Information-aware context summarization for LangChain and LangGraph agents.
Large tool outputs shrink without losing their signal, and the facts that
matter survive every summary.**

Agents accumulate long, mixed context: tool results that combine prose, JSON,
logs and stack traces, user corrections, and IDs the next step depends on.
Summarizing the oldest messages blindly loses exactly those details.
ContextSage replaces LangChain's `SummarizationMiddleware` with a middleware
that understands what it summarizes:

- **Compacts structured content.** Runs of similar log lines, identical JSON
  records and duplicate table rows collapse, while warnings, errors and
  identifiers stay.
- **Keeps what matters.** User corrections, standing instructions, identifiers
  tied to failures and conflicting evidence become facts that every rewritten
  history must contain.
- **Verifies every summary.** Facts the summary model dropped are restated
  verbatim inside the summary, and tool results never lose their tool call.
- **Survives model failures.** If the summary model fails, the agent continues
  on a trimmed history that restates the latest request and the lost facts.
- **Traces every summary** to the messages it replaced, across summaries of
  summaries, in a [langgraph-xai](https://pypi.org/project/langgraph-xai/)
  provenance store.
- **Reports every rewrite** as a content-free event, for logs and metrics.

ContextSage builds on LangChain, which still writes every summary, on
[parsefabric](https://pypi.org/project/parsefabric/), which parses the
content, and on langgraph-xai.

## Installation

```bash
pip install contextsage
```

ContextSage requires Python 3.12 or newer. Summaries are written by any
LangChain chat model; install the integration for your provider, such as
`langchain-openai`.

## Quickstart

Add the middleware to a LangChain agent wherever you would use
`SummarizationMiddleware`:

```python
from langchain.agents import create_agent
from langchain_core.tools import tool

from contextsage import IntelligentSummarizationMiddleware


@tool
def order_status(order_id: str) -> str:
    """Return the status of an order."""
    return f"{order_id}: shipped"


agent = create_agent(
    model="openai:gpt-5",
    tools=[order_status],
    middleware=[
        IntelligentSummarizationMiddleware(
            model="openai:gpt-5-mini",
            trigger=("tokens", 100_000),
            keep=("messages", 20),
        )
    ],
)
```

## See it work

This history holds a tool result of 50 routine log lines and an error. The
middleware runs here with a scripted model, exactly as the agent would run it
before its next model call:

```python
from itertools import cycle

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from contextsage import IntelligentSummarizationMiddleware

log = "".join(f"2026-10-04T08:00:{s:02d}Z INFO heartbeat ok\n" for s in range(50))
log += "2026-10-04T08:00:50Z ERROR payment failed for order ORD-5521"
history = [
    HumanMessage("Why did the payment fail?"),
    AIMessage("", tool_calls=[{"id": "c1", "name": "read_logs", "args": {}}]),
    ToolMessage(log, tool_call_id="c1"),
]
middleware = IntelligentSummarizationMiddleware(
    model=GenericFakeChatModel(messages=cycle([AIMessage("unused")])),
    trigger=("tokens", 500),
)
update = middleware.before_model({"messages": history}, Runtime())
print(update["messages"][-1].text)
```

Output:

```text
2026-10-04T08:00:00Z INFO heartbeat ok
... 48 similar lines omitted (lines 2-49) ...
2026-10-04T08:00:49Z INFO heartbeat ok
2026-10-04T08:00:50Z ERROR payment failed for order ORD-5521
```

The routine lines collapsed into one marker that names the omitted lines; the
error and the order ID stayed as they were. With a longer history, LangChain
would then summarize the older messages, and ContextSage would check that the
order ID survived the summary.

## How it works

![Before each model call, ContextSage checks the trigger and token budget, analyzes and compacts the history, has LangChain summarize older messages, and validates the result. It returns the rewritten history and records provenance links and an event.](https://raw.githubusercontent.com/smuniharish/contextsage/master/docs/assets/diagrams/architecture.png)

1. **Trigger.** Count the history's tokens and stop unless the trigger fires
   or the history exceeds the token budget.
2. **Analyze.** Parse every message into prose, JSON, log, table, code and
   stack-trace units; score them; and derive the facts that must survive.
3. **Compact.** Rewrite repetitive structured content deterministically,
   within what each unit's preservation level allows.
4. **Summarize.** LangChain's `SummarizationMiddleware` summarizes the
   messages older than the `keep` window.
5. **Validate.** Restate missing facts in the summary, link the summary to
   its sources, and emit a `SummarizationEvent`.

## Documentation

The [documentation](https://contextsage.readthedocs.io/en/latest/) covers
[configuration](https://contextsage.readthedocs.io/en/latest/guide/configuration/),
[preservation policies](https://contextsage.readthedocs.io/en/latest/guide/policies/),
[validation and recovery](https://contextsage.readthedocs.io/en/latest/guide/validation-recovery/),
[observability](https://contextsage.readthedocs.io/en/latest/guide/observability/),
[provenance](https://contextsage.readthedocs.io/en/latest/guide/provenance/)
and the [API reference](https://contextsage.readthedocs.io/en/latest/reference/).
[Runnable examples](https://github.com/smuniharish/contextsage/tree/master/examples)
show every feature offline and with Deep Agents and LangGraph Swarm.

An [Agent Skill](https://contextsage.readthedocs.io/en/latest/agent-skills/)
teaches coding agents such as Claude Code, Codex, Cursor and GitHub Copilot to
integrate ContextSage correctly.

## Contributing

Contributions are welcome; see the
[contributing guide](https://github.com/smuniharish/contextsage/blob/master/CONTRIBUTING.md).
This project follows a
[code of conduct](https://github.com/smuniharish/contextsage/blob/master/CODE_OF_CONDUCT.md).
Report security issues privately as described in the
[security policy](https://github.com/smuniharish/contextsage/blob/master/SECURITY.md).

## License

Apache License 2.0; see
[LICENSE](https://github.com/smuniharish/contextsage/blob/master/LICENSE).
