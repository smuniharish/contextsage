# Quickstart

ContextSage accepts framework-neutral `Message` objects and an asynchronous
`parsefabric.LanguageModel`. The history below uses a scripted model so it
runs offline and prints stable output.

## Run the example

From the repository root:

```powershell
uv sync --locked --all-extras --all-groups
uv run python examples\quickstart.py
```

The script is also included below:

```python
--8<--
examples/quickstart.py
--8<--
```

Expected output:

```text
--8<-- "examples/expected/quickstart.txt"
```

## Connect your framework

Before each model call, convert the framework history to
`contextsage.Message`, then apply a result only when the engine returns one:

```python
async def update_history(summarizer, messages, thread_id):
    result = await summarizer.summarize(messages, thread_id=thread_id)
    if result is not None:
        messages = list(result.messages)
    return messages
```

The trigger defaults to the configured token budget. Set
`trigger=("tokens", n)` or `trigger=("messages", n)` to choose another
threshold. `keep=("messages", n)` retains the most recent messages outside
the summary window. See [configuration](../guide/configuration.md) and the
[custom framework adapter](../guide/integrations.md#custom-frameworks).

## Use LangChain

Install `contextsage[langchain]` and add
`IntelligentSummarizationMiddleware` from
`contextsage.integrations.langchain` to a LangChain agent. The integration
adapts native messages, model calls and token counting to the same core
engine. See the [LangChain guide](../guide/integrations.md#langchain).
