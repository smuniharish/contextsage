from __future__ import annotations

import re
from typing import override

import pytest
from parsefabric import ParseEngine
from parsefabric.builtins import (
    ApplicationLogParser,
    CodeDetector,
    JSONParser,
    MixedContentParser,
)
from parsefabric.execution import AsyncExecutionBackend
from parsefabric.observability import NullObservabilitySink
from parsefabric.patterns import RegexPattern
from parsefabric.registry import InMemoryParserRegistry

from contextsage import ConfigurationError, ParsingOptions


class Detector(CodeDetector):
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.prepared = 0
        self.languages = ("python", "go")

    @override
    async def prepare(self) -> None:
        self.prepared += 1
        if self.error is not None:
            raise self.error

    @override
    async def detect(self, text: str) -> str | None:
        return None


async def test_build_parser_without_code_detection():
    options = ParsingOptions(code_detector=None)
    await options.prepare()
    assert isinstance(await options.build_parser(), MixedContentParser)
    assert isinstance(options.build_engine(), ParseEngine)


async def test_prepare_loads_the_detector():
    detector = Detector()
    await ParsingOptions(code_detector=detector).prepare()
    assert detector.prepared == 1


async def test_grammar_load_failure_explains_how_to_fix_it():
    options = ParsingOptions(code_detector=Detector(OSError("network is unreachable")))
    with pytest.raises(ConfigurationError) as raised:
        await options.prepare()
    message = str(raised.value)
    assert "network is unreachable" in message
    assert "['python', 'go']" in message
    assert "code_detector=None" in message
    assert isinstance(raised.value.__cause__, OSError)


async def test_named_parsers_resolve_through_the_registry():
    registry = InMemoryParserRegistry()
    parser = ApplicationLogParser()
    await registry.register(parser)
    options = ParsingOptions(
        code_detector=None,
        routes=((RegexPattern("app", r"^APP "), parser.name),),
        fence_routes={"log": parser.name},
        registry=registry,
        sink=NullObservabilitySink(),
        backend=AsyncExecutionBackend(),
        patterns=(),
    )
    assert isinstance(await options.build_parser(), MixedContentParser)


async def test_unregistered_parser_names_are_configuration_errors():
    options = ParsingOptions(
        code_detector=None, fence_routes={"sql": "missing"}, registry=InMemoryParserRegistry()
    )
    with pytest.raises(ConfigurationError, match="'missing' is not registered"):
        await options.build_parser()


async def test_conflicting_route_names_are_configuration_errors():
    route = (RegexPattern("contextsage-json", r"^SELECT"), JSONParser())
    with pytest.raises(ConfigurationError, match="invalid content parsing"):
        await ParsingOptions(code_detector=None, routes=(route,)).build_parser()


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"patterns": "x"}, "patterns"),
        ({"patterns": [re.compile("x")]}, "patterns"),
        ({"routes": "x"}, "routes"),
        ({"routes": [(RegexPattern("a", "a"),)]}, "routes"),
        ({"routes": [(RegexPattern("a", "a"), "")]}, "routes"),
        ({"fence_routes": ["x"]}, "fence_routes"),
        ({"fence_routes": {"sql": 1}}, "fence_routes"),
        ({"code_detector": object()}, "code_detector"),
        ({"json_codec": object()}, "json_codec"),
        ({"registry": object()}, "registry"),
        ({"sink": object()}, "sink"),
        ({"backend": object()}, "backend"),
        ({"fence_routes": {"sql": "json"}}, "needs a registry"),
        ({"max_concurrency": 0}, "max_concurrency"),
        ({"max_concurrency": True}, "max_concurrency"),
    ],
)
def test_invalid_options(options, message):
    with pytest.raises(ConfigurationError, match=message):
        ParsingOptions(**options)
