"""pinmap_lint.py - pin, bus and address conflict validation.

The headline case is real: a resistor-ladder keypad on the only free pin of a
board whose every ADC1 channel is already consumed. Nothing about it looks wrong
until the Wi-Fi driver starts and every analog read returns a timeout.
"""

from __future__ import annotations

from conftest import codes, finding, run_tool


def test_resistor_ladder_keypad_is_rejected(fx):
    """The finding that killed a whole keypad design, reproduced."""
    out, rc = run_tool("pinmap_lint.py", fx("pinmap_resistor_ladder.json"))
    assert rc == 1
    assert out["ok"] is False

    adc2 = finding(out, "ADC2_WITH_WIFI")
    assert adc2["pin"] == 17
    assert adc2["severity"] == "error"
    assert "ESP_ERR_TIMEOUT" in adc2["message"]

    # And the fix has to be architectural, because there is nowhere to move it to.
    no_adc1 = finding(out, "NO_FREE_ADC1")
    assert no_adc1["severity"] == "error"
    assert "MCP23017" in no_adc1["fix"]


def test_wake_source_must_be_rtc_capable(fx):
    out, _ = run_tool("pinmap_lint.py", fx("pinmap_resistor_ladder.json"))
    f = finding(out, "WAKE_NOT_RTC")
    assert f["pin"] == 44
    assert "0-21" in f["message"]


def test_external_pull_on_a_strapping_pin_is_an_error(fx):
    out, _ = run_tool("pinmap_lint.py", fx("pinmap_resistor_ladder.json"))
    f = finding(out, "PIN_STRAPPING_PULL")
    assert f["pin"] == 45
    assert f["severity"] == "error"
    assert "1.8 V" in f["fix"]


def test_consumed_pin_is_rejected_with_its_owner_named(fx):
    out, _ = run_tool("pinmap_lint.py", fx("pinmap_resistor_ladder.json"))
    f = finding(out, "PIN_RESERVED")
    assert f["pin"] == 6
    assert "BUSY" in f["consumed_by"]


def test_duplicate_i2c_address_is_an_error(fx):
    out, _ = run_tool("pinmap_lint.py", fx("pinmap_resistor_ladder.json"))
    f = finding(out, "I2C_ADDR_COLLISION")
    assert f["addr"] == "0x20"
    assert sorted(f["devices"]) == ["expander", "second_expander"]


def test_three_stacked_module_pullups_are_flagged(fx):
    out, _ = run_tool("pinmap_lint.py", fx("pinmap_resistor_ladder.json"))
    f = finding(out, "I2C_PULLUP_STACKED")
    assert f["effective_ohm"] < 4000


def test_final_pager_pinmap_passes_strict(example):
    """The other half of the proof: the design that survives must come back clean."""
    out, rc = run_tool("pinmap_lint.py", example("pager-style-handheld", "pinmap.json"), "--strict")
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["ok"] is True
    assert out["counts"]["error"] == 0


def test_jtag_cost_is_acknowledgeable_not_silenceable(example):
    out, _ = run_tool("pinmap_lint.py", example("pager-style-handheld", "pinmap.json"), "--strict")
    jtag = finding(out, "JTAG_COST")
    assert jtag["severity"] == "info"
    assert jtag["accepted"] is True
    assert len(jtag["accepted_reason"]) > 40


def test_sensor_example_pinmap_is_clean(example):
    out, rc = run_tool("pinmap_lint.py", example("esp32s3-lipo-sensor", "pinmap.json"), "--strict")
    assert rc == 0
    assert out["counts"]["error"] == 0
    assert out["counts"]["warning"] == 0


def test_board_id_is_mandatory(tmp_path):
    """A pin question answered without a board ID is a guess wearing a number."""
    p = tmp_path / "no-board.json"
    p.write_text('{"schema":"hardware-electronics/pinmap","version":"1.0","nets":[]}', encoding="utf-8")
    out, rc = run_tool("pinmap_lint.py", str(p))
    assert rc == 2
    assert "BOARD_MISSING" in codes(out)


