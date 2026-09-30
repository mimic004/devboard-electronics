"""profile_lint.py - self-consistency and research hygiene.

A profile is a liability if it is wrong, because the paired skill's pinmap_lint
will validate a design against it and report a clean pass. These tests cover the
two ways a profile goes wrong: it contradicts itself, or nobody checked it.
"""

from __future__ import annotations

from conftest import codes, finding, good_board, good_part, minimal_board, run_tool, write


# --------------------------------------------------------------------------
# self-consistency
# --------------------------------------------------------------------------


def test_a_good_profile_passes_strict(tmp_path):
    p = write(tmp_path, "b.json", good_board())
    out, rc = run_tool("profile_lint.py", p, "--kind", "board", "--strict")
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]


def test_adc_channel_on_a_nonexistent_pin(tmp_path):
    p = write(tmp_path, "b.json", good_board(adc1={"1": "ADC1_CH0", "99": "ADC1_CH9"}))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "PIN_NOT_IN_GPIO_VALID")
    assert f["field"] == "adc1"
    assert 99 in f["pins"]


def test_pin_both_free_and_consumed(tmp_path):
    p = write(tmp_path, "b.json", good_board(free=[4, 5, 6]))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "FREE_CLAIMS_CONSUMED_PIN")
    assert 6 in f["pins"]
    assert "dangerous direction" in f["fix"]


def test_same_pin_on_both_adc_banks(tmp_path):
    p = write(tmp_path, "b.json", good_board(adc2={"1": "ADC2_CH0"}))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "ADC_BANK_OVERLAP")
    assert 1 in f["pins"]


def test_consumed_may_document_a_pin_that_does_not_exist(tmp_path):
    """Saying why GPIO6-11 are missing is more useful than silence."""
    p = write(tmp_path, "b.json", good_board(consumed={"6": "flash", "7": "flash", "40": "not broken out"}))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board", "--strict")
    assert rc == 0
    f = finding(out, "CONSUMED_DOCUMENTS_ABSENT_PIN")
    assert f["severity"] == "info"
    assert 40 in f["pins"]


def test_wrong_family_copy_paste(tmp_path):
    """An S3 profile listing GPIO34-39 input-only was copied from a classic ESP32."""
    p = write(tmp_path, "b.json", good_board(input_only=[3, 4]))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "FAMILY_MISMATCH")
    assert "CLASSIC ESP32" in f["fix"]
    assert "rarely copied in only one place" in f["fix"]


def test_adc2_caveat_must_be_stated(tmp_path):
    p = write(tmp_path, "b.json", good_board(notes=["nothing useful here"]))
    out, _ = run_tool("profile_lint.py", p, "--kind", "board")
    f = finding(out, "ADC2_CAVEAT_MISSING")
    assert "once Wi-Fi comes up" in f["fix"]


def test_every_pin_rtc_capable_is_suspicious(tmp_path):
    p = write(tmp_path, "b.json", good_board(rtc_capable=list(range(11))))
    out, _ = run_tool("profile_lint.py", p, "--kind", "board")
    f = finding(out, "RTC_RANGE_SUSPECT")
    assert "sleeps and never wakes" in f["fix"]


def test_superseded_needs_a_successor(tmp_path):
    p = write(tmp_path, "b.json", good_board(status="superseded", superseded_by=None))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    assert "SUPERSEDED_WITHOUT_SUCCESSOR" in codes(out)


# --------------------------------------------------------------------------
# research hygiene
# --------------------------------------------------------------------------


def test_no_corroboration_at_all(tmp_path):
    p = write(tmp_path, "b.json", good_board(corroboration=None))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "CORROBORATION_MISSING")
    assert "no stated reason to believe anything" in f["message"]


def test_two_documents_that_copy_each_other_count_once(tmp_path):
    corr = {
        "sources": [
            {"id": "ds", "kind": "datasheet", "ref": "vendor datasheet 2.2"},
            {"id": "faq", "kind": "faq", "ref": "vendor FAQ", "derives_from": "ds"},
            {"id": "page", "kind": "product_page", "ref": "shop page", "derives_from": "ds"},
        ],
        "groups": {"gpio_map": {"sources": ["ds", "faq", "page"], "agreement": "full"}},
    }
    p = write(tmp_path, "b.json", minimal_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "CORROBORATION_INSUFFICIENT")
    assert f["independent"] == 1
    assert f["required"] == 3
    assert "sharing an upstream count once" in f["fix"]


