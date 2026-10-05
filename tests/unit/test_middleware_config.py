from __future__ import annotations

import re
from typing import Any, cast

import pytest
from langchain_core.messages.utils import count_tokens_approximately
from langgraph_xai import InMemoryProvenanceStore

import contextsage
from contextsage import (
    ConfigurationError,
    ContextSageError,
    IntelligentSummarizationMiddleware,
    SummarizationEvent,
)
from contextsage import middleware as middleware_module
from tests.support.builders import profiled_model, summary_model


def middleware(**options: Any) -> IntelligentSummarizationMiddleware:
    options.setdefault("code_languages", ())
    return IntelligentSummarizationMiddleware(summary_model(), **options)


def test_public_api():
    assert set(contextsage.__all__) == {
        "DEFAULT_IDENTIFIER_PATTERNS",
        "ConfigurationError",
        "ContextSageError",
        "IntelligentSummarizationMiddleware",
        "RecoveryStatus",
        "SummarizationEvent",
        "ValidationStatus",
        "__version__",
    }
    assert re.fullmatch(r"\d+\.\d+\.\d+", contextsage.__version__)
    assert all(
        isinstance(pattern, re.Pattern)
        for pattern in contextsage.DEFAULT_IDENTIFIER_PATTERNS
    )


def test_configuration_errors_are_value_errors():
    assert issubclass(ConfigurationError, ContextSageError)
    assert issubclass(ConfigurationError, ValueError)


def test_event_as_dict_is_a_copy():
    event = SummarizationEvent(
        summary_id="s",
        generation=1,
        thread_id=None,
        trigger_reason="r",
        input_messages=1,
        input_tokens=10,
        available_tokens=100,
        overflow_tokens=0,
        prepared_tokens=10,
        output_messages=1,
        output_tokens=5,
        compression_ratio=0.5,
        compacted_units=0,
        must_preserve_units=0,
        must_preserve_facts=0,
        content_kinds={"text": 1},
        validation_status="passed",
        recovery_status="none_needed",
        latency_ms=1.0,
    )
    data = event.as_dict()
    cast("dict[str, int]", data["content_kinds"])["text"] = 99
    assert event.content_kinds == {"text": 1}
    assert data["summary_id"] == "s"


def test_defaults():
    instance = middleware()
    assert isinstance(instance.provenance_store, InMemoryProvenanceStore)
    assert instance.name == "IntelligentSummarizationMiddleware"
    assert IntelligentSummarizationMiddleware.transformers


def test_custom_provenance_store_and_token_counter():
    store = InMemoryProvenanceStore()
    instance = middleware(
        provenance_store=store, token_counter=count_tokens_approximately
    )
    assert instance.provenance_store is store


def test_model_identifiers_are_initialized_with_init_chat_model():
    with pytest.raises(ConfigurationError, match="cannot initialize model"):
        IntelligentSummarizationMiddleware("no-such-provider:model", code_languages=())


def test_any_model_initialization_failure_is_a_configuration_error(monkeypatch):
    def missing_credentials(model: str) -> None:
        raise RuntimeError("no API key")

    monkeypatch.setattr(middleware_module, "init_chat_model", missing_credentials)
    with pytest.raises(ConfigurationError, match="cannot initialize model: no API key"):
        IntelligentSummarizationMiddleware("openai:gpt-5-mini", code_languages=())


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"policy": "aggressive"}, "policy must be one of"),
        ({"summary_prompt": "no placeholder"}, "\\{messages\\} placeholder"),
        ({"trim_tokens_to_summarize": 0}, "trim_tokens_to_summarize"),
        ({"trim_tokens_to_summarize": True}, "trim_tokens_to_summarize"),
        ({"identifier_patterns": ["TX-\\d+"]}, "compiled text regexes"),
        ({"identifier_patterns": [re.compile(rb"TX")]}, "compiled text regexes"),
        ({"observability_hook": "print"}, "must be callable"),
        ({"trigger": ("tokens", -1)}, "positive integer"),
        ({"keep": ("messages", 0)}, "keep must be"),
        ({"keep": ("seconds", 3)}, "keep must be"),
        ({"keep": ("fraction", 1.5)}, "keep must be"),
        ({"maximum_context_tokens": 0}, "maximum_context_tokens"),
        ({"safety_margin": 1.5}, "safety_margin"),
        ({"reserved_output_tokens": 200_000}, "no room for input"),
        ({"code_languages": "python"}, "invalid content parsing"),
    ],
)
def test_invalid_configuration(options, message):
    with pytest.raises(ConfigurationError, match=message):
        middleware(**options)


def test_fraction_keep_is_a_share_of_the_context_window():
    without_profile = middleware(keep=("fraction", 0.3), maximum_context_tokens=10_000)
    assert without_profile._keep == ("tokens", 3_000)
    profiled = IntelligentSummarizationMiddleware(
        profiled_model(20_000), keep=("fraction", 0.3), code_languages=()
    )
    assert profiled._keep == ("tokens", 6_000)
