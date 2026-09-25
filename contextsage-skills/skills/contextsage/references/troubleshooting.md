# Debugging and testing ContextSage

Use a reproduction before changing configuration or application code. Capture
the exact middleware constructor arguments, message list shape, model name,
LangChain/LangGraph versions, and whether the sync or async path runs.

## Investigation sequence

1. **Confirm activation.** Check whether the trigger or the budget analyzer
   requires summarization. A `None` result from `before_model` or
   `abefore_model` means no summarization was required.
2. **Inspect the real budget.** Check the context-window assumption,
   reserved output, safety margin, summarization overhead, trigger, and
   `keep`. Do not guess from character count.
3. **Inspect middleware order and message protocol.** Preserve AI tool-call
   / `ToolMessage` result pairs and verify the agent executes the expected
   middleware path.
4. **Inspect actual content.** Determine whether the input is plain text,
   JSON, logs, code, errors, tables, or mixed. A mixed tool result should
   remain mixed; do not pre-slice it into lossy strings.
5. **Use diagnostics.** Inspect the `contextsage.observability` event or a
   configured `observability_hook` for trigger reason, input and available
   tokens, selected target count, validation/recovery status, compression
   ratio, and latency. Events are aggregate-only by design.
6. **Differentiate failures.** A validation failure can append preserved facts;
   a LangGraph summarization-call failure can use deterministic trim plus
   preserved facts. Inspect the recovery status before adding application
   fallbacks.
7. **Compare with a verified example/test.** Use the closest repository
   example and focused tests; do not call internal engines as a production
   workaround.

## Focused tests to adapt

| Behavior to verify | Existing evidence |
| --- | --- |
| Triggered and non-triggered paths | [test_middleware_pipeline.py](https://github.com/smuniharish/contextsage/blob/master/tests/integration/test_middleware_pipeline.py) |
| Sync and async middleware paths | [test_middleware_pipeline.py](https://github.com/smuniharish/contextsage/blob/master/tests/integration/test_middleware_pipeline.py) |
| Missing-fact recovery and tool-call pairing | [test_middleware_pipeline.py](https://github.com/smuniharish/contextsage/blob/master/tests/integration/test_middleware_pipeline.py) |
| Provider/summarization failure recovery | [test_summarization_failure.py](https://github.com/smuniharish/contextsage/blob/master/tests/failure/test_summarization_failure.py) |
| Budget and token accounting | [test_budget_analyzer.py](https://github.com/smuniharish/contextsage/blob/master/tests/unit/test_budget_analyzer.py), [test_tokens.py](https://github.com/smuniharish/contextsage/blob/master/tests/unit/test_tokens.py) |
| Structured/log transformation | [test_transformation_engine.py](https://github.com/smuniharish/contextsage/blob/master/tests/unit/test_transformation_engine.py) |
| Preservation and relationships | [test_preservation.py](https://github.com/smuniharish/contextsage/blob/master/tests/unit/test_preservation.py), [test_relationships.py](https://github.com/smuniharish/contextsage/blob/master/tests/unit/test_relationships.py) |

For an integration change, test the measurable property that motivated it:
the middleware triggers at the intended pressure; important facts remain;
tool pairing remains valid; the context fits the modeled budget; and recovery
is explicit when the model or validation path fails.

## Repository checks

For runtime changes, the repository CI runs:

```bash
ruff check src tests examples
ruff format --check src tests examples
pyrefly check
pytest tests -q
mkdocs build --strict
```

Skill-only changes do not need runtime tests, but they must pass the
distribution process in [`../../../validation/README.md`](../../../validation/README.md).
