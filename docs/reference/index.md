# API reference

The public API is exported by the `contextsage` package. Internal names and
modules beginning with `_` are implementation details.

This page is generated from the source by `scripts/generate_api_reference.py`.

## Core engine

### `ContextSummarizer` { #contextsage.ContextSummarizer }

```python
class ContextSummarizer:
    def __init__(
        self,
        model: LanguageModel,
        *,
        trigger: TriggerSpec | None = None,
        keep: ContextSize = ("messages", 20),
        policy: PreservationPolicy | None = None,
        maximum_context_tokens: int = DEFAULT_MAXIMUM_CONTEXT_TOKENS,
        reserved_output_tokens: int = 4_000,
        safety_margin: float = 0.10,
        summarization_overhead_tokens: int = 2_000,
        token_counter: TokenCounter | None = None,
        identifier_patterns: Sequence[re.Pattern[str]] | None = None,
        validation_enabled: bool = True,
        summary_prompt: str = DEFAULT_SUMMARY_PROMPT,
        trim_tokens_to_summarize: int | None = 4_000,
        parsing: ParsingOptions | None = None,
        sink: EventSink | None = None,
        runtime: XAIRuntime | None = None,
        propagate_errors: Sequence[type[BaseException]] = (),
    ) -> None: ...
```

Information-aware summarization of an agent's message history.

`summarize` decides whether the history needs summarizing. When it does,
ContextSage parses every message with parsefabric into content units
(prose, JSON, logs, tables, code, stack traces), scores them, decides what
must be preserved, and losslessly compacts low-value structured content.
The summary model then summarizes the older messages, ContextSage verifies
that every must-preserve fact survived and restates any that did not, and
links the summarized messages to the summary in an agxai provenance store.

