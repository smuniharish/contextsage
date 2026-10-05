# Content parsing

ContextSage parses every message with parsefabric's `MixedContentParser`,
which routes each line to the parser that understands it. The resulting
content units decide how each part of a message is scored, preserved and
compacted.

<figure class="diagram" markdown="span">
  ![Each line of a message goes through parsefabric's MixedContentParser: fenced blocks go to the matching fence_routes parser or become code; other lines try your routes and then the JSON route, then the line patterns for stack traces, logs and tables, and finally code detection. The kind and severity of every line form the content units.](../assets/diagrams/decomposition.png){ width="460" }
  <figcaption>Every line gets a kind and a severity. Consecutive lines of the
  same kind form a content unit.</figcaption>
</figure>

## How lines are recognized

For each line, in order:

1. **Fenced blocks.** A block that opens with a Markdown code fence goes to
   the `fence_routes` parser registered for its language tag, if any, and is
   code otherwise.
2. **Routes.** Your `routes` are tried first, then the built-in JSON route,
   which claims a line that opens a JSON object or array, through the end of
   the document.
3. **Line patterns.** Stack-trace lines from Python, the JVM, Node.js and Go;
   log lines that start with a timestamp or a level such as `ERROR`, or carry
   logfmt `level=` and `msg=` fields; and table rows.
4. **Code detection.** Remaining lines are checked with the tree-sitter
   grammars in `code_languages`, and are prose (`text`) otherwise.

Lines then form units. Consecutive lines of one kind form one unit, and each
JSON document and fenced block is a unit of its own. Log runs split where the
severity crosses `WARNING`, so warnings and errors are never compacted along
with routine lines. Indented source lines between stack-trace lines join the
trace, and blank lines join the unit before them.

The patterns run on untrusted text, so they are written to run in linear
time. Nothing is ever executed: parsing only reads text.

## Teach ContextSage your formats

`routes` sends matching lines to your own parsefabric parser, and
`fence_routes` does the same for fenced blocks by language tag. The routed
parser's `name` becomes the content kind of the lines it claims. Content of a
custom kind is scored and preserved like any other, and is never compacted.

The example below teaches ContextSage to recognize SQL with
[sqlglot](https://pypi.org/project/sqlglot/). The same parser instance serves
the route and the fence, because parsefabric requires routed parsers that share
a name to be identical:

```python
--8<--
examples/custom_parsing.py
--8<--
```

Output:

```text
--8<-- "examples/expected/custom_parsing.txt"
```

Built-in parsing already recognized the query and the suggested index as
code. With the parser, both became `sql` content.

## Code detection

`code_languages` lists the tree-sitter grammars used to recognize unfenced
code. The default is parsefabric's `DEFAULT_CODE_LANGUAGES`: Python,
JavaScript, TypeScript, Java, Go, Rust, C, C++ and SQL.

- Pass a shorter list to load fewer grammars, for example
  `code_languages=("python", "sql")` for an agent that only sees those
  languages.
- Pass `code_languages=()` to turn code detection off. Unfenced code then
  counts as prose; fenced blocks are still code.
- Grammars that accept ordinary prose, such as `bash` or `ruby`, are rejected,
  because every sentence would look like code.

Code detection is the most expensive part of parsing prose-heavy histories;
see [Performance](../operations/performance.md). Grammars are downloaded on
first use, as described in [Installation](../getting-started/installation.md).
