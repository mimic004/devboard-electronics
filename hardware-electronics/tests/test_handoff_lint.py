"""handoff_lint.py - the CAD contract.

The milestone this whole skill is built around: a substitution on the
electronics side has to invalidate the geometry on the CAD side, BY NAME, rather
than being discovered during assembly.
"""

from __future__ import annotations

import json

from conftest import codes, finding, run_tool


def test_round_parts_are_checked_as_round(fx):
    """Two 35 mm discs whose bounding boxes overlap but whose circles do not.

    Describing a circle by its bounding box reserves 21% more area than it
    occupies, all of it in the corners - which is exactly where a round part
    usually has to live. A bounding-box check would reject this valid layout.
    """
    out, rc = run_tool("handoff_lint.py", fx("manifest_round_corner.json"), "--strict")
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert "KEEPOUT_OVERLAP" not in codes(out)


def test_overlapping_parts_are_named_with_their_kinds(fx):
    out, rc = run_tool("handoff_lint.py", fx("manifest_bad_handoff.json"))
    assert rc == 1
    f = finding(out, "KEEPOUT_OVERLAP")
    assert {f["a"], f["b"]} & {"board", "cell"}


def test_part_outside_the_envelope(fx):
    out, _ = run_tool("handoff_lint.py", fx("manifest_bad_handoff.json"))
    f = finding(out, "NOT_CONTAINED")
    assert f["component"] == "buzzer"
    assert "veto" in f["fix"]


def test_assumed_dimension_being_printed_around(fx):
    out, _ = run_tool("handoff_lint.py", fx("manifest_bad_handoff.json"))
    f = finding(out, "ASSUMED_DIMENSION")
    assert f["component"] == "cell"
    assert "accepted_risk" in f["fix"]


def test_part_with_a_functional_axis_needs_an_orientation(fx):
    out, _ = run_tool("handoff_lint.py", fx("manifest_bad_handoff.json"))
    f = finding(out, "ORIENTATION_UNCONSTRAINED")
    assert f["component"] == "buzzer"


def test_rf_keepout_violated_by_a_battery(fx):
    out, _ = run_tool("handoff_lint.py", fx("manifest_bad_handoff.json"))
    f = finding(out, "RF_KEEPOUT_VIOLATED")
    assert f["intruder"] == "cell"


def test_filled_filament_is_a_veto(fx):
    out, _ = run_tool("handoff_lint.py", fx("manifest_bad_handoff.json"))
    f = finding(out, "RF_MATERIAL_VIOLATED")
    assert f["material"] == "carbon_filled"
    assert "veto" in f["fix"].lower()


def test_cable_run_without_a_channel_minimum(fx):
    out, _ = run_tool("handoff_lint.py", fx("manifest_bad_handoff.json"))
    f = finding(out, "CABLE_NO_CHANNEL")
    assert f["cable"] == "cell_to_board"


def test_pager_manifest_passes_strict(example):
    out, rc = run_tool(
        "handoff_lint.py", example("pager-style-handheld", "component-manifest.json"), "--strict"
    )
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["content_hash"].startswith("sha256:")


def test_declared_hash_matches_computed_hash(example):
    out, _ = run_tool(
        "handoff_lint.py", example("pager-style-handheld", "component-manifest.json")
    )
    assert out["declared_hash"] == out["content_hash"]


def test_conditional_keepout_resolves_against_the_assembly_block(example):
    """A conditional keep-out nobody can evaluate is a keep-out nobody checked."""
    out, _ = run_tool(
        "handoff_lint.py", example("pager-style-handheld", "component-manifest.json")
    )
    f = finding(out, "KEEPOUT_INACTIVE")
    assert f["keepout"] == "header_zone"
    assert "KEEPOUT_CONDITIONAL" not in codes(out)


def test_unresolvable_condition_is_reported(example, tmp_path):
    src = json.load(open(example("pager-style-handheld", "component-manifest.json"), encoding="utf-8"))
    del src["assembly"]
    p = tmp_path / "m.json"
    p.write_text(json.dumps(src), encoding="utf-8")
    out, _ = run_tool("handoff_lint.py", str(p))
    f = finding(out, "KEEPOUT_CONDITIONAL")
    assert f["keepout"] == "header_zone"


def test_speaker_substitution_names_the_stl_to_reprint(example, tmp_path):
    """20 mm -> 28 mm speaker. The lock must say REPRINT and name the file.

    This is the failure the whole contract exists to prevent: a part swap that
    nothing notices until the shell is already printed.
    """
    src = json.load(open(example("pager-style-handheld", "component-manifest.json"), encoding="utf-8"))
    for c in src["components"]:
        if c["id"] == "speaker":
            c["footprint"]["d"] = 28.0
    p = tmp_path / "m.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        "handoff_lint.py", str(p), "--check-lock", example("pager-style-handheld", "cad_lock.json")
    )
    assert rc == 1
    f = finding(out, "HASH_STALE")
    change = [c for c in f["changed_fields"] if c["path"].endswith("footprint.d")][0]
    assert change["was"] == 20
    assert change["now"] == 28
    assert change["cad_parameters"] == ["spk_d"]
    assert change["affects_stls"] == ["pager_p2_back_shell.stl"]
    assert change["verdict"] == "REPRINT pager_p2_back_shell.stl"


