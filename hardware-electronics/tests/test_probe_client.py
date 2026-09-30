"""probe_client.py - where an implausibly good result becomes a failure.

The headline case: a 29 ms e-paper refresh that reported success while the panel
controller was unpowered. Nothing errored. Every line of the transcript says ok.
The only thing wrong with it is that it is physically impossible.
"""

from __future__ import annotations

import json

from conftest import codes, finding, run_tool


def test_the_29ms_panel_refresh_is_a_failure(example, fx):
    """A success that cannot physically have happened did not happen."""
    out, rc = run_tool(
        "probe_client.py",
        example("pager-style-handheld", "probes/epaper-panel.json"),
        "--transcript", fx("transcript_panel_29ms.json"),
    )
    assert rc == 1
    assert out["result"] == "ok", "the probe itself reported success - that is the point"

    f = finding(out, "IMPLAUSIBLE_SUCCESS")
    assert f["measurement"] == "busy_ms"
    assert f["value"] == 29
    assert f["band"] == [300, 3000]
    assert "too GOOD to be true" in f["message"]
    assert "Do not widen the band" in f["fix"]


def test_the_precondition_failure_is_caught_too(example, fx):
    """The rail never went high, which is the actual cause of the fast success.

    The rail probe itself returned ok. Only checking that the LEVEL moved
    catches it - which is the same lesson one layer down.
    """
    out, _ = run_tool(
        "probe_client.py",
        example("pager-style-handheld", "probes/epaper-panel.json"),
        "--transcript", fx("transcript_panel_29ms.json"),
    )
    f = finding(out, "PRECONDITION_FAILED")
    assert f["expected"] == "high"
    assert f["actual"] == "low"
    assert "never changed" in f["message"]


def test_a_real_refresh_passes(example, fx):
    out, rc = run_tool(
        "probe_client.py",
        example("pager-style-handheld", "probes/epaper-panel.json"),
        "--transcript", fx("transcript_panel_ok.json"),
    )
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["measurements"]["busy_ms"] == 1180
    assert "MEASUREMENT_PLAUSIBLE" in codes(out)
    assert "TRANSITION_OBSERVED" in codes(out)


def test_never_started_is_reported_as_never_started(example, fx):
    """Assert-before-release turns a silent lie into an explicit failure."""
    out, rc = run_tool(
        "probe_client.py",
        example("pager-style-handheld", "probes/epaper-panel.json"),
        "--transcript", fx("transcript_panel_never_started.json"),
    )
    assert rc == 1
    assert out["result"] == "fail"
    f = finding(out, "RESULT_MISMATCH")
    assert "Do NOT simply retry" in f["fix"]
    assert "MEASUREMENT_MISSING" in codes(out)


def test_exact_i2c_address_set(example, fx):
    out, rc = run_tool(
        "probe_client.py",
        example("pager-style-handheld", "probes/i2c.json"),
        "--transcript", fx("transcript_i2c_ok.json"),
    )
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["i2c_addresses"] == ["0x20", "0x5a"]
    assert "I2C_SET_EXACT" in codes(out)


def test_an_unexpected_device_is_as_interesting_as_a_missing_one(example, fx, tmp_path):
    src = json.load(open(fx("transcript_i2c_ok.json"), encoding="utf-8"))
    src["exchanges"][0]["rx"].insert(5, "probe.i2c.found 0x3c")
    src["exchanges"][0]["rx"] = [
        "probe.i2c.count 3" if ln.startswith("probe.i2c.count") else ln
        for ln in src["exchanges"][0]["rx"]
    ]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        "probe_client.py", example("pager-style-handheld", "probes/i2c.json"),
        "--transcript", str(p),
    )
    assert rc == 1
    f = finding(out, "I2C_SET_MISMATCH")
    assert f["unexpected"] == ["0x3c"]
    assert "EXACT, not a superset" in f["fix"]


def test_a_replayed_probe_is_never_called_hardware(example, fx):
    out, _ = run_tool(
        "probe_client.py", example("pager-style-handheld", "probes/i2c.json"),
        "--transcript", fx("transcript_i2c_ok.json"),
    )
    assert out["source"] == "recorded"
    assert any("may be described as measured" in n for n in out["notes"])


def test_a_spec_with_no_plausibility_band_is_flagged(tmp_path, fx):
    """A check that only asks 'did it error' manufactures false confidence."""
    spec = {
        "peripheral": "i2c_bus",
        "command": "PROBE i2c 39 38 100000",
        "expect": {"result": "ok"},
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")

    out, _ = run_tool("probe_client.py", str(p), "--transcript", fx("transcript_i2c_ok.json"))
    f = finding(out, "NO_PLAUSIBILITY_BAND")
    assert "29 ms" in f["fix"]


def test_transition_requirement_cannot_be_satisfied_by_a_steady_state(tmp_path, fx):
    """E-ink keeps its last image with no power. Demand a change you watched."""
    spec = {
        "peripheral": "panel",
        "command": "PROBE busy 6 18 active_high 5000",
        "expect": {"result": "ok"},
        "plausibility": {
            "busy_ms": {"min": 0, "max": 100000, "why": "deliberately wide for this test"}
        },
        "requires_transition": {
            "measurement": "frame_counter",
            "must_change": True,
            "why": "A static image survives a dead driver, a wiped flash and an unpowered board.",
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")

    out, rc = run_tool("probe_client.py", str(p), "--transcript", fx("transcript_panel_ok.json"))
    assert rc == 1
    f = finding(out, "TRANSITION_UNPROVEN")
    assert f["measurement"] == "frame_counter"


def test_retries_are_off_by_default(example, fx):
    """A retry that sometimes works is a wiring fault, not a flake."""
    out, _ = run_tool(
        "probe_client.py",
        example("pager-style-handheld", "probes/epaper-panel.json"),
        "--transcript", fx("transcript_panel_never_started.json"),
    )
    assert "RETRIED" not in codes(out)
