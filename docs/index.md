# ContextSage

**Information-aware context summarization for LangChain and LangGraph agents.
Large tool outputs shrink without losing their signal, and the facts that
matter survive every summary.**

ContextSage replaces LangChain's `SummarizationMiddleware`. Before a model
call, it reads the conversation the way an engineer would. It parses every
message into prose, JSON, logs, tables, code and stack traces with
[parsefabric](https://pypi.org/project/parsefabric/), decides what must
survive, and compacts repetitive structured content. LangChain then writes the
summary. Finally, ContextSage checks that every critical fact survived,
restates any that did not, and links the summary to the messages it replaced.

<div class="grid cards" markdown>

-   :material-arrow-collapse-vertical:{ .lg .middle } **Compacts structured content**

    ---

    Repeated log lines collapse into one marker naming the omitted lines,
    identical JSON records into counted entries and duplicate table rows into
    one. Warnings, errors and identifiers stay.

-   :material-shield-check-outline:{ .lg .middle } **Keeps what matters**

    ---

    User corrections, standing instructions, identifiers tied to failures and
    conflicting evidence become facts that every rewritten history must
    contain.

-   :material-check-decagram-outline:{ .lg .middle } **Verifies every summary**

    ---

    Facts the summary model dropped are restated verbatim inside the summary,
    and tool results never lose the tool call they answer.

-   :material-lifebuoy:{ .lg .middle } **Survives model failures**

    ---

    When the summary model fails, the history is trimmed with LangChain's
    `trim_messages`, with a notice that restates the latest request and the
    lost facts.

-   :material-source-branch:{ .lg .middle } **Traceable**

    ---

    Every summary is linked to the messages it replaced in a
    [langgraph-xai](https://pypi.org/project/langgraph-xai/) provenance store,
    across summaries of summaries.

-   :material-chart-timeline-variant:{ .lg .middle } **Observable**

    ---

    Every rewrite emits one content-free `SummarizationEvent` to the
    `contextsage` logger and to your hook.

</div>

## A first look

A tool result holds 50 routine log lines and an error. Before the agent's next
model call, ContextSage compacts it; here the middleware runs with a scripted
model, exactly as the agent would run it:

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

The routine lines collapsed into one marker that names the omitted lines,
while the error and the order ID stayed as they were. In a longer history,
LangChain then summarizes the older messages, and ContextSage checks that the
facts that matter, such as `ORD-5521`, survived the summary. The
[quickstart](getting-started/quickstart.md) runs the whole cycle in an agent.

## How it fits together

<figure class="diagram" markdown="span">
  ![An agent calls ContextSage before each model call. The middleware checks the trigger and budget, analyzes and compacts the history, has LangChain summarize older messages, and validates the result. It returns the rewritten history and records provenance links and an event.](assets/diagrams/architecture.png){ width="720" }
  <figcaption>ContextSage runs before each model call and returns the
  rewritten history. Provenance links and an event record every
  rewrite.</figcaption>
</figure>

## Next steps

<div class="grid cards" markdown>

-   :material-download-outline: **[Installation](getting-started/installation.md)**

    Install the package and prepare the code-detection grammars.

-   :material-rocket-launch-outline: **[Quickstart](getting-started/quickstart.md)**

    Add ContextSage to an agent and read what it did.

-   :material-book-open-variant: **[User guide](guide/how-it-works.md)**

    Learn how analysis, compaction, validation and recovery work.

-   :material-code-braces: **[API reference](reference/index.md)**

    The public classes, generated from the source.

</div>
