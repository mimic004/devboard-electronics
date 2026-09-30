"""cad_bridge - the CAD half of the contract, without touching the CAD skill."""

from __future__ import annotations

import json
import os

from conftest import codes, finding, run_tool

PARAMS = os.path.join("cad_bridge", "consume_manifest.py")
RUNNER = os.path.join("cad_bridge", "run_cad_model.py")


def test_params_resolve_through_openings_and_footprints(example):
    """win_offset_x has to come out of openings.display_window.offset.x."""
    out, rc = run_tool(PARAMS, "params", example("pager-style-handheld", "component-manifest.json"))
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    p = out["params"]
    assert p["spk_d"] == 20.0
    assert p["board_l"] == 87.96
    assert p["win_offset_x"] == -3.05
    assert p["usb_ch_w"] == 6.26
    assert p["piezo_d"] == 15.0


def test_params_carry_their_provenance(example):
    out, _ = run_tool(PARAMS, "params", example("pager-style-handheld", "component-manifest.json"))
    assert out["provenance"]["board_l"] == "datasheet"
    assert out["provenance"]["spk_d"] == "measured"


def test_unresolvable_parameter_is_an_error(example, tmp_path):
    """A CAD script that defaults a missing parameter invents a dimension."""
    src = json.load(open(example("pager-style-handheld", "component-manifest.json"), encoding="utf-8"))
    src["components"][0]["cad_parameters"]["bogus"] = "openings.no_such_thing.l"
    p = tmp_path / "m.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(PARAMS, "params", str(p))
    assert rc == 1
    f = finding(out, "PARAMETER_UNRESOLVED")
    assert f["parameter"] == "bogus"
    assert "silently invents" in f["fix"]


def test_generated_python_is_importable_and_annotated(example, tmp_path):
    py = tmp_path / "manifest_params.py"
    out, rc = run_tool(
        PARAMS, "params",
        example("pager-style-handheld", "component-manifest.json"),
        "--out-py", str(py),
        "--out", str(tmp_path / "cad-params.json"),
    )
    assert rc == 0
    text = py.read_text(encoding="utf-8")
    assert "MANIFEST_HASH" in text
    assert "spk_d = 20.0  # measured" in text
    assert "double-clearancing" in text

    ns: dict = {}
    exec(compile(text, str(py), "exec"), ns)  # noqa: S102 - generated file under test
    assert ns["PARAMS"]["spk_d"] == 20.0
    assert ns["MANIFEST_HASH"] == out["manifest_hash"]


def test_envelope_reports_locked_orientations(example):
    out, rc = run_tool(PARAMS, "envelope", example("pager-style-handheld", "component-manifest.json"))
    assert rc == 0
    f = finding(out, "ORIENTATION_LOCKED")
    assert "speaker" in f["components"]
    assert "may NOT rotate" in f["message"]
    assert out["envelope"]["material_constraint"] is not None


def test_respond_scaffolds_every_assertion_as_unevaluated(example, tmp_path):
    resp = tmp_path / "cad-response.json"
    out, rc = run_tool(
        PARAMS, "respond", example("pager-style-handheld", "component-manifest.json"),
        "--out", str(resp),
    )
    assert rc == 0
    data = json.loads(resp.read_text(encoding="utf-8"))
    assert data["responds_to"] == out["manifest_hash"]
    assert all(a["result"] == "not_evaluated" for a in data["assertions"])
    assert len(data["assertions"]) == 5


def test_check_rejects_a_scaffold_handed_back_unfilled(example, tmp_path):
    """Handing back a scaffold is handing back nothing."""
    resp = tmp_path / "cad-response.json"
    run_tool(
        PARAMS, "respond", example("pager-style-handheld", "component-manifest.json"),
        "--out", str(resp),
    )
    out, rc = run_tool(
        PARAMS, "check", example("pager-style-handheld", "component-manifest.json"),
        "--response", str(resp),
    )
    assert rc == 1
    assert codes(out).count("ASSERTION_NOT_EVALUATED") == 5


def test_check_passes_the_real_response(example):
    out, rc = run_tool(
        PARAMS, "check",
        example("pager-style-handheld", "component-manifest.json"),
        "--response", example("pager-style-handheld", "cad-response.json"),
    )
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert "RESPONSE_READY" in codes(out)


