"""Generate the API reference page from the package source.

Usage:
    python scripts/generate_api_reference.py           # write docs/reference/index.md
    python scripts/generate_api_reference.py --check   # fail if the page is stale

The page is rendered from the source with the standard library alone: no
package is imported, so no optional integration needs to be installed.
Signatures come from the syntax tree and descriptions from the Google-style
docstrings. Every name exported by ``contextsage`` and by
``contextsage.integrations.langchain`` must appear exactly once.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import re
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
OUTPUT = ROOT / "docs" / "reference" / "index.md"
PACKAGE = "contextsage"
LANGCHAIN = "contextsage.integrations.langchain"
LINE_LIMIT = 88
_SOURCES: dict[int, str] = {}
"""Source text of every parsed node, by node identity; trees are cached."""

SECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Core engine", PACKAGE, ("ContextSummarizer", "SummarizationResult")),
    ("Message model", PACKAGE, ("Message", "ToolCall", "Fact", "SummaryLineage", "Role")),
    (
        "Extension ABCs",
        PACKAGE,
        (
            "FrameworkAdapter",
            "TokenCounter",
            "PreservationPolicy",
            "EventSink",
            "JSONCompaction",
            "PreservationThresholds",
        ),
    ),
    (
        "Configuration and events",
        PACKAGE,
        (
            "ParsingOptions",
            "default_patterns",
            "SummarizationEvent",
            "ValidationStatus",
            "RecoveryStatus",
            "DEFAULT_IDENTIFIER_PATTERNS",
            "DEFAULT_SUMMARY_PROMPT",
        ),
    ),
    (
        "Built-in implementations",
        PACKAGE,
        (
            "BalancedPolicy",
            "MaximumPreservationPolicy",
            "MaximumCompressionPolicy",
            "TokenizerTokenCounter",
            "LoggingEventSink",
            "CompositeEventSink",
            "OpenTelemetryEventSink",
        ),
    ),
    (
        "Errors and agxai",
        PACKAGE,
        ("ContextSageError", "ConfigurationError", "create_agxai_runtime"),
    ),
    (
        "Optional LangChain integration",
        LANGCHAIN,
        (
            "IntelligentSummarizationMiddleware",
            "LangChainAdapter",
            "LangChainSummaryModel",
            "LangChainTokenCounter",
            "LINEAGE_KEY",
        ),
    ),
)

INTRODUCTION = """\
# API reference

The public API is exported by the `contextsage` package. Internal names and
modules beginning with `_` are implementation details.

