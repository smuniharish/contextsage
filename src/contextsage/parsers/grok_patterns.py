"""A minimal, dependency-free "grok" pattern library.

`Grok <https://github.com/logstash-plugins/logstash-patterns-core>`_ patterns
are the de-facto public standard for naming common log sub-patterns
(``%{TIMESTAMP_ISO8601}``, ``%{LOGLEVEL}``, ``%{IP}``, ...), popularized by
Logstash and widely reused across the log-processing ecosystem. Rather than
depending on a full grok-matching engine (existing Python ports are thin,
largely unmaintained wrappers around exactly this kind of pattern table), we
vendor the small subset of the public pattern definitions ContextSage actually
needs and resolve ``%{NAME}``/``%{NAME:field}`` references ourselves at
import time into plain :mod:`re` patterns with named groups.

This keeps log/error detection anchored to the same well-known vocabulary
operators expect (a ``LOGLEVEL`` match means what it means in every ELK
deployment) without adding a runtime dependency for a handful of regexes.
"""

from __future__ import annotations

import re

# Base building blocks, verbatim (module names) from the public
# logstash-patterns-core `grok-patterns` file. Only the subset ContextSage's
# log/error detection needs is reproduced here.
_BASE_PATTERNS: dict[str, str] = {
    "YEAR": r"(?:\d\d){1,2}",
    "MONTHNUM": r"(?:0?[1-9]|1[0-2])",
    "MONTHDAY": r"(?:(?:0[1-9])|(?:[12][0-9])|(?:3[01])|[1-9])",
    "HOUR": r"(?:2[0123]|[01]?[0-9])",
    "MINUTE": r"(?:[0-5][0-9])",
    "SECOND": r"(?:(?:[0-5]?[0-9]|60)(?:[:.,][0-9]+)?)",
    "ISO8601_TIMEZONE": r"(?:Z|[+-]\d{2}:?\d{2})",
    "TIMESTAMP_ISO8601": (
        r"%{YEAR}-%{MONTHNUM}-%{MONTHDAY}[T ]%{HOUR}:%{MINUTE}(?::%{SECOND})?%{ISO8601_TIMEZONE}?"
    ),
    "MONTH": (
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b"
    ),
    "SYSLOGTIMESTAMP": r"%{MONTH} +%{MONTHDAY} %{HOUR}:%{MINUTE}:%{SECOND}",
    "LOGLEVEL": (
        r"([Aa]lert|ALERT|[Tt]race|TRACE|[Dd]ebug|DEBUG|[Nn]otice|NOTICE|[Ii]nfo|INFO|"
        r"[Ww]arn(?:ing)?|WARN(?:ING)?|[Ee]rr(?:or)?|ERR(?:OR)?|[Cc]rit(?:ical)?|CRIT(?:ICAL)?|"
        r"[Ff]atal|FATAL|[Ss]evere|SEVERE|EMERG(?:ENCY)?|[Ee]merg(?:ency)?)"
    ),
    "UUID": r"[A-Fa-f0-9]{8}-(?:[A-Fa-f0-9]{4}-){3}[A-Fa-f0-9]{12}",
    "IPV4": (
        r"(?:(?:25[0-5]|2[0-4][0-9]|[0-1]?[0-9]{1,2})\."
        r"(?:25[0-5]|2[0-4][0-9]|[0-1]?[0-9]{1,2})\."
        r"(?:25[0-5]|2[0-4][0-9]|[0-1]?[0-9]{1,2})\."
        r"(?:25[0-5]|2[0-4][0-9]|[0-1]?[0-9]{1,2}))"
    ),
    "WORD": r"\b\w+\b",
    "JAVACLASS": r"(?:[a-zA-Z$_][a-zA-Z$_0-9]*\.)*[a-zA-Z$_][a-zA-Z$_0-9]*(?:Exception|Error)",
}

_REF_RE = re.compile(r"%\{(\w+)(?::(\w+))?\}")


def _resolve(name: str, _stack: tuple[str, ...] = ()) -> str:
    """Recursively expand ``%{NAME}``/``%{NAME:field}`` references to plain regex."""
    if name in _stack:
        msg = f"circular grok pattern reference: {' -> '.join((*_stack, name))}"
        raise ValueError(msg)
    raw = _BASE_PATTERNS[name]

    def _substitute(match: re.Match[str]) -> str:
        ref_name, field = match.group(1), match.group(2)
        expanded = _resolve(ref_name, (*_stack, name))
        return f"(?P<{field}>{expanded})" if field else f"(?:{expanded})"

    return _REF_RE.sub(_substitute, raw)


def compile_pattern(name: str) -> re.Pattern[str]:
    """Compile one named base/composite pattern (with field captures) to ``re``."""
    return re.compile(_resolve(name))


#: A single log line: an ISO-8601 or syslog-style timestamp followed
#: (anywhere on the line) by a recognized severity level.
GROK_LOG_LINE = re.compile(
    rf"(?P<timestamp>{_resolve('TIMESTAMP_ISO8601')}|{_resolve('SYSLOGTIMESTAMP')})"
)
GROK_LOGLEVEL = compile_pattern("LOGLEVEL")
GROK_UUID = compile_pattern("UUID")
GROK_IPV4 = compile_pattern("IPV4")
#: A Java/Python-style fully-qualified exception class name
#: (``com.example.FooException`` / ``requests.exceptions.ConnectionError``).
GROK_JAVACLASS = compile_pattern("JAVACLASS")
