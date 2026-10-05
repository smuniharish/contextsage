"""Run the offline examples and compare their output with the recorded output.

Usage:
    python examples/verify_examples.py            # verify every offline example
    python examples/verify_examples.py --update   # re-record the expected output

Each offline example runs in a fresh interpreter with a fixed hash seed and
UTF-8 output, and must print exactly ``examples/expected/<name>.txt``. The
live examples call a real model and are not verified here.
"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
EXPECTED = EXAMPLES / "expected"
OFFLINE = (
    "quickstart",
    "large_tool_output",
    "preservation",
    "policies",
    "recovery",
    "custom_parsing",
    "provenance",
    "observability",
    "observability_prometheus",
)
LIVE = ("live_agent", "deep_agent", "swarm")


def run(name: str) -> str:
    """Run one example and return what it printed."""
    environment = {
        **os.environ,
        "OBSERVABILITY_DEMO_SECONDS": "0",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
    }
    completed = subprocess.run(
        [sys.executable, str(EXAMPLES / f"{name}.py")],
        capture_output=True,
        check=False,
        cwd=EXAMPLES.parent,
        encoding="utf-8",
        env=environment,
    )
    if completed.returncode:
        raise SystemExit(
            f"{name}.py exited with {completed.returncode}:\n{completed.stderr}"
        )
    return completed.stdout.replace("\r\n", "\n")


def main() -> int:
    """Verify, or with ``--update`` re-record, every offline example."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--update", action="store_true", help="re-record the expected output"
    )
    update = parser.parse_args().update
    failed = []
    for name in OFFLINE:
        output = run(name)
        expected_path = EXPECTED / f"{name}.txt"
        if update:
            expected_path.write_text(output, encoding="utf-8", newline="\n")
            print(f"recorded {name}")
            continue
        expected = expected_path.read_text(encoding="utf-8")
        if output == expected:
            print(f"ok       {name}")
            continue
        failed.append(name)
        print(f"FAILED   {name}")
        sys.stdout.writelines(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                output.splitlines(keepends=True),
                f"expected/{name}.txt",
                f"{name}.py",
            )
        )
    if failed:
        print(f"{len(failed)} example(s) changed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