This page is generated from the source by `scripts/generate_api_reference.py`.
"""

LANGCHAIN_INTRODUCTION = """\
Install `contextsage[langchain]` to import
`contextsage.integrations.langchain`.
"""

_LIST_SECTIONS = {
    "Args": "Arguments",
    "Arguments": "Arguments",
    "Attributes": "Attributes",
    "Raises": "Raises",
    "Type Parameters": "Type parameters",
}
_TEXT_SECTIONS = {
    "Returns": "Returns",
    "Yields": "Yields",
    "Example": "Example",
    "Examples": "Examples",
}
_ADMONITIONS = {"Note": "note", "Notes": "note", "Warning": "warning"}
_SECTION = re.compile(r"^(?P<title>[A-Z][A-Za-z ]+):$")
_ITEM = re.compile(r"^(?P<name>\*{0,2}[\w.]+)(?:\s*\((?P<type>[^)]*)\))?:\s*(?P<text>.*)$")
_REFERENCE = re.compile(r"(?<!`)`(?P<name>contextsage(?:\.\w+)+)`(?!`)")
_KEPT_DECORATORS = {"property", "abstractmethod", "staticmethod", "classmethod", "cached_property"}


@dataclass(frozen=True, slots=True)
class Definition:
    """A top-level definition and the module that holds it."""

    node: ast.stmt
    docstring: str | None


def _module_file(module: str) -> Path:
    path = SOURCE.joinpath(*module.split("."))
    package = path / "__init__.py"
    return package if package.is_file() else path.with_suffix(".py")


@cache
def _parse(module: str) -> ast.Module:
    source = _module_file(module).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        _SOURCES[id(node)] = source
    return tree


def _text(node: ast.AST) -> str:
    """Return the source of ``node`` as written, on one line."""
    segment = ast.get_source_segment(_SOURCES[id(node)], node)
    assert segment is not None
    if "\n" not in segment:
        return segment
    segment = re.sub(r"\s*\n\s*", " ", segment)
    return re.sub(r",? ([\])])", r"\1", re.sub(r"([\[(]) ", r"\1", segment))


def _following_docstring(body: list[ast.stmt], index: int) -> str | None:
    if index + 1 < len(body):
        following = body[index + 1]
        if (
            isinstance(following, ast.Expr)
            and isinstance(following.value, ast.Constant)
            and isinstance(following.value.value, str)
        ):
            return inspect.cleandoc(following.value.value)
    return None


def _assigned_name(node: ast.stmt) -> str | None:
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id
    if isinstance(node, ast.TypeAlias):
        return node.name.id
    return None


def exported_names(module: str) -> list[str]:
    """Return the ``__all__`` of ``module``, read from its source."""
    for node in _parse(module).body:
        if _assigned_name(node) == "__all__":
            assert isinstance(node, ast.Assign | ast.AnnAssign)
            value = node.value
            assert isinstance(value, ast.List | ast.Tuple)
            return [ast.literal_eval(element) for element in value.elts]
    raise SystemExit(f"{module} defines no __all__")


def _resolve(module: str, name: str) -> Definition:
    """Find where ``name``, as seen from ``module``, is defined."""
    tree = _parse(module)
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == name:
                return Definition(node, ast.get_docstring(node))
        elif _assigned_name(node) == name:
            return Definition(node, _following_docstring(tree.body, index))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    return _resolve(node.module, alias.name)
    raise SystemExit(f"cannot find the definition of {module}.{name}")


def _decorators(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    kept = []
    for decorator in node.decorator_list:
        text = _text(decorator)
        if text.split(".")[-1] in _KEPT_DECORATORS or text.startswith("dataclass"):
            kept.append(f"@{text}")
    return kept


def _parameters(arguments: ast.arguments) -> list[str]:
    def parameter(argument: ast.arg, default: ast.expr | None, prefix: str = "") -> str:
        text = prefix + argument.arg
        if argument.annotation is not None:
            text += f": {_text(argument.annotation)}"
            if default is not None:
                text += f" = {_text(default)}"
        elif default is not None:
            text += f"={_text(default)}"
        return text

    positional = [*arguments.posonlyargs, *arguments.args]
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(arguments.defaults))
    defaults += arguments.defaults
    rendered = []
    for index, (argument, default) in enumerate(zip(positional, defaults, strict=True)):
        rendered.append(parameter(argument, default))
        if arguments.posonlyargs and index == len(arguments.posonlyargs) - 1:
            rendered.append("/")
    if arguments.vararg is not None:
        rendered.append(parameter(arguments.vararg, None, "*"))
    elif arguments.kwonlyargs:
        rendered.append("*")
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
        rendered.append(parameter(argument, default))
    if arguments.kwarg is not None:
        rendered.append(parameter(arguments.kwarg, None, "**"))
    return rendered


def _type_parameters(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    parameters = getattr(node, "type_params", [])
    return f"[{', '.join(_text(parameter) for parameter in parameters)}]" if parameters else ""


def _function_stub(node: ast.FunctionDef | ast.AsyncFunctionDef, indent: str = "") -> list[str]:
    keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {_text(node.returns)}" if node.returns is not None else ""
    head = f"{indent}{keyword} {node.name}{_type_parameters(node)}("
    parameters = _parameters(node.args)
    lines = [f"{indent}{decorator}" for decorator in _decorators(node)]
    single = f"{head}{', '.join(parameters)}){returns}: ..."
    if len(single) <= LINE_LIMIT:
        return [*lines, single]
    return [
        *lines,
        head,
        *(f"{indent}    {parameter}," for parameter in parameters),
        f"{indent}){returns}: ...",
    ]


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _class_stub(node: ast.ClassDef) -> list[str]:
    bases = [*map(ast.unparse, node.bases), *map(ast.unparse, node.keywords)]
    header = f"class {node.name}{_type_parameters(node)}"
    header += f"({', '.join(bases)}):" if bases else ":"
    body: list[str] = []
    for statement in node.body:
        name = _assigned_name(statement)
        if name is not None and _is_public(name):
            annotation = statement.annotation if isinstance(statement, ast.AnnAssign) else None
            if annotation is not None and "ClassVar" in _text(annotation):
                continue
            body.append(f"    {_text(statement)}")
        elif isinstance(statement, ast.FunctionDef) and statement.name == "__init__":
            if body:
                body.append("")
            body.extend(_function_stub(statement, "    "))
    if not body:
        return [*_decorators(node), f"{header} ..."]
    return [*_decorators(node), header, *body]


def _value_stub(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.TypeAlias):
        return [_text(node)]
    if isinstance(node, ast.AnnAssign):
        return [f"{_text(node.target)}: {_text(node.annotation)}"]
    assert isinstance(node, ast.Assign)
    name = _text(node.targets[0])
    value = _text(node.value)
    if len(value) <= 40:
        return [f"{name} = {value}"]
    if isinstance(node.value, ast.Constant):
        return [f"{name}: {type(node.value.value).__name__}"]
    raise SystemExit(f"{name} needs a type annotation to be documented")


class Renderer:
    """Renders definitions to Markdown with links between documented names."""

    def __init__(self, anchors: set[str]) -> None:
        self.anchors = anchors

    def link(self, text: str) -> str:
        """Link `contextsage.Name` references outside code fences."""
        parts = re.split(r"(^[ \t]*```.*?^[ \t]*```[ \t]*$)", text, flags=re.MULTILINE | re.DOTALL)
        for index in range(0, len(parts), 2):
            parts[index] = _REFERENCE.sub(self._link_match, parts[index])
        return "".join(parts)

    def _link_match(self, match: re.Match[str]) -> str:
        name = match["name"]
        return f"[`{name}`](#{name})" if name in self.anchors else match[0]

    def docstring(self, docstring: str | None) -> list[str]:
        """Render a Google-style docstring."""
        if not docstring:
            return []
        lines = docstring.splitlines()
        output: list[str] = []
        index = 0
        in_fence = False
        while index < len(lines):
            line = lines[index]
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
            section = None if in_fence else _SECTION.match(line)
            if section is None or section["title"] not in (
                _LIST_SECTIONS.keys() | _TEXT_SECTIONS.keys() | _ADMONITIONS.keys()
            ):
                output.append(line)
                index += 1
                continue
            index += 1
            block = []
            while index < len(lines) and (not lines[index].strip() or lines[index][:1] == " "):
                block.append(lines[index])
                index += 1
            while block and not block[-1].strip():
                block.pop()
            output.extend(self._section(section["title"], inspect.cleandoc("\n".join(block))))
        return self.link("\n".join(output).strip()).splitlines()

    def _section(self, title: str, block: str) -> list[str]:
        if title in _ADMONITIONS:
            indented = [f"    {line}" for line in block.splitlines()]
            return ["", f"!!! {_ADMONITIONS[title]}", "", *indented]
        if title in _TEXT_SECTIONS:
            return ["", f"**{_TEXT_SECTIONS[title]}**", "", *block.splitlines()]
        items: list[list[str]] = []
        for line in block.splitlines():
            item = _ITEM.match(line)
            if item is not None and not line.startswith(" "):
                kind = f" ({item['type']})" if item["type"] else ""
                items.append([f"- `{item['name']}`{kind}: {item['text']}"])
            elif items and line.strip():
                items[-1].append(f"  {line.strip()}")
        return ["", f"**{_LIST_SECTIONS[title]}**", "", *(line for item in items for line in item)]


def _heading(level: int, title: str, anchor: str) -> str:
    return f"{'#' * level} `{title}` {{ #{anchor} }}"


def _code(lines: list[str]) -> list[str]:
    return ["```python", *lines, "```"]


def _members(node: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Public methods, without overrides that only implement a documented contract."""
    return [
        statement
        for statement in node.body
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef)
        and _is_public(statement.name)
        and (
            ast.get_docstring(statement) is not None
            or not any(_text(decorator) == "override" for decorator in statement.decorator_list)
        )
    ]


