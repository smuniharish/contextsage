"""The Agent Skill distribution follows the Agent Skills specification."""

from __future__ import annotations

import json
import re
import tomllib

from tests.support.paths import ROOT, SKILLS

NAMES = ("contextsage", "contextsage-extend")
_FRONTMATTER = re.compile(r"\A---\n(?P<header>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _frontmatter(name: str) -> tuple[dict[str, str], str]:
    path = SKILLS / "skills" / name / "SKILL.md"
    match = _FRONTMATTER.match(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
    assert match, f"{path} must start with YAML frontmatter"

    fields: dict[str, str] = {}
    description: list[str] = []
    current: str | None = None
    for line in match["header"].splitlines():
        if line.startswith("  ") and current == "description":
            description.append(line.strip())
        elif line.startswith("  version:") and current == "metadata":
            fields["metadata.version"] = line.partition(":")[2].strip().strip('"')
        elif line and not line.startswith(" "):
            key, separator, value = line.partition(":")
            assert separator
            current = key
            fields[key] = value.strip()
    fields["description"] = " ".join(description)
    return fields, match["body"]


def test_distribution_contains_both_skills_and_manifest():
    skills = sorted(path.name for path in (SKILLS / "skills").iterdir())
    assert skills == sorted(NAMES)
    manifest = json.loads((ROOT / "skills.sh.json").read_text(encoding="utf-8"))
    assert manifest["paths"] == ["./contextsage-skills/skills"]
    assert (SKILLS / "README.md").is_file()
    assert (SKILLS / "validation" / "README.md").is_file()


def test_skill_frontmatter_matches_the_package_version():
    with (ROOT / "pyproject.toml").open("rb") as project_file:
        version = tomllib.load(project_file)["project"]["version"]
    for name in NAMES:
        fields, _ = _frontmatter(name)
        assert fields["name"] == name
        assert 1 <= len(name) <= 64
        assert _NAME.fullmatch(name)
        assert fields["description"].startswith("Use this skill when")
        assert 1 <= len(fields["description"]) <= 1024
        assert fields["license"] == "Apache-2.0"
        assert fields["metadata.version"] == version


def test_skills_have_workflows_and_verification_guidance():
    required_sections = {
        "contextsage": (
            "## Activate when",
            "## Workflow",
            "## Configuration guide",
            "## Rules",
            "## Verify",
        ),
        "contextsage-extend": (
            "## Choose the boundary",
            "## Workflow",
            "## Adapter invariants",
            "## Dependency-component invariants",
            "## Verification",
        ),
    }
    for name, sections in required_sections.items():
        _, body = _frontmatter(name)
        assert len(body.splitlines()) < 500
        for section in sections:
            assert section in body
