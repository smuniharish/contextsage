"""Unit tests for structural signal detection."""

from __future__ import annotations

from contextsage.classification.signals import StructuralSignalDetector, normalize_for_repetition
from contextsage.core.models import RegionKind


def test_detects_json():
    signals = StructuralSignalDetector().detect('{"status": "ok"}')
    assert signals.kind == RegionKind.JSON
    assert signals.confidence > 0.5


def test_detects_logs():
    text = "\n".join(f"2024-01-0{i} 10:00:0{i} INFO heartbeat" for i in range(1, 5))
    signals = StructuralSignalDetector().detect(text)
    assert signals.kind == RegionKind.LOG


def test_ambiguous_text_falls_back_to_plain_text_with_low_confidence():
    signals = StructuralSignalDetector().detect("This is just a normal sentence about things.")
    assert signals.kind == RegionKind.TEXT
    assert signals.confidence <= 0.6


def test_extracts_identifiers():
    signals = StructuralSignalDetector().detect("transaction_id: TX-991 for customer 456")
    assert any("456" in ident or "TX-991" in ident for ident in signals.identifiers)


def test_empty_text_is_treated_as_plain_text():
    signals = StructuralSignalDetector().detect("   ")
    assert signals.kind == RegionKind.TEXT


def test_normalize_for_repetition_collapses_volatile_substrings():
    a = normalize_for_repetition("request 12345 completed at 10:00:01")
    b = normalize_for_repetition("request 98765 completed at 10:00:02")
    assert a == b
