# Configuration

All configuration is passed to the `IntelligentSummarizationMiddleware`
constructor. There are no separate registration calls, plugin classes, or
config files required.

```python
from contextiq import IntelligentSummarizationMiddleware

middleware = IntelligentSummarizationMiddleware(
    model=model,
    trigger=("tokens", 100_000),
    keep=("messages", 20),
    policy="balanced",
    safety_margin=0.10,
    validation_enabled=True,
    observability_enabled=True,
)
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `model` | `str` or `BaseChatModel` | required | The model used both for LangGraph's semantic summarization step and (unless overridden) for token counting. A string is resolved via `langchain.chat_models.init_chat_model`. |
| `trigger` | `("tokens", int)` or `("messages", int)` or `("fraction", float)` or `None` | `None` | When summarization should be considered. `None` falls back to the budget analyzer's own overflow detection (i.e. "whenever the context would not fit"). |
| `keep` | `("messages", int)` or `("tokens", int)` or `("fraction", float)` | `("messages", 20)` | Forwarded to LangGraph's `SummarizationMiddleware` — how much of the tail of the conversation must remain unsummarized. |
| `policy` | `"balanced"` or `"maximum_preservation"` or `"maximum_compression"` | `"balanced"` | Adjusts how aggressively the planner targets units for compression vs. leaving them untouched. |
| `maximum_context_tokens` | `int` or `None` | inferred from the model | Overrides automatic model-context-window inference. |
| `reserved_output_tokens` | `int` | `4000` | Tokens reserved for the model's own response, subtracted from the available budget. |
| `safety_margin` | `float` | `0.10` | Fraction of the context window held back as a safety buffer. |
| `summarization_overhead_tokens` | `int` | `2000` | Tokens reserved for the summarization call's own prompt/response overhead, subtracted from the available budget alongside `reserved_output_tokens` and the safety margin. |
| `validation_enabled` | `bool` | `True` | Whether `SummaryValidator` runs after each summarization. Disabling it disables the recovery loop too — not recommended in production. |
| `observability_enabled` | `bool` | `True` | Whether a default `LoggingObservabilityHook` is attached (ignored if `observability_hook` is provided). |
| `observability_hook` | `ObservabilityHook` or `None` | `None` | Supply a custom hook (e.g. to forward events to your own telemetry system) instead of the default logger. |
| `provenance_enabled` | `bool` | `True` | Whether `langgraph-xai` provenance recording is attempted (best-effort; failures never abort summarization). |
| `token_counter` | `TokenCounter` or `None` | inferred | Override token counting (e.g. to force `tiktoken`-based counting). See [`contextiq.budget.tokens`](api-reference.md#token-counting). |
| `parsers` | `Sequence[ContentParser]` or `None` | `None` | Custom structural-content detectors (e.g. a protobuf/SQL parser) tried, in order, *before* the built-in JSON/table/code/log/error parsers — so a custom parser overrides detection for its kind while every other kind still falls back to the built-ins. See [Structural content parsers](api-reference.md#structural-content-parsers). |
| `severity_pattern` | `re.Pattern[str]` or `None` | `None` | Overrides how log/error severity (`DEBUG`/`INFO`/`ERROR`/...) is recognized. A classification-layer concern, distinct from `parsers` — applies uniformly to every detected content kind. Defaults to `contextiq.classification.signals.DEFAULT_SEVERITY_PATTERN`. |
| `error_keywords_pattern` | `re.Pattern[str]` or `None` | `None` | Overrides which keywords mark a region as an error for preservation purposes (e.g. an application's own incident vocabulary). Defaults to `contextiq.classification.signals.DEFAULT_ERROR_KEYWORDS_PATTERN`. |
| `identifier_patterns` | `Sequence[re.Pattern[str]]` or `None` | `None` | Overrides which substrings are extracted as must-preserve identifiers (e.g. an application's own ticket/order-ID format). Defaults to `contextiq.classification.signals.DEFAULT_IDENTIFIER_PATTERNS`. |
| `summary_prompt` | `str` or `None` | LangGraph's default | Forwarded to LangGraph's `SummarizationMiddleware`. |
| `trim_tokens_to_summarize` | `int` or `None` | `4000` | Forwarded to LangGraph's `SummarizationMiddleware`; caps how much is sent to the LLM in one summarization call. |

## Policies

- **`balanced`** (default): the planner targets units for deterministic
  compression when they are classified `COMPRESSIBLE` or `REDUNDANT`, and
  protects `MUST_PRESERVE`/`SHOULD_PRESERVE` units.
- **`maximum_preservation`**: raises the bar for what counts as a
  compression candidate — prefers `preserve_untouched` outcomes when in
  doubt.
- **`maximum_compression`**: lowers the bar — treats `SHOULD_PRESERVE` units
  as compression candidates too, while `MUST_PRESERVE` units (user
  corrections, active constraints, critical identifiers tied to errors,
  etc.) are still never candidates for destructive compression.
