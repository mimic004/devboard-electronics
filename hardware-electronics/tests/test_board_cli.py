"""board_cli.py - bring-up against recorded silicon.

No hardware required. Every test here replays a captured esptool session, which
is the whole reason board_cli was written in Python instead of PowerShell: a
parser and a profile comparison you cannot test are a parser and a profile
comparison you do not trust.
"""

from __future__ import annotations

from conftest import codes, finding, run_tool


def test_identify_parses_silicon(fx):
    out, rc = run_tool(
        "board_cli.py", "identify",
        "--transcript", fx("esptool_e290_ok.json"),
        "--board", "heltec_vision_master_e290",
    )
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["chip"]["family"] == "ESP32-S3"
    assert out["chip"]["revision"] == "v0.2"
    assert out["chip"]["crystal_mhz"] == 40
    assert out["chip"]["mac"] == "d4:05:92:7b:c8:08"
    assert out["flash"]["size_mb"] == 8
    assert out["toolchain"]["esptool"] == "4.8.1"


def test_a_replayed_run_is_never_called_hardware(fx):
    """There is no flag that turns a recorded run into a measurement."""
    out, _ = run_tool(
        "board_cli.py", "identify",
        "--transcript", fx("esptool_e290_ok.json"),
        "--board", "heltec_vision_master_e290",
    )
    assert out["source"] == "recorded"
    assert any("nothing here may be described as measured" in n for n in out["notes"])


def test_silicon_matching_the_profile_confirms_the_field(fx):
    out, _ = run_tool(
        "board_cli.py", "identify",
        "--transcript", fx("esptool_e290_ok.json"),
        "--board", "heltec_vision_master_e290",
    )
    pm = out["profile_match"]
    assert pm["ok"] is True
    assert "flash.size_mb" in pm["confirmed"]
    assert "family" in pm["confirmed"]


def test_silicon_disagreeing_with_the_profile_is_a_hard_fail(fx):
    """16 MB on the wire against 8 MB in the profile. Silicon wins, loudly."""
    out, rc = run_tool(
        "board_cli.py", "identify",
        "--transcript", fx("esptool_flash_mismatch.json"),
        "--board", "heltec_vision_master_e290",
    )
    assert rc == 1
    f = finding(out, "PROFILE_MISMATCH")
    assert f["field"] == "flash.size_mb"
    assert f["profile"] == 8
    assert f["silicon"] == 16
    assert "measure_log.py record" in f["fix"]
    assert out["profile_match"]["ok"] is False


def test_identify_without_a_board_is_only_a_reading(fx):
    """A reading that is never compared cannot catch a wrong assumption."""
    out, _ = run_tool("board_cli.py", "identify", "--transcript", fx("esptool_e290_ok.json"))
    f = finding(out, "NO_PROFILE_COMPARED")
    assert f["severity"] == "warning"
    assert "CHECK" in f["fix"]


def test_psram_zero_is_explained_not_alarmed(fx):
    out, _ = run_tool(
        "board_cli.py", "identify",
        "--transcript", fx("esptool_e290_ok.json"),
        "--board", "heltec_vision_master_e290",
    )
    assert "BOARD_HAS_PSRAM" in out["psram"]["explanation"]
    assert "PROFILE_MISMATCH" not in codes(out)


def test_identify_tells_you_how_to_record_the_result(fx):
    out, _ = run_tool(
        "board_cli.py", "identify",
        "--transcript", fx("esptool_e290_ok.json"),
        "--board", "heltec_vision_master_e290",
    )
    f = finding(out, "RECORD_THIS")
    assert "--provenance measured" in f["message"]
    assert "flash.size_mb" in f["message"]


def test_superseded_profile_warns_during_bringup(fx):
    out, _ = run_tool(
        "board_cli.py", "identify",
        "--transcript", fx("esptool_e290_ok.json"),
        "--board", "crowpanel_213_v1",
    )
    assert "BOARD_SUPERSEDED" in codes(out)


def test_monitor_expect_missing_is_an_error(fx):
    """Silence is not a pass."""
    out, rc = run_tool(
        "board_cli.py", "monitor",
        "--transcript", fx("transcript_i2c_ok.json"),
        "--expect", "probe\\.ready",
        "--expect", "this-string-is-not-there",
    )
    assert rc == 1
    assert "EXPECT_MATCHED" in codes(out)
    f = finding(out, "EXPECT_MISSING")
    assert "Silence is not a pass" in f["fix"]


def test_monitor_replay_reports_lines(fx):
    out, rc = run_tool(
        "board_cli.py", "monitor",
        "--transcript", fx("transcript_i2c_ok.json"),
        "--expect", "probe\\.done i2c ok",
    )
    assert rc == 0
    assert out["source"] == "recorded"
    assert out["line_count"] > 5
