"""Comparing the ``policy`` parameter's effect on preservation decisions.

Run with:

    python examples/policy.py

The same moderately-important tool output is classified under each policy
to show that ``policy`` genuinely changes preservation outcomes (not just
documentation text) — see
``contextiq.preservation.engine._POLICY_THRESHOLDS``.
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage

from contextiq.budget.tokens import TiktokenTokenCounter
from contextiq.context.decomposition import ContextDecomposer
from contextiq.importance.engine import ImportanceEngine
from contextiq.preservation.engine import PreservationEngine


def main() -> None:
    token_counter = TiktokenTokenCounter(encoding_name="cl100k_base")
    messages = [
        ToolMessage(
            content="Health check queued; results pending.",
            tool_call_id="c-1",
            id="t-1",
        ),
        ToolMessage(
            content=(
                "Health check REQ-8842 decision: scale the worker pool before the next batch run."
            ),
            tool_call_id="c0",
            id="t0",
        ),
    ]
    units = ContextDecomposer(token_counter).decompose(messages)
    scored = ImportanceEngine().score(units)

    for policy in ("maximum_preservation", "balanced", "maximum_compression"):
        classified = PreservationEngine(policy).classify(scored, [])
        target = next(u for u in classified if "REQ-8842" in u.content)
        print(f"policy={policy!r:24} -> preservation={target.preservation.value}")


if __name__ == "__main__":
    main()
