# Quickstart

## Add ContextSage to an agent

`IntelligentSummarizationMiddleware` is agent middleware. Add it to
`create_agent` wherever you would use LangChain's `SummarizationMiddleware`:

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

- `model` writes the summaries. It can differ from the agent's model.
- `trigger` decides when to summarize: here, once the history reaches 100,000
  tokens. Leave it out to summarize only when the history no longer fits the
  model's context window.
- `keep` is how much recent history stays verbatim: here, the last 20
  messages. Older messages are replaced by the summary.

Everything else has production defaults; see
[Configuration](../guide/configuration.md).

## Watch it work

The quickstart example runs an agent on a history whose large incident report
pushes it past the trigger. It uses scripted models, so it runs offline and
always prints the same output:

```python
--8<--
examples/quickstart.py
--8<--
```

Output:

```text
--8<-- "examples/expected/quickstart.txt"
```

Before the agent's model call, ContextSage:

1. **Checked the trigger.** The history held 3,283 tokens, over the 2,000-token
   trigger.
2. **Analyzed the history.** It parsed each message into content units and
   found two facts that must survive: the incident `INC-9931` and the
   transaction `TX-991`.
3. **Compacted the report.** 200 routine log lines collapsed into a marker
   naming the omitted lines, and 40 identical JSON records into one counted
   entry, bringing the history down to 166 tokens.
4. **Had LangChain summarize** the messages older than the last two.
5. **Validated the result.** Both facts are in the summary, so validation
   passed and nothing had to be restated.

The `SummarizationEvent` passed to `observability_hook` records each of these
numbers, without any message content.

## Next steps

- [How it works](../guide/how-it-works.md) explains each step in detail.
- [Examples](../examples.md) shows compaction, preservation, recovery,
  provenance and observability, offline and with a live model.
- [Agent Skills](../agent-skills.md) teach coding agents to integrate
  ContextSage correctly.