def _attribute_docs(node: ast.ClassDef) -> list[tuple[str, str]]:
    documented = []
    for index, statement in enumerate(node.body):
        name = _assigned_name(statement)
        docstring = _following_docstring(node.body, index)
        if name is not None and _is_public(name) and docstring:
            documented.append((name, docstring))
    return documented


def _documented(module: str, names: tuple[str, ...]) -> list[tuple[str, str, Definition]]:
    return [(f"{module}.{name}", name, _resolve(module, name)) for name in names]


def _anchors() -> set[str]:
    anchors = set()
    for _, module, names in SECTIONS:
        for qualified, _, definition in _documented(module, names):
            anchors.add(qualified)
            if isinstance(definition.node, ast.ClassDef):
                anchors.update(f"{qualified}.{member.name}" for member in _members(definition.node))
    return anchors


def check_coverage() -> None:
    """Fail unless every exported name is documented exactly once."""
    for module in (PACKAGE, LANGCHAIN):
        exported = {name for name in exported_names(module) if name != "__version__"}
        listed = [name for _, owner, names in SECTIONS if owner == module for name in names]
        duplicated = sorted({name for name in listed if listed.count(name) > 1})
        missing = sorted(exported - set(listed))
        unknown = sorted(set(listed) - exported)
        if duplicated or missing or unknown:
            raise SystemExit(
                f"{module}: missing {missing}, not exported {unknown}, duplicated {duplicated}"
            )


