"""The Agent Skill distribution follows the Agent Skills specification."""

from __future__ import annotations

import re

from tests.support.paths import SKILLS

SKILL = SKILLS / "skills" / "contextsage"
_FRONTMATTER = re.compile(r"\A---\n(?P<header>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def frontmatter() -> tuple[dict[str, str], str]:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    assert match, "SKILL.md must start with YAML frontmatter"
    fields = dict(
        line.split(": ", 1) for line in match["header"].splitlines() if line.strip()
    )
    return fields, match["body"]


def test_distribution_contains_exactly_one_skill():
    skills = sorted(path.name for path in (SKILLS / "skills").iterdir())
    assert skills == ["contextsage"]
    assert (SKILLS / "README.md").is_file()
    assert (SKILLS / "validation" / "README.md").is_file()


def test_frontmatter_has_only_the_required_fields():
    fields, _ = frontmatter()
    assert list(fields) == ["name", "description"]


def test_name_matches_the_directory_and_the_specification():
    name = frontmatter()[0]["name"]
    assert name == SKILL.name
    assert 1 <= len(name) <= 64
    assert _NAME.fullmatch(name)


def test_description_says_what_the_skill_does_and_when_to_use_it():
    description = frontmatter()[0]["description"]
    assert 1 <= len(description) <= 1024
    assert "contextsage" in description
    assert "Use when" in description


def test_body_stays_within_the_recommended_size():
    body = frontmatter()[1]
    assert len(body.splitlines()) < 500
    for section in (
        "## Activate when",
        "## Required workflow",
        "## Integration rules",
        "## Prohibited shortcuts",
        "## Verification checklist",
    ):
        assert section in body
