"""The examples, their recorded output and their README stay in sync."""

from __future__ import annotations

from pathlib import Path

import verify_examples

EXAMPLES = Path(verify_examples.__file__).parent
HELPERS = {"_models", "verify_examples"}
ALL = (*verify_examples.OFFLINE, *verify_examples.LIVE)


def test_every_example_is_either_verified_or_live():
    scripts = {path.stem for path in EXAMPLES.glob("*.py")} - HELPERS
    assert scripts == set(ALL)
    assert len(ALL) == len(set(ALL))


def test_every_offline_example_has_recorded_output():
    recorded = {path.stem for path in verify_examples.EXPECTED.glob("*.txt")}
    assert recorded == set(verify_examples.OFFLINE)


def test_the_readme_links_every_example():
    readme = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    for name in ALL:
        assert f"[`{name}.py`]({name}.py)" in readme
