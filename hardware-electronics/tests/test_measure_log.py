"""measure_log.py - the provenance ledger.

The honesty machine. These tests check that the only path from a guess to a
verified number runs through an instrument, and that nothing can shortcut it.
"""

from __future__ import annotations

import json

from conftest import codes, finding, run_tool


def _ledger(tmp_path):
    return str(tmp_path / "measurements.jsonl")


def test_record_and_read_back(tmp_path):
    led = _ledger(tmp_path)
    out, rc = run_tool(
        "measure_log.py", "--ledger", led, "record",
        "--key", "cell.thickness", "--value", "7.4", "--unit", "mm",
        "--provenance", "measured",
        "--instrument", "Mitutoyo calipers, thickest point",
    )
    assert rc == 0
    assert out["recorded"] is True

    out, rc = run_tool("measure_log.py", "--ledger", led, "get", "--key", "cell.thickness")
    assert rc == 0
    assert out["entry"]["value"] == 7.4
    assert out["verified"] is True


def test_measured_without_an_instrument_is_refused(tmp_path):
    """There is no flag that fakes a measurement. Exit 4."""
    out, rc = run_tool(
        "measure_log.py", "--ledger", _ledger(tmp_path), "record",
        "--key", "sleep_ua", "--value", "18", "--provenance", "measured",
    )
    assert rc == 4
    f = finding(out, "MEASURED_WITHOUT_INSTRUMENT")
    assert f["severity"] == "refusal"
    assert out.get("recorded") is False


def test_weaker_provenance_may_not_quietly_overwrite_stronger(tmp_path):
    led = _ledger(tmp_path)
    run_tool(
        "measure_log.py", "--ledger", led, "record",
        "--key", "flash_mb", "--value", "8", "--provenance", "measured",
        "--instrument", "esp_flash_get_size() on silicon",
    )
    out, rc = run_tool(
        "measure_log.py", "--ledger", led, "record",
        "--key", "flash_mb", "--value", "16", "--provenance", "vendor_claim",
    )
    assert rc == 4
    assert finding(out, "PROVENANCE_DEMOTION")["severity"] == "refusal"


def test_demotion_is_possible_but_must_be_deliberate(tmp_path):
    led = _ledger(tmp_path)
    run_tool(
        "measure_log.py", "--ledger", led, "record",
        "--key", "x", "--value", "1", "--provenance", "measured", "--instrument", "meter",
    )
    out, rc = run_tool(
        "measure_log.py", "--ledger", led, "record",
        "--key", "x", "--value", "2", "--provenance", "assumed",
        "--allow-demotion", "--note", "the earlier reading was taken on the wrong pin",
    )
    assert rc == 0
    assert out["recorded"] is True


def test_supersession_is_recorded(tmp_path):
    """The 16 MB -> 8 MB case: silicon beats the listing, and the history survives."""
    led = _ledger(tmp_path)
    run_tool(
        "measure_log.py", "--ledger", led, "record",
        "--key", "flash_mb", "--value", "16", "--provenance", "datasheet",
    )
    out, _ = run_tool(
        "measure_log.py", "--ledger", led, "record",
        "--key", "flash_mb", "--value", "8", "--provenance", "measured",
        "--instrument", "esp_flash_get_size() on silicon",
        "--note", "Settles the 8 vs 16 MB conflict in favour of the board definition.",
    )
    assert out["entry"]["supersedes"]["value"] == 16
    assert out["entry"]["supersedes"]["provenance"] == "datasheet"
    assert "PROMOTED" in codes(out)


def test_audit_fails_while_a_build_critical_number_is_a_guess(example, tmp_path):
    """The pager's sleep current and charge resistor are open gates."""
    out, rc = run_tool(
        "measure_log.py",
        "--ledger", example("pager-style-handheld", "measurements.jsonl"),
        "audit",
        "--manifest", example("pager-style-handheld", "component-manifest.json"),
    )
    assert rc == 1
    keys = {f["key"] for f in out["findings"] if f["code"] == "GATE_OPEN"}
    assert "mainboard.sleep_current_ua" in keys
    assert "mainboard.charge.prog_resistor_ohm" in keys
    gate = [f for f in out["findings"] if f.get("key") == "mainboard.sleep_current_ua"][0]
    assert "USB DISCONNECTED" in gate["fix"]


def test_audit_passes_when_every_gate_is_closed(example):
    out, rc = run_tool(
        "measure_log.py",
        "--ledger", example("esp32s3-lipo-sensor", "measurements.jsonl"),
        "audit",
        "--bom", example("esp32s3-lipo-sensor", "bom.json"),
    )
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["gates_open"] == 0
    assert out["gates_closed"] > 0


def test_audit_over_nothing_is_not_a_pass(tmp_path):
    out, rc = run_tool("measure_log.py", "--ledger", _ledger(tmp_path), "--strict", "audit")
    assert rc == 1
    assert "NO_GATES_DECLARED" in codes(out)


def test_report_produces_the_two_tier_table(example):
    out, _ = run_tool(
        "measure_log.py",
        "--ledger", example("pager-style-handheld", "measurements.jsonl"),
        "report",
    )
    md = out["report_markdown"]
    assert "## Verified on hardware" in md
    assert "## Not yet measured" in md
    assert "guess with a price attached" in md
    assert out["verified_count"] > 0


def test_sweep_bounded_from_the_wrong_end(tmp_path):
    """Of 3.0 / 3.2 / 3.4 / 3.6, only 3.0 gripped - so 3.0 was never bracketed."""
    out, rc = run_tool(
        "measure_log.py", "--ledger", _ledger(tmp_path), "sweep",
        "--key", "clip.interference",
        "--values", "3.0", "3.2", "3.4", "3.6",
        "--winner", "3.0",
    )
    assert rc == 1
    f = finding(out, "SWEEP_BOUNDED_WRONG")
    assert "smallest" in f["message"]
    assert "second round" in f["fix"]


def test_sweep_properly_bracketed(tmp_path):
    out, rc = run_tool(
        "measure_log.py", "--ledger", _ledger(tmp_path), "sweep",
        "--key", "ring.bore",
        "--values", "20.2", "20.4", "20.6", "20.8",
        "--winner", "20.6",
    )
    assert rc == 0
    assert "SWEEP_BRACKETED" in codes(out)


def test_sweep_recording_needs_an_instrument(tmp_path):
    out, rc = run_tool(
        "measure_log.py", "--ledger", _ledger(tmp_path), "sweep",
        "--key", "ring.bore", "--values", "20.2", "20.4", "20.6",
        "--winner", "20.4", "--record",
    )
    assert rc == 4
    assert "MEASURED_WITHOUT_INSTRUMENT" in codes(out)


def test_sweep_records_when_bracketed_and_instrumented(tmp_path):
    led = _ledger(tmp_path)
    out, rc = run_tool(
        "measure_log.py", "--ledger", led, "sweep",
        "--key", "ring.bore", "--values", "20.2", "20.4", "20.6",
        "--winner", "20.4", "--record",
        "--instrument", "printed fit coupon B, calipers",
    )
    assert rc == 0
    assert out["recorded"] is True
    entry = json.loads(open(led, encoding="utf-8").read().strip().splitlines()[-1])
    assert entry["provenance"] == "measured"
    assert entry["sweep"]["winner"] == 20.4


def test_unknown_provenance_value_is_rejected(tmp_path):
    out, rc = run_tool(
        "measure_log.py", "--ledger", _ledger(tmp_path), "record",
        "--key", "x", "--value", "1", "--provenance", "probably_fine",
    )
    assert rc == 2