def test_unknown_board_lists_what_is_available(tmp_path):
    p = tmp_path / "bad-board.json"
    p.write_text(
        '{"schema":"hardware-electronics/pinmap","version":"1.0",'
        '"board":"not_a_real_board","nets":[]}',
        encoding="utf-8",
    )
    out, rc = run_tool("pinmap_lint.py", str(p))
    assert rc == 2
    f = finding(out, "BOARD_UNKNOWN")
    assert "heltec_vision_master_e290" in f["message"]


def test_superseded_board_warns_loudly(tmp_path):
    """GPIO 7 means opposite things on the two boards, so using the old one must say so."""
    p = tmp_path / "old-board.json"
    p.write_text(
        '{"schema":"hardware-electronics/pinmap","version":"1.0",'
        '"board":"crowpanel_213_v1","nets":[{"net":"panel_pwr","pin":7,"mode":"output"}]}',
        encoding="utf-8",
    )
    out, _ = run_tool("pinmap_lint.py", str(p))
    f = finding(out, "BOARD_SUPERSEDED")
    assert "heltec_vision_master_e290" in f["message"]
    reserved = finding(out, "PIN_RESERVED")
    assert "PANEL POWER ENABLE" in reserved["consumed_by"]


def test_double_booked_pin_names_both_owners(tmp_path):
    p = tmp_path / "clash.json"
    p.write_text(
        '{"schema":"hardware-electronics/pinmap","version":"1.0",'
        '"board":"esp32s3-generic","nets":['
        '{"net":"led","pin":4,"mode":"output"},'
        '{"net":"button","pin":4,"mode":"input_pullup"}]}',
        encoding="utf-8",
    )
    out, rc = run_tool("pinmap_lint.py", str(p))
    assert rc == 1
    f = finding(out, "PIN_DOUBLE_BOOKED")
    assert sorted(f["owners"]) == ["button", "led"]


def test_classic_esp32_input_only_pins(tmp_path):
    p = tmp_path / "classic.json"
    p.write_text(
        '{"schema":"hardware-electronics/pinmap","version":"1.0",'
        '"board":"esp32-classic","nets":[{"net":"relay","pin":34,"mode":"output"}]}',
        encoding="utf-8",
    )
    out, rc = run_tool("pinmap_lint.py", str(p))
    assert rc == 1
    f = finding(out, "PIN_INPUT_ONLY")
    assert f["pin"] == 34


def test_s3_reports_input_only_as_not_applicable(example):
    """The rule that does not transfer between families must say so, not stay silent."""
    out, _ = run_tool("pinmap_lint.py", example("pager-style-handheld", "pinmap.json"))
    assert any("no input-only GPIOs" in n for n in out.get("notes", []))


def test_pin_budget_shortfall_is_named(tmp_path):
    p = tmp_path / "budget.json"
    p.write_text(
        '{"schema":"hardware-electronics/pinmap","version":"1.0",'
        '"board":"heltec_vision_master_e290","nets":['
        '{"net":"a","pin":17,"mode":"output"},{"net":"b","pin":40,"mode":"output"},'
        '{"net":"c","pin":41,"mode":"output"},{"net":"d","pin":42,"mode":"output"},'
        '{"net":"e","pin":47,"mode":"output"},{"net":"f","pin":48,"mode":"output"}],'
        '"required_pins":{"digital":8,"reason":"an 8-key keypad wired directly"}}',
        encoding="utf-8",
    )
    out, rc = run_tool("pinmap_lint.py", str(p))
    assert rc == 1
    f = finding(out, "PIN_BUDGET_EXHAUSTED")
    assert f["shortfall"] > 0
    assert "expander" in f["fix"]


# --------------------------------------------------------------------------
# profile trustworthiness - patched in alongside the devboard-profiles skill
# --------------------------------------------------------------------------


