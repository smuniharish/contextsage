from __future__ import annotations

import re

import pytest
from parsefabric.builtins import MixedContentParser
from parsefabric.patterns import RegexPattern

from contextsage import ConfigurationError
from contextsage._pipeline import parsing
from contextsage._pipeline.parsing import (
    JSON_START,
    LEVEL_LOG_LINE,
    LOGFMT_LOG_LINE,
    TABLE_ROW,
    TIMESTAMPED_LOG_LINE,
    TRACEBACK_LINE,
    TRACEBACK_LINES,
    build_parser,
    default_patterns,
)


@pytest.mark.parametrize(
    ("line", "level"),
    [
        ("2024-01-01T10:00:00Z INFO started", "INFO"),
        ("2024-01-01 10:00:00,123 - app - ERROR - boom", "ERROR"),
        ("[2024-01-01 10:00:00] warn disk almost full", "warn"),
        ("Jan  5 10:00:00 host app[1]: CRITICAL failure", "CRITICAL"),
        ("10:00:01.250 DEBUG tick", "DEBUG"),
        ("2024-01-01T10:00:00+02:00 worker started", None),
    ],
)
def test_timestamped_log_lines(line, level):
    match = re.search(TIMESTAMPED_LOG_LINE, line)
    assert match is not None
    assert match.group("level") == level


@pytest.mark.parametrize("line", ["2024-01-01 was a good day", "Version 1.2.3 shipped"])
def test_prose_is_not_a_timestamped_log_line(line):
    assert re.search(TIMESTAMPED_LOG_LINE, line) is None


@pytest.mark.parametrize(
    "line", ["INFO heartbeat ok", "ERROR: boom", "[WARN] slow", "<FATAL> down", "ERROR"]
)
def test_level_first_log_lines(line):
    assert re.search(LEVEL_LOG_LINE, line) is not None


@pytest.mark.parametrize("line", ["Error: something happened", "INFORMATION desk"])
def test_level_first_requires_an_upper_case_level_word(line):
    assert re.search(LEVEL_LOG_LINE, line) is None


def test_logfmt_lines():
    match = re.search(LOGFMT_LOG_LINE, 'time=1 level=warn msg="slow query"')
    assert match is not None
    assert match.group("level") == "warn"
    assert re.search(LOGFMT_LOG_LINE, "level=warn only") is None


@pytest.mark.parametrize(
    "line",
    [
        "Traceback (most recent call last):",
        '  File "app.py", line 3, in main',
        "    at com.example.Foo.bar(Foo.java:10)",
        "    at /srv/app.js:10:5",
        "Caused by: java.io.IOException: closed",
        "    ... 12 more",
        "panic: runtime error: index out of range",
        "goroutine 1 [running]:",
        'Exception in thread "main" java.lang.IllegalStateException: bad',
        "ValueError: bad value",
        "requests.exceptions.ConnectionError",
        "KeyboardInterrupt",
    ],
)
def test_stack_trace_lines(line):
    assert re.search(TRACEBACK_LINE, line) is not None


@pytest.mark.parametrize("line", ["MemoryError happened today", "Errors are rare"])
def test_prose_mentioning_errors_is_not_a_stack_trace(line):
    assert re.search(TRACEBACK_LINE, line) is None


def test_stack_trace_expressions_are_anchored_alternatives():
    assert all(expression.startswith("^") for expression in TRACEBACK_LINES)
    assert re.search(TRACEBACK_LINE, "x  at com.example.Foo.bar(Foo.java:10)") is None


def test_stack_frame_pattern_is_linear_on_long_lines():
    line = "  at " + "(" * 20_000
    assert re.search(TRACEBACK_LINE, line) is None


@pytest.mark.parametrize("line", ["| a | b |", "|---|---|", "  | x |  "])
def test_table_rows(line):
    assert re.search(TABLE_ROW, line) is not None


@pytest.mark.parametrize(
    "line",
    [
        '{"a": 1}',
        "{}",
        "{",
        '{ "a"',
        "[1, 2]",
        "[1]",
        "[]",
        "[",
        '[{"a":1}]',
        '["x"]',
        "[true]",
        "[[1]]",
        "[-1.5e3, 2]",
    ],
)
def test_json_start_lines(line):
    assert re.search(JSON_START, line) is not None


@pytest.mark.parametrize(
    "line", ["[2024-01-01 10:00:00] ERROR boom", "[INFO] started", "{name} is unset"]
)
def test_bracketed_text_is_not_json(line):
    assert re.search(JSON_START, line) is None


def test_default_patterns_are_fresh_and_uniquely_named():
    first, second = default_patterns(), default_patterns()
    assert first is not second
    names = [pattern.name for pattern in first]
    assert len(names) == len(set(names))
    assert all(name.startswith("contextsage-") for name in names)


def test_build_parser_without_code_detection():
    assert isinstance(
        build_parser(routes=(), fence_routes=None, code_languages=()),
        MixedContentParser,
    )


def test_build_parser_rejects_conflicting_route_names():
    route = (RegexPattern("contextsage-json", r"^SELECT"), parsing.JSONParser())
    with pytest.raises(ConfigurationError, match="invalid content parsing"):
        build_parser(routes=(route,), fence_routes=None, code_languages=())


def test_build_parser_rejects_a_string_of_languages():
    with pytest.raises(ConfigurationError, match="invalid content parsing"):
        build_parser(routes=(), fence_routes=None, code_languages="python")


def test_build_parser_rejects_prose_accepting_grammars():
    with pytest.raises(ConfigurationError, match="invalid content parsing"):
        build_parser(routes=(), fence_routes=None, code_languages=("bash",))


def test_grammar_load_failure_explains_how_to_fix_it(monkeypatch):
    def unavailable(*args: object, **kwargs: object) -> MixedContentParser:
        raise OSError("network is unreachable")

    monkeypatch.setattr(parsing, "MixedContentParser", unavailable)
    with pytest.raises(ConfigurationError) as raised:
        build_parser(routes=(), fence_routes=None, code_languages=("python", "go"))
    message = str(raised.value)
    assert "python, go" in message
    assert "network is unreachable" in message
    assert "t.download(['python', 'go'])" in message
    assert "code_languages=()" in message
    assert isinstance(raised.value.__cause__, OSError)
