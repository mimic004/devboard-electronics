"""bom_lint.py - the traps that cost money.

Every case here is a real mistake that a Markdown "Drives CAD" column warns
about but cannot catch.
"""

from __future__ import annotations

from conftest import codes, finding, run_tool


def test_connector_pitch_mismatch(fx):
    """A 2.0 mm cell lead will not go into a 1.25 mm socket. They do not mate."""
    out, rc = run_tool("bom_lint.py", fx("bom_traps.json"))
    assert rc == 1
    f = finding(out, "CONNECTOR_MISMATCH")
    assert {f["pitch_a"], f["pitch_b"]} == {2.0, 1.25}
    assert f["severity"] == "error"


def test_cell_below_the_charger_minimum(fx):
    """Charge current is fixed in hardware, so the CELL has to move, not the code."""
    out, _ = run_tool("bom_lint.py", fx("bom_traps.json"), "--power", fx("power_amp_on_ldo.json"))
    f = finding(out, "CAPACITY_BELOW_CHARGER_MIN")
    assert f["capacity_mah"] == 500
    assert f["min_cell_mah"] == 600
    assert "1.20 C" in f["message"]


def test_unresolved_variant_locked_at_order(fx):
    """A regional radio band cannot be changed after you press Buy."""
    out, _ = run_tool("bom_lint.py", fx("bom_traps.json"))
    variants = [f for f in out["findings"] if f["code"] == "VARIANT_UNRESOLVED"]
    axes = {f["axis"] for f in variants}
    assert "lora_frequency_band" in axes
    assert "diameter" in axes  # the 20-27 mm piezo


def test_seller_claimed_dimension_driving_cad(fx):
    """A guess with a price attached, about to be printed around."""
    out, _ = run_tool("bom_lint.py", fx("bom_traps.json"))
    rows = {f["row"] for f in out["findings"] if f["code"] == "PROVENANCE_SELLER_CLAIMED"}
    assert "speaker" in rows
    assert "piezo" in rows


def test_order_one_first_for_multiples(fx):
    """Eight unverified switches is just a more expensive wrong dimension."""
    out, _ = run_tool("bom_lint.py", fx("bom_traps.json"))
    f = finding(out, "ORDER_ONE_FIRST")
    assert f["row"] == "tactile_switches"


def test_height_convention_must_be_declared(fx):
    """W x L x H: the third figure is often to the top of the plunger, not the body."""
    out, _ = run_tool("bom_lint.py", fx("bom_traps.json"))
    rows = {f["row"] for f in out["findings"] if f["code"] == "DIMENSION_CONVENTION"}
    assert "tactile_switches" in rows
    f = finding(out, "DIMENSION_CONVENTION")
    assert "plunger" in f["fix"]


def test_filled_filament_with_an_rf_part(fx):
    out, _ = run_tool("bom_lint.py", fx("bom_traps.json"))
    f = finding(out, "RF_FILAMENT")
    assert f["material"] == "carbon_filled"
    assert "2.4 GHz" in f["fix"]


def test_silent_failure_needs_a_liveness_check(fx):
    """A dead sensor that fails silently stops the whole system with no error."""
    out, _ = run_tool("bom_lint.py", fx("bom_traps.json"))
    f = finding(out, "SILENT_FAILURE_NO_MONITOR")
    assert f["row"] == "zigbee_sensor"


def test_unmetered_polarity_on_a_two_pin_power_connector(fx):
    out, _ = run_tool("bom_lint.py", fx("bom_traps.json"))
    rows = {f["row"] for f in out["findings"] if f["code"] == "POLARITY_UNVERIFIED"}
    assert rows == {"mainboard", "battery"}


def test_pager_bom_is_clean(example):
    out, rc = run_tool("bom_lint.py", example("pager-style-handheld", "bom.json"), "--strict")
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["counts"]["error"] == 0


def test_pager_bom_agrees_with_its_manifest(example):
    """Every drives_cad parameter must exist on the CAD side of the contract."""
    out, rc = run_tool(
        "bom_lint.py",
        example("pager-style-handheld", "bom.json"),
        "--manifest",
        example("pager-style-handheld", "component-manifest.json"),
        "--power",
        example("pager-style-handheld", "power.json"),
        "--strict",
    )
    assert rc == 0
    assert "DRIVES_CAD_ORPHAN" not in codes(out)


def test_distinct_connector_pitches_are_credited(example):
    """Making a cross-plug physically impossible is a virtue worth noticing."""
    out, _ = run_tool("bom_lint.py", example("pager-style-handheld", "bom.json"))
    assert "CONNECTOR_CROSSPLUG_SAFE" in codes(out)
    assert "CONNECTOR_CROSSPLUG" not in codes(out)


def test_a_mating_pair_is_not_a_cross_plug(example):
    """Two rows that mate with each other share a connector by definition."""
    out, _ = run_tool("bom_lint.py", example("esp32s3-lipo-sensor", "bom.json"), "--strict")
    assert "CONNECTOR_CROSSPLUG" not in codes(out)


def test_bom_renders_a_drives_cad_table(example, tmp_path):
    md = tmp_path / "bom.md"
    out, rc = run_tool(
        "bom_lint.py", example("pager-style-handheld", "bom.json"), "--render", str(md)
    )
    assert rc == 0
    text = md.read_text(encoding="utf-8")
    assert "Drives CAD" in text
    assert "spk_d" in text
    assert "handoff_lint.py --check-lock" in text