def test_weak_sources_never_count(tmp_path):
    corr = {
        "sources": [
            {"id": "a", "kind": "listing", "ref": "marketplace listing"},
            {"id": "b", "kind": "product_page", "ref": "vendor page"},
            {"id": "c", "kind": "pinout_image", "ref": "pinout png"},
        ],
        "groups": {"gpio_map": {"sources": ["a", "b", "c"], "agreement": "full"}},
    }
    p = write(tmp_path, "b.json", minimal_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    assert "SOURCE_WEAK_ONLY" in codes(out)
    assert finding(out, "CORROBORATION_INSUFFICIENT")["independent"] == 0


def test_conservative_profile_needs_only_one_source(tmp_path):
    """Over-reserving fails safe, so the bar is lower - but it must be argued."""
    corr = {
        "sources": [{"id": "ds", "kind": "datasheet", "ref": "family datasheet"}],
        "groups": {"gpio_map": {"sources": ["ds"], "agreement": "full"}},
        "conservative": True,
        "conservative_rationale": "Family fallback: marks flash and PSRAM pins consumed unconditionally and never enumerates a free list.",
    }
    p = write(tmp_path, "b.json", minimal_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board", "--strict")
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]


def test_conservative_must_be_justified(tmp_path):
    corr = {
        "sources": [{"id": "ds", "kind": "datasheet", "ref": "family datasheet"}],
        "groups": {"gpio_map": {"sources": ["ds"], "agreement": "full"}},
        "conservative": True,
    }
    p = write(tmp_path, "b.json", minimal_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "CONSERVATIVE_UNJUSTIFIED")
    assert "argued rather than asserted" in f["fix"]


def test_active_status_requires_corroboration(tmp_path):
    corr = {
        "sources": [{"id": "ds", "kind": "datasheet", "ref": "vendor datasheet section 2.2"}],
        "groups": {"gpio_map": {"sources": ["ds"], "agreement": "full"}},
    }
    p = write(tmp_path, "b.json", minimal_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "ACTIVE_WITHOUT_CORROBORATION")
    assert "a promise about the data" in f["fix"]


def test_the_same_profile_is_acceptable_as_a_draft(tmp_path):
    corr = {
        "sources": [{"id": "ds", "kind": "datasheet", "ref": "vendor datasheet section 2.2"}],
        "groups": {"gpio_map": {"sources": ["ds"], "agreement": "full"}},
    }
    p = write(tmp_path, "b.json", minimal_board(status="draft", corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 0
    assert "PROFILE_IS_DRAFT" in codes(out)


def test_group_citing_an_undeclared_source(tmp_path):
    corr = {
        "sources": [{"id": "ds", "kind": "datasheet", "ref": "vendor datasheet section 2.2"}],
        "groups": {"gpio_map": {"sources": ["ds", "ghost"], "agreement": "full"}},
    }
    p = write(tmp_path, "b.json", minimal_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    assert "GROUP_SOURCE_UNKNOWN" in codes(out)


def test_conflicting_group_must_record_the_conflict(tmp_path):
    corr = good_board()["corroboration"]
    corr["groups"]["gpio_map"]["agreement"] = "conflicting"
    p = write(tmp_path, "b.json", good_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "CONFLICT_UNRECORDED")
    assert "Never average" in f["fix"]


def test_unresolved_contradiction_is_reported_not_hidden(tmp_path):
    corr = good_board()["corroboration"]
    corr["contradictions"] = [
        {
            "field": "power.sleep_current_ua",
            "readings": [
                {"value": 18, "source": "ds"},
                {"value": 20, "source": "sch"},
            ],
            "resolution": "unresolved",
            "impact": "Dominates any battery-life estimate.",
            "how_to_close": "Meter it, USB disconnected.",
        }
    ]
    p = write(tmp_path, "b.json", good_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 0
    f = finding(out, "CONTRADICTION_UNRESOLVED")
    assert f["severity"] == "warning"
    assert "Meter it" in f["fix"]


def test_choosing_a_reading_needs_a_reason(tmp_path):
    corr = good_board()["corroboration"]
    corr["contradictions"] = [
        {
            "field": "power.charge.ic",
            "readings": [{"value": "A", "source": "ds"}, {"value": "B", "source": "sch"}],
            "resolution": "chosen",
            "resolved_value": "B",
        }
    ]
    p = write(tmp_path, "b.json", good_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    f = finding(out, "CONTRADICTION_CHOSEN_BLINDLY")
    assert "must look weaker" in f["fix"]


def test_self_derived_source(tmp_path):
    corr = good_board()["corroboration"]
    corr["sources"][0]["derives_from"] = "ds"
    p = write(tmp_path, "b.json", good_board(corroboration=corr))
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    assert "SOURCE_SELF_DERIVED" in codes(out)


def test_errors_cannot_be_accepted_away(tmp_path):
    p = write(
        tmp_path, "b.json",
        good_board(
            input_only=[3],
            accepted_findings={"FAMILY_MISMATCH": "we are in a hurry and it is probably fine"},
        ),
    )
    out, rc = run_tool("profile_lint.py", p, "--kind", "board")
    assert rc == 1
    assert "ACCEPTANCE_NOT_PERMITTED" in codes(out)
    assert finding(out, "FAMILY_MISMATCH")["severity"] == "error"


# --------------------------------------------------------------------------
# parts
# --------------------------------------------------------------------------


def test_a_good_part_passes_strict(tmp_path):
    p = write(tmp_path, "p.json", good_part())
    out, rc = run_tool("profile_lint.py", p, "--kind", "part", "--strict")
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]


def test_round_part_needs_a_diameter(tmp_path):
    p = write(tmp_path, "p.json", good_part(footprint={"shape": "circle", "h": 4.0}))
    out, rc = run_tool("profile_lint.py", p, "--kind", "part")
    assert rc == 1
    f = finding(out, "FOOTPRINT_INCOMPLETE")
    assert "21%" in f["fix"]


def test_height_convention_must_be_declared(tmp_path):
    fp = good_part()["footprint"]
    del fp["height_includes"]
    p = write(tmp_path, "p.json", good_part(footprint=fp))
    out, _ = run_tool("profile_lint.py", p, "--kind", "part")
    f = finding(out, "HEIGHT_CONVENTION_MISSING")
    assert "plunger" in f["fix"]


def test_default_address_outside_the_declared_range(tmp_path):
    p = write(tmp_path, "p.json", good_part(i2c={"addresses": ["0x20"], "default": "0x5a", "address_select": "fixed"}))
    out, rc = run_tool("profile_lint.py", p, "--kind", "part")
    assert rc == 1
    assert "I2C_DEFAULT_NOT_IN_RANGE" in codes(out)


def test_fixed_address_must_say_so(tmp_path):
    p = write(tmp_path, "p.json", good_part(i2c={"addresses": ["0x5a"], "default": "0x5a", "onboard_pullup_ohm": None}))
    out, _ = run_tool("profile_lint.py", p, "--kind", "part")
    f = finding(out, "I2C_FIXED_ADDRESS_UNSTATED")
    assert "redesign" in f["fix"]


def test_silent_failure_forces_a_liveness_check(tmp_path):
    p = write(tmp_path, "p.json", good_part(failure_mode="silent"))
    out, rc = run_tool("profile_lint.py", p, "--kind", "part")
    assert rc == 1
    f = finding(out, "SILENT_WITHOUT_LIVENESS")
    assert "inherits the requirement" in f["fix"]


def test_part_with_a_functional_axis_should_record_it(tmp_path):
    p = write(tmp_path, "p.json", good_part(**{"class": "microphone"}))
    out, _ = run_tool("profile_lint.py", p, "--kind", "part")
    f = finding(out, "ORIENTATION_UNRECORDED")
    assert "drives geometry" in f["fix"]


def test_a_driver_ic_is_not_expected_to_have_an_axis(tmp_path):
    """A haptic DRIVER has no functional axis; the motor it drives does."""
    p = write(tmp_path, "p.json", good_part(**{"class": "haptic"}))
    out, _ = run_tool("profile_lint.py", p, "--kind", "part")
    assert "ORIENTATION_UNRECORDED" not in codes(out)


def test_onboard_pullups_must_be_recorded_even_when_none(tmp_path):
    p = write(tmp_path, "p.json", good_part(i2c={"addresses": ["0x20", "0x21"], "default": "0x20", "address_select": "A0"}))
    out, _ = run_tool("profile_lint.py", p, "--kind", "part")
    f = finding(out, "ONBOARD_PULLUP_UNRECORDED")
    assert "count wrong for every design" in f["fix"]


# --------------------------------------------------------------------------
# against the real installation
# --------------------------------------------------------------------------


def test_every_installed_profile_is_clean(parent):
    out, rc = run_tool("profile_lint.py", "--all", "--parent", parent)
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["count"] >= 10


def test_the_e290_is_the_corroboration_gold_standard(parent):
    import os

    out, rc = run_tool(
        "profile_lint.py",
        os.path.join(parent, "boards", "heltec_vision_master_e290.json"),
        "--kind", "board",
    )
    assert rc == 0
    g = out["corroboration"]["groups"]["gpio_map"]
    assert g["independent"] >= 3
    assert g["ok"] is True
    # and its disagreements are recorded rather than smoothed
    assert codes(out).count("CONTRADICTION_UNRESOLVED") == 2


