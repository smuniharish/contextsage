<p align="center">
  <img src="https://raw.githubusercontent.com/smuniharish/contextsage/master/docs/assets/logo.svg" alt="ContextSage logo" width="96">
</p>

<h1 align="center">ContextSage</h1>

<p align="center">
  <a href="https://pypi.org/project/contextsage/"><img src="https://img.shields.io/pypi/v/contextsage" alt="PyPI"></a>
  <a href="https://pypi.org/project/contextsage/"><img src="https://img.shields.io/pypi/pyversions/contextsage" alt="Python versions"></a>
  <a href="https://github.com/smuniharish/contextsage/actions/workflows/ci.yml"><img src="https://github.com/smuniharish/contextsage/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://contextsage.readthedocs.io/"><img src="https://img.shields.io/readthedocs/contextsage" alt="Documentation"></a>
  <a href="https://github.com/smuniharish/contextsage/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/contextsage" alt="License"></a>
</p>

**Information-aware context summarization for AI agents.** ContextSage
compresses long conversation histories while preserving important facts,
tool relationships and provenance. Its asynchronous, framework-agnostic core
uses a neutral message model and can be adapted to any agent framework.

## Install

```bash
pip install contextsage
```

Install optional integrations only when you use them:

```bash
pip install "contextsage[langchain]"  # LangChain and LangGraph
pip install "contextsage[otel]"       # OpenTelemetry SDK and OTLP exporter
pip install "contextsage[all]"        # both optional integrations
```

The core requires Python 3.12 or newer and does not install an agent framework.

## Framework-neutral quickstart

Implement `parsefabric.LanguageModel` with your summary provider, convert your
framework's history to `contextsage.Message`, then call the async engine before
the next model turn:

```python
async def summarize_history(summary_model, messages):
    async with ContextSummarizer(summary_model, trigger=("tokens", 100_000)) as engine:
        result = await engine.summarize(messages, thread_id="conversation-42")
        if result is not None:
            messages = list(result.messages)
```

The engine parses text and structured content, compacts repetitive material,
preserves facts such as identifiers and corrections, validates the result,
and records lineage. If the history does not meet the trigger, `summarize`
returns `None`. See the runnable [quickstart](examples/quickstart.py) and the
[core concepts](docs/guide/how-it-works.md).

## Integrations

The optional LangChain integration wraps the same core engine:

```python
from contextsage.integrations.langchain import IntelligentSummarizationMiddleware

middleware = IntelligentSummarizationMiddleware(
    "openai:gpt-5-mini",
    trigger=("tokens", 100_000),
    keep=("messages", 20),
)
```

Or implement `FrameworkAdapter` for your framework's message type. The
adapter maps between native messages and the neutral `Message` model; no
framework dependency is needed by the core. See the [LangChain integration](docs/guide/integrations.md)
and [custom framework example](examples/custom_framework.py).

## Downstream customization

ContextSage exposes the extension points of its dependencies rather than
restricting them to built-in choices:

| Package | Customizable components |
| --- | --- |
| [parsefabric](https://pypi.org/project/parsefabric/) | `LanguageModel`, tokenizers, line patterns, parsers and registries, fenced-code routes, code detection, JSON codec, lifecycle sink, and execution backend. |
| [agxai](https://pypi.org/project/agxai/) | `ProvenanceStore`, observability, attribution, explanation and policy providers, capture policy, runtime configuration, registry, plugins, and custom state capture. |
| OpenTelemetry | Use the built-in event sink and SDK/exporters, or supply an `EventSink` for your telemetry platform. |
| LangChain (optional) | Supply a chat model, token counter, and `LangChainAdapter` to the integration. |

Use `ParsingOptions` to configure parsefabric and
`create_agxai_runtime(...)` to configure agxai. The
[downstream customization example](examples/downstream_customization.py)
demonstrates custom components from both packages.

## Examples and documentation

The [examples](examples/README.md) include framework adapters, LangChain,
PostgreSQL provenance, OpenTelemetry, Prometheus, custom parsing, policies,
and recovery. Scripted examples run without API keys and their output is
verified in CI. The
[documentation site](https://contextsage.readthedocs.io/) includes
installation, configuration, integration guides, operations guidance and the
[API reference](https://contextsage.readthedocs.io/en/latest/reference/).

ContextSage also publishes [Agent Skills](contextsage-skills/README.md) for
coding agents that need to integrate or extend the package. The
[skills guide](docs/agent-skills.md) also lists independently maintained
dependency and integration skills.

## Downloads

<p>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520sum%2528count%2529%2520v%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527contextsage%2527%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=downloads&amp;color=blue&amp;cacheSeconds=3600" alt="Total downloads"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520sum%2528count%2529%2520v%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520date%2520%253E%253D%2520toStartOfWeek%2528toDate%2528now%2528%2527UTC%2527%2529%2529%252C%25201%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=this%20week&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads this week"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520sum%2528count%2529%2520v%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520date%2520%253E%253D%2520toStartOfMonth%2528toDate%2528now%2528%2527UTC%2527%2529%2529%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=this%20month&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads this month"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520sum%2528count%2529%2520v%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520date%2520%253E%253D%2520toStartOfYear%2528toDate%2528now%2528%2527UTC%2527%2529%2529%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=this%20year&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads this year"></a>
</p>
<p>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528toString%2528x.1%2529%252C%2520%2527%253A%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528groupArray%2528%2528y%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520toYear%2528date%2529%2520y%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527contextsage%2527%2520GROUP%2520BY%2520y%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=by%20year&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by year"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BA%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20A&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country A"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BB%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20B&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country B"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BC%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20C&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country C"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BD%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20D&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country D"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BE%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20E&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country E"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BF%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20F&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country F"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BG%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20G&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country G"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BH%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20H&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country H"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BI%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20I&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country I"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BJ%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20J&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country J"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BK%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20K&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country K"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BL%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20L&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country L"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BM%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20M&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country M"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BNO%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20N-O&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country N-O"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BPQ%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20P-Q&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country P-Q"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BR%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20R&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country R"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BS%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20S&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country S"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BT%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20T&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country T"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/contextsage"><img class="off-glb" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528arrayMap%2528x%2520-%253E%2520concat%2528x.1%252C%2520%2527%2520%2527%252C%2520toString%2528x.2%2529%2529%252C%2520arraySort%2528x%2520-%253E%2520%2528-toInt64%2528x.2%2529%252C%2520x.1%2529%252C%2520groupArray%2528%2528country%252C%2520c%2529%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520ifNull%2528nullIf%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527unknown%2527%2529%2520country%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527contextsage%2527%2520AND%2520match%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%2520%2527%255E%255BUVWXYZ%255D%255BA-Z%255D%2524%2527%2529%2520GROUP%2520BY%2520country%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20U-Z&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by country U-Z"></a>
</p>

These badges use the public [ClickHouse PyPI dataset](https://clickpy.clickhouse.com/dashboard/contextsage),
which refreshes daily, so counts may be about a day behind. Shields fetches the
data when badges are requested and caches images for up to an hour; GitHub may
also cache them. Weeks start on Monday (UTC). Country badges exclude missing
or invalid country codes. Explore interactive charts on the
[ClickPy dashboard](https://clickpy.clickhouse.com/dashboard/contextsage).

## Development

```bash
uv sync --locked --all-extras --all-groups
uv run pytest
uv run ruff check .
uv run pyrefly check
```

See [contributing](CONTRIBUTING.md) and [testing](docs/development/testing.md).
ContextSage is licensed under the [Apache License 2.0](LICENSE).
