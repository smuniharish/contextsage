# Installation

ContextSage requires Python 3.12 or newer. Install it from PyPI:

=== "pip"

    ```bash
    pip install contextsage
    ```

=== "uv"

    ```bash
    uv add contextsage
    ```

Check the installation:

```python
import contextsage

print(contextsage.__version__)
```

Output:

```text
1.0.0
```

## What gets installed

ContextSage builds on established libraries instead of reimplementing them:

| Package | What ContextSage uses it for |
| --- | --- |
| [langchain](https://pypi.org/project/langchain/) | The agent middleware interface, `SummarizationMiddleware`, which writes every summary, and model-aware token counting |
| [langchain-core](https://pypi.org/project/langchain-core/) | Messages, chat models and `trim_messages`, used by the fallback |
| [langgraph](https://pypi.org/project/langgraph/) | The runtime and the state updates that replace the history |
| [langgraph-xai](https://pypi.org/project/langgraph-xai/) | The provenance store that links each summary to its sources |
| [parsefabric](https://pypi.org/project/parsefabric/) | Parsing each message into prose, JSON, logs, tables, code and stack traces |

## A chat model for summaries

Summaries are written by any LangChain chat model. Install the integration
for your provider, for example `pip install langchain-openai`, and pass either
a model instance or an
[`init_chat_model`](https://docs.langchain.com/oss/python/langchain/models)
identifier such as `"openai:gpt-5-mini"`. A small, fast model is usually the
right choice for summaries.

## Code-detection grammars

parsefabric recognizes unfenced source code with tree-sitter grammars. By
default it uses these grammars:

```python
from parsefabric.builtins import DEFAULT_CODE_LANGUAGES

print(", ".join(DEFAULT_CODE_LANGUAGES))
```

Output:

```text
python, javascript, typescript, java, go, rust, c, cpp, sql
```

tree-sitter-language-pack downloads a grammar the first time it is needed and
caches it per user, and creating the middleware downloads any grammar that is
missing. On a host without internet access, download the grammars once while
online, for example while building your container image:

```bash
python -c "import tree_sitter_language_pack as t; t.download(['python', 'javascript', 'typescript', 'java', 'go', 'rust', 'c', 'cpp', 'sql'])"
```

If the grammars cannot be loaded, the constructor raises
`contextsage.ConfigurationError` with these instructions. Pass
`code_languages=()` to turn code detection off, or a shorter list to load
fewer grammars; see [Content parsing](../guide/content-parsing.md).

## Next steps

- Follow the [quickstart](quickstart.md) to add ContextSage to an agent.
- To work on ContextSage itself, see [Contributing](../development/contributing.md).
