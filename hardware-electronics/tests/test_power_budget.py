"""power_budget.py - rails, charge sanity, duty cycles and honest runtimes.

The output is always simulated. These tests check that it says so, that the
arithmetic is right, and that the refusals are refusals rather than warnings.
"""

from __future__ import annotations

from conftest import codes, finding, run_tool


def test_class_d_amp_on_a_small_ldo(fx):
    """The average is harmless. The peak browns out the board."""
    out, rc = run_tool("power_budget.py", fx("power_amp_on_ldo.json"))
    assert rc == 1
    f = [x for x in out["findings"] if x["code"] == "RAIL_OVERDRAWN" and x.get("load") == "amp_max98357a"]
    assert f, codes(out)
    assert f[0]["peak_ma"] == 1000.0
    assert f[0]["rail"] == "3V3"
    assert "load switch" in f[0]["fix"]


def test_large_transient_without_bulk_capacitance(fx):
    out, _ = run_tool("power_budget.py", fx("power_amp_on_ldo.json"))
    loads = {f["load"] for f in out["findings"] if f["code"] == "TRANSIENT_NO_BULK"}
    assert {"amp_max98357a", "motor"} <= loads


def test_inductive_load_without_a_flyback_diode(fx):
    out, _ = run_tool("power_budget.py", fx("power_amp_on_ldo.json"))
    f = finding(out, "INDUCTIVE_NO_FLYBACK")
    assert f["load"] == "motor"


def test_duty_cycles_must_partition_the_time(fx):
    out, _ = run_tool("power_budget.py", fx("power_amp_on_ldo.json"))
    f = finding(out, "DUTY_SUM")
    assert abs(f["duty_sum"] - 0.9) < 1e-9


def test_charging_an_unprotected_cell_is_refused(fx):
    """Exit 4: a safety rule blocked the operation. Not a warning."""
    out, rc = run_tool("power_budget.py", fx("power_unprotected_cell.json"))
    assert rc == 4
    f = finding(out, "CELL_UNPROTECTED")
    assert f["severity"] == "refusal"
    assert out["counts"]["refusal"] == 1


def test_output_is_always_marked_simulated(example):
    out, _ = run_tool("power_budget.py", example("pager-style-handheld", "power.json"))
    assert out["source"] == "simulated"
    assert any("CALCULATED, not measured" in n for n in out["notes"])


def test_pager_runtime_arithmetic(example):
    out, _ = run_tool("power_budget.py", example("pager-style-handheld", "power.json"))
    assert abs(out["average_ma"] - 1.0903) < 0.002
    assert abs(out["runtime_days"] - 35.73) < 0.1
    assert abs(out["margin_x"] - 11.91) < 0.1


def test_margin_is_reported_not_just_a_bare_number(example):
    out, _ = run_tool("power_budget.py", example("pager-style-handheld", "power.json"))
    f = finding(out, "RUNTIME_MARGIN_OK")
    assert "margin" in f["message"]
    assert out["margin_x"] > 1


def test_conflicting_vendor_figures_produce_a_range(example):
    """18 uA or 20 uA, nobody has measured it, so the answer is a range."""
    out, _ = run_tool("power_budget.py", example("pager-style-handheld", "power.json"))
    assert "RUNTIME_IS_A_RANGE" in codes(out)
    lo, hi = out["runtime_days_range"]
    assert lo < hi


def test_unmeasured_share_is_quantified(example):
    out, rc = run_tool("power_budget.py", example("pager-style-handheld", "power.json"), "--strict")
    assert rc == 1, "an entirely unmeasured runtime estimate must not pass a strict gate"
    assert out["unmeasured_share"] == 1.0
    assert "vendor_claim" in out["provenance_shares"]
    assert "SLEEP_UNMEASURED" in codes(out)


def test_sleep_unmeasured_cannot_be_accepted_away(example, tmp_path):
    """You may proceed on an unmeasured estimate. You may not silence the caveat."""
    import json

    src = json.load(open(example("pager-style-handheld", "power.json"), encoding="utf-8"))
    src["accepted_findings"] = {"SLEEP_UNMEASURED": "we are in a hurry and it is probably fine"}
    p = tmp_path / "power.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool("power_budget.py", str(p))
    assert rc == 1
    f = finding(out, "ACCEPTANCE_NOT_PERMITTED")
    assert f["accepted_code"] == "SLEEP_UNMEASURED"
    assert finding(out, "SLEEP_UNMEASURED")["severity"] == "warning"


def test_fully_measured_project_passes_strict(example):
    out, rc = run_tool("power_budget.py", example("esp32s3-lipo-sensor", "power.json"), "--strict")
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["unmeasured_share"] == 0.0
    assert "SLEEP_UNMEASURED" not in codes(out)


def test_fixed_charge_current_emits_a_minimum_cell_size(example):
    out, _ = run_tool("power_budget.py", example("pager-style-handheld", "power.json"))
    f = finding(out, "CHARGE_FIXED_IN_HW")
    assert f["min_cell_mah"] == 600
    assert out["charge"]["c_rate"] < 1.0


def test_lifepo4_on_a_lithium_ion_charger_is_refused(tmp_path):
    import json

    data = {
        "schema": "hardware-electronics/power",
        "version": "1.0",
        "project": "fixture",
        "battery": {"chemistry": "lifepo4", "capacity_mah": 1500, "protection": True},
        "charge": {"ic": "TP4056", "ma": 500, "provenance": "datasheet"},
        "rails": [{"id": "VBAT", "rating_ma": 1500}],
        "loads": [{"id": "mcu", "rail": "VBAT", "i_avg_ma": 20.0, "provenance": "datasheet"}],
        "states": [{"id": "on", "duty": 1.0, "ma": 20.0, "provenance": "datasheet"}],
    }
    p = tmp_path / "lifepo4.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    out, rc = run_tool("power_budget.py", str(p))
    assert rc == 4
    assert finding(out, "CHEMISTRY_CHARGER_MISMATCH")["severity"] == "refusal"
