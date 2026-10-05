# Preservation policies

`policy` sets how readily ContextSage compacts content. Every unit of the
history is placed at one of three preservation levels, and the level decides
which compaction it may receive.

<figure class="diagram" markdown="span">
  ![A content unit is must-preserve if it holds a user correction, a user-stated identifier, an identifier in a failure or one side of a conflict. Otherwise its importance score is compared with the policy's thresholds, making it must-preserve, should-preserve or compressible. Must and should units only receive lossless compaction; compressible units may also lose repetitive detail.](../assets/diagrams/preservation.png){ width="560" }
  <figcaption>Structural signals make a unit must-preserve under every policy;
  the policy's thresholds place everything else.</figcaption>
</figure>

## The three policies

| Policy | Must preserve from | Should preserve from | Errors must preserve from | JSON compaction |
| --- | --- | --- | --- | --- |
| `maximum_preservation` | 0.60 | 0.30 | 0.45 | Minify |
| `balanced` (default) | 0.75 | 0.45 | 0.60 | Minify, and collapse runs of identical items |
| `maximum_compression` | 0.90 | 0.65 | 0.80 | Also group identical items anywhere in a list, and sample long lists of compressible units |

A unit whose importance reaches a threshold gets that level; units below the
should-preserve threshold are compressible. Units with error severity, such as
stack traces and `ERROR` log lines, use the lower "errors" threshold for
must-preserve.

Whatever the policy:

- **Must-preserve** and **should-preserve** units only receive lossless
  compaction: minified JSON, counted runs of identical JSON items, and runs of
  identical table rows.
- **Compressible** units may also lose repetitive detail: similar log lines
  collapse to their first and last line around a marker, and under
  `maximum_compression` long JSON lists are sampled.
- Facts come only from must-preserve units, so no policy can compact away a
  fact.

## The same payload under each policy

```python
--8<--
examples/policies.py
--8<--
```

Output:

```text
--8<-- "examples/expected/policies.txt"
```

`balanced` collapsed the two runs of three identical pallets and kept the
order of everything else. `maximum_compression` also grouped the six identical
pallets across the list and sampled the twelve distinct ones, replacing four
of them with `{"__omitted__": 4}`, so the model knows that data was elided.

## Choosing a policy

- **`balanced`** suits most agents. It loses nothing from important content
  and removes the repetition that dominates tool output.
- **`maximum_preservation`** suits audited or regulated work where the model
  must see data as it was returned. JSON is still minified.
- **`maximum_compression`** suits exploratory work over very large results,
  where a representative sample of a long list is enough and context space
  matters most.
