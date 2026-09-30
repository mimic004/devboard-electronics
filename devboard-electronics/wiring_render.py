#!/usr/bin/env python3
"""wiring_render.py - netlist to a connection graph and a bench table.

Two outputs, deliberately in that order of importance:

  * ``wiring.md`` - a CONNECTION TABLE. One row per wire, with a checkbox
    column. This is what people actually use with a crimper in one hand.
  * ``wiring.svg`` (or ``wiring.mmd``) - a connection graph. Not a schematic.
    Falls back to Mermaid text when Graphviz is absent, so it degrades instead
    of failing.

Explicitly NOT here: schematic capture, KiCad netlist export, gerbers,
auto-placement. Those are a different discipline and out of scope.

The checks are what make this a gate rather than a drawing:

    NET_DANGLING          a net with fewer than two endpoints
    PIN_UNCONNECTED       a component pin neither in a net nor marked nc
    NO_DECOUPLING         an IC with no decoupling capacitor declared
    NO_COMMON_GROUND      two powered components with no shared ground net
    WIRE_GAUGE_UNDERSIZED peak current against an AWG table
    REF_UNKNOWN           a net endpoint naming a component that does not exist
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    PARTS_DIR,
    Report,
    base_parser,
    load_json,
    validate_schema,
)

TOOL = "wiring_render"

#: Advisory findings a netlist may accept with a written reason.
ACKNOWLEDGEABLE = frozenset(
    {
        "NO_COLOUR_CONVENTION",
        "NET_SINGLE_ENDPOINT_POWER",
        "GRAPHVIZ_MISSING",
    }
)

NET_COLOURS = {
    "power": "#c62828",
    "ground": "#212121",
    "signal": "#1565c0",
    "analog": "#6a1b9a",
    "rf": "#ef6c00",
}

DEFAULT_WIRE_COLOUR = {
    "power": "red",
    "ground": "black",
    "signal": "yellow",
    "analog": "green",
    "rf": "white",
}


def load_awg_table() -> List[Dict[str, Any]]:
    path = os.path.join(PARTS_DIR, "connectors.json")
    if os.path.isfile(path):
        data = load_json(path, TOOL)
        table = (data.get("awg_current") or {}).get("table")
        if table:
            return table
    return [
        {"awg": 30, "max_a": 0.86},
        {"awg": 28, "max_a": 1.4},
        {"awg": 26, "max_a": 2.2},
        {"awg": 24, "max_a": 3.5},
        {"awg": 22, "max_a": 7.0},
        {"awg": 20, "max_a": 11.0},
    ]


def awg_capacity(awg: int, table: List[Dict[str, Any]]) -> Optional[float]:
    for row in table:
        if int(row["awg"]) == int(awg):
            return float(row["max_a"])
    return None


def smallest_awg_for(amps: float, table: List[Dict[str, Any]]) -> Optional[int]:
    for row in sorted(table, key=lambda r: -int(r["awg"])):
        if float(row["max_a"]) >= amps:
            return int(row["awg"])
    return None


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def check_netlist(netlist: Dict[str, Any], rep: Report) -> Dict[str, Any]:
    comps = {c["ref"]: c for c in netlist.get("components", [])}
    nets = netlist.get("nets", [])
    awg_table = load_awg_table()

    connected: Set[Tuple[str, str]] = set()
    ground_refs: Set[str] = set()
    powered_refs: Set[str] = set()

    for net in nets:
        endpoints = net.get("endpoints", [])
        kind = net.get("kind", "signal")

        for ep in endpoints:
            ref, pin = ep.get("ref"), str(ep.get("pin"))
            if ref not in comps:
                rep.error(
                    "REF_UNKNOWN",
                    f"Net {net['id']!r} connects to {ref!r}, which is not declared in "
                    f"components[].",
                    fix="Add the component, or fix the reference. A net to nowhere "
                    "renders fine and solders badly.",
                    net=net["id"],
                    ref=ref,
                )
                continue
            connected.add((ref, pin))
            if kind == "ground":
                ground_refs.add(ref)
            if kind == "power":
                powered_refs.add(ref)

        if len(endpoints) < 2:
            severity = "warning" if kind == "power" and len(endpoints) == 1 else "error"
            code = "NET_SINGLE_ENDPOINT_POWER" if severity == "warning" else "NET_DANGLING"
            (rep.warn if severity == "warning" else rep.error)(
                code,
                f"Net {net['id']!r} has {len(endpoints)} endpoint(s). A wire needs two "
                f"ends.",
                fix="Connect it, or delete it. A single-ended net is either a missing "
                "wire or a leftover from an earlier revision, and both are worth "
                "finding before the crimper comes out.",
                net=net["id"],
            )

        # gauge
        peak_ma = net.get("i_peak_ma")
        awg = net.get("awg")
        if peak_ma and awg:
            amps = float(peak_ma) / 1000.0
            cap = awg_capacity(int(awg), awg_table)
            if cap is not None and amps > cap:
                want = smallest_awg_for(amps, awg_table)
                rep.error(
                    "WIRE_GAUGE_UNDERSIZED",
                    f"Net {net['id']!r} carries {peak_ma} mA peak on {awg} AWG, rated "
                    f"about {cap} A.",
                    fix=f"Use {want} AWG or thicker."
                    if want
                    else "Use a thicker conductor, or split the current.",
                    net=net["id"],
                    awg=awg,
                    peak_ma=peak_ma,
                )
        elif peak_ma and float(peak_ma) >= 500 and not awg:
            rep.warn(
                "WIRE_GAUGE_UNDECLARED",
                f"Net {net['id']!r} carries {peak_ma} mA peak and declares no gauge.",
                fix="State the AWG. Above about half an amp the conductor stops being "
                "an implementation detail.",
                net=net["id"],
            )

    # unconnected pins
    for ref, comp in comps.items():
        for pin in comp.get("pins", []):
            key = (ref, str(pin.get("pin")))
            if pin.get("nc"):
                continue
            if key not in connected:
                rep.error(
                    "PIN_UNCONNECTED",
                    f"{ref}.{pin.get('pin')}"
                    + (f" ({pin['name']})" if pin.get("name") else "")
                    + " is in no net and is not marked nc.",
                    fix="Connect it, or mark it \"nc\": true so the omission is "
                    "deliberate. Never leave a CMOS input floating - an unconnected "
                    "input is not an off input, it is an antenna.",
                    ref=ref,
                    pin=pin.get("pin"),
                )

    # decoupling
    for ref, comp in comps.items():
        if not (comp.get("is_ic") or comp.get("kind") in ("ic", "mcu")):
            continue
        if comp.get("decoupling_uf") in (None, 0):
            rep.error(
                "NO_DECOUPLING",
                f"{ref} is an IC with no decoupling capacitor declared.",
                fix="100 nF at every IC power pin, plus one bulk electrolytic per "
                "rail, placed AT THE PIN and not at the connector. Set "
                "decoupling_uf to record it.",
                ref=ref,
            )

    # common ground
    if len(ground_refs) == 1 and len(comps) > 1:
        rep.error(
            "NO_COMMON_GROUND",
            f"Only {sorted(ground_refs)} is on a ground net, but there are "
            f"{len(comps)} components.",
            fix="Every powered part needs a return path to the same ground. Two "
            "boards sharing a signal but not a ground is a classic 'it works on the "
            "bench, sometimes' fault.",
        )
    elif not ground_refs and comps:
        rep.error(
            "NO_COMMON_GROUND",
            "No net is marked \"kind\": \"ground\".",
            fix="Declare the ground net. Current has to get home.",
        )
    else:
        missing_gnd = sorted(powered_refs - ground_refs)
        if missing_gnd:
            rep.error(
                "NO_COMMON_GROUND",
                f"{missing_gnd} are on a power net but on no ground net.",
                fix="Give each of them a ground connection.",
                refs=missing_gnd,
            )

    return {
        "components": len(comps),
        "nets": len(nets),
        "connections": sum(len(n.get("endpoints", [])) for n in nets),
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def _label(comp: Dict[str, Any]) -> str:
    bits = [comp["ref"]]
    if comp.get("i2c_addr"):
        bits.append(f"I2C {comp['i2c_addr']}")
    if comp.get("logic_v"):
        bits.append(f"{comp['logic_v']} V")
    return "\\n".join(bits)


def render_dot(netlist: Dict[str, Any]) -> str:
    comps = netlist.get("components", [])
    lines = [
        "digraph wiring {",
        "  rankdir=LR;",
        "  graph [splines=true, nodesep=0.5, ranksep=1.2, fontname=\"Segoe UI\"];",
        "  node  [shape=box, style=\"rounded,filled\", fillcolor=\"#f5f5f5\", "
        "fontname=\"Segoe UI\", fontsize=10];",
        "  edge  [fontname=\"Segoe UI\", fontsize=9];",
    ]
    for c in comps:
        shape = "box3d" if c.get("kind") == "mcu" else "box"
        lines.append(f'  "{c["ref"]}" [label="{_label(c)}", shape={shape}];')

    for net in netlist.get("nets", []):
        kind = net.get("kind", "signal")
        colour = NET_COLOURS.get(kind, "#1565c0")
        eps = net.get("endpoints", [])
        for i in range(len(eps) - 1):
            a, b = eps[i], eps[i + 1]
            label = f'{net["id"]}\\n{a.get("pin")} - {b.get("pin")}'
            lines.append(
                f'  "{a.get("ref")}" -> "{b.get("ref")}" '
                f'[label="{label}", color="{colour}", dir=none, penwidth=1.4];'
            )
    lines.append("}")
    return "\n".join(lines)


def render_mermaid(netlist: Dict[str, Any]) -> str:
    """Fallback when Graphviz is absent. Degrade, never fail."""
    lines = ["flowchart LR"]
    for c in netlist.get("components", []):
        label = _label(c).replace("\\n", "<br/>")
        lines.append(f'  {c["ref"]}["{label}"]')
    for net in netlist.get("nets", []):
        eps = net.get("endpoints", [])
        for i in range(len(eps) - 1):
            a, b = eps[i], eps[i + 1]
            lines.append(
                f'  {a.get("ref")} --- |"{net["id"]}: {a.get("pin")}-{b.get("pin")}"| {b.get("ref")}'
            )
    return "\n".join(lines)


def render_table(netlist: Dict[str, Any]) -> str:
    rows: List[str] = []
    for net in netlist.get("nets", []):
        kind = net.get("kind", "signal")
        colour = net.get("colour") or DEFAULT_WIRE_COLOUR.get(kind, "-")
        awg = net.get("awg", "-")
        eps = net.get("endpoints", [])
        for i in range(len(eps) - 1):
            a, b = eps[i], eps[i + 1]
            rows.append(
                f"| [ ] | `{net['id']}` | {kind} | {a.get('ref')}.{a.get('pin')} | "
                f"{b.get('ref')}.{b.get('pin')} | {colour} | {awg} | "
                f"{net.get('i_peak_ma', '-')} |"
            )

    out = [
        f"# Wiring - {netlist.get('project', 'project')}",
        "",
        "One row per wire. Tick them off as you make them; the point of the column "
        "is that a half-built harness is indistinguishable from a finished one "
        "without it.",
        "",
        "| Done | Net | Kind | From | To | Colour | AWG | Peak mA |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    out.extend(rows)
    out += [
        "",
        "## Before power-on",
        "",
        "- [ ] Continuity and short check across every power rail, board unpowered.",
        "- [ ] Battery connector polarity metered. Polarity is not standardised.",
        "- [ ] First power-on current-limited if a bench supply is available.",
        "- [ ] One peripheral at a time. Silence from two at once tells you nothing.",
        "",
        "See `reference/bench-review.md` for the full checklist.",
        "",
    ]
    return "\n".join(out)


def have_graphviz() -> Optional[str]:
    return shutil.which("dot")


def write_text(path: str, text: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser(
        "wiring_render.py", "Validate a netlist and render a connection graph and table."
    )
    p.add_argument("netlist", help="Path to netlist.json")
    p.add_argument("--out-dir", default=".", help="Where to write wiring.* (default: cwd)")
    p.add_argument("--no-render", action="store_true", help="Check only; write nothing")
    args = p.parse_args(argv)

    netlist = load_json(args.netlist, TOOL)
    rep = Report(TOOL, source="static", project=netlist.get("project"))
    validate_schema(netlist, "netlist", rep)

    stats = check_netlist(netlist, rep)
    rep.set(**stats)

    artifacts: Dict[str, str] = {}
    if not args.no_render:
        table_path = os.path.join(args.out_dir, "wiring.md")
        write_text(table_path, render_table(netlist))
        artifacts["table"] = table_path

        dot_src = render_dot(netlist)
        dot_path = os.path.join(args.out_dir, "wiring.dot")
        write_text(dot_path, dot_src)
        artifacts["dot"] = dot_path

        dot_bin = have_graphviz()
        if dot_bin:
            svg_path = os.path.join(args.out_dir, "wiring.svg")
            try:
                proc = subprocess.run(
                    [dot_bin, "-Tsvg", dot_path, "-o", svg_path],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if proc.returncode == 0 and os.path.isfile(svg_path):
                    artifacts["svg"] = svg_path
                else:
                    rep.warn(
                        "GRAPHVIZ_FAILED",
                        f"dot exited {proc.returncode}: {proc.stderr.strip()[:300]}",
                        fix="The .dot source was still written, and the connection "
                        "table - which is the artefact that gets used - is unaffected.",
                    )
            except Exception as exc:  # pragma: no cover - environment dependent
                rep.warn("GRAPHVIZ_FAILED", f"Could not run dot: {exc}")
        else:
            mmd_path = os.path.join(args.out_dir, "wiring.mmd")
            write_text(mmd_path, render_mermaid(netlist))
            artifacts["mermaid"] = mmd_path
            rep.warn(
                "GRAPHVIZ_MISSING",
                "Graphviz `dot` is not on PATH, so a Mermaid flowchart was written "
                "instead of an SVG.",
                fix="Install Graphviz for the SVG, or paste wiring.mmd into anything "
                "that renders Mermaid. The connection table is the artefact that "
                "actually gets used at the bench, and it is unaffected either way.",
            )

    rep.set(artifacts=artifacts)
    rep.apply_acceptances(netlist.get("accepted_findings"), ACKNOWLEDGEABLE)
    return rep.emit(args.strict)


if __name__ == "__main__":
    sys.exit(main())
