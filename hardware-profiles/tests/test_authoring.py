"""new_profile.py and verify_profile.py - authoring and evidence.

The scaffolder's job is to be EMPTY. A scaffolder that pre-fills a plausible pin
map produces a profile that looks researched and is not, which is the exact
failure this skill exists to prevent.
"""

from __future__ import annotations

import json
import os

from conftest import codes, finding, good_board, run_tool, write


# --------------------------------------------------------------------------
# scaffolding
# --------------------------------------------------------------------------


def test_scaffold_guesses_nothing(tmp_path):
    out, rc = run_tool(
        "new_profile.py", "--kind", "board", "--id", "test_board",
        "--family", "ESP32-S3", "--out", str(tmp_path),
    )
    assert rc == 0
    data = json.loads(open(out["out"], encoding="utf-8").read())

    assert data["status"] == "draft"
    assert data["gpio_valid"] == []
    assert data["consumed"] == {}
    assert data["free"] is None
    assert data["adc1"] == {}
    assert data["corroboration"]["sources"] == []
    assert data["mcu"]["flash_mb"] is None


def test_scaffold_carries_the_family_checklist(tmp_path):
    out, _ = run_tool(
        "new_profile.py", "--kind", "board", "--id", "b",
        "--family", "ESP32-S3", "--out", str(tmp_path),
    )
    data = json.loads(open(out["out"], encoding="utf-8").read())
    questions = " ".join(q["question"] for q in data["corroboration"]["open_questions"])
    assert "no input-only" in questions.lower()
    assert "GPIO45" in questions
    assert all(q["blocks_active"] for q in data["corroboration"]["open_questions"])


def test_classic_esp32_gets_a_different_checklist(tmp_path):
    out, _ = run_tool(
        "new_profile.py", "--kind", "board", "--id", "b",
        "--family", "ESP32", "--out", str(tmp_path),
    )
    data = json.loads(open(out["out"], encoding="utf-8").read())
    questions = " ".join(q["question"] for q in data["corroboration"]["open_questions"])
    assert "GPIO34-39 are input-only" in questions


def test_missing_family_is_flagged(tmp_path):
    out, _ = run_tool("new_profile.py", "--kind", "board", "--id", "b", "--out", str(tmp_path))
    f = finding(out, "NO_FAMILY")
    assert "one family was applied to another" in f["fix"]


def test_scaffold_will_not_silently_overwrite(tmp_path):
    run_tool("new_profile.py", "--kind", "board", "--id", "b", "--out", str(tmp_path))
    out, rc = run_tool("new_profile.py", "--kind", "board", "--id", "b", "--out", str(tmp_path))
    assert rc == 1
    f = finding(out, "PROFILE_EXISTS")
    assert "discard research someone already did" in f["fix"]


def test_bad_id_is_rejected(tmp_path):
    out, rc = run_tool(
        "new_profile.py", "--kind", "board", "--id", "Not A Valid Id", "--out", str(tmp_path)
    )
    assert rc == 2
    assert "BAD_ID" in codes(out)


def test_an_empty_scaffold_fails_its_own_linter(tmp_path):
    """The scaffold is a starting point, not a deliverable."""
    out, _ = run_tool(
        "new_profile.py", "--kind", "board", "--id", "b",
        "--family", "ESP32-S3", "--out", str(tmp_path),
    )
    lint, rc = run_tool("profile_lint.py", out["out"], "--kind", "board")
    assert rc == 1
    assert "NO_GPIO_VALID" in codes(lint)


def test_part_scaffold_has_null_dimensions(tmp_path):
    """Null, not a plausible round number."""
    out, _ = run_tool(
        "new_profile.py", "--kind", "part", "--id", "p",
        "--class", "sensor_module", "--out", str(tmp_path),
    )
    data = json.loads(open(out["out"], encoding="utf-8").read())
    assert data["footprint"]["l"] is None
    assert data["footprint"]["height_includes"] == "unknown"
    assert data["failure_mode"] == "unknown"


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------


def _identify(tmp_path, **over):
    base = {
        "tool": "board_cli",
        "ok": True,
        "source": "hardware",
        "port": "COM7",
        "chip": {"family": "ESP32-S3", "revision": "v0.2"},
        "flash": {"size_mb": 8},
    }
    base.update(over)
    return write(tmp_path, "id.json", base)


def test_silicon_agreeing_with_the_profile(tmp_path):
    prof = write(tmp_path, "b.json", good_board(mcu={"family": "ESP32-S3", "flash_mb": 8}))
    out, rc = run_tool("verify_profile.py", "against-silicon", prof, "--identify", _identify(tmp_path))
    assert rc == 0
    assert "flash.size_mb" in out["agreements"]


def test_silicon_contradicting_the_profile(tmp_path):
    prof = write(tmp_path, "b.json", good_board(mcu={"family": "ESP32-S3", "flash_mb": 16}))
    out, rc = run_tool("verify_profile.py", "against-silicon", prof, "--identify", _identify(tmp_path))
    assert rc == 1
    f = finding(out, "PROFILE_CONTRADICTED_BY_SILICON")
    assert f["silicon"] == 8
    assert "Silicon wins" in f["fix"]