def render() -> str:
    """Return the API reference page."""
    check_coverage()
    renderer = Renderer(_anchors())
    lines = INTRODUCTION.splitlines()
    for title, module, names in SECTIONS:
        lines += ["", f"## {title}", ""]
        if module == LANGCHAIN:
            lines += [*LANGCHAIN_INTRODUCTION.splitlines(), ""]
        for qualified, name, definition in _documented(module, names):
            node = definition.node
            lines += [_heading(3, name, qualified), ""]
            if isinstance(node, ast.ClassDef):
                lines += _code(_class_stub(node))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                lines += _code(_function_stub(node))
            else:
                lines += _code(_value_stub(node))
            if documentation := renderer.docstring(definition.docstring):
                lines += ["", *documentation]
            lines.append("")
            if not isinstance(node, ast.ClassDef):
                continue
            attributes = _attribute_docs(node)
            if attributes and "Attributes:" not in (definition.docstring or ""):
                lines += ["**Members**", ""]
                for attribute, docstring in attributes:
                    text = renderer.link(" ".join(docstring.split()))
                    lines.append(f"- `{attribute}`: {text}")
                lines.append("")
            for member in _members(node):
                lines += [_heading(4, f"{name}.{member.name}", f"{qualified}.{member.name}"), ""]
                lines += _code(_function_stub(member))
                if documentation := renderer.docstring(ast.get_docstring(member)):
                    lines += ["", *documentation]
                lines.append("")
    page = "\n".join(line.rstrip() for line in lines).rstrip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", page)


def code_blocks(page: str) -> list[str]:
    """Return the signature blocks of a rendered page, for syntax checks."""
    return re.findall(r"^```python\n(.*?)^```$", page, flags=re.MULTILINE | re.DOTALL)


def main() -> int:
    """Write the page, or with ``--check`` verify that it is current."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the page is stale")
    page = render()
    if parser.parse_args().check:
        current = OUTPUT.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != page:
            print("docs/reference/index.md is stale; run: python scripts/generate_api_reference.py")
            return 1
        print("docs/reference/index.md is current")
        return 0
    OUTPUT.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