The engine works with [`contextsage.Message`](#contextsage.Message) objects, so it fits any agent
framework: convert native messages with a [`contextsage.FrameworkAdapter`](#contextsage.FrameworkAdapter),
or use a ready-made integration such as
``contextsage.integrations.langchain``.

**Example**

```python
from contextsage import ContextSummarizer, Message

async with ContextSummarizer(model, trigger=("tokens", 100_000)) as summarizer:
    result = await summarizer.summarize(history, thread_id="thread-1")
    if result is not None:
        history = list(result.messages)
```

**Arguments**

- `model`: The parsefabric ``LanguageModel`` that writes summaries.
- `trigger`: When to summarize: ``("tokens", n)``, ``("messages", n)``,
  ``("fraction", f)``, a clause such as
  ``{"tokens": 4000, "messages": 10}`` whose conditions must all
  hold, or a list in which any item may hold. ``None`` (the default)
  summarizes when the history no longer fits the token budget
  described by the next four arguments.
- `keep`: How much recent history stays verbatim, as ``("messages", n)``,
  ``("tokens", n)`` or ``("fraction", f)``, a share of
  ``maximum_context_tokens``.
- `policy`: How readily content is compacted. Defaults to
  [`contextsage.BalancedPolicy`](#contextsage.BalancedPolicy).
- `maximum_context_tokens`: The model's context window.
- `reserved_output_tokens`: Tokens kept free for the model's response.
- `safety_margin`: Fraction of the context window held back as a buffer.
- `summarization_overhead_tokens`: Tokens kept free for the system prompt,
  tool schemas and the summary call's own prompt.
- `token_counter`: Counts the tokens of messages. Defaults to
  [`contextsage.TokenizerTokenCounter`](#contextsage.TokenizerTokenCounter).
- `identifier_patterns`: Regular expressions for identifiers that must
  survive summarization. Replaces
  [`contextsage.DEFAULT_IDENTIFIER_PATTERNS`](#contextsage.DEFAULT_IDENTIFIER_PATTERNS); pass
  ``[*DEFAULT_IDENTIFIER_PATTERNS, re.compile(...)]`` to extend them.
- `validation_enabled`: Verify the rewritten history and restate missing
  facts.
- `summary_prompt`: Prompt for the summary model, with a ``{messages}``
  placeholder for the transcript being summarized.
- `trim_tokens_to_summarize`: Token budget for the transcript sent to the
  summary model, or ``None`` to send it all.
- `parsing`: How message text is parsed; see [`contextsage.ParsingOptions`](#contextsage.ParsingOptions).
- `sink`: Receives a [`contextsage.SummarizationEvent`](#contextsage.SummarizationEvent) for each rewrite.
  Defaults to [`contextsage.LoggingEventSink`](#contextsage.LoggingEventSink).
- `runtime`: The agxai runtime whose ``ProvenanceStore`` and identity
  record summary lineage. Build one with
  [`contextsage.create_agxai_runtime`](#contextsage.create_agxai_runtime). Defaults to a runtime with an
  in-memory store, which keeps links until the process exits.
- `propagate_errors`: Exception types from the summary model that are
  re-raised instead of triggering the trimming fallback, such as a
  framework's control-flow exceptions.

**Raises**

- `ConfigurationError`: If an argument is invalid.

#### `ContextSummarizer.runtime` { #contextsage.ContextSummarizer.runtime }

```python
@property
def runtime(self) -> XAIRuntime: ...
```

The agxai runtime that records summary lineage.

#### `ContextSummarizer.sink` { #contextsage.ContextSummarizer.sink }

```python
@property
def sink(self) -> EventSink: ...
```

The sink that receives summarization events.

#### `ContextSummarizer.policy` { #contextsage.ContextSummarizer.policy }

```python
@property
def policy(self) -> PreservationPolicy: ...
```

The preservation policy in effect.

#### `ContextSummarizer.prepare` { #contextsage.ContextSummarizer.prepare }

```python
async def prepare(self) -> None: ...
```

Load parsing resources, such as tree-sitter grammars, now.

`summarize` loads them on first use and, if the grammars cannot be
loaded, continues without code detection. Call `prepare` at start-up
to fail fast instead.

**Raises**

- `ConfigurationError`: If parsing resources cannot be loaded.

#### `ContextSummarizer.summarize` { #contextsage.ContextSummarizer.summarize }

```python
async def summarize(
    self,
    messages: Sequence[Message],
    *,
    thread_id: str | None = None,
    graph_id: str | None = None,
) -> SummarizationResult | None: ...
```

Summarize ``messages`` if the trigger fires.

**Arguments**

- `messages`: The full message history, oldest first.
- `thread_id`: The conversation the history belongs to. Provenance is
  scoped by it, so pass the same value to `lineage`.
- `graph_id`: The agent graph, recorded with provenance links.
  Defaults to the runtime's ``graph_id``.

**Returns**

The rewritten history, or ``None`` when it is left unchanged.

**Raises**

- `TypeError`: If an item of ``messages`` is not a [`contextsage.Message`](#contextsage.Message).
- `ContextSageError`: If the summarizer is closed.

#### `ContextSummarizer.lineage` { #contextsage.ContextSummarizer.lineage }

```python
async def lineage(
    self,
    summary_id: str,
    *,
    thread_id: str | None = None,
) -> tuple[ProvenanceLink, ...]: ...
```

Return the provenance of a summary, nearest links first.

Walks back from the summary through every earlier summary it replaced
to the original messages.

**Arguments**

- `summary_id`: ID of a summary message, also reported as
  `contextsage.SummarizationEvent.summary_id`.
- `thread_id`: The thread passed to `summarize`.

**Returns**

The ``derived_from`` links, each from a source to what it became.

#### `ContextSummarizer.delete_lineage` { #contextsage.ContextSummarizer.delete_lineage }

```python
async def delete_lineage(self, *, thread_id: str | None = None) -> int: ...
```

Delete the provenance recorded for a conversation thread.

Use it when a conversation is erased, for example to honor a
retention policy or a deletion request. Only links ContextSage
recorded for the thread are removed; agxai run records of the agent
itself are kept.

**Arguments**

- `thread_id`: The thread passed to `summarize`.

**Returns**

The number of records the ``ProvenanceStore`` removed.

#### `ContextSummarizer.aclose` { #contextsage.ContextSummarizer.aclose }

```python
async def aclose(self) -> None: ...
```

Flush the sink and release what the summarizer created.

The default sink, worker thread and agxai runtime are closed; a sink,
backend or runtime you passed in is flushed at most, never closed.
Idempotent.

### `SummarizationResult` { #contextsage.SummarizationResult }

```python
@dataclass(frozen=True, slots=True)
class SummarizationResult:
    messages: tuple[Message, ...]
    event: SummarizationEvent
```

The rewritten history and the event describing the rewrite.

**Attributes**

- `messages`: The history to use from now on. It replaces the whole input
  history, including any leading system messages, which are kept.
- `event`: Counts, ratios and statuses of the rewrite.

## Message model

### `Message` { #contextsage.Message }

```python
@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str
    id: str | None = None
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    rewritable: bool = True
    lineage: SummaryLineage | None = None
    native: object = field(default=None, compare=False, repr=False)
```

One message of an agent's history.

**Attributes**

- `role`: ``"system"``, ``"user"``, ``"assistant"`` or ``"tool"``.
- `content`: The message text. For multimodal content, the text parts.
- `id`: Stable message ID; provenance links refer to it.
- `name`: Optional author name, such as the agent of a multi-agent swarm.
- `tool_calls`: Tool invocations requested by an assistant message.
- `tool_call_id`: For a tool result, the ID of the call it answers.
- `rewritable`: Whether ContextSage may rewrite ``content``. Adapters set
  it to ``False`` for content that is not plain text, such as image
  blocks, so it is never compacted.
- `lineage`: Set on summary messages; see `SummaryLineage`.
- `native`: The framework's own message object, for adapters to update
  instead of rebuilding. Ignored by ContextSage and by equality.

**Raises**

- `ValueError`: If ``role`` is unknown or ``content`` is not a string.

#### `Message.is_summary` { #contextsage.Message.is_summary }

```python
@property
def is_summary(self) -> bool: ...
```

Whether the message is a summary of earlier history.

#### `Message.with_content` { #contextsage.Message.with_content }

```python
def with_content(self, content: str) -> Message: ...
```

Return a copy with new ``content``, keeping every other field.

### `ToolCall` { #contextsage.ToolCall }

```python
@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)
```

One tool invocation requested by an assistant message.

**Attributes**

- `id`: Identifier that the matching tool result refers to.
- `name`: Tool name.
- `arguments`: JSON-compatible tool arguments.

### `Fact` { #contextsage.Fact }

```python
@dataclass(frozen=True, slots=True)
class Fact:
    statement: str
    required: tuple[str, ...]
```

Information a rewritten history must still contain.

**Attributes**

- `statement`: The text restated verbatim if the fact goes missing.
- `required`: Strings that must all appear in a single message, as whole
  words and ignoring case, whitespace and apostrophe style, for the
  fact to count as preserved.

### `SummaryLineage` { #contextsage.SummaryLineage }

```python
@dataclass(frozen=True, slots=True)
class SummaryLineage:
    summary_id: str
    generation: int = 1
    source_summary_ids: tuple[str, ...] = ()
    facts: tuple[Fact, ...] = ()
```

Identity and ancestry of a summary message.

Lineage travels with the summary message, so it survives checkpoints and
needs no state in the engine.

**Attributes**

- `summary_id`: The summary message ID.
- `generation`: 1 for a first summary, 2 for a summary of a summary, and
  so on.
- `source_summary_ids`: IDs of the earlier summaries this one replaced.
- `facts`: Facts that later summarizations must keep, after the messages
  they came from are gone.

#### `SummaryLineage.to_dict` { #contextsage.SummaryLineage.to_dict }

```python
def to_dict(self) -> dict[str, object]: ...
```

Return the lineage as a JSON-compatible dictionary.

Framework adapters store this dictionary in the native message's
metadata and read it back with `from_dict`.

#### `SummaryLineage.from_dict` { #contextsage.SummaryLineage.from_dict }

```python
@classmethod
def from_dict(cls, record: object, *, summary_id: str) -> SummaryLineage: ...
```

Read a lineage record written by `to_dict`, tolerating damage.

A record edited by hand or truncated in a checkpoint never fails a
run: malformed fields fall back to the values of a first summary and
malformed facts are skipped.

**Arguments**

- `record`: The stored record, of any type.
- `summary_id`: The ID of the message the record belongs to, used when
  the record does not name one.

**Returns**

The lineage.

### `Role` { #contextsage.Role }

```python
type Role = Literal["system", "user", "assistant", "tool"]
```

Who wrote a message: the system prompt, the user, the agent's model or a tool.

## Extension ABCs

### `FrameworkAdapter` { #contextsage.FrameworkAdapter }

```python
class FrameworkAdapter[NativeT](ABC): ...
```

Converts an agent framework's messages to and from [`contextsage.Message`](#contextsage.Message).

Implement `to_message` and `from_message`; `to_messages` and
`from_messages` convert whole histories. Keep the framework object in
`contextsage.Message.native` so that `from_message` can return it unchanged,
or update it in place of rebuilding, when ContextSage did not rewrite it.

[`contextsage.integrations.langchain.LangChainAdapter`](#contextsage.integrations.langchain.LangChainAdapter) is the reference
implementation.

#### `FrameworkAdapter.propagated_errors` { #contextsage.FrameworkAdapter.propagated_errors }

```python
@property
def propagated_errors(self) -> tuple[type[BaseException], ...]: ...
```

Exceptions from the summary model that must reach the framework.

ContextSage recovers from summary-model failures by trimming the
history. Frameworks that signal control flow with exceptions, such as
LangGraph interrupts, list those exception types here. The default is
none.

#### `FrameworkAdapter.to_message` { #contextsage.FrameworkAdapter.to_message }

```python
@abstractmethod
def to_message(self, native: NativeT) -> Message: ...
```

Convert one framework message.

**Arguments**

- `native`: The framework's message.

**Returns**

The neutral message, with ``native`` set to the original object.

#### `FrameworkAdapter.from_message` { #contextsage.FrameworkAdapter.from_message }

```python
@abstractmethod
def from_message(self, message: Message) -> NativeT: ...
```

Convert one neutral message back to the framework's type.

**Arguments**

- `message`: A message from the rewritten history. Summaries and
  restated facts are new messages with no ``native`` object.

**Returns**

The framework's message.

#### `FrameworkAdapter.to_messages` { #contextsage.FrameworkAdapter.to_messages }

```python
def to_messages(self, natives: Sequence[NativeT]) -> list[Message]: ...
```

Convert a framework history; see `to_message`.

#### `FrameworkAdapter.from_messages` { #contextsage.FrameworkAdapter.from_messages }

```python
def from_messages(self, messages: Sequence[Message]) -> list[NativeT]: ...
```

Convert a rewritten history back; see `from_message`.

### `TokenCounter` { #contextsage.TokenCounter }

```python
class TokenCounter(ABC): ...
```

Counts the tokens a list of messages occupies in a model's context.

Implement `count` with the model's own tokenizer when exact budgets
matter. The engine counts the whole history before every model call, so
cache per message when counting is expensive, as
[`contextsage.TokenizerTokenCounter`](#contextsage.TokenizerTokenCounter) does.

#### `TokenCounter.count` { #contextsage.TokenCounter.count }

```python
@abstractmethod
async def count(self, messages: Sequence[Message]) -> int: ...
```

Return the number of tokens ``messages`` occupy.

**Arguments**

- `messages`: Messages in history order.

**Returns**

A non-negative token count.

### `PreservationPolicy` { #contextsage.PreservationPolicy }

```python
class PreservationPolicy(ABC): ...
```

Decides how readily content is compacted and summarized away.

Structural signals always win: user corrections, identifiers the user
stated or that appear next to failures, and both sides of a contradiction
are must-preserve under every policy, and repetitive content is always
compressible. A policy sets the importance thresholds for everything else
and how far JSON may be compacted.

Use [`contextsage.BalancedPolicy`](#contextsage.BalancedPolicy), [`contextsage.MaximumPreservationPolicy`](#contextsage.MaximumPreservationPolicy)
or [`contextsage.MaximumCompressionPolicy`](#contextsage.MaximumCompressionPolicy), or subclass this.

#### `PreservationPolicy.name` { #contextsage.PreservationPolicy.name }

```python
@property
def name(self) -> str: ...
```

Name reported in logs; the class name by default.

#### `PreservationPolicy.thresholds` { #contextsage.PreservationPolicy.thresholds }

```python
@property
@abstractmethod
def thresholds(self) -> PreservationThresholds: ...
```

The importance cut-offs of this policy.

#### `PreservationPolicy.json_compaction` { #contextsage.PreservationPolicy.json_compaction }

```python
@property
@abstractmethod
def json_compaction(self) -> JSONCompaction: ...
```

How far JSON documents may be compacted.

### `EventSink` { #contextsage.EventSink }

```python
class EventSink(ABC): ...
```

Receives one [`contextsage.SummarizationEvent`](#contextsage.SummarizationEvent) per rewritten history.

Implement `emit`; override `flush` and `close` if the destination buffers
events or holds a connection. A sink that raises is logged and skipped:
observability never fails an agent run.

#### `EventSink.emit` { #contextsage.EventSink.emit }

```python
@abstractmethod
async def emit(self, event: SummarizationEvent) -> None: ...
```

Deliver one event.

**Arguments**

- `event`: Aggregate, content-free record of one summarization.

#### `EventSink.flush` { #contextsage.EventSink.flush }

```python
async def flush(self) -> None: ...
```

Deliver buffered events. The default does nothing.

#### `EventSink.close` { #contextsage.EventSink.close }

```python
async def close(self) -> None: ...
```

Flush and release resources. The default does nothing.

### `JSONCompaction` { #contextsage.JSONCompaction }

```python
class JSONCompaction(StrEnum):
    MINIFY = "minify"
    COLLAPSE_RUNS = "collapse_runs"
    SAMPLE = "sample"
```

How far JSON documents may be compacted.

**Members**

- `MINIFY`: Remove insignificant whitespace only.
- `COLLAPSE_RUNS`: Also replace runs of identical consecutive list items with ``{"__repeated__": n, "value": item}``, which loses nothing.
- `SAMPLE`: Also collapse identical items anywhere in a list and keep only the first and last five entries of long lists, with ``{"__omitted__": n}`` between. Applied only to compressible content; other content gets `COLLAPSE_RUNS`.

### `PreservationThresholds` { #contextsage.PreservationThresholds }

```python
@dataclass(frozen=True, slots=True)
class PreservationThresholds:
    must: float
    should: float
    error_must: float
```

Importance cut-offs that map a content unit to a preservation level.

**Attributes**

- `must`: Importance at or above which a unit is must-preserve.
- `should`: Importance at or above which a unit is should-preserve.
- `error_must`: Lower must-preserve cut-off for units that report errors.

**Raises**

- `ConfigurationError`: If a value is outside ``[0, 1]`` or ``should`` is
  above ``must``.

## Configuration and events

### `ParsingOptions` { #contextsage.ParsingOptions }

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class ParsingOptions:
    patterns: Sequence[Pattern] | None = None
    routes: Sequence[tuple[Pattern, Parser[Aggregate] | str]] = ()
    fence_routes: Mapping[str, Parser[Aggregate] | str] = field(default_factory=dict)
    code_detector: CodeDetector | None = DEFAULT_CODE_DETECTOR
    json_codec: JSONCodec | None = None
    registry: ParserRegistry | None = None
    sink: ObservabilitySink | None = None
    backend: ExecutionBackend | None = None
    max_concurrency: int = 8
```

How ContextSage parses message text, built from parsefabric extension points.

**Attributes**

- `patterns`: Line patterns for logs, stack traces and tables. ``None``
  uses `default_patterns`; pass ``[*default_patterns(), mine]`` to
  extend them.
- `routes`: ``(selector, parser)`` pairs tried before ContextSage's JSON
  route, so a custom parser can claim lines that would otherwise be
  read as JSON. A parser may be given by name, resolved through
  ``registry``. A routed parser's name becomes the content kind of
  the lines it parses. Use parsefabric's ``CLIOutputParser`` here to
  read command output with your own ``CommandOutputBackend``.
- `fence_routes`: Parsers for fenced code blocks, by lowercase language
  tag; also by object or registry name.
- `code_detector`: Recognizes unfenced code. Defaults to parsefabric's
  shared tree-sitter detector; ``None`` disables code detection.
- `json_codec`: Decoder for JSON documents, such as a faster third-party
  JSON library. Defaults to parsefabric's strict codec.
- `registry`: Resolves parser names in ``routes`` and ``fence_routes``.
- `sink`: Receives parsefabric's parse and execution lifecycle events.
  ContextSage's own events go to [`contextsage.EventSink`](#contextsage.EventSink).
- `backend`: Where CPU-bound analysis runs. Defaults to a worker thread
  owned by the summarizer, so analysis never blocks the event loop.
  A backend you pass is yours to shut down.
- `max_concurrency`: Messages parsed concurrently. Raise it for parsers
  that wait on I/O, such as model-backed semantic parsers.

**Raises**

- `ConfigurationError`: If an option has the wrong type, or a parser is
  named without a ``registry``.

#### `ParsingOptions.prepare` { #contextsage.ParsingOptions.prepare }

```python
async def prepare(self) -> None: ...
```

Load the code detector's resources, such as tree-sitter grammars.

The summarizer calls this before its first parse. Call it at start-up
to fail fast on a host that cannot load them.

**Raises**

- `ConfigurationError`: If the detector cannot load its resources.

#### `ParsingOptions.build_parser` { #contextsage.ParsingOptions.build_parser }

```python
async def build_parser(self) -> MixedContentParser[Aggregate]: ...
```

Build the mixed-content parser, resolving named parsers.

**Returns**

The configured parser.

**Raises**

- `ConfigurationError`: If a named parser is not registered or
  parsefabric rejects the configuration.

#### `ParsingOptions.build_engine` { #contextsage.ParsingOptions.build_engine }

```python
def build_engine(self) -> ParseEngine: ...
```

Return the parsefabric engine that reports to `sink`.

### `default_patterns` { #contextsage.default_patterns }

```python
def default_patterns() -> tuple[Pattern, ...]: ...
```

Return fresh line patterns for stack traces, logs and tables.

### `SummarizationEvent` { #contextsage.SummarizationEvent }

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class SummarizationEvent:
    summary_id: str | None
    generation: int
    thread_id: str | None
    trigger_reason: str
    input_messages: int
    input_tokens: int
    available_tokens: int
    overflow_tokens: int
    prepared_tokens: int
    output_messages: int
    output_tokens: int
    compression_ratio: float
    compacted_units: int
    must_preserve_units: int
    must_preserve_facts: int
    content_kinds: dict[str, int] = field(default_factory=dict)
    validation_status: ValidationStatus
    recovery_status: RecoveryStatus
    policy: str
    latency_ms: float
```

Aggregate, content-free record of one summarization.

One event is delivered to the configured [`contextsage.EventSink`](#contextsage.EventSink) each
time the engine rewrites the message history; the default sink logs it to
the ``contextsage`` logger at ``INFO`` level. Events contain counts,
ratios and statuses only: never message content, tool output or
credentials.

**Attributes**

- `summary_id`: Message ID of the summary that now opens the history, or
  ``None`` when only deterministic compaction was applied.
- `generation`: How many summaries this one descends from: 1 for a first
  summary, 2 for a summary of a summary, and 0 when no summary was
  produced.
- `thread_id`: Conversation thread the summary belongs to, if the caller
  named one.
- `trigger_reason`: Why summarization ran.
- `input_messages`: Messages in the history before summarization.
- `input_tokens`: Tokens in the history before summarization.
- `available_tokens`: Input tokens available under the configured budget.
- `overflow_tokens`: Tokens over the trigger threshold or budget.
- `prepared_tokens`: Tokens after deterministic compaction, before the
  summary model ran.
- `output_messages`: Messages in the rewritten history.
- `output_tokens`: Tokens in the rewritten history.
- `compression_ratio`: ``output_tokens / input_tokens``.
- `compacted_units`: Content units that were compacted deterministically.
- `must_preserve_units`: Content units classified as must-preserve.
- `must_preserve_facts`: Literal facts that validation required.
- `content_kinds`: Number of content units per kind, such as ``json`` or
  ``log``.
- `validation_status`: See `ValidationStatus`.
- `recovery_status`: See `RecoveryStatus`.
- `policy`: Name of the preservation policy in effect.
- `latency_ms`: Wall-clock time spent summarizing, in milliseconds.

#### `SummarizationEvent.as_dict` { #contextsage.SummarizationEvent.as_dict }

```python
def as_dict(self) -> dict[str, object]: ...
```

Return the event as a JSON-compatible dictionary.

**Returns**

Every field, with ``content_kinds`` copied.

### `ValidationStatus` { #contextsage.ValidationStatus }

```python
type ValidationStatus = Literal["passed", "failed_recovered", "failed_unrecovered", "skipped", "disabled"]
```

Outcome of checking the rewritten history.

- ``passed``: every must-preserve fact survived and every tool result still
  follows its tool call. Compaction alone always passes, because it never
  removes must-preserve content.
- ``failed_recovered``: facts were missing and ContextSage restated them.
- ``failed_unrecovered``: a tool result lost its tool call, which restating
  facts cannot repair; ContextSage logs a warning.
- ``skipped``: there was no summary to check because the summary model failed.
- ``disabled``: validation is turned off (``validation_enabled=False``).

### `RecoveryStatus` { #contextsage.RecoveryStatus }

```python
type RecoveryStatus = Literal["none_needed", "restated_facts", "trimmed_fallback", "none_applicable"]
```

What ContextSage did after validation or a summary-model failure.

- ``none_needed``: nothing was missing, or validation is disabled.
- ``restated_facts``: missing facts were added verbatim to the summary message.
- ``trimmed_fallback``: the summary model failed, so the history was trimmed to
  the ``keep`` window, with a notice restating the latest user request and
  the facts the window lost.
- ``none_applicable``: a tool result lost its tool call, but no facts were
  missing, so there was nothing to restate.

### `DEFAULT_IDENTIFIER_PATTERNS` { #contextsage.DEFAULT_IDENTIFIER_PATTERNS }

```python
DEFAULT_IDENTIFIER_PATTERNS: tuple[re.Pattern[str], ...]
```

Built-in identifier formats: UUIDs, ``ABC-123`` keys, ``request_id=...``
assignments and phrases such as ``customer 456``.

### `DEFAULT_SUMMARY_PROMPT` { #contextsage.DEFAULT_SUMMARY_PROMPT }

```python
DEFAULT_SUMMARY_PROMPT: str
```

The default prompt; it must contain a ``{messages}`` placeholder.

## Built-in implementations

### `BalancedPolicy` { #contextsage.BalancedPolicy }

```python
class BalancedPolicy(PreservationPolicy): ...
```

The default: lossless JSON compaction and moderate thresholds.

### `MaximumPreservationPolicy` { #contextsage.MaximumPreservationPolicy }

```python
class MaximumPreservationPolicy(PreservationPolicy): ...
```

Keep as much as possible; JSON is only minified.

### `MaximumCompressionPolicy` { #contextsage.MaximumCompressionPolicy }

```python
class MaximumCompressionPolicy(PreservationPolicy): ...
```

Compact aggressively; long JSON lists of compressible content are sampled.

### `TokenizerTokenCounter` { #contextsage.TokenizerTokenCounter }

```python
class TokenizerTokenCounter(TokenCounter):
    def __init__(
        self,
        tokenizer: Tokenizer = DEFAULT_TOKENIZER,
        *,
        tokens_per_message: int = 3,
        cache_size: int = 4096,
    ) -> None: ...
```

Counts messages with a parsefabric `parsefabric.compression.Tokenizer`.

Each message costs the tokens of its content, author name and tool calls,
plus a fixed per-message overhead for the chat format. Counts are cached
per message, so re-counting a growing history only tokenizes new
messages.

**Arguments**

- `tokenizer`: Counts the tokens of a text. Defaults to parsefabric's
  approximate tokenizer (one token per four UTF-8 bytes); pass the
  model's own tokenizer for exact budgets.
- `tokens_per_message`: Overhead added for every message.
- `cache_size`: Most messages whose counts are cached; 0 disables the
  cache.

**Raises**

- `ConfigurationError`: If an argument is invalid.

#### `TokenizerTokenCounter.tokenizer` { #contextsage.TokenizerTokenCounter.tokenizer }

```python
@property
def tokenizer(self) -> Tokenizer: ...
```

The tokenizer that counts message text.

### `LoggingEventSink` { #contextsage.LoggingEventSink }

```python
class LoggingEventSink(EventSink):
    def __init__(self, logger: logging.Logger | None = None) -> None: ...
```

Log every event as one structured ``INFO`` record.

The record's message is ``"contextsage summarization"`` and the event is
attached as the ``contextsage`` attribute (``extra={"contextsage": ...}``),
ready for a JSON log formatter. This is the default sink.

**Arguments**

- `logger`: Logger to write to. Defaults to the ``contextsage`` logger.

### `CompositeEventSink` { #contextsage.CompositeEventSink }

```python
class CompositeEventSink(EventSink):
    def __init__(self, sinks: Iterable[EventSink]) -> None: ...
```

Deliver every event to several sinks, in order.

A failing child sink is logged and skipped; the others still receive the
event.

**Arguments**

- `sinks`: Sinks that receive every event.

**Raises**

- `ConfigurationError`: If an item is not an `EventSink`.

#### `CompositeEventSink.sinks` { #contextsage.CompositeEventSink.sinks }

```python
@property
def sinks(self) -> tuple[EventSink, ...]: ...
```

The child sinks, in delivery order.

#### `CompositeEventSink.flush` { #contextsage.CompositeEventSink.flush }

```python
async def flush(self) -> None: ...
```

Flush every child sink, then raise any failures together.

**Raises**

- `ExceptionGroup`: If one or more child sinks failed to flush.

#### `CompositeEventSink.close` { #contextsage.CompositeEventSink.close }

```python
async def close(self) -> None: ...
```

Close every child sink, then raise any failures together.

**Raises**

- `ExceptionGroup`: If one or more child sinks failed to close.

### `OpenTelemetryEventSink` { #contextsage.OpenTelemetryEventSink }

```python
class OpenTelemetryEventSink(EventSink):
    def __init__(self, meter: Meter | None = None) -> None: ...
```

Record every event as OpenTelemetry metrics.

Instruments, all tagged with ``validation_status``, ``recovery_status`` and
``policy``:

- ``contextsage.summarizations`` (counter): rewritten histories.
- ``contextsage.input_tokens`` and ``contextsage.output_tokens``
  (histograms, ``{token}``): history size before and after.
- ``contextsage.compression_ratio`` (histogram): output over input tokens.
- ``contextsage.compacted_units`` (counter): units compacted
  deterministically.
- ``contextsage.duration`` (histogram, ``ms``): time spent summarizing.

ContextSage does not configure an OpenTelemetry SDK; without one, the
API's no-op meter records nothing. Install ``contextsage[otel]`` for the
SDK and the OTLP exporter. Spans are recorded by the engine itself.

**Arguments**

- `meter`: Meter to create the instruments on. Defaults to
  ``metrics.get_meter("contextsage")``.

## Errors and agxai

### `ContextSageError` { #contextsage.ContextSageError }

```python
class ContextSageError(Exception): ...
```

Base class for every error raised by ContextSage.

### `ConfigurationError` { #contextsage.ConfigurationError }

```python
class ConfigurationError(ContextSageError, ValueError): ...
```

The middleware configuration is invalid or its resources are unavailable.

Raised by [`contextsage.ContextSummarizer`](#contextsage.ContextSummarizer) or an integration for invalid
arguments, and when parsing resources cannot be loaded during preparation.

### `create_agxai_runtime` { #contextsage.create_agxai_runtime }

```python
def create_agxai_runtime(
    *,
    config: XAIConfig | None = None,
    registry: Registry | None = None,
    application_id: str = "contextsage",
    tenant_id: str = "default",
    graph_id: str = "agent",
    plugins: Sequence[XAIPlugin] = (),
    custom_state_capture: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None,
    store: ProvenanceStore | None = None,
    observability: ObservabilityProvider | None = None,
    attribution: AttributionEngine | None = None,
    explanation: ExplanationEngine | None = None,
    policy: PolicyProvider | None = None,
    capture_policy: CapturePolicy | None = None,
) -> XAIRuntime: ...
```

Build an ``agxai.XAIRuntime`` with any of its components replaced.

Every agxai extension point can be supplied here: the runtime settings and
identity, plugins, custom state capture, and each registered capability.
A capability left as ``None`` keeps the provider already in ``registry``,
or agxai's default. Pass the runtime to
``ContextSummarizer(runtime=...)``; share it with your agent's agxai
instrumentation so summaries appear in the same provenance graph.

**Arguments**

- `config`: ``agxai.XAIConfig`` capture, failure and concurrency settings.
- `registry`: An ``agxai.Registry`` to share providers between runtimes.
- `application_id`: Application identifier of recorded links and runs.
- `tenant_id`: Tenant identifier of recorded links and runs.
- `graph_id`: Graph identifier of recorded links and runs.
- `plugins`: ``agxai.XAIPlugin`` instances that receive semantic artifacts.
- `custom_state_capture`: The state capture function agxai requires for
  ``CaptureMode.CUSTOM``.
- `store`: The ``agxai.ProvenanceStore`` that records summary lineage.
- `observability`: The ``agxai.ObservabilityProvider`` canonical events go to.
- `attribution`: The ``agxai.AttributionEngine`` that scores decisions.
- `explanation`: The ``agxai.ExplanationEngine`` that renders explanations.
- `policy`: The ``agxai.PolicyProvider`` that filters explanations by audience.
- `capture_policy`: The ``agxai.CapturePolicy`` that gates captured events.

**Returns**

The configured runtime.

**Raises**

- `ConfigurationError`: If a component is not an instance of its agxai
  base class, or agxai rejects the configuration.

## Optional LangChain integration

Install `contextsage[langchain]` to import
`contextsage.integrations.langchain`.

### `IntelligentSummarizationMiddleware` { #contextsage.integrations.langchain.IntelligentSummarizationMiddleware }

```python
class IntelligentSummarizationMiddleware(AgentMiddleware[AgentState[Any], Any, Any]):
    transformers = (InternalCallTransformer,)

    def __init__(
        self,
        model: str | BaseChatModel,
        *,
        trigger: TriggerSpec | None = None,
        keep: ContextSize = ("messages", 20),
        policy: PreservationPolicy | None = None,
        maximum_context_tokens: int | None = None,
        reserved_output_tokens: int = 4_000,
        safety_margin: float = 0.10,
        summarization_overhead_tokens: int = 2_000,
        token_counter: TokenCounter | None = None,
        identifier_patterns: Sequence[re.Pattern[str]] | None = None,
        validation_enabled: bool = True,
        summary_prompt: str = DEFAULT_SUMMARY_PROMPT,
        trim_tokens_to_summarize: int | None = 4_000,
        parsing: ParsingOptions | None = None,
        sink: EventSink | None = None,
        runtime: XAIRuntime | None = None,
        adapter: LangChainAdapter | None = None,
    ) -> None: ...
```

Information-aware replacement for LangChain's ``SummarizationMiddleware``.

Before each model call, the middleware runs a [`contextsage.ContextSummarizer`](#contextsage.ContextSummarizer)
on the agent's messages and, when it rewrites them, replaces the history
in the agent state. Provenance is scoped by the LangGraph thread ID.

**Example**

```python
from langchain.agents import create_agent

from contextsage.integrations.langchain import IntelligentSummarizationMiddleware

agent = create_agent(
    model="openai:gpt-5",
    tools=tools,
    middleware=[
        IntelligentSummarizationMiddleware(
            "openai:gpt-5-mini",
            trigger=("tokens", 100_000),
            keep=("messages", 20),
        )
    ],
)
```

**Arguments**

- `model`: Chat model, or ``init_chat_model`` identifier, that writes
  summaries.
- `maximum_context_tokens`: The model's context window. Defaults to the
  model profile's ``max_input_tokens``, else 128,000.
- `token_counter`: Counts tokens. Defaults to `LangChainTokenCounter`.
- `adapter`: Converts LangChain messages. Defaults to `LangChainAdapter`.
Every other argument is passed to [`contextsage.ContextSummarizer`](#contextsage.ContextSummarizer).

**Raises**

- `ConfigurationError`: If an argument is invalid or the model cannot be
  initialized.

**Members**

- `transformers`: Keeps the summary model's tokens out of the agent's streamed messages.

#### `IntelligentSummarizationMiddleware.summarizer` { #contextsage.integrations.langchain.IntelligentSummarizationMiddleware.summarizer }

```python
@property
def summarizer(self) -> ContextSummarizer: ...
```

The engine that rewrites the history.

#### `IntelligentSummarizationMiddleware.alineage` { #contextsage.integrations.langchain.IntelligentSummarizationMiddleware.alineage }

```python
async def alineage(
    self,
    summary_id: str,
    *,
    thread_id: str | None = None,
) -> tuple[ProvenanceLink, ...]: ...
```

Return the provenance of a summary; see [`contextsage.ContextSummarizer.lineage`](#contextsage.ContextSummarizer.lineage).

#### `IntelligentSummarizationMiddleware.adelete_lineage` { #contextsage.integrations.langchain.IntelligentSummarizationMiddleware.adelete_lineage }

```python
async def adelete_lineage(self, *, thread_id: str | None = None) -> int: ...
```

Delete a thread's provenance; see [`contextsage.ContextSummarizer.delete_lineage`](#contextsage.ContextSummarizer.delete_lineage).

#### `IntelligentSummarizationMiddleware.aclose` { #contextsage.integrations.langchain.IntelligentSummarizationMiddleware.aclose }

```python
async def aclose(self) -> None: ...
```

Release the summarizer's resources; see [`contextsage.ContextSummarizer.aclose`](#contextsage.ContextSummarizer.aclose).

Also stops the event loop thread used by the synchronous hook.

#### `IntelligentSummarizationMiddleware.abefore_model` { #contextsage.integrations.langchain.IntelligentSummarizationMiddleware.abefore_model }

```python
async def abefore_model(
    self,
    state: AgentState[Any],
    runtime: Runtime[Any],
) -> dict[str, Any] | None: ...
```

Summarize the history before a model call when the trigger fires.

**Returns**

A state update replacing the history, or ``None`` to leave it.

#### `IntelligentSummarizationMiddleware.before_model` { #contextsage.integrations.langchain.IntelligentSummarizationMiddleware.before_model }

```python
def before_model(
    self,
    state: AgentState[Any],
    runtime: Runtime[Any],
) -> dict[str, Any] | None: ...
```

Synchronous counterpart of `abefore_model`, for ``agent.invoke``.

The work runs on a private event loop thread; prefer ``agent.ainvoke``.

### `LangChainAdapter` { #contextsage.integrations.langchain.LangChainAdapter }

```python
class LangChainAdapter(FrameworkAdapter[BaseMessage]): ...
```

Converts LangChain messages to and from [`contextsage.Message`](#contextsage.Message).

Summaries are ``HumanMessage`` objects marked with
``additional_kwargs={"lc_source": "summarization"}``, with the lineage
record under ``additional_kwargs["contextsage"]``. Messages whose content
is not plain text, such as image blocks, are never rewritten.

### `LangChainSummaryModel` { #contextsage.integrations.langchain.LangChainSummaryModel }

```python
class LangChainSummaryModel(LanguageModel):
    def __init__(self, model: str | BaseChatModel) -> None: ...
```

A `parsefabric.LanguageModel` backed by a LangChain chat model.

Summary calls are tagged with ``lc_source="summarization"`` and
LangChain's internal-call metadata, so their tokens never appear in the
agent's streamed messages.

**Arguments**

- `model`: A LangChain chat model, or an ``init_chat_model`` identifier
  such as ``"openai:gpt-5-mini"``.

**Raises**

- `ConfigurationError`: If the model cannot be initialized.

#### `LangChainSummaryModel.model` { #contextsage.integrations.langchain.LangChainSummaryModel.model }

```python
@property
def model(self) -> BaseChatModel: ...
```

The wrapped chat model.

#### `LangChainSummaryModel.max_input_tokens` { #contextsage.integrations.langchain.LangChainSummaryModel.max_input_tokens }

```python
@property
def max_input_tokens(self) -> int | None: ...
```

The context window from the model's profile, if it declares one.

### `LangChainTokenCounter` { #contextsage.integrations.langchain.LangChainTokenCounter }

```python
class LangChainTokenCounter(TokenCounter):
    def __init__(
        self,
        counter: Callable[[Sequence[BaseMessage]], int] = count_tokens_approximately,
        *,
        adapter: LangChainAdapter | None = None,
    ) -> None: ...
```

Counts tokens with a LangChain message-counting function.

**Arguments**

- `counter`: Counts a list of LangChain messages. Defaults to
  ``count_tokens_approximately``.
- `adapter`: Converts messages to LangChain messages.

### `LINEAGE_KEY` { #contextsage.integrations.langchain.LINEAGE_KEY }

```python
LINEAGE_KEY = "contextsage"
```

Key of the lineage record in a summary message's ``additional_kwargs``.
