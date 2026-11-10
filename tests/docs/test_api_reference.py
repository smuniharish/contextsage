"""The generated API reference is current, complete and syntactically valid."""

from __future__ import annotations

import ast

import pytest

from scripts import generate_api_reference
from tests.support.paths import DOCS

PAGE = generate_api_reference.render()
BLOCKS = generate_api_reference.code_blocks(PAGE)


def test_the_committed_reference_is_current():
    committed = (DOCS / "reference" / "index.md").read_text(encoding="utf-8")
    assert committed.replace("\r\n", "\n") == PAGE, (
        "the API reference is stale; run: python scripts/generate_api_reference.py"
    )


def test_every_exported_name_has_one_entry():
    generate_api_reference.check_coverage()
    for module in (generate_api_reference.PACKAGE, generate_api_reference.LANGCHAIN):
        for name in generate_api_reference.exported_names(module):
            if name != "__version__":
                assert PAGE.count(f"{{ #{module}.{name} }}") == 1, name


def test_the_reference_has_no_plugin_directives():
    assert not [line for line in PAGE.splitlines() if line.startswith(":::")]


@pytest.mark.parametrize("block", BLOCKS, ids=range(len(BLOCKS)))
def test_every_python_block_compiles(block: str):
    compile(block, "reference", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
