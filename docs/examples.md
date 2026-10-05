# Examples

Every example is a short, runnable script from the
[`examples/`](https://github.com/smuniharish/contextsage/tree/master/examples)
directory. The offline examples use scripted chat models, so they run without
network access or API keys, and the output shown is the recorded output that
the test suite checks on every change.

To run them, clone the repository and use [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run python examples/quickstart.py
```

The scripts share two small helpers from
[`examples/_models.py`](https://github.com/smuniharish/contextsage/blob/master/examples/_models.py):
`scripted_model`, a LangChain `GenericFakeChatModel` that answers with fixed
replies, and `live_model`, which builds a `ChatOpenAI` model from environment
variables.

## Getting started

### Quickstart

A `create_agent` agent whose history triggers compaction, a summary and
validation in one turn.

=== "quickstart.py"

    ```python
    --8<--
    examples/quickstart.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/quickstart.txt"
    ```

### Large tool output

A mixed MCP-style tool result: repeated log lines and JSON records collapse,
while every distinct line, warning, error and identifier stays.

=== "large_tool_output.py"

    ```python
    --8<--
    examples/large_tool_output.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/large_tool_output.txt"
    ```

## Preservation

### Restated facts

A vague summary loses a standing instruction, identifiers, a correction and a
conflict; ContextSage restates them.

=== "preservation.py"

    ```python
    --8<--
    examples/preservation.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/preservation.txt"
    ```

### Policies

One JSON payload under the three preservation policies.

=== "policies.py"

    ```python
    --8<--
    examples/policies.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/policies.txt"
    ```

### Recovery

The summary model fails, and the agent continues on a trimmed history.

=== "recovery.py"

    ```python
    --8<--
    examples/recovery.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/recovery.txt"
    ```

## Parsing, provenance and observability

### Custom parsing

A parsefabric parser, built on sqlglot, teaches ContextSage to recognize SQL.

=== "custom_parsing.py"

    ```python
    --8<--
    examples/custom_parsing.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/custom_parsing.txt"
    ```

### Provenance

The lineage of a summary of a summary, back to the original messages.

=== "provenance.py"

    ```python
    --8<--
    examples/provenance.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/provenance.txt"
    ```

### Logs and a hook

The structured event behind every summarization.

=== "observability.py"

    ```python
    --8<--
    examples/observability.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/observability.txt"
    ```

### Prometheus metrics

Events exported as Prometheus metrics, with a matching
[scrape configuration](https://github.com/smuniharish/contextsage/blob/master/examples/observability_prometheus.yml).

=== "observability_prometheus.py"

    ```python
    --8<--
    examples/observability_prometheus.py
    --8<--
    ```

=== "Output"

    ```text
    --8<-- "examples/expected/observability_prometheus.txt"
    ```

## With a live model

These examples call a real model through any OpenAI-compatible chat
completions endpoint. Set `CONTEXTSAGE_LLM_API_KEY`, and optionally
`CONTEXTSAGE_LLM_BASE_URL` and `CONTEXTSAGE_LLM_MODEL`, in the environment or
in a `.env` file; the
[examples README](https://github.com/smuniharish/contextsage/blob/master/examples/README.md)
describes them. Their output depends on the model, so it is not recorded.

### Agent with a large tool result

=== "live_agent.py"

    ```python
    --8<--
    examples/live_agent.py
    --8<--
    ```

### Deep agent

=== "deep_agent.py"

    ```python
    --8<--
    examples/deep_agent.py
    --8<--
    ```

### Swarm

=== "swarm.py"

    ```python
    --8<--
    examples/swarm.py
    --8<--
    ```
