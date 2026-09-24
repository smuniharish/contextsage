# Security Policy

## Supported Versions

ContextSage is currently pre-1.0 (`0.x`). Security fixes are made against
the latest released `0.x` version only; there is no long-term support
branch yet.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report privately via GitHub's
[private vulnerability reporting](https://github.com/smuniharish/contextsage/security/advisories/new)
feature, or email the maintainer listed in `pyproject.toml`
(`authors`).

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, including the `IntelligentSummarizationMiddleware`
  configuration and message shapes involved, if applicable.
- Any suggested remediation, if you have one.

You should expect an initial response within 5 business days. Once a fix
is available, it will be released as a new `0.x` patch version and noted
in `CHANGELOG.md`.

## Scope notes

ContextSage processes agent conversation content (including tool output) in
order to decompose, classify, and summarize it. It does not execute code,
evaluate SQL, or otherwise act on the content it inspects — parsers such
as `CodeParser` (via `tree-sitter`) and the `sqlglot`-based example SQL
parser only *parse* text to measure structural confidence; they never
execute or transpile it against a live database or interpreter. Reports
related to a bundled third-party dependency (e.g. `tree-sitter`,
`tiktoken`, `langgraph-xai`) should generally be reported upstream to that
project as well.
