"""Summary validation.

Runs after the wrapped LangGraph summarization step and before any recovery
action. Validation checks three independent invariants:

1. Every literal "must preserve" fact (user corrections, identifiers,
   constraint sentences) is present, verbatim, somewhere in the resulting
   message text.
2. Tool-call/result pairing remains valid — no orphaned ``ToolMessage``.
3. Known contradictions are not silently collapsed into a single false
   certainty; both conflicting values must still be discoverable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from contextiq.core.models import Relationship, RelationType, ValidationFinding, ValidationResult
from contextiq.relationships.engine import pair_tool_calls

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage


class SummaryValidator:
    """Validates a produced message list against preservation requirements."""

    def validate(
        self,
        *,
        new_messages: Sequence[BaseMessage],
        must_preserve_facts: tuple[str, ...],
        contradiction_relationships: tuple[Relationship, ...] = (),
    ) -> ValidationResult:
        findings: list[ValidationFinding] = []
        combined_text = _combined_text(new_messages).lower()

        for fact in must_preserve_facts:
            if fact.lower() not in combined_text:
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        description="required fact was not found in the produced summary",
                        fact=fact,
                    )
                )

        findings.extend(self._validate_tool_call_pairing(new_messages))
        findings.extend(self._validate_contradictions(contradiction_relationships, combined_text))

        passed = not any(f.severity == "critical" for f in findings)
        return ValidationResult(passed=passed, findings=tuple(findings))

    @staticmethod
    def _validate_tool_call_pairing(messages: Sequence[BaseMessage]) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        pairs = pair_tool_calls(messages)
        for tool_call_id, (ai_id, tool_id) in pairs.items():
            if tool_id is not None and ai_id is None:
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        description=(
                            f"orphaned ToolMessage for tool_call_id={tool_call_id!r}: "
                            "no matching AIMessage tool call survived"
                        ),
                    )
                )
        return findings

    @staticmethod
    def _validate_contradictions(
        relationships: tuple[Relationship, ...], combined_text: str
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for rel in relationships:
            if rel.relation is not RelationType.CONTRADICTS:
                continue
            key = rel.metadata.get("key")
            value_a = str(rel.metadata.get("value_a", "")).lower()
            value_b = str(rel.metadata.get("value_b", "")).lower()
            present_a = bool(value_a) and value_a in combined_text
            present_b = bool(value_b) and value_b in combined_text
            if not (present_a and present_b):
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        description=(
                            f"contradiction on key={key!r} did not survive with both "
                            f"conflicting values discoverable ({value_a!r} vs {value_b!r})"
                        ),
                        # Recovery restates literal facts by reading `.fact`;
                        # encode both conflicting values so neither is lost.
                        fact=f"{key}: {value_a} vs {value_b} (contradictory sources)",
                    )
                )
        return findings


def _combined_text(messages: Sequence[BaseMessage]) -> str:
    parts = []
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    parts.append(str(block.get("text", block)))
        else:
            parts.append(str(content))
    return "\n".join(parts)
