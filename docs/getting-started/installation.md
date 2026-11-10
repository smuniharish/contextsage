# Installation

ContextSage supports Python 3.12 and newer. Install the framework-neutral
core from PyPI:

=== "pip"

    ```bash
    pip install contextsage
    ```

=== "uv"

    ```bash
    uv add contextsage
    ```

The core depends on agxai, OpenTelemetry API, and parsefabric. It does not
install LangChain or another agent framework.

## Optional integrations

Install only the capabilities your application uses:

| Extra | Install | Provides |
| --- | --- | --- |
| `langchain` | `pip install "contextsage[langchain]"` | LangChain and LangGraph adapters, middleware, chat-model bridge and token counter |
| `otel` | `pip install "contextsage[otel]"` | OpenTelemetry SDK and OTLP exporter |
| `all` | `pip install "contextsage[all]"` | Both optional integrations |

The summary model is a `parsefabric.LanguageModel`. Implement that ABC around
your provider's async client, or install the LangChain extra and use
`LangChainSummaryModel`.

## Check the installation

```python
import contextsage

print(contextsage.__version__)
```

Output:

```text
1.0.1
```

## Code detection

The default parser uses parsefabric's shared tree-sitter detector to recognize
unfenced source code. Its grammars are prepared lazily on the first
summarization. To verify availability during application startup:

```python
async def prepare_summarizer(model):
    async with ContextSummarizer(model) as summarizer:
        await summarizer.prepare()
```

`prepare()` raises `ConfigurationError` if the grammar resources cannot be
loaded. For hosts where code detection is unnecessary or unavailable, pass
`ParsingOptions(code_detector=None)` to the summarizer.

## Next steps

- Follow the [quickstart](quickstart.md).
- Configure [parsing and downstream components](../guide/configuration.md).
- See [framework integrations](../guide/integrations.md).
