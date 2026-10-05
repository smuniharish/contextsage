# Security policy

## Supported versions

Security fixes are released for the latest minor version.

| Version | Supported |
| --- | --- |
| 1.0.x | Yes |
| 0.1.x | No |

## Reporting a vulnerability

Please do not report security vulnerabilities in public issues.

Report them privately through
[GitHub private vulnerability reporting](https://github.com/smuniharish/contextsage/security/advisories/new),
or by email to samamuniharish@gmail.com. Include:

- the affected ContextSage, LangChain and Python versions,
- a description of the vulnerability and its impact, and
- a minimal script or history that reproduces it, without real credentials or
  private conversation content.

The maintainer aims to acknowledge reports within five business days. Once
the issue is confirmed, a fix is prepared and released, and the vulnerability
is disclosed in a GitHub security advisory and the changelog, with credit to
the reporter unless you prefer otherwise.

## Scope

ContextSage treats conversation content, including tool output, as untrusted,
and its configuration, including custom parsers, routes and identifier
patterns, as trusted. The
[security guide](https://contextsage.readthedocs.io/en/latest/operations/security/)
describes this model: what leaves the process, what is logged and stored, and
how untrusted content is handled. Reports that require trusted code or
configuration to be malicious are out of scope. Vulnerabilities in a
dependency, such as LangChain, parsefabric or langgraph-xai, should also be
reported to that project.
