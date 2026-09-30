"""Shared test helpers.

Every tool is invoked the way the agent invokes it - as a subprocess whose only
contract is one JSON object on stdout plus an exit code - so the tests exercise
the actual interface rather than the Python API behind it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Tuple

import pytest

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
EXAMPLES = os.path.join(SKILL_ROOT, "examples")


def run_tool(script: str, *args: str) -> Tuple[Dict[str, Any], int]:
    """Run a skill tool and return (parsed stdout JSON, exit code)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(SKILL_ROOT, script), *args],
        capture_output=True,
        text=True,
        cwd=SKILL_ROOT,
    )
    assert proc.stdout.strip(), (
        f"{script} produced no stdout. stderr was:\n{proc.stderr}"
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        raise AssertionError(
            f"{script} did not emit a single JSON object on stdout: {exc}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        ) from exc
    return payload, proc.returncode


def codes(payload: Dict[str, Any]) -> List[str]:
    return [f["code"] for f in payload.get("findings", [])]


def finding(payload: Dict[str, Any], code: str) -> Dict[str, Any]:
    matches = [f for f in payload.get("findings", []) if f["code"] == code]
    assert matches, f"expected a {code} finding, got {codes(payload)}"
    return matches[0]


def severity_of(payload: Dict[str, Any], code: str) -> str:
    return finding(payload, code)["severity"]


@pytest.fixture
def fx():
    """Path to a file in tests/fixtures."""

    def _fx(name: str) -> str:
        path = os.path.join(FIXTURES, name)
        assert os.path.isfile(path), f"missing fixture {name}"
        return path

    return _fx


@pytest.fixture
def example():
    """Path to a file inside one of the worked examples."""

    def _example(project: str, name: str) -> str:
        path = os.path.join(EXAMPLES, project, name)
        assert os.path.isfile(path), f"missing example file {project}/{name}"
        return path

    return _example
