"""wiring_render.py - the connection table and its checks."""

from __future__ import annotations

import os

from conftest import codes, finding, run_tool


def test_dangling_net(fx, tmp_path):
    out, rc = run_tool("wiring_render.py", fx("netlist_broken.json"), "--out-dir", str(tmp_path))
    assert rc == 1
    f = finding(out, "NET_DANGLING")
    assert f["net"] == "orphan"


def test_unconnected_pin_must_be_deliberate(fx, tmp_path):
    out, _ = run_tool("wiring_render.py", fx("netlist_broken.json"), "--out-dir", str(tmp_path))
    pins = {(f["ref"], str(f["pin"])) for f in out["findings"] if f["code"] == "PIN_UNCONNECTED"}
    assert ("mcu", "5") in pins
    f = finding(out, "PIN_UNCONNECTED")
    assert "floating" in f["fix"]


def test_missing_decoupling(fx, tmp_path):
    out, _ = run_tool("wiring_render.py", fx("netlist_broken.json"), "--out-dir", str(tmp_path))
    refs = {f["ref"] for f in out["findings"] if f["code"] == "NO_DECOUPLING"}
    assert {"mcu", "driver"} <= refs
    f = finding(out, "NO_DECOUPLING")
    assert "AT THE PIN" in f["fix"]


def test_no_common_ground(fx, tmp_path):
    out, _ = run_tool("wiring_render.py", fx("netlist_broken.json"), "--out-dir", str(tmp_path))
    f = finding(out, "NO_COMMON_GROUND")
    assert "driver" in str(f.get("refs", f["message"]))


def test_undersized_wire(fx, tmp_path):
    out, _ = run_tool("wiring_render.py", fx("netlist_broken.json"), "--out-dir", str(tmp_path))
    f = finding(out, "WIRE_GAUGE_UNDERSIZED")
    assert f["net"] == "vbat"
    assert f["awg"] == 30
    assert "AWG" in f["fix"]


def test_net_to_a_nonexistent_component(fx, tmp_path):
    out, _ = run_tool("wiring_render.py", fx("netlist_broken.json"), "--out-dir", str(tmp_path))
    f = finding(out, "REF_UNKNOWN")
    assert f["ref"] == "nonexistent"


def test_pager_netlist_is_clean(example, tmp_path):
    out, rc = run_tool(
        "wiring_render.py",
        example("pager-style-handheld", "netlist.json"),
        "--out-dir", str(tmp_path),
        "--strict",
    )
    assert rc == 0, [f for f in out["findings"] if f["severity"] != "info"]
    assert out["components"] == 9
    assert out["connections"] > 40


def test_connection_table_is_the_primary_artifact(example, tmp_path):
    out, _ = run_tool(
        "wiring_render.py", example("pager-style-handheld", "netlist.json"),
        "--out-dir", str(tmp_path),
    )
    table = out["artifacts"]["table"]
    assert os.path.isfile(table)
    text = open(table, encoding="utf-8").read()
    assert "| Done |" in text, "the checkbox column is the point of the table"
    assert "spk_p" in text
    assert "Before power-on" in text
    assert "polarity metered" in text.lower()


def test_graph_degrades_to_mermaid_without_graphviz(example, tmp_path):
    """Degrade, never fail. The diagram gets looked at once; the table gets used."""
    out, _ = run_tool(
        "wiring_render.py", example("pager-style-handheld", "netlist.json"),
        "--out-dir", str(tmp_path),
    )
    artifacts = out["artifacts"]
    assert os.path.isfile(artifacts["dot"])
    assert "svg" in artifacts or "mermaid" in artifacts
    if "mermaid" in artifacts:
        text = open(artifacts["mermaid"], encoding="utf-8").read()
        assert text.startswith("flowchart LR")
        assert "mainboard" in text


def test_no_render_writes_nothing(example, tmp_path):
    out, rc = run_tool(
        "wiring_render.py", example("pager-style-handheld", "netlist.json"),
        "--out-dir", str(tmp_path), "--no-render",
    )
    assert rc == 0
    assert out["artifacts"] == {}
    assert not os.listdir(tmp_path)