def test_check_catches_a_rotated_locked_part(example, tmp_path):
    """CAD may not rotate a part whose orientation constraint is locked."""
    src = json.load(open(example("pager-style-handheld", "cad-response.json"), encoding="utf-8"))
    src["realised"]["placements"]["speaker"]["rotation_z"] = 90.0
    p = tmp_path / "resp.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        PARAMS, "check", example("pager-style-handheld", "component-manifest.json"),
        "--response", str(p),
    )
    assert rc == 1
    f = finding(out, "ORIENTATION_VIOLATED")
    assert f["component"] == "speaker"


def test_check_requires_every_channel_to_be_reported(example, tmp_path):
    src = json.load(open(example("pager-style-handheld", "cad-response.json"), encoding="utf-8"))
    del src["realised"]["channels"]["batt_to_jp1"]
    p = tmp_path / "resp.json"
    p.write_text(json.dumps(src), encoding="utf-8")

    out, rc = run_tool(
        PARAMS, "check", example("pager-style-handheld", "component-manifest.json"),
        "--response", str(p),
    )
    assert rc == 1
    f = finding(out, "CHANNEL_UNREPORTED")
    assert f["cable"] == "batt_to_jp1"
    assert "quiet" in f["fix"]


# --------------------------------------------------------------------------
# the exit-code trap
# --------------------------------------------------------------------------


def _script(tmp_path, body: str) -> str:
    p = tmp_path / "model.py"
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_sentinel_is_trusted_over_a_nonzero_exit(tmp_path):
    """A nonzero exit WITH a valid sentinel is a pass.

    This is the whole point: CadQuery exits -1073740940 on success here, from an
    OpenCASCADE teardown crash after the STL is already written.
    """
    script = _script(
        tmp_path,
        "import json, sys\n"
        "open('front.stl','w').write('solid x\\nendsolid x\\n')\n"
        "print('HWEL_RESULT ' + json.dumps({'ok': True, 'stls': ['front.stl']}))\n"
        "sys.stdout.flush()\n"
        "sys.exit(-1073740940)\n",
    )
    out, rc = run_tool(RUNNER, script, "--expect-stl", "front.stl")
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert "TEARDOWN_CRASH" in codes(out)
    assert "SENTINEL_OK" in codes(out)
    assert "EXPECTED_STL_PRESENT" in codes(out)


def test_fresh_artifacts_are_the_fallback(tmp_path):
    script = _script(
        tmp_path,
        "open('back.stl','w').write('solid x\\nendsolid x\\n')\n",
    )
    out, rc = run_tool(RUNNER, script)
    assert rc == 0
    f = finding(out, "NO_SENTINEL")
    assert "HWEL_RESULT" in f["fix"]
    assert any(a.endswith("back.stl") for a in out["fresh_artifacts"])


def test_nothing_written_is_a_real_failure(tmp_path):
    script = _script(tmp_path, "raise SystemExit(1)\n")
    out, rc = run_tool(RUNNER, script)
    assert rc == 1
    f = finding(out, "NO_OUTPUT")
    assert "proves nothing on this platform" in f["fix"]


def test_a_script_reporting_its_own_failure_is_believed(tmp_path):
    script = _script(
        tmp_path,
        "import json\n"
        "print('HWEL_RESULT ' + json.dumps({'ok': False, 'error': 'fillet failed'}))\n",
    )
    out, rc = run_tool(RUNNER, script)
    assert rc == 1
    f = finding(out, "SCRIPT_REPORTED_FAILURE")
    assert "try/except" in f["fix"]


def test_a_stale_stl_does_not_count(tmp_path):
    """The check is timestamp-based on purpose."""
    old = tmp_path / "front.stl"
    old.write_text("solid x\nendsolid x\n", encoding="utf-8")
    os.utime(old, (1000000, 1000000))

    script = _script(tmp_path, "print('nothing to see here')\n")
    out, rc = run_tool(RUNNER, script, "--expect-stl", "front.stl")
    assert rc == 1
    assert "EXPECTED_STL_MISSING" in codes(out)