def test_a_recorded_run_cannot_corroborate(tmp_path):
    """A replayed transcript proves the parser works, not the board."""
    prof = write(tmp_path, "b.json", good_board(mcu={"family": "ESP32-S3", "flash_mb": 8}))
    ident = _identify(tmp_path, source="recorded")
    out, _ = run_tool(
        "verify_profile.py", "against-silicon", prof, "--identify", ident, "--write"
    )
    assert "EVIDENCE_NOT_HARDWARE" in codes(out)
    assert "written" not in out
    data = json.loads(open(prof, encoding="utf-8").read())
    assert not any(
        s["kind"] == "measurement" for s in data["corroboration"]["sources"]
    )


def test_hardware_evidence_is_recorded(tmp_path):
    prof = write(tmp_path, "b.json", good_board(mcu={"family": "ESP32-S3", "flash_mb": 8}))
    out, rc = run_tool(
        "verify_profile.py", "against-silicon", prof, "--identify", _identify(tmp_path), "--write"
    )
    assert rc == 0
    assert "CORROBORATION_ADDED" in codes(out)
    data = json.loads(open(prof, encoding="utf-8").read())
    assert any(s["kind"] == "measurement" for s in data["corroboration"]["sources"])


def _sweep(tmp_path, frees, helds, source="hardware"):
    return write(
        tmp_path, "sweep.json",
        {
            "tool": "probe_client",
            "source": source,
            "port": "COM7",
            "measurements": {
                "frees": [str(p) for p in frees],
                "helds": [f"{p} low" for p in helds],
            },
        },
    )


def test_sweep_catches_a_pin_the_profile_blessed(tmp_path):
    """The dangerous direction: profile says free, hardware says driven."""
    prof = write(tmp_path, "b.json", good_board())
    sweep = _sweep(tmp_path, frees=[4, 8], helds=[5])
    out, rc = run_tool("verify_profile.py", "against-sweep", prof, "--sweep", sweep)
    assert rc == 1
    f = finding(out, "PROFILE_BLESSES_HELD_PIN")
    assert 5 in f["pins"]
    assert "fight the hardware" in f["fix"]


def test_sweep_over_reservation_is_only_a_warning(tmp_path):
    """The safe direction: profile refuses a pin that would have worked."""
    prof = write(tmp_path, "b.json", good_board())
    sweep = _sweep(tmp_path, frees=[4, 5, 8, 6], helds=[])
    out, rc = run_tool("verify_profile.py", "against-sweep", prof, "--sweep", sweep)
    assert rc == 0
    f = finding(out, "PROFILE_OVER_RESERVES")
    assert 6 in f["pins"]
    assert "SAFE direction" in f["fix"]


def test_sweep_will_not_record_over_a_contradiction(tmp_path):
    prof = write(tmp_path, "b.json", good_board())
    sweep = _sweep(tmp_path, frees=[4, 8], helds=[5])
    run_tool("verify_profile.py", "against-sweep", prof, "--sweep", sweep, "--write")
    data = json.loads(open(prof, encoding="utf-8").read())
    assert not any(s["kind"] == "measurement" for s in data["corroboration"]["sources"])


# --------------------------------------------------------------------------
# install
# --------------------------------------------------------------------------


def test_install_refuses_a_profile_that_fails_its_linter(tmp_path, parent):
    bad = write(tmp_path, "b.json", good_board(id="zz_test_bad", input_only=[3]))
    out, rc = run_tool("verify_profile.py", "install", bad, "--parent", parent)
    assert rc == 1
    f = finding(out, "LINT_FAILED")
    assert "inherits the problem silently" in f["fix"]
    assert not os.path.isfile(os.path.join(parent, "boards", "zz_test_bad.json"))


def test_install_places_a_good_profile_and_cleans_up(tmp_path, parent):
    good = write(tmp_path, "b.json", good_board(id="zz_test_ok"))
    dest = os.path.join(parent, "boards", "zz_test_ok.json")
    try:
        out, rc = run_tool("verify_profile.py", "install", good, "--parent", parent)
        assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
        assert os.path.isfile(dest)
        assert out["status"] == "active"
    finally:
        if os.path.isfile(dest):
            os.remove(dest)


def test_installing_a_draft_warns(tmp_path, parent):
    draft = write(tmp_path, "b.json", good_board(id="zz_test_draft", status="draft"))
    dest = os.path.join(parent, "boards", "zz_test_draft.json")
    try:
        out, rc = run_tool("verify_profile.py", "install", draft, "--parent", parent)
        assert rc == 0
        f = finding(out, "INSTALLING_DRAFT")
        assert "visibly provisional" in f["fix"]
    finally:
        if os.path.isfile(dest):
            os.remove(dest)
