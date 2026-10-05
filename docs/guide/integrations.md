# Agent integrations

`IntelligentSummarizationMiddleware` is LangChain agent middleware. It works
with agents built by `create_agent` and with frameworks built on it, such as
Deep Agents and LangGraph Swarm.

## LangChain agents

Pass the middleware to `create_agent`, as in the
[quickstart](../getting-started/quickstart.md). Use one summarization
middleware per agent: ContextSage replaces LangChain's
`SummarizationMiddleware` rather than running alongside it.

When an agent has several middleware, their `before_model` hooks run in list
order. Put ContextSage where you would put `SummarizationMiddleware`,
typically after middleware that adds messages to the history and before
middleware that only inspects the model call.

## Synchronous and asynchronous agents

`invoke` and `stream` run the synchronous hook, and `ainvoke` and `astream`
the asynchronous one; both behave identically. Analysis is CPU-bound, so the
asynchronous hook runs it in a worker thread and never blocks the event loop.
parsefabric parses asynchronously, so the synchronous hook runs it on a
private event loop, which leaves any event loop your thread has set
untouched.

## Checkpointers and threads

With a checkpointer, the rewritten history is saved in the thread's state like
any other update, and each later turn starts from it. A summary that is
summarized again becomes the next generation of the same lineage, and
provenance links are scoped to the thread; see
[Provenance and lineage](provenance.md).

## Streaming

When you stream an agent with `stream_events(version="v3")`, the summary
model's tokens are kept out of the agent's message stream: ContextSage marks
the summary call as internal, as LangChain does for its own summarization.

## Deep Agents

Deep Agents add LangChain's `SummarizationMiddleware` to every deep agent.
Exclude it with a harness profile for your model provider, so that
ContextSage replaces it instead of running alongside it:

```python
--8<--
examples/deep_agent.py
--8<--
```

## LangGraph Swarm

In a swarm, add ContextSage to the agents whose histories grow large, such as
those that call tools with large results. Each agent's middleware sees the
shared conversation before that agent's model calls:

```python
--8<--
examples/swarm.py
--8<--
```

`without_speaker_names` is only needed for OpenAI-compatible endpoints that
reject the `name` that swarm agents put on their messages; the OpenAI API
accepts it.

## Run the live examples

These examples call a real model. Configure an OpenAI-compatible endpoint
through the environment, or a local `.env` file, as described in the
[examples README](https://github.com/smuniharish/contextsage/blob/master/examples/README.md),
then run, for example:

```bash
uv run python examples/deep_agent.py
```
