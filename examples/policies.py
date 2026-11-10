"""Compare the preservation policies, and write your own.

Run: python examples/policies.py

`MaximumPreservationPolicy` only minifies JSON. `BalancedPolicy` (the default)
also collapses runs of identical items, which loses nothing.
`MaximumCompressionPolicy` groups identical items anywhere in a list and
samples long lists. A policy is a `PreservationPolicy` subclass, so a custom
one picks its own score thresholds and JSON compaction.
"""

from __future__ import annotations

import asyncio
import json

from _shared import ScriptedModel

from contextsage import (
    BalancedPolicy,
    ContextSummarizer,
    JSONCompaction,
    MaximumCompressionPolicy,
    MaximumPreservationPolicy,
    Message,
    PreservationPolicy,
    PreservationThresholds,
)


class AuditPolicy(PreservationPolicy):
    """Keep nearly everything, but still collapse runs of identical JSON items."""

    @property
    def thresholds(self) -> PreservationThresholds:
        return PreservationThresholds(must=0.5, should=0.2, error_must=0.3)

    @property
    def json_compaction(self) -> JSONCompaction:
        return JSONCompaction.COLLAPSE_RUNS


INVENTORY = {
    "warehouse": "berlin-2",
    "pallets": (
        [{"sku": "A-1", "state": "ok"}] * 3
        + [{"sku": "B-2", "state": "ok"}]
        + [{"sku": "A-1", "state": "ok"}] * 3
        + [{"sku": f"C-{index}", "state": "ok"} for index in range(12)]
    ),
}
HISTORY = [
    Message("user", "Summarize the warehouse inventory."),
    Message("tool", json.dumps(INVENTORY, indent=2), tool_call_id="call-1"),
]


async def main() -> None:
    policies: list[PreservationPolicy] = [
        MaximumPreservationPolicy(),
        BalancedPolicy(),
        MaximumCompressionPolicy(),
        AuditPolicy(),
    ]
    for policy in policies:
        async with ContextSummarizer(
            ScriptedModel("unused"),
            trigger=("tokens", 200),
            keep=("messages", 20),
            policy=policy,
        ) as summarizer:
            result = await summarizer.summarize(HISTORY)
        if result is None:
            raise SystemExit("The tool result was not compacted.")
        compacted = result.messages[-1].content
        print(f"{policy.name} ({len(compacted)} characters, {policy.thresholds}):")
        print(f"  {compacted}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
