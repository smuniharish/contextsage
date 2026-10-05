from __future__ import annotations

import re
import time

import pytest

from contextsage._pipeline.models import canonical_severity, severity_rank
from contextsage._pipeline.signals import (
    DEFAULT_IDENTIFIER_PATTERNS,
    find_identifiers,
    mask_numbers,
    mask_volatile,
    mentions_failure,
    normalize_volatile,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "id 3f2b9c1e-1d2a-4c5b-9e8f-0123456789ab here",
            ("3f2b9c1e-1d2a-4c5b-9e8f-0123456789ab",),
        ),
        ("ticket INC-9931 and TX-991", ("INC-9931", "TX-991")),
        ("request_id=req-77 trace-id: 'abc'", ("request_id=req-77", "trace-id: 'abc")),
        ("for customer 456 and order #42", ("customer 456", "order #42")),
        ("UTF-8 and a 12-step plan", ()),
    ],
)
def test_default_identifier_patterns(text, expected):
    assert find_identifiers(text, DEFAULT_IDENTIFIER_PATTERNS)[0] == expected


def test_custom_identifier_patterns_deduplicate_in_order():
    patterns = (re.compile(r"WGT#\d+"), re.compile(r"\bESC-\d+"))
    assert find_identifiers("WGT#1 ESC-2 WGT#1 ESC-2 WGT#3", patterns)[0] == (
        "WGT#1",
        "WGT#3",
        "ESC-2",
    )


def test_identifier_lines_are_the_lines_a_match_touches():
    text = "ok\nTX-991 failed\r\nrequest_id\n= req-7\nok\n"
    identifiers, lines = find_identifiers(text, DEFAULT_IDENTIFIER_PATTERNS)
    assert identifiers == ("TX-991", "request_id\n= req-7")
    assert lines == {1, 2, 3}
    assert find_identifiers("nothing here\n", DEFAULT_IDENTIFIER_PATTERNS) == (
        (),
        frozenset(),
    )


@pytest.mark.parametrize(
    "text",
    [
        "The payment failed",
        "connection timed out after 30s",
        "Root cause: pool exhaustion",
        "request was denied",
        "An exception was raised",
    ],
)
def test_failure_language(text):
    assert mentions_failure(text)


@pytest.mark.parametrize(
    "text",
    ["No errors found", "finished without failures", "zero errors today", "All good"],
)
def test_negated_or_absent_failure_language(text):
    assert not mentions_failure(text)


def test_normalize_volatile_masks_timestamps_ids_and_numbers():
    first = normalize_volatile("2024-01-01T10:00:00Z job 4f9c2e1a done in 120ms")
    second = normalize_volatile("2024-01-02T11:30:00Z job 7aa0b3c9 done in 95ms")
    assert first == second == "<ts> job <id> done in <n>ms"


def test_masks_keep_lines_and_whitespace():
    text = "Oct  4 10:00:00 job 4f9c2e1a\r\nstatus 500  retry 3\n"
    masked = mask_volatile(text)
    assert masked == "<ts> job <id>\r\nstatus 500  retry 3\n"
    assert mask_numbers(masked) == "<ts> job <id>\r\nstatus <n>  retry <n>\n"


def test_hexadecimal_runs_are_ids_only_with_a_digit():
    assert mask_volatile("deadbeef-cafe a1b2c3d4-e5f6 badc0ffee") == (
        "deadbeef-cafe <id> <id>"
    )


def test_hexadecimal_masking_is_linear():
    text = "a-" * 50_000
    start = time.perf_counter()
    assert mask_volatile(text) == text
    assert time.perf_counter() - start < 0.5


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("warn", "WARNING"),
        (" Fatal ", "CRITICAL"),
        ("err", "ERROR"),
        ("trace", "DEBUG"),
        ("notice", "INFO"),
        ("ERROR", "ERROR"),
        ("verbose", None),
        (None, None),
        (3, None),
    ],
)
def test_canonical_severity(value, expected):
    assert canonical_severity(value) == expected


def test_severity_rank_orders_levels():
    ranks = [
        severity_rank(level)
        for level in (None, "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    ]
    assert ranks == sorted(ranks)
    assert ranks[0] == 0
