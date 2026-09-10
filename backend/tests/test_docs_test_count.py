"""The README states how many backend tests there are. Keep it true.

A number written into prose goes stale the moment a test is added, and nothing
notices, because nothing reads prose. The README said 98 while the suite ran
101 -- a small number, but it is the first thing a reader checks the repo
against, and a reader who runs the command and gets a different number has to
decide which of the two to believe.

So the number is derived here rather than trusted: this collects the suite in a
subprocess and compares the total against every statement in the docs that
names a pytest count. Adding a test now either updates the README or reds CI.

A statement that is deliberately frozen -- a changelog entry describing what
was true at a release -- belongs in HISTORICAL_COUNTS with the reason, not in
the live set.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).resolve().parents[1]

# (path relative to repo root, the exact stated count, why it is frozen).
# Nothing here yet; a CHANGELOG line describing a past release would go here.
HISTORICAL_COUNTS: list[tuple[str, int, str]] = []

# A count claim is "live" when the same line names the command that produces it.
_COUNT_ON_A_PYTEST_LINE = re.compile(r"(\d{1,4})\s+tests?\b")


def _collected_test_count() -> int:
    """Collect the suite in a subprocess and return the number of tests.

    A subprocess, not this process's own collection, so the answer does not
    depend on how the caller invoked pytest: `-k`, a single file, or
    `--last-failed` would all otherwise report a smaller suite and turn this
    into a check that fails for the wrong reason.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        pytest.fail(f"collection failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    match = re.search(r"^(\d+) tests? collected", proc.stdout, re.M)
    if match is None:
        pytest.fail(f"could not read a collected count from:\n{proc.stdout[-2000:]}")
    return int(match.group(1))


def _live_claims() -> list[tuple[Path, int, str]]:
    """Every docs line that states a pytest test count, with its number."""
    frozen = {(REPO_ROOT / p).resolve() for p, _, _ in HISTORICAL_COUNTS}
    out: list[tuple[Path, int, str]] = []
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if "node_modules" in path.parts or ".git" in path.parts:
            continue
        if path.resolve() in frozen:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            # Only lines that also name the command, so the frontend's
            # "npm test  # 36 tests" is not compared against the pytest total.
            if "pytest" not in line:
                continue
            for match in _COUNT_ON_A_PYTEST_LINE.finditer(line):
                out.append((path, int(match.group(1)), line.strip()))
    return out


def test_every_stated_pytest_count_is_the_current_one():
    total = _collected_test_count()
    claims = _live_claims()
    assert claims, (
        "no docs line states a pytest count any more. If that is deliberate, "
        "delete this test; if a line was reworded, this check just went blind."
    )
    stale = [
        f"{path.relative_to(REPO_ROOT)}: says {stated}, suite has {total} -- {line!r}"
        for path, stated, line in claims
        if stated != total
    ]
    assert not stale, "stale test counts:\n  " + "\n  ".join(stale)
