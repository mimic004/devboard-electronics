"""hw.py - the phase gates, and the three project shapes they must all serve.

The bug these tests exist for: phase 0 used to fail any project whose owner had
no multimeter, including a pill box watched by a vendor sensor on its own coin
cell - which has no rails, no charge current and no sleep current to meter. That
is the "every project is a reference project A" failure, and it would have refused to help
with the far more common hobbyist case.
"""

from __future__ import annotations

import os
import json

from conftest import codes, finding, run_tool


def _project(tmp_path, **over):
    base = {
        "schema": "hardware-electronics/project",
        "version": "1.0",
        "project": "fixture",
        "voltage_class": {"max_v": 5.0, "kind": "dc", "mains_involved": False},
        "application": {"description": "a gadget", "safety_critical": False},
        "tools": {"multimeter": False, "calipers": True},
        "skipped": [],
    }
    base.update(over)
    p = tmp_path / "project.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return str(tmp_path)


def test_no_multimeter_fails_when_something_needs_metering(tmp_path):
    d = _project(tmp_path)
    out, rc = run_tool("hw.py", "check", "--phase", "0", "--dir", d)
    assert rc == 1
    f = finding(out, "NO_MULTIMETER")
    assert f["severity"] == "error"
    assert f["live_metered_phases"] == [3, 6, 7]


def test_no_multimeter_is_fine_when_nothing_is_powered(tmp_path):
    """A pill box with a vendor sensor on a coin cell has nothing to meter."""
    d = _project(
        tmp_path,
        skipped=[
            {"phase": 3, "reason": "The only active part is a vendor sensor with its own cell."},
            {"phase": 6, "reason": "There is no board to bring up."},
            {"phase": 7, "reason": "There are no peripherals to probe."},
        ],
    )
    out, rc = run_tool("hw.py", "check", "--phase", "0", "--dir", d)
    assert rc == 0
    f = finding(out, "NO_MULTIMETER_NOT_NEEDED")
    assert f["severity"] == "info"
    assert out["reachable_gates"]["metered_gates_in_scope"] is False
    assert "NO_MULTIMETER" not in codes(out)


def test_partially_skipped_still_demands_a_meter(tmp_path):
    """Skipping the power budget does not excuse you from bring-up."""
    d = _project(
        tmp_path,
        skipped=[{"phase": 3, "reason": "No rails to balance in this build at all."}],
    )
    out, rc = run_tool("hw.py", "check", "--phase", "0", "--dir", d)
    assert rc == 1
    assert finding(out, "NO_MULTIMETER")["live_metered_phases"] == [6, 7]


def test_mains_is_refused(tmp_path):
    d = _project(
        tmp_path,
        voltage_class={"max_v": 230.0, "kind": "ac", "mains_involved": True},
        tools={"multimeter": True, "calipers": True},
    )
    out, rc = run_tool("hw.py", "check", "--phase", "0", "--dir", d)
    assert rc == 4
    assert finding(out, "MAINS_REFUSED")["severity"] == "refusal"


def test_a_dispenser_is_refused_but_a_reminder_is_not(tmp_path):
    """The boundary is real and it is narrow."""
    d = _project(
        tmp_path,
        application={
            "description": "dispenses the right pill at the right time",
            "safety_critical": True,
            "safety_category": "medical",
        },
        tools={"multimeter": True, "calipers": True},
    )
    out, rc = run_tool("hw.py", "check", "--phase", "0", "--dir", d)
    assert rc == 4
    f = finding(out, "SAFETY_CRITICAL_REFUSED")
    assert "REMINDER" in f["fix"]


def test_missing_artifact_is_not_the_same_as_a_deliberate_skip(tmp_path):
    d = _project(tmp_path, tools={"multimeter": True, "calipers": True})
    out, rc = run_tool("hw.py", "check", "--phase", "3", "--dir", d)
    assert rc == 1
    f = finding(out, "PHASE_INPUT_MISSING")
    assert "look identical from the outside" in f["fix"]


def test_phases_command_lists_all_nine(tmp_path):
    out, rc = run_tool("hw.py", "phases")
    assert rc == 0
    assert [p["n"] for p in out["phases"]] == list(range(10))
    assert all(p["built"] for p in out["phases"])


# --------------------------------------------------------------------------
# the three project shapes
# --------------------------------------------------------------------------


def test_sensor_shape_passes_every_applicable_gate(example):
    d = os.path.dirname(example("esp32s3-lipo-sensor", "project.json"))
    for phase in (0, 1, 2, 3, 4, 9):
        out, rc = run_tool("hw.py", "check", "--phase", str(phase), "--dir", d)
        assert rc == 0, f"phase {phase}: {[f for f in out['findings'] if f['severity'] != 'info']}"


def test_pager_shape_fails_only_where_it_should(example):
    d = os.path.dirname(example("pager-style-handheld", "project.json"))
    expected = {0: 0, 1: 0, 2: 0, 3: 1, 4: 0, 5: 0, 8: 0, 9: 1}
    for phase, want in expected.items():
        _, rc = run_tool("hw.py", "check", "--phase", str(phase), "--dir", d)
        assert rc == want, f"phase {phase} exited {rc}, expected {want}"


def test_vendor_sensor_shape_passes_every_applicable_gate(example):
    """No MCU, no firmware, no rails, no wiring - and still a real project."""
    d = os.path.dirname(example("vendor-sensor-enclosure", "project.json"))
    for phase in (0, 1, 2, 8, 9):
        out, rc = run_tool("hw.py", "check", "--phase", str(phase), "--dir", d)
        assert rc == 0, f"phase {phase}: {[f for f in out['findings'] if f['severity'] != 'info']}"


def test_vendor_sensor_orientation_and_liveness_are_enforced(example):
    out, rc = run_tool(
        "handoff_lint.py",
        example("vendor-sensor-enclosure", "component-manifest.json"),
        "--bom", example("vendor-sensor-enclosure", "bom.json"),
        "--strict",
    )
    assert rc == 0
    assert "ORIENTATION_UNCONSTRAINED" not in codes(out)

    bom_out, bom_rc = run_tool(
        "bom_lint.py", example("vendor-sensor-enclosure", "bom.json"), "--strict"
    )
    assert bom_rc == 0
    assert "SILENT_FAILURE_NO_MONITOR" not in codes(bom_out)


def test_a_clean_audit_is_not_an_empty_one(example):
    """Every gate closed is a pass. No sources at all is not."""
    out, rc = run_tool(
        "measure_log.py",
        "--ledger", example("vendor-sensor-enclosure", "measurements.jsonl"),
        "--strict", "audit",
        "--manifest", example("vendor-sensor-enclosure", "component-manifest.json"),
        "--bom", example("vendor-sensor-enclosure", "bom.json"),
    )
    assert rc == 0
    assert "AUDIT_NO_OPEN_GATES" in codes(out)
    assert "NO_GATES_DECLARED" not in codes(out)
    assert len(out["sources"]) == 2

