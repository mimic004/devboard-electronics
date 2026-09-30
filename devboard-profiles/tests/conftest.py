"""Shared test helpers for devboard-profiles.

Tools are invoked as subprocesses so the tests exercise the real interface: one
JSON object on stdout, plus an exit code.
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


def run_tool(script: str, *args: str) -> Tuple[Dict[str, Any], int]:
    proc = subprocess.run(
        [sys.executable, os.path.join(SKILL_ROOT, script), *args],
        capture_output=True,
        text=True,
        cwd=SKILL_ROOT,
    )
    assert proc.stdout.strip(), f"{script} produced no stdout. stderr:\n{proc.stderr}"
    try:
        return json.loads(proc.stdout), proc.returncode
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise AssertionError(
            f"{script} did not emit one JSON object: {exc}\n{proc.stdout}\n{proc.stderr}"
        ) from exc


def codes(payload: Dict[str, Any]) -> List[str]:
    return [f["code"] for f in payload.get("findings", [])]


def finding(payload: Dict[str, Any], code: str) -> Dict[str, Any]:
    matches = [f for f in payload.get("findings", []) if f["code"] == code]
    assert matches, f"expected a {code} finding, got {codes(payload)}"
    return matches[0]


def write(tmp_path, name: str, data: Any) -> str:
    p = tmp_path / name
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(p)


@pytest.fixture
def fx():
    def _fx(name: str) -> str:
        path = os.path.join(FIXTURES, name)
        assert os.path.isfile(path), f"missing fixture {name}"
        return path

    return _fx


@pytest.fixture
def parent():
    """The installed devboard-electronics skill, if there is one."""
    from proflib import find_parent  # noqa: E402

    sys.path.insert(0, SKILL_ROOT)
    p = find_parent()
    if not p:
        pytest.skip("devboard-electronics is not installed next to this skill")
    return p


def good_board(**over) -> Dict[str, Any]:
    """A minimal board profile that passes everything, for targeted mutation."""
    base: Dict[str, Any] = {
        "schema": "hardware-electronics/board",
        "version": "1.0",
        "id": "test_board",
        "display_name": "Test Board",
        "status": "active",
        "family": "ESP32-S3",
        "logic_v": 3.3,
        "gpio_valid": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "input_only": [],
        "strapping": {"0": "boot select", "3": "jtag select"},
        "rtc_capable": [0, 1, 2, 3, 4, 5],
        "adc1": {"1": "ADC1_CH0", "2": "ADC1_CH1"},
        "adc2": {"9": "ADC2_CH8"},
        "consumed": {"6": "flash", "7": "flash"},
        "free": [4, 5, 8],
        "conditional_free": {},
        "notes": ["ADC2 is unusable while Wi-Fi is active on this family."],
        "corroboration": {
            "sources": [
                {"id": "ds", "kind": "datasheet", "ref": "vendor datasheet section 2.2"},
                {"id": "sch", "kind": "schematic", "ref": "board schematic", "revision": "A"},
                {"id": "hdr", "kind": "variant_header", "ref": "core variants/test/pins_arduino.h"},
            ],
            "groups": {
                "gpio_map": {"sources": ["ds", "sch", "hdr"], "agreement": "full"},
                "strapping": {"sources": ["ds", "hdr"], "agreement": "full"},
                "adc": {"sources": ["ds", "hdr"], "agreement": "full"},
                "rtc_wake": {"sources": ["ds", "hdr"], "agreement": "full"},
            },
            "conservative": False,
            "contradictions": [],
        },
    }
    base.update(over)
    return base


def minimal_board(**over) -> Dict[str, Any]:
    """A board with ONLY a GPIO map, for tests that focus on corroboration.

    Stripping strapping, ADC and RTC data keeps those groups out of scope, so a
    corroboration test exercises one threshold instead of four.
    """
    base = good_board()
    for k in ("strapping", "adc1", "adc2", "rtc_capable", "radio"):
        base.pop(k, None)
    base["corroboration"] = {
        "sources": [
            {"id": "ds", "kind": "datasheet", "ref": "vendor datasheet section 2.2"},
            {"id": "sch", "kind": "schematic", "ref": "board schematic", "revision": "A"},
            {"id": "hdr", "kind": "variant_header", "ref": "core variants/test/pins_arduino.h"},
        ],
        "groups": {"gpio_map": {"sources": ["ds", "sch", "hdr"], "agreement": "full"}},
        "conservative": False,
        "contradictions": [],
    }
    base.update(over)
    return base


def good_part(**over) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "schema": "hardware-electronics/part",
        "version": "1.0",
        "id": "test_part",
        "description": "A test breakout",
        "status": "active",
        "class": "expander",
        "footprint": {
            "shape": "rect",
            "l": 20.0,
            "w": 15.0,
            "h": 3.0,
            "height_includes": "body_only",
            "provenance": "datasheet",
        },
        "logic_v": 3.3,
        "i2c": {
            "addresses": ["0x20", "0x21"],
            "default": "0x20",
            "address_select": "A0 strap",
            "onboard_pullup_ohm": 10000,
        },
        "failure_mode": "loud",
        "corroboration": {
            "sources": [{"id": "ds", "kind": "datasheet", "ref": "vendor datasheet"}],
            "groups": {
                "footprint": {"sources": ["ds"], "agreement": "full"},
                "electrical": {"sources": ["ds"], "agreement": "full"},
                "addressing": {"sources": ["ds"], "agreement": "full"},
            },
        },
    }
    base.update(over)
    return base
