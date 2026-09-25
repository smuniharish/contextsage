# ContextSage

ContextSage is an intelligent, production-grade replacement for LangGraph's
built-in `SummarizationMiddleware`. It adds an information-aware planning
layer on top of LangGraph/LangChain's existing summarization mechanism.

```python
from langchain.agents import create_agent
from contextsage import IntelligentSummarizationMiddleware

middleware = IntelligentSummarizationMiddleware(
    model=model,
    trigger=("tokens", 100_000),
    keep=("messages", 20),
)

agent = create_agent(model=model, tools=tools, middleware=[middleware])
```

Use the navigation to explore:

- [Architecture](architecture.md) — the full pipeline and design principles.
- [Configuration](configuration.md) — every public constructor parameter.
- [API reference](api-reference.md) — the public surface (intentionally small).
- [Provenance](provenance.md) — how `langgraph-xai` is used.
- [Observability](observability.md) — structured events emitted per operation.
- [Migration](migration.md) — differences from LangGraph's `SummarizationMiddleware`.
- [Agent Skills](agent-skills.md) — install the canonical ContextSage skill in
  Claude Code, Codex, Cursor, GitHub Copilot, and other compatible agents.
