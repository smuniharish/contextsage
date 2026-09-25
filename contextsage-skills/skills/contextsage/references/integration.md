# Verified integration workflows

These workflows use the package's only public import:

```python
from contextsage import IntelligentSummarizationMiddleware
```

The full constructor contract is in
[Configuration - ContextSage](https://contextsage.readthedocs.io/en/latest/configuration/).
Do not import internal engines from `contextsage.*` for normal application
integration.

## Install

Install the published package:

```bash
pip install contextsage
```

For this repository's live network-backed examples, install the `examples`
extra and follow the key setup in the
[repository README](https://github.com/smuniharish/contextsage/blob/master/README.md).
Do not add an API key to source control or copy that live-example setup into
a production application without its own secret-management process.

The complete published documentation is at
[contextsage.readthedocs.io](https://contextsage.readthedocs.io/en/latest/).
The current example collection is at
[github.com/smuniharish/contextsage/tree/master/examples](https://github.com/smuniharish/contextsage/tree/master/examples);
use the local links below when working from a checkout.

## LangChain/LangGraph agent

This is the verified primary pattern, adapted from the
[compiled-agent example](https://github.com/smuniharish/contextsage/blob/master/examples/agent_create_agent.py):

```python
from langchain.agents import create_agent
from contextsage import IntelligentSummarizationMiddleware

middleware = IntelligentSummarizationMiddleware(
    model=model,
    trigger=("tokens", 100_000),
    keep=("messages", 20),
)

agent = create_agent(
    model=model,
    tools=tools,
    middleware=[middleware],
)
```

`model` accepts a LangChain `BaseChatModel` or a model string resolved by
LangChain. Use thresholds derived from the application's model context
window, output reservation, and observed message sizes—not the illustrative
values above.

ContextSage supports `trigger=("tokens", integer)`,
`("messages", integer)`, `("fraction", float)`, and `None`. With `None`,
its budget analyzer triggers only when the message context would not fit.
`keep` accepts the LangGraph context-size forms documented in
[Configuration - ContextSage](https://contextsage.readthedocs.io/en/latest/configuration/).

## Supported example integrations

Use a repository example as the starting point for the matching workload:

| Need | Authoritative example |
| --- | --- |
| Minimal direct middleware behavior | [basic.py](https://github.com/smuniharish/contextsage/blob/master/examples/basic.py) |
| Compiled `create_agent` agent | [agent_create_agent.py](https://github.com/smuniharish/contextsage/blob/master/examples/agent_create_agent.py) |
| Large JSON plus logs from a tool | [large_tool_output.py](https://github.com/smuniharish/contextsage/blob/master/examples/large_tool_output.py) |
| Mixed MCP-style prose, JSON, logs, and code | [mixed_mcp_output.py](https://github.com/smuniharish/contextsage/blob/master/examples/mixed_mcp_output.py) |
| Repetitive logs with trace/root-cause preservation | [logs.py](https://github.com/smuniharish/contextsage/blob/master/examples/logs.py) |
| Structured JSON compaction | [structured_data.py](https://github.com/smuniharish/contextsage/blob/master/examples/structured_data.py) |
| Conflicting retrieval evidence | [rag.py](https://github.com/smuniharish/contextsage/blob/master/examples/rag.py) |
| Failure recovery | [recovery.py](https://github.com/smuniharish/contextsage/blob/master/examples/recovery.py) |
| Deep agent | [deep_agent.py](https://github.com/smuniharish/contextsage/blob/master/examples/deep_agent.py) |
| LangGraph swarm | [swarm.py](https://github.com/smuniharish/contextsage/blob/master/examples/swarm.py) |

`deepagents` and `langgraph-swarm` are example-only dependencies, not core
ContextSage integrations. Confirm an application's own dependency versions
before adopting those examples.

## Middleware ordering

Preserve the existing order unless a test and the host middleware
documentation establish an intended change. ContextSage is itself the
summarization middleware for its agent; do not silently combine it with
LangGraph's standard `SummarizationMiddleware`.

When an agent has tools, retain the normal AI tool-call and `ToolMessage`
result sequence. ContextSage explicitly validates that pairing after a
summarization operation.