def _board_copy(tmp_path, base: str, **over):
    """Copy an installed board profile into a temp dir, with overrides."""
    import json, os
    from conftest import SKILL_ROOT

    src = os.path.join(SKILL_ROOT, "boards", base + ".json")
    data = json.load(open(src, encoding="utf-8"))
    data.update(over)
    d = tmp_path / "boards"
    d.mkdir(exist_ok=True)
    (d / (data["id"] + ".json")).write_text(json.dumps(data), encoding="utf-8")
    return str(d), data["id"]


def _pinmap(tmp_path, board_id: str, name: str = "pm.json"):
    import json

    p = tmp_path / name
    p.write_text(
        json.dumps({
            "schema": "hardware-electronics/pinmap",
            "version": "1.0",
            "board": board_id,
            "nets": [{"net": "led", "pin": 17, "mode": "output"}],
        }),
        encoding="utf-8",
    )
    return str(p)


def test_draft_board_profile_is_flagged(tmp_path):
    """A clean pass against an uncorroborated profile is not evidence."""
    d, bid = _board_copy(tmp_path, "heltec_vision_master_e290", id="e290_draft", status="draft")
    out, rc = run_tool("pinmap_lint.py", _pinmap(tmp_path, bid), "--board-dir", d)
    f = finding(out, "BOARD_DRAFT")
    assert f["severity"] == "warning"
    assert "not been corroborated" in f["message"]
    assert "devboard-profiles" in f["fix"]


def test_board_with_no_corroboration_is_flagged(tmp_path):
    d, bid = _board_copy(
        tmp_path, "heltec_vision_master_e290", id="e290_bare", corroboration=None
    )
    out, _ = run_tool("pinmap_lint.py", _pinmap(tmp_path, bid), "--board-dir", d)
    f = finding(out, "BOARD_UNCORROBORATED")
    assert "why its pin numbers should be believed" in f["message"]


def test_thin_corroboration_is_flagged(tmp_path):
    """Two documents that copy each other are one source."""
    corr = {
        "sources": [
            {"id": "a", "kind": "datasheet", "ref": "vendor datasheet s2.2"},
            {"id": "b", "kind": "faq", "ref": "vendor FAQ restating the datasheet", "derives_from": "a"},
        ],
        "groups": {"gpio_map": {"sources": ["a", "b"], "agreement": "full"}},
    }
    d, bid = _board_copy(tmp_path, "heltec_vision_master_e290", id="e290_thin", corroboration=corr)
    out, _ = run_tool("pinmap_lint.py", _pinmap(tmp_path, bid), "--board-dir", d)
    f = finding(out, "BOARD_UNCORROBORATED")
    assert f["independent"] == 1
    assert f["required"] == 3


def test_conservative_profile_needs_fewer_sources(tmp_path):
    """Over-reserving has a safe failure mode, so the bar is lower."""
    out, rc = run_tool(
        "pinmap_lint.py", example_pinmap_for("esp32s3-generic", tmp_path), "--strict"
    )
    assert "BOARD_UNCORROBORATED" not in codes(out)
    assert "BOARD_CORROBORATED" in codes(out)


def example_pinmap_for(board_id: str, tmp_path):
    import json

    p = tmp_path / "gen.json"
    p.write_text(
        json.dumps({
            "schema": "hardware-electronics/pinmap",
            "version": "1.0",
            "board": board_id,
            "nets": [{"net": "led", "pin": 4, "mode": "output"}],
        }),
        encoding="utf-8",
    )
    return str(p)


def test_shipped_profiles_are_all_corroborated(example):
    """Every board a design can be validated against states why to believe it."""
    out, rc = run_tool("pinmap_lint.py", example("pager-style-handheld", "pinmap.json"), "--strict")
    assert rc == 0
    assert "BOARD_CORROBORATED" in codes(out)
    assert "BOARD_UNCORROBORATED" not in codes(out)


def test_unresolved_contradictions_surface_in_the_design_report(example):
    """The 18 vs 20 uA disagreement follows the board into every design."""
    out, _ = run_tool("pinmap_lint.py", example("pager-style-handheld", "pinmap.json"))
    fields = {f.get("field") for f in out["findings"] if f["code"] == "BOARD_CONTRADICTION"}
    assert "power.sleep_current_ua" in fields
