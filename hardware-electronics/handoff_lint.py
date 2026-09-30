#!/usr/bin/env python3
"""handoff_lint.py - component manifest validator and CAD hash lock.

This is the point of the exercise. A BOM's "Drives CAD" column works right up
until two people hold the two halves, and then it fails silently: someone
substitutes a 20 mm speaker for a 28 mm one, nothing complains, and a back shell
gets printed around a part that will not fit it.

The manifest makes the coupling machine-readable and the hash lock makes a
change on one side invalidate the other, by name:

    electronics edits BOM -> manifest regenerated -> content_hash changes
                                                          |
                              cad_lock.json still holds the OLD hash
                                                          |
                        --check-lock -> exit 1, HASH_STALE, naming which
                        fields moved, which cad_parameters they feed, and
                        therefore which STL has to be reprinted.

Commands:

    handoff_lint.py manifest.json [--bom bom.json] [--strict]
    handoff_lint.py manifest.json --write-lock cad_lock.json
    handoff_lint.py manifest.json --check-lock cad_lock.json
    handoff_lint.py manifest.json --check-response cad-response.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    Report,
    WEAK_PROVENANCE,
    base_parser,
    canonicalise,
    content_hash,
    diff_canonical,
    load_json,
    shape_within,
    shapes_overlap,
    validate_schema,
    write_json,
    z_ranges_overlap,
)

TOOL = "handoff_lint"

#: Advisory findings a manifest may accept with a written reason. Notably absent:
#: ASSUMED_DIMENSION, KEEPOUT_OVERLAP, NOT_CONTAINED, HOMELESS_PART,
#: CLEARANCE_UNSATISFIED, HASH_STALE and COUNTER_CONSTRAINT_OPEN. Those are the
#: findings that cost a reprint, and a reprint is not a preference.
ACKNOWLEDGEABLE = frozenset(
    {
        "RF_UNVERIFIED",
        "KEEPOUT_CONDITIONAL",
        "CABLE_CHANNEL_TIGHT",
        "CABLE_POLARITY_UNVERIFIED",
        "ASSEMBLY_ORDER_GAPPY",
        "ASSEMBLY_IRREVERSIBLE_UNEXPLAINED",
        "HASH_DECLARED_MISMATCH",
    }
)


#: Component classes with a functional axis. A part in one of these that has no
#: orientation_constraint is almost certainly going to be installed the obvious
#: way round, which is frequently the wrong way round.
AXIS_CLASSES = {
    "transducer": "a speaker radiates along its cone axis; a piezo along its disc normal",
    "sensor_module": "a reed switch, Hall sensor or optical sensor has a sensing axis",
    "microphone": "a MEMS microphone has a port on one specific face",
    "antenna": "an antenna has a radiation pattern and a ground-plane relationship",
    "display": "a display has a viewing direction and an active-area offset",
    "magnet": "a magnet has a polarity axis",
    "motor": "an eccentric-mass motor has a preferred mounting plane",
}


def _prov_map(fp: Dict[str, Any]) -> Dict[str, str]:
    prov = fp.get("provenance")
    if isinstance(prov, dict):
        return prov
    if isinstance(prov, str):
        if prov.startswith("measured"):
            prov = "measured"
        return {k: prov for k in ("l", "w", "h", "d") if fp.get(k) is not None}
    return {}


def _resolve_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _UNRESOLVED
    return cur


_UNRESOLVED = object()


def _parse_literal(tok: str) -> Any:
    tok = tok.strip().strip("'\"")
    low = tok.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    try:
        return float(tok) if "." in tok else int(tok)
    except ValueError:
        return tok


def eval_condition(manifest: Dict[str, Any], expr: str) -> Optional[bool]:
    """Evaluate a ``<dotted.path> == <literal>`` condition against the manifest.

    Deliberately tiny. A conditional keep-out that nothing can evaluate is a
    keep-out nobody checked, so the grammar is kept small enough to be reliable
    rather than expressive enough to be wrong.
    """
    for op in ("==", "!="):
        if op in expr:
            lhs, rhs = expr.split(op, 1)
            val = _resolve_path(manifest, lhs.strip())
            if val is _UNRESOLVED:
                return None
            want = _parse_literal(rhs)
            return (val == want) if op == "==" else (val != want)
    return None


def _placed(comp: Dict[str, Any], shape: Dict[str, Any]) -> Dict[str, Any]:
    """Component placement shifted by a keep-out's own offset.

    Real keep-outs are rarely concentric with the part: an antenna channel runs
    along one edge, a connector zone sits at one end.
    """
    place = dict(comp.get("placement") or {})
    off = shape.get("offset") or {}
    place["x"] = float(place.get("x", 0.0)) + float(off.get("x", 0.0))
    place["y"] = float(place.get("y", 0.0)) + float(off.get("y", 0.0))
    if off.get("z") is not None:
        place["z"] = float(place.get("z", 0.0)) + float(off["z"])
    return place


def _shapes_of(comp: Dict[str, Any], manifest: Dict[str, Any], rep: Report) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """The footprint plus every ACTIVE keep-out, as (label, shape, placement)."""
    out: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = [
        (comp["id"], comp["footprint"], _placed(comp, comp["footprint"]))
    ]
    for ko in comp.get("keepouts", []) or []:
        cond = ko.get("conditional_on")
        if cond:
            active = eval_condition(manifest, cond)
            if active is None:
                rep.warn(
                    "KEEPOUT_CONDITIONAL",
                    f"{comp['id']}.{ko['id']} is conditional on {cond!r}, which nothing "
                    f"in this manifest resolves, so it was NOT checked for overlap.",
                    fix="Declare the value the condition refers to (for example an "
                    "\"assembly\" block) before the handoff. A conditional keep-out "
                    "that turns out to apply is a keep-out you did not check."
                    + (f" Context: {ko['reason']}" if ko.get("reason") else ""),
                    component=comp["id"],
                    keepout=ko["id"],
                )
                continue
            if not active:
                rep.info(
                    "KEEPOUT_INACTIVE",
                    f"{comp['id']}.{ko['id']} does not apply: {cond} is false.",
                    fix="If the assembly decision changes, this keep-out comes back and "
                    "the geometry changes with it."
                    + (f" {ko['reason']}" if ko.get("reason") else ""),
                    component=comp["id"],
                    keepout=ko["id"],
                )
                continue
        out.append((f"{comp['id']}.{ko['id']}", ko, _placed(comp, ko)))
    return out


def check_overlaps(manifest: Dict[str, Any], rep: Report) -> None:
    comps = [c for c in manifest.get("components", []) if c.get("placement")]
    placed: List[Tuple[str, Dict[str, Any], Dict[str, Any], str]] = []
    for c in comps:
        for label, shape, place in _shapes_of(c, manifest, rep):
            placed.append((label, shape, place, c["id"]))

    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            la, sa, pa, ca = placed[i]
            lb, sb, pb, cb = placed[j]
            if ca == cb:
                continue
            if not z_ranges_overlap(sa, pa, sb, pb):
                continue
            if not shapes_overlap(sa, pa, sb, pb):
                continue
            kind_a = sa.get("kind", "footprint")
            kind_b = sb.get("kind", "footprint")
            rep.error(
                "KEEPOUT_OVERLAP",
                f"{la} ({kind_a}, {sa.get('shape')}) overlaps {lb} ({kind_b}, "
                f"{sb.get('shape')}) in plan view at the same height.",
                fix="Move one part, rotate it if its orientation is not locked, or grow "
                "the envelope. Round parts are checked as ROUND here: describing a "
                "35 mm circle by its bounding box would reserve 21% more area than it "
                "occupies, all of it in the corners - which is exactly where a round "
                "part usually has to live.",
                a=la,
                b=lb,
                a_kind=kind_a,
                b_kind=kind_b,
                reason_a=sa.get("reason"),
                reason_b=sb.get("reason"),
            )


def check_containment(manifest: Dict[str, Any], rep: Report) -> None:
    interior = (manifest.get("envelope") or {}).get("interior") or {}
    if not interior:
        return
    for c in manifest.get("components", []):
        place = c.get("placement")
        if not place:
            continue
        if not shape_within(c["footprint"], place, interior):
            rep.error(
                "NOT_CONTAINED",
                f"{c['id']} extends outside the declared interior envelope "
                f"({interior.get('l')} x {interior.get('w')} mm).",
                fix="Move the part, or veto the envelope. Electronics is entitled to "
                "veto a CAD-proposed envelope when the parts do not fit - that veto is "
                "how an enclosure legitimately grows, and it is far cheaper than "
                "discovering it after a print.",
                component=c["id"],
            )
        h = c["footprint"].get("h")
        if h and interior.get("h"):
            top = float(place.get("z", 0.0)) + float(h)
            if top > float(interior["h"]) + 1e-6:
                rep.error(
                    "NOT_CONTAINED",
                    f"{c['id']} reaches {top:.2f} mm, above the {interior['h']} mm "
                    f"interior height.",
                    fix="Lower the part, reduce the stack, or raise the envelope.",
                    component=c["id"],
                )


def check_provenance(manifest: Dict[str, Any], rep: Report) -> None:
    for c in manifest.get("components", []):
        fp = c.get("footprint") or {}
        prov = _prov_map(fp)
        weak = {k: p for k, p in prov.items() if p in WEAK_PROVENANCE}
        if not weak:
            continue
        if not c.get("drives_cad"):
            continue
        if fp.get("accepted_risk"):
            rep.warn(
                "ASSUMED_DIMENSION_ACCEPTED",
                f"{c['id']} is being built around {list(weak)} dimensions that are "
                f"{sorted(set(weak.values()))}, under a risk accepted by "
                f"{fp['accepted_risk'].get('who')}: {fp['accepted_risk'].get('why')}",
                fix="Legitimate, but not a measurement. Do not call this dimension "
                "verified in any summary.",
                component=c["id"],
            )
            continue
        rep.error(
            "ASSUMED_DIMENSION",
            f"{c['id']} drives CAD and its {list(weak)} dimensions are "
            f"{sorted(set(weak.values()))}. The enclosure is being built around a guess.",
            fix="Measure the part with calipers and promote it through "
            "measure_log.py record, or record footprint.accepted_risk naming who "
            "accepted it and why. There is no third option: this number is about to be "
            "cut into plastic."
            + (
                " This part is also flagged fit_coupon_required - print the coupon first."
                if fp.get("fit_coupon_required")
                else ""
            ),
            component=c["id"],
            weak=weak,
        )


def check_orientation(manifest: Dict[str, Any], rep: Report) -> None:
    for c in manifest.get("components", []):
        oc = c.get("orientation_constraint")
        if oc:
            if oc.get("locked") and not oc.get("reason"):
                rep.error(
                    "ORIENTATION_UNEXPLAINED",
                    f"{c['id']} locks its orientation but gives no reason.",
                    fix="State the functional fact that locks it. An unexplained lock "
                    "gets 'helpfully' rotated by the next person.",
                    component=c["id"],
                )
            continue
        cls = c.get("class")
        if cls in AXIS_CLASSES:
            rep.error(
                "ORIENTATION_UNCONSTRAINED",
                f"{c['id']} is class {cls!r} and has a functional axis "
                f"({AXIS_CLASSES[cls]}), but declares no orientation_constraint.",
                fix="Declare the axis and why it matters. Orientation is the single "
                "most under-recorded electronics fact that drives geometry: in one "
                "reference project, one sensor's sensing axis determined the wall "
                "thickness, the boss, the lid geometry, the magnet pocket and 13.8 mm "
                "of interior depth - and it was written down only in prose.",
                component=c["id"],
            )


def check_cables(manifest: Dict[str, Any], rep: Report) -> None:
    for run in manifest.get("cable_runs", []) or []:
        if not run.get("channel_min"):
            rep.error(
                "CABLE_NO_CHANNEL",
                f"Cable run {run['id']} declares no minimum channel cross-section.",
                fix="State channel_min. Electronics owns the minimum; CAD implements at "
                "least that and reports the realised value back. A run with no stated "
                "minimum gets whatever slot is left over after everything else, which "
                "is how a battery lead ends up unroutable.",
                cable=run["id"],
            )
        else:
            bundle = run.get("bundle_d_mm")
            ch = run["channel_min"]
            if bundle and (float(ch.get("w", 0)) < float(bundle) or float(ch.get("h", 0)) < float(bundle)):
                rep.warn(
                    "CABLE_CHANNEL_TIGHT",
                    f"Cable run {run['id']} has a {bundle} mm bundle and a "
                    f"{ch.get('w')} x {ch.get('h')} mm minimum channel.",
                    fix="A channel smaller than the bundle in either axis means the "
                    "cable is being squeezed. Allow for the bend radius too.",
                    cable=run["id"],
                )
        conn = run.get("connector") or {}
        if conn and conn.get("polarity_verified") is False:
            rep.warn(
                "CABLE_POLARITY_UNVERIFIED",
                f"Cable run {run['id']} uses a {conn.get('type')} connector whose "
                f"polarity has not been metered.",
                fix="Meter it before crimping or plugging. Connector polarity is not "
                "standardised.",
                cable=run["id"],
            )


def check_rf(manifest: Dict[str, Any], rep: Report) -> None:
    env = manifest.get("envelope") or {}
    filled = env.get("material_filled", "none")
    comps = {c["id"]: c for c in manifest.get("components", [])}

    rf_present = any(c.get("rf") for c in comps.values())
    if rf_present and filled not in ("none", None):
        rep.error(
            "RF_MATERIAL_VIOLATED",
            f"The enclosure material is {filled} and this assembly contains an antenna.",
            fix="Electronics owns the material CONSTRAINT as a veto, even though CAD "
            "owns the material choice. Filled filaments are lossy at 2.4 GHz; plain "
            "PLA or PETG makes no measurable difference.",
            material=filled,
        )

    for c in comps.values():
        for rf in c.get("rf", []) or []:
            if rf.get("status") == "UNVERIFIED":
                rep.warn(
                    "RF_UNVERIFIED",
                    f"{c['id']}.{rf['id']} is marked UNVERIFIED: {rf.get('note', '')}",
                    fix="Physically inspect the board before designing an antenna port "
                    "around it. Vendor documents contradict each other about connector "
                    "types more often than you would like.",
                    component=c["id"],
                )
            ko = rf.get("keepout")
            if not ko:
                continue
            if not c.get("placement"):
                continue
            ko_place = _placed(c, ko)
            for other_id in rf.get("clearance_from", []) or []:
                base = other_id.split(".")[0]
                other = comps.get(base)
                if not other or not other.get("placement"):
                    continue
                oshape = other["footprint"]
                if "." in other_id:
                    for k in other.get("keepouts", []) or []:
                        if k["id"] == other_id.split(".", 1)[1]:
                            oshape = k
                            break
                if shapes_overlap(ko, ko_place, oshape, _placed(other, oshape)):
                    rep.error(
                        "RF_KEEPOUT_VIOLATED",
                        f"{other_id} sits inside the {rf['id']} RF keep-out on "
                        f"{c['id']} ({rf['band_mhz']} MHz).",
                        fix="Move it out. Batteries, speaker magnets and motors all "
                        "detune and shadow an antenna, and retrofitting an antenna "
                        "path into a finished shell is painful.",
                        component=c["id"],
                        intruder=other_id,
                    )


def check_homeless(manifest: Dict[str, Any], bom: Optional[Dict[str, Any]], rep: Report) -> None:
    if not bom:
        return
    manifest_ids = {c["id"] for c in manifest.get("components", [])}
    manifest_bom_refs = {c.get("bom_ref") for c in manifest.get("components", [])}
    for row in bom.get("rows", []):
        if not row.get("drives_cad"):
            continue
        if row["id"] in manifest_ids or row["id"] in manifest_bom_refs:
            continue
        rep.error(
            "HOMELESS_PART",
            f"BOM row {row['id']!r} is marked drives_cad but has no entry in the "
            f"manifest. It has nowhere to live in the enclosure.",
            fix="Add a manifest component for it, or clear its drives_cad flag. A part "
            "that drives geometry and has no declared home is a part that will be "
            "discovered during assembly.",
            row=row["id"],
        )


def check_assembly_order(manifest: Dict[str, Any], rep: Report) -> None:
    steps = manifest.get("assembly_order") or []
    if not steps:
        return
    nums = [s["step"] for s in steps]
    if sorted(nums) != list(range(1, len(nums) + 1)):
        rep.warn(
            "ASSEMBLY_ORDER_GAPPY",
            f"Assembly steps are numbered {nums}, which is not a clean 1..n sequence.",
            fix="Renumber. An ambiguous order is the same as no order.",
        )
    for s in steps:
        if s.get("irreversible") and not s.get("why_this_order"):
            rep.warn(
                "ASSEMBLY_IRREVERSIBLE_UNEXPLAINED",
                f"Step {s['step']} ({s['what']}) is irreversible and does not say why it "
                f"sits where it does.",
                fix="Explain the ordering. Irreversible steps done early are the "
                "expensive kind of mistake - a board that has never been powered on "
                "should not be modified, and a solder joint made before a fit check "
                "has to be undone.",
            )


def check_response(
    manifest: Dict[str, Any], response: Dict[str, Any], rep: Report, mhash: str
) -> None:
    validate_schema(response, "cad-response", rep)

    if response.get("responds_to") != mhash:
        rep.error(
            "RESPONSE_STALE",
            f"cad-response.json answers manifest {response.get('responds_to')}, but this "
            f"manifest hashes to {mhash}.",
            fix="Re-run the CAD side against the current manifest. A response to a "
            "different manifest is not an answer to this one.",
            responds_to=response.get("responds_to"),
            manifest_hash=mhash,
        )

    assertions = {a["id"]: a for a in manifest.get("assertions", []) or []}
    reported = {a["id"]: a for a in response.get("assertions", []) or []}

    for aid, a in assertions.items():
        if a.get("owner") == "electronics":
            continue
        r = reported.get(aid)
        if r is None:
            if a.get("blocking", True):
                rep.error(
                    "ASSERTION_UNREPORTED",
                    f"Blocking assertion {aid!r} was not reported on by the CAD side.",
                    fix="The CAD side must evaluate every blocking assertion and report "
                    "pass, fail or not_evaluated. Silence is not a pass.",
                    assertion=aid,
                    why=a.get("why"),
                )
            continue
        if r.get("result") == "fail" or (
            r.get("value") is not None
            and (
                (a.get("min_mm") is not None and float(r["value"]) < float(a["min_mm"]))
                or (a.get("max_mm") is not None and float(r["value"]) > float(a["max_mm"]))
            )
        ):
            rep.error(
                "CLEARANCE_UNSATISFIED",
                f"Assertion {aid!r} realised {r.get('value')} against a band of "
                f"[{a.get('min_mm')}, {a.get('max_mm')}]."
                + (f" Why it matters: {a['why']}" if a.get("why") else ""),
                fix="Fix the geometry. Do NOT widen the band to make it pass - the band "
                "is the requirement, not the score.",
                assertion=aid,
                value=r.get("value"),
                min_mm=a.get("min_mm"),
                max_mm=a.get("max_mm"),
            )

    for run in manifest.get("cable_runs", []) or []:
        realised = ((response.get("realised") or {}).get("channels") or {}).get(run["id"])
        cmin = run.get("channel_min")
        if realised and cmin:
            if float(realised.get("w", 0)) < float(cmin["w"]) or float(realised.get("h", 0)) < float(cmin["h"]):
                rep.error(
                    "CHANNEL_BELOW_MINIMUM",
                    f"Cable run {run['id']}: CAD realised "
                    f"{realised.get('w')} x {realised.get('h')} mm against a declared "
                    f"minimum of {cmin['w']} x {cmin['h']} mm.",
                    fix="Electronics states the minimum; CAD must implement at least it. "
                    "This failure mode is QUIET - the model simply shrinks the channel "
                    "to suit whatever else is in the way, and nothing tells you the "
                    "cable will not fit.",
                    cable=run["id"],
                )

    for cc in response.get("counter_constraints", []) or []:
        if cc.get("acknowledged"):
            rep.info(
                "COUNTER_CONSTRAINT_ACKNOWLEDGED",
                f"{cc['component']}.{cc['field']}: {cc['reason']}",
                component=cc["component"],
            )
            continue
        rep.error(
            "COUNTER_CONSTRAINT_OPEN",
            f"CAD pushed back on an electronics-owned number and it has not been "
            f"acknowledged: {cc['component']}.{cc['field']} was {cc.get('was')}, "
            f"maximum possible {cc.get('max_possible', cc.get('required'))}. "
            f"{cc['reason']}",
            fix=cc.get("action_required")
            or "Edit the BOM and regenerate the manifest. That changes the hash, which "
            "is the invalidation loop working as intended. The dependency runs BOTH "
            "ways: a CAD-side search over real footprints can discover that a part in "
            "the BOM cannot physically fit anywhere.",
            component=cc["component"],
            field=cc["field"],
        )

    if response.get("status") == "rejected":
        rep.error(
            "CAD_REJECTED",
            "The CAD side rejected this manifest outright.",
            fix="Read counter_constraints. Something in the parts list does not fit any "
            "arrangement of the declared envelope.",
        )


def _param_index(manifest: Dict[str, Any]) -> Dict[str, List[str]]:
    """manifest path -> the cad_parameters fed by it."""
    idx: Dict[str, List[str]] = {}
    for i, comp in enumerate(manifest.get("components", []) or []):
        for param, path in (comp.get("cad_parameters") or {}).items():
            full = f"components[{i}].{path}"
            idx.setdefault(full, []).append(param)
            idx.setdefault(f"components.{comp['id']}.{path}", []).append(param)
    return idx


def check_lock(manifest: Dict[str, Any], lock: Dict[str, Any], rep: Report, mhash: str) -> None:
    lhash = lock.get("manifest_hash")
    if lhash == mhash:
        rep.info(
            "LOCK_FRESH",
            f"cad_lock.json matches the manifest ({mhash[:19]}...). The exported "
            f"geometry was built from these numbers.",
        )
        return

    old = lock.get("canonical")
    changes: List[Dict[str, Any]] = []
    if old is not None:
        changes = diff_canonical(old, canonicalise(manifest))

    idx = _param_index(manifest)
    scripts = lock.get("scripts") or {}
    detailed: List[Dict[str, Any]] = []
    for ch in changes:
        path = ch["path"]
        params: List[str] = []
        for key, plist in idx.items():
            if path.endswith(key.split("components.", 1)[-1]) or path == key:
                params.extend(plist)
        params = sorted(set(params))
        affected_scripts = sorted({s for p in params for s in scripts.get(p, [])})
        affected_stls = sorted(
            {s for p in params for s in (lock.get("stls") or {}).get(p, [])}
        )
        detailed.append(
            {
                "path": path,
                "was": ch["was"],
                "now": ch["now"],
                "cad_parameters": params,
                "affects_scripts": affected_scripts,
                "affects_stls": affected_stls,
                "verdict": (
                    f"REPRINT {', '.join(affected_stls)}"
                    if affected_stls
                    else ("re-run CAD" if params else "no geometry dependency recorded")
                ),
            }
        )

    rep.error(
        "HASH_STALE",
        f"The CAD lock was built against a different manifest. Lock holds "
        f"{(lhash or 'nothing')[:19]}...; the manifest now hashes to {mhash[:19]}..."
        + (f" {len(changes)} field(s) moved." if changes else ""),
        fix="Re-run the CAD script with the new parameters, then re-issue "
        "cad-response.json and re-write the lock. Note the hash deliberately ignores "
        "prose: editing a comment must not force a reprint, editing a dimension must.",
        manifest_hash=mhash,
        lock_hash=lhash,
        changed_fields=detailed or None,
    )
    rep.set(changed_fields=detailed)


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser(
        "handoff_lint.py", "Validate the CAD handoff manifest and its hash lock."
    )
    p.add_argument("manifest", help="Path to component-manifest.json")
    p.add_argument("--bom", help="bom.json, to catch drives_cad rows with no home")
    p.add_argument("--check-lock", help="cad_lock.json to validate the manifest against")
    p.add_argument("--write-lock", help="Write a fresh cad_lock.json here")
    p.add_argument("--check-response", help="cad-response.json from the CAD skill")
    args = p.parse_args(argv)

    manifest = load_json(args.manifest, TOOL)
    rep = Report(TOOL, source="static", project=manifest.get("project"))

    validate_schema(manifest, "component-manifest", rep)

    mhash = content_hash(manifest)
    rep.set(
        content_hash=mhash,
        declared_hash=manifest.get("content_hash"),
        components=len(manifest.get("components", []) or []),
    )
    if manifest.get("content_hash") and manifest["content_hash"] != mhash:
        rep.warn(
            "HASH_DECLARED_MISMATCH",
            f"The manifest's own content_hash field ({manifest['content_hash'][:19]}...) "
            f"does not match its computed hash ({mhash[:19]}...).",
            fix="Rewrite content_hash from the computed value, or find out what changed "
            "after it was stamped.",
        )

    bom = load_json(args.bom, TOOL) if args.bom else None

    check_overlaps(manifest, rep)
    check_containment(manifest, rep)
    check_provenance(manifest, rep)
    check_orientation(manifest, rep)
    check_cables(manifest, rep)
    check_rf(manifest, rep)
    check_homeless(manifest, bom, rep)
    check_assembly_order(manifest, rep)

    if args.check_response:
        check_response(manifest, load_json(args.check_response, TOOL), rep, mhash)

    if args.check_lock:
        if not os.path.isfile(args.check_lock):
            rep.error(
                "LOCK_MISSING",
                f"No CAD lock at {args.check_lock}.",
                fix="Run --write-lock after the CAD side has exported geometry from this "
                "manifest. Without a lock there is nothing that knows which STL "
                "belongs to which numbers.",
            )
        else:
            check_lock(manifest, load_json(args.check_lock, TOOL), rep, mhash)

    if args.write_lock:
        lock = {
            "schema": "hardware-electronics/cad-lock",
            "version": "1.0",
            "manifest_hash": mhash,
            "written": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "canonical": canonicalise(manifest),
            "scripts": {},
            "stls": {},
        }
        if os.path.isfile(args.write_lock):
            prev = load_json(args.write_lock, TOOL)
            lock["scripts"] = prev.get("scripts", {})
            lock["stls"] = prev.get("stls", {})
        write_json(args.write_lock, lock)
        rep.set(lock_written=args.write_lock)
        rep.note(
            "Lock written. Populate its \"scripts\" and \"stls\" maps (cad_parameter -> "
            "files) so a future HASH_STALE can name exactly what has to be reprinted "
            "instead of just saying something changed."
        )

    rep.apply_acceptances(manifest.get("accepted_findings"), ACKNOWLEDGEABLE)

    return rep.emit(args.strict)


if __name__ == "__main__":
    sys.exit(main())
