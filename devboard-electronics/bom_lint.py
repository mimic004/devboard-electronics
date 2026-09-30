#!/usr/bin/env python3
"""bom_lint.py - BOM schema validation and trap detection.

The BOM is the join table between electronics and CAD. One reference project
already discovered this and wrote a literal "Drives CAD" column into its BOM -
but it was prose in a Markdown table, so nothing could check it. This tool
checks it.

The traps it exists to catch are all real and all cost money:

  * a cell lead whose connector does not mate with the socket it is going into
  * a charge current fixed in hardware that makes small cells unsafe
  * a frequency band that is locked the moment you press Buy
  * a substitute part 8 mm larger than the pocket it has to sit in
  * a dimension a seller typed into a listing, being printed around
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    PARTS_DIR,
    Report,
    WEAK_PROVENANCE,
    base_parser,
    load_json,
    load_part,
    validate_schema,
)

TOOL = "bom_lint"

#: Advisory findings a BOM may accept with a written reason. POLARITY_UNVERIFIED,
#: CONNECTOR_MISMATCH, VARIANT_UNRESOLVED and CAPACITY_BELOW_CHARGER_MIN are not
#: here: they are errors, and an error is not a preference.
ACKNOWLEDGEABLE = frozenset(
    {
        "CONNECTOR_UNKNOWN",
        "CONNECTOR_FAMILY_DIFFERS",
        "CONNECTOR_GENDER",
        "CONNECTOR_CROSSPLUG",
        "DIMENSION_CONVENTION",
        "PART_REF_UNKNOWN",
    }
)



def load_connectors(search: List[str]) -> Dict[str, Any]:
    for d in list(search) + [PARTS_DIR]:
        path = os.path.join(d, "connectors.json")
        if os.path.isfile(path):
            return load_json(path, TOOL)
    return {"families": {}}


def family_of(name: Optional[str], conns: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not name:
        return None
    fams = conns.get("families", {})
    if name in fams:
        return name, fams[name]
    low = name.strip().lower()
    for fam, data in fams.items():
        if fam.lower() == low:
            return fam, data
        for alias in data.get("aka", []) or []:
            if alias.lower() == low:
                return fam, data
    return None


def pitch_of(conn: Dict[str, Any], conns: Dict[str, Any]) -> Optional[float]:
    if conn.get("pitch_mm") is not None:
        return float(conn["pitch_mm"])
    fam = family_of(conn.get("type"), conns)
    if fam and fam[1].get("pitch_mm") is not None:
        return float(fam[1]["pitch_mm"])
    return None


COMPLEMENTARY = {
    ("plug", "socket"),
    ("socket", "plug"),
    ("wire_lead", "socket"),
    ("socket", "wire_lead"),
    ("plug", "header"),
    ("header", "plug"),
}


def check_connectors(bom: Dict[str, Any], rep: Report, conns: Dict[str, Any]) -> None:
    rows = bom.get("rows", [])
    by_id = {r["id"]: r for r in rows}

    for row in rows:
        conn = row.get("connector")
        if not conn:
            continue

        fam = family_of(conn.get("type"), conns)
        if conn.get("type") and not fam and conn.get("type") not in ("solder_pad", "none"):
            rep.warn(
                "CONNECTOR_UNKNOWN",
                f"{row['id']}: connector type {conn['type']!r} is not in "
                f"parts/connectors.json, so it cannot be checked for mating.",
                fix="Add it to parts/connectors.json with its pitch, or use a listed "
                "family name. Pitch is the fact; the family name is marketing.",
                row=row["id"],
            )

        mate_id = conn.get("mates_with")
        if not mate_id:
            if conn.get("type") not in (None, "solder_pad", "none", "wire_lead"):
                rep.info(
                    "CONNECTOR_UNMATED",
                    f"{row['id']} has a {conn['type']} connector but names nothing it "
                    f"mates with.",
                    fix="Set connector.mates_with to the id of the counterpart row, so "
                    "the pitch check can run.",
                    row=row["id"],
                )
            continue

        other = by_id.get(mate_id)
        if other is None:
            rep.error(
                "CONNECTOR_MATE_MISSING",
                f"{row['id']}.connector.mates_with names {mate_id!r}, which is not a "
                f"row in this BOM.",
                fix="Add the counterpart row, or fix the reference.",
                row=row["id"],
            )
            continue

        oconn = other.get("connector") or {}
        p1, p2 = pitch_of(conn, conns), pitch_of(oconn, conns)
        n1, n2 = conn.get("pins"), oconn.get("pins")

        if p1 is not None and p2 is not None and abs(p1 - p2) > 0.01:
            rep.error(
                "CONNECTOR_MISMATCH",
                f"{row['id']} ({conn.get('type')}, {p1} mm pitch) does not mate with "
                f"{mate_id} ({oconn.get('type')}, {p2} mm pitch). They do not fit, and "
                f"forcing them damages both.",
                fix=f"Change one side, or fit an adapter lead. This is the single most "
                f"common connector mistake in hobby builds: a {p1} mm lead will not "
                f"enter a {p2} mm socket.",
                row=row["id"],
                mates_with=mate_id,
                pitch_a=p1,
                pitch_b=p2,
            )
        elif n1 and n2 and n1 != n2:
            rep.error(
                "CONNECTOR_PIN_COUNT",
                f"{row['id']} has {n1} pins; {mate_id} has {n2}.",
                fix="Match the pin counts.",
                row=row["id"],
            )
        elif p1 is not None and p2 is not None:
            f1 = family_of(conn.get("type"), conns)
            f2 = family_of(oconn.get("type"), conns)
            if f1 and f2 and f1[0] != f2[0]:
                rep.warn(
                    "CONNECTOR_FAMILY_DIFFERS",
                    f"{row['id']} ({f1[0]}) and {mate_id} ({f2[0]}) share a {p1} mm "
                    f"pitch but are named as different families. Vendor naming in this "
                    f"space is unreliable.",
                    fix="Physically compare the parts, or buy the mating lead from the "
                    "same source as the socket.",
                    row=row["id"],
                )

        g1, g2 = conn.get("gender"), oconn.get("gender")
        if g1 and g2 and (g1, g2) not in COMPLEMENTARY:
            rep.warn(
                "CONNECTOR_GENDER",
                f"{row['id']} ({g1}) and {mate_id} ({g2}) are not complementary genders.",
                fix="Check which side carries the socket.",
                row=row["id"],
            )

        if conn.get("pins", 0) == 2 and not conn.get("polarity_verified"):
            rep.error(
                "POLARITY_UNVERIFIED",
                f"{row['id']} is a 2-pin power connector and its polarity has not been "
                f"metered.",
                fix="Check polarity with a meter before plugging anything in. Connector "
                "polarity is NOT standardised - two leads with identical housings can "
                "be wired opposite ways, and reversing a cell into a charger is the "
                "kind of mistake that ends with smoke. Set polarity_verified true only "
                "after the meter has told you.",
                row=row["id"],
            )

    # Cross-plug analysis. A mating PAIR legitimately shares one connector type -
    # that is what mating means - so rows linked by mates_with are collapsed into
    # one net first, and only two genuinely different nets sharing a connector
    # are flagged.
    parent: Dict[str, str] = {r["id"]: r["id"] for r in rows}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for row in rows:
        mate = (row.get("connector") or {}).get("mates_with")
        if mate in parent:
            union(row["id"], mate)

    net_by_conn: Dict[Tuple[str, Optional[float], Optional[int]], Dict[str, List[str]]] = {}
    for row in rows:
        conn = row.get("connector") or {}
        if conn.get("type") in (None, "solder_pad", "none"):
            continue
        key = (str(conn.get("type")), pitch_of(conn, conns), conn.get("pins"))
        net_by_conn.setdefault(key, {}).setdefault(find(row["id"]), []).append(row["id"])

    crossplug = [k for k, groups in net_by_conn.items() if len(groups) > 1]
    for key in crossplug:
        members = sorted(m for g in net_by_conn[key].values() for m in g)
        rep.warn(
            "CONNECTOR_CROSSPLUG",
            f"{len(net_by_conn[key])} independent nets ({', '.join(members)}) all use a "
            f"{key[0]} {key[2]}-pin connector at {key[1]} mm pitch, so they can be "
            f"plugged into each other's sockets.",
            fix="Deliberately choose DIFFERENT pitches for different nets. Making a "
            "cross-plug physically impossible is worth more than a label. One "
            "reference board does exactly this: the battery is 1.25 mm and the sensor "
            "bus is 1.0 mm, so the two cannot be swapped.",
            rows=members,
        )
    if len(net_by_conn) > 1 and not crossplug:
        rep.info(
            "CONNECTOR_CROSSPLUG_SAFE",
            "Every connector type in this BOM belongs to exactly one net, so no two "
            "cables can be cross-plugged. That is a design virtue, not an accident - "
            "keep it when you substitute parts.",
        )


def check_variants(bom: Dict[str, Any], rep: Report) -> None:
    for row in bom.get("rows", []):
        v = row.get("variant")
        if not v:
            continue
        if v.get("locked_at_order") and v.get("chosen") in (None, ""):
            rep.error(
                "VARIANT_UNRESOLVED",
                f"{row['id']}: the {v['axis']!r} variant is locked at order time and has "
                f"not been chosen"
                + (f". Options: {v['options']}" if v.get("options") else "")
                + ".",
                fix="Decide now. A variant locked at order cannot be changed later, "
                "however much of a stretch goal the feature is. A regional radio band "
                "is the classic case: the wrong band is a paperweight in your country.",
                row=row["id"],
                axis=v.get("axis"),
                options=v.get("options"),
            )


def _dims(fp: Dict[str, Any]) -> Dict[str, float]:
    return {k: v for k, v in fp.items() if k in ("l", "w", "h", "d") and isinstance(v, (int, float))}


def _prov_map(fp: Dict[str, Any]) -> Dict[str, str]:
    prov = fp.get("provenance")
    if isinstance(prov, dict):
        return prov
    if isinstance(prov, str):
        return {k: prov for k in _dims(fp)}
    return {}


def check_footprints(bom: Dict[str, Any], rep: Report) -> None:
    for row in bom.get("rows", []):
        drives = row.get("drives_cad")
        drives_on = bool(drives) and drives is not False
        fp = row.get("footprint") or {}
        dims = _dims(fp)

        if drives_on and not dims:
            rep.error(
                "FOOTPRINT_MISSING",
                f"{row['id']} drives CAD parameters but has no dimensions.",
                fix="Add footprint dimensions with a provenance tag for each axis. CAD "
                "cannot build a pocket around a part whose size nobody has written down.",
                row=row["id"],
            )
            continue

        if not dims:
            continue

        prov = _prov_map(fp)
        missing = [k for k in dims if k not in prov]
        if missing:
            rep.error(
                "FOOTPRINT_PROVENANCE_MISSING",
                f"{row['id']}: dimensions {missing} carry no provenance tag.",
                fix="Every number needs to say where it came from. An untagged number "
                "is indistinguishable from a guess.",
                row=row["id"],
            )

        weak = {k: p for k, p in prov.items() if p in WEAK_PROVENANCE}
        if drives_on and weak and fp.get("verify_before") in (None, "none"):
            rep.error(
                "PROVENANCE_SELLER_CLAIMED",
                f"{row['id']} drives CAD and its {list(weak)} dimensions are "
                f"{sorted(set(weak.values()))} with no verify_before gate.",
                fix="Set footprint.verify_before to \"print\" (or \"order\") and, for a "
                "press fit, fit_coupon_required true. A seller-claimed dimension is a "
                "guess with a price attached; printing plastic around it is how a "
                "part ends up 1.9 mm too tall.",
                row=row["id"],
                weak=weak,
            )

        if "h" in dims and fp.get("height_includes") in (None, "unknown"):
            rep.warn(
                "DIMENSION_CONVENTION",
                f"{row['id']} gives a height of {dims['h']} mm without saying what it "
                f"includes.",
                fix="Set footprint.height_includes. For a W x L x H part the third "
                "figure is often the OVERALL height from the seating plane to the top "
                "of the plunger or shaft, not the body. Getting this wrong on a "
                "tactile switch made a set of them about 1.9 mm too tall - enough to "
                "hold every key permanently pressed.",
                row=row["id"],
            )

        if drives_on and row.get("qty", 1) > 1 and weak:
            plan = row.get("order_plan") or {}
            if not plan.get("order_one_first"):
                rep.error(
                    "ORDER_ONE_FIRST",
                    f"{row['id']}: qty {row['qty']}, drives CAD, and its dimensions are "
                    f"still {sorted(set(weak.values()))}.",
                    fix="Order ONE first and measure it, or record order_plan."
                    "order_one_first with a reason. Ten minutes here saves a ten-hour "
                    "mistake, and a wrong dimension multiplied by ten is just a more "
                    "expensive wrong dimension.",
                    row=row["id"],
                )

        if drives_on and isinstance(drives, dict) and not drives.get("parameters"):
            rep.error(
                "DRIVES_CAD_UNNAMED",
                f"{row['id']} is marked as driving CAD but names no parameters.",
                fix="List the CAD parameter names it feeds. An unnamed coupling is "
                "exactly the Markdown-column problem this schema exists to fix.",
                row=row["id"],
            )


def check_power_coupling(bom: Dict[str, Any], power: Optional[Dict[str, Any]], rep: Report) -> None:
    if not power:
        return
    charge = power.get("charge") or {}
    min_cell = charge.get("min_cell_mah")
    if min_cell is None and charge.get("ma") and charge.get("fixed_in_hardware"):
        min_cell = float(charge["ma"])  # 1.0 C floor
    if min_cell is None:
        return
    for row in bom.get("rows", []):
        cap = (row.get("electrical") or {}).get("capacity_mah")
        if cap is None:
            continue
        if float(cap) < float(min_cell):
            rep.error(
                "CAPACITY_BELOW_CHARGER_MIN",
                f"{row['id']} is {cap} mAh, below the {min_cell} mAh floor set by a "
                f"{charge.get('ma')} mA charge current that is fixed in hardware"
                + (f" ({charge.get('source')})" if charge.get("source") else "")
                + f". That cell would charge at {float(charge['ma']) / float(cap):.2f} C.",
                fix="Fit a larger cell, or change the PROG resistor. The charge current "
                "is set by a fitted resistor and is not adjustable from firmware, so "
                "the cell has to move, not the code.",
                row=row["id"],
                capacity_mah=cap,
                min_cell_mah=min_cell,
            )


def check_rf_and_silence(bom: Dict[str, Any], rep: Report) -> None:
    enc = bom.get("enclosure") or {}
    filled = enc.get("material_filled", "none")
    rf_rows = [r for r in bom.get("rows", []) if r.get("rf")]

    if rf_rows and filled not in ("none", None):
        rep.error(
            "RF_FILAMENT",
            f"This BOM contains {len(rf_rows)} RF part(s) and the enclosure material is "
            f"{filled}.",
            fix="Do not print this in a carbon-, glass- or metal-filled filament. Those "
            "are lossy at 2.4 GHz. Plain PLA or PETG is transparent enough that it "
            "makes no measurable difference.",
            rows=[r["id"] for r in rf_rows],
            material=filled,
        )

    for row in rf_rows:
        rf = row["rf"]
        v = row.get("variant") or {}
        if rf.get("transmits") and not rf.get("band_mhz") and not v.get("chosen"):
            rep.error(
                "RF_BAND_UNRESOLVED",
                f"{row['id']} transmits but no frequency band is fixed.",
                fix="The regional band is locked the moment you order. Choose it now.",
                row=row["id"],
            )
        if rf.get("transmits"):
            rep.info(
                "RF_ANTENNA_REMINDER",
                f"{row['id']} transmits. Never power it up without an antenna connected.",
                row=row["id"],
            )

    for row in bom.get("rows", []):
        if row.get("failure_mode") == "silent":
            live = row.get("liveness_check") or {}
            if not live.get("how"):
                rep.error(
                    "SILENT_FAILURE_NO_MONITOR",
                    f"{row['id']} fails silently and no liveness check is declared.",
                    fix="Declare liveness_check.how. A part whose failure mode is "
                    "silence needs something watching it: a last-seen alert, a battery "
                    "alert, a heartbeat. Otherwise the system simply stops working and "
                    "nobody finds out why.",
                    row=row["id"],
                )


def check_manifest_coupling(bom: Dict[str, Any], manifest: Optional[Dict[str, Any]], rep: Report) -> None:
    if not manifest:
        return
    params: set = set()
    for comp in manifest.get("components", []) or []:
        params |= set((comp.get("cad_parameters") or {}).keys())
    for row in bom.get("rows", []):
        drives = row.get("drives_cad")
        if not isinstance(drives, dict):
            continue
        for name in drives.get("parameters", []):
            if name not in params:
                rep.error(
                    "DRIVES_CAD_ORPHAN",
                    f"{row['id']} claims to drive CAD parameter {name!r}, which no "
                    f"component in the manifest declares.",
                    fix="Either the parameter was renamed on the CAD side, or the "
                    "manifest entry is missing. An orphan coupling means a "
                    "substitution will silently fail to propagate.",
                    row=row["id"],
                    parameter=name,
                )


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser("bom_lint.py", "Validate a BOM and catch its traps.")
    p.add_argument("bom", help="Path to bom.json")
    p.add_argument("--power", help="power.json, to check cell capacity against the charge current")
    p.add_argument("--manifest", help="component-manifest.json, to check drives_cad parameter names")
    p.add_argument("--parts-dir", action="append", default=[], help="Extra parts directory")
    p.add_argument("--render", help="Write a human-readable bom.md here")
    args = p.parse_args(argv)

    bom = load_json(args.bom, TOOL)
    search = list(args.parts_dir) + [os.path.dirname(os.path.abspath(args.bom))]
    rep = Report(TOOL, source="static", project=bom.get("project"), rows=len(bom.get("rows", [])))

    validate_schema(bom, "bom", rep)

    ids = [r.get("id") for r in bom.get("rows", [])]
    dupes = sorted({i for i in ids if ids.count(i) > 1 and i})
    if dupes:
        rep.error(
            "ROW_ID_DUPLICATE",
            f"Duplicate row ids: {dupes}.",
            fix="Row ids are referenced by the manifest and by cable runs; they must be unique.",
        )

    conns = load_connectors(search)
    power = load_json(args.power, TOOL) if args.power else None
    manifest = load_json(args.manifest, TOOL) if args.manifest else None

    check_variants(bom, rep)
    check_connectors(bom, rep, conns)
    check_footprints(bom, rep)
    check_power_coupling(bom, power, rep)
    check_rf_and_silence(bom, rep)
    check_manifest_coupling(bom, manifest, rep)

    for row in bom.get("rows", []):
        if row.get("part_ref") and load_part(row["part_ref"], TOOL, search) is None:
            rep.warn(
                "PART_REF_UNKNOWN",
                f"{row['id']} references part {row['part_ref']!r}, which is not in "
                f"parts/.",
                fix="Add the part profile, or drop the reference. Without it the linter "
                "cannot check addresses, levels or on-module pull-ups for this part.",
                row=row["id"],
            )

    total = sum(
        (r.get("unit_cost_usd") or 0) * r.get("qty", 1) for r in bom.get("rows", [])
    )
    rep.set(
        drives_cad_rows=[r["id"] for r in bom.get("rows", []) if r.get("drives_cad")],
        estimated_cost_usd=round(total, 2) if total else None,
    )

    rep.apply_acceptances(bom.get("accepted_findings"), ACKNOWLEDGEABLE)

    if args.render:
        _render_md(bom, args.render)
        rep.set(rendered=args.render)

    return rep.emit(args.strict)


def _render_md(bom: Dict[str, Any], path: str) -> None:
    lines = [f"# BOM - {bom.get('project', 'project')}", ""]
    lines.append("| id | description | qty | variant | footprint | provenance | Drives CAD |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in bom.get("rows", []):
        fp = r.get("footprint") or {}
        dims = " x ".join(
            f"{fp[k]}" for k in ("l", "w", "h") if isinstance(fp.get(k), (int, float))
        ) or (f"d{fp['d']}" if fp.get("d") else "-")
        prov = _prov_map(fp)
        provs = ", ".join(sorted(set(prov.values()))) or "-"
        v = r.get("variant") or {}
        drives = r.get("drives_cad")
        dtxt = (
            ", ".join(drives.get("parameters", []))
            if isinstance(drives, dict)
            else ("yes" if drives else "-")
        )
        lines.append(
            f"| `{r['id']}` | {r.get('description', '')} | {r.get('qty', 1)} | "
            f"{v.get('chosen', '-')} | {dims} | {provs} | {dtxt} |"
        )
    lines += [
        "",
        "> If you substitute a part, check the **Drives CAD** column and update the "
        "matching parameter before printing. `handoff_lint.py --check-lock` will catch "
        "it if you forget, which is the point of generating this table rather than "
        "maintaining it by hand.",
        "",
    ]
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