def test_editing_prose_does_not_force_a_reprint(example, tmp_path):
    """Editing a comment must not invalidate geometry; editing a dimension must."""
    src = json.load(open(example("pager-style-handheld", "component-manifest.json"), encoding="utf-8"))
    src["components"][0]["footprint"]["reason"] = "a completely different explanation"
    src["datum"]["note"] = "reworded"
    p = tmp_path / "m.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        "handoff_lint.py", str(p), "--check-lock", example("pager-style-handheld", "cad_lock.json")
    )
    assert "HASH_STALE" not in codes(out)
    assert "LOCK_FRESH" in codes(out)
    assert rc == 0


def test_full_loop_with_bom_and_cad_response(example):
    out, rc = run_tool(
        "handoff_lint.py",
        example("pager-style-handheld", "component-manifest.json"),
        "--bom",
        example("pager-style-handheld", "bom.json"),
        "--check-lock",
        example("pager-style-handheld", "cad_lock.json"),
        "--check-response",
        example("pager-style-handheld", "cad-response.json"),
        "--strict",
    )
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert "HOMELESS_PART" not in codes(out)
    assert "CLEARANCE_UNSATISFIED" not in codes(out)
    assert codes(out).count("COUNTER_CONSTRAINT_ACKNOWLEDGED") == 2


def test_unacknowledged_counter_constraint_blocks(example, tmp_path):
    """CAD pushing back on an electronics number is not advice. It is a gate."""
    src = json.load(open(example("pager-style-handheld", "cad-response.json"), encoding="utf-8"))
    src["counter_constraints"][0]["acknowledged"] = False
    p = tmp_path / "resp.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        "handoff_lint.py",
        example("pager-style-handheld", "component-manifest.json"),
        "--check-response",
        str(p),
    )
    assert rc == 1
    f = finding(out, "COUNTER_CONSTRAINT_OPEN")
    assert f["component"] == "piezo"


def test_realised_channel_below_the_declared_minimum(example, tmp_path):
    """The quiet failure: the model shrinks the channel to suit whatever is in the way."""
    src = json.load(open(example("pager-style-handheld", "cad-response.json"), encoding="utf-8"))
    src["realised"]["channels"]["batt_to_jp1"] = {"w": 2.1, "h": 3.2}
    p = tmp_path / "resp.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        "handoff_lint.py",
        example("pager-style-handheld", "component-manifest.json"),
        "--check-response",
        str(p),
    )
    assert rc == 1
    f = finding(out, "CHANNEL_BELOW_MINIMUM")
    assert f["cable"] == "batt_to_jp1"
    assert "QUIET" in f["fix"]


def test_assertion_outside_its_band_cannot_be_widened_away(example, tmp_path):
    src = json.load(open(example("pager-style-handheld", "cad-response.json"), encoding="utf-8"))
    for a in src["assertions"]:
        if a["id"] == "spk-air-gap":
            a["value"] = 2.4
    p = tmp_path / "resp.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        "handoff_lint.py",
        example("pager-style-handheld", "component-manifest.json"),
        "--check-response",
        str(p),
    )
    assert rc == 1
    f = finding(out, "CLEARANCE_UNSATISFIED")
    assert f["assertion"] == "spk-air-gap"
    assert "Do NOT widen the band" in f["fix"]


def test_response_to_a_different_manifest_is_not_an_answer(example, tmp_path):
    src = json.load(open(example("pager-style-handheld", "cad-response.json"), encoding="utf-8"))
    src["responds_to"] = "sha256:" + "0" * 64
    p = tmp_path / "resp.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        "handoff_lint.py",
        example("pager-style-handheld", "component-manifest.json"),
        "--check-response",
        str(p),
    )
    assert rc == 1
    assert "RESPONSE_STALE" in codes(out)


def test_homeless_drives_cad_row(example, tmp_path):
    src = json.load(open(example("pager-style-handheld", "bom.json"), encoding="utf-8"))
    src["rows"].append(
        {
            "id": "oled",
            "description": "a screen nobody found room for",
            "qty": 1,
            "drives_cad": {"parameters": ["oled_l"], "owner_script": "pager_enclosure.py"},
            "footprint": {
                "shape": "rect",
                "l": 27.0,
                "w": 27.0,
                "h": 4.0,
                "height_includes": "body_only",
                "provenance": {"l": "measured", "w": "measured", "h": "measured"},
                "verify_before": "none",
            },
        }
    )
    p = tmp_path / "bom.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        "handoff_lint.py",
        example("pager-style-handheld", "component-manifest.json"),
        "--bom",
        str(p),
    )
    assert rc == 1
    f = finding(out, "HOMELESS_PART")
    assert f["row"] == "oled"
