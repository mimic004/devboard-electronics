#!/usr/bin/env python3
"""consume_manifest.py - the CAD side of the handoff, without touching the CAD skill.

`parametric-3d-printing` is third-party and licensed separately, so this bridge
lives here instead of being patched into it. Nothing in this file imports
CadQuery; it turns a component manifest into plain data a CAD script can read,
and turns a finished build back into a `cad-response.json` the electronics side
can validate.

    params    manifest -> a flat parameter dict (JSON) plus an importable
              manifest_params.py, so a CadQuery script never hard-codes a
              dimension the BOM owns
    envelope  the keep-out and containment budget, as data
    respond   scaffold a cad-response.json pre-filled with the manifest's own
              assertions, cable minima and component list
    check     validate a filled-in response against the manifest before it is
              handed back

The ownership rule this enforces by construction: electronics owns what is true
about the PART, CAD owns what is true about the PLASTIC. Every value emitted by
`params` is electronics-owned and must be read, never invented; anything CAD
decides - placement, wall, clearance, fillets - is absent from it on purpose.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hwlib import (  # noqa: E402
    Report,
    WEAK_PROVENANCE,
    base_parser,
    content_hash,
    load_json,
    write_json,
)

TOOL = "consume_manifest"


def _resolve(comp: Dict[str, Any], path: str) -> Any:
    """Resolve a cad_parameters path like 'openings.display_window.offset.x'.

    Openings and keep-outs are lists in the manifest but addressed by id here,
    because a CAD script wants ``win_offset_x``, not ``components[0].openings[3]``.
    """
    cur: Any = comp
    for part in path.split("."):
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
                continue
            listed = cur.get(part + "s") if isinstance(cur.get(part + "s"), list) else None
            if listed is not None:
                cur = listed
                continue
            return None
        if isinstance(cur, list):
            match = [item for item in cur if isinstance(item, dict) and item.get("id") == part]
            if match:
                cur = match[0]
                continue
            return None
        return None
    return cur


def _prov_of(comp: Dict[str, Any], path: str) -> Optional[str]:
    if not path.startswith("footprint."):
        return None
    axis = path.split(".", 1)[1]
    prov = (comp.get("footprint") or {}).get("provenance")
    if isinstance(prov, dict):
        return prov.get(axis)
    if isinstance(prov, str):
        return "measured" if prov.startswith("measured") else prov
    return None


def collect_params(manifest: Dict[str, Any], rep: Report) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    provenance: Dict[str, str] = {}

    for comp in manifest.get("components", []) or []:
        for name, path in (comp.get("cad_parameters") or {}).items():
            value = _resolve(comp, path)
            if value is None:
                rep.error(
                    "PARAMETER_UNRESOLVED",
                    f"{comp['id']}.cad_parameters[{name!r}] points at {path!r}, which "
                    f"resolves to nothing.",
                    fix="Fix the path or add the field. A CAD script that falls back "
                    "to a default for a missing parameter is a CAD script that "
                    "silently invents a dimension the BOM owns.",
                    component=comp["id"],
                    parameter=name,
                    path=path,
                )
                continue
            if name in params and params[name] != value:
                rep.error(
                    "PARAMETER_COLLISION",
                    f"Parameter {name!r} is defined twice with different values "
                    f"({params[name]!r} and {value!r}).",
                    fix="Rename one. Two components cannot own the same CAD parameter.",
                    parameter=name,
                )
                continue
            params[name] = value
            prov = _prov_of(comp, path)
            if prov:
                provenance[name] = prov

    weak = {k: v for k, v in provenance.items() if v in WEAK_PROVENANCE}
    if weak:
        rep.warn(
            "PARAMETERS_UNMEASURED",
            f"{len(weak)} parameter(s) come from numbers nobody has measured: {weak}.",
            fix="These are about to become plastic. Close them with calipers and "
            "measure_log.py, or record an accepted_risk on the manifest. Note that "
            "handoff_lint.py --strict will refuse the handoff for any of them that "
            "drive CAD without one.",
            parameters=sorted(weak),
        )

    return {"params": params, "provenance": provenance}


def collect_envelope(manifest: Dict[str, Any]) -> Dict[str, Any]:
    env = manifest.get("envelope") or {}
    out: Dict[str, Any] = {
        "interior": env.get("interior"),
        "exterior": env.get("exterior"),
        "split_plane_z": env.get("split_plane_z"),
        "wall": env.get("wall"),
        "material_constraint": {
            "forbidden_filled": ["carbon_filled", "glass_filled", "metal_filled"],
            "why": "Filled filaments are lossy at 2.4 GHz. Plain PLA or PETG is "
            "transparent enough that it makes no measurable difference. Electronics "
            "owns this as a VETO even though CAD owns the material choice.",
        }
        if any(c.get("rf") for c in manifest.get("components", []) or [])
        else None,
        "datum": manifest.get("datum"),
        "components": [],
        "cable_channel_minima": {},
        "assertions": manifest.get("assertions", []),
    }

    for comp in manifest.get("components", []) or []:
        oc = comp.get("orientation_constraint") or {}
        out["components"].append(
            {
                "id": comp["id"],
                "class": comp.get("class"),
                "footprint": {
                    k: v
                    for k, v in (comp.get("footprint") or {}).items()
                    if k in ("shape", "l", "w", "h", "d", "points", "tolerance")
                },
                "keepouts": comp.get("keepouts", []),
                "openings": comp.get("openings", []),
                "rf": comp.get("rf", []),
                "orientation_locked": bool(oc.get("locked")),
                "orientation_axis": oc.get("axis"),
                "orientation_reason": oc.get("reason"),
                "placement_owner": "cad",
            }
        )

    for run in manifest.get("cable_runs", []) or []:
        if run.get("channel_min"):
            out["cable_channel_minima"][run["id"]] = {
                **run["channel_min"],
                "bundle_d_mm": run.get("bundle_d_mm"),
                "min_bend_r_mm": run.get("min_bend_r_mm"),
            }
    return out


PY_HEADER = '''"""manifest_params.py - GENERATED. Do not edit.

Generated by electronics-design/cad_bridge/consume_manifest.py from
{project} at manifest hash {hash}.

Every value here is ELECTRONICS-OWNED. Read them; do not round them, pad them,
or "clean them up". In particular do not add your own clearance to a dimension
that already carries a tolerance - double-clearancing is a real failure and it
is invisible until the part rattles.

If a number here is wrong, fix the BOM and regenerate the manifest. Editing this
file makes the hash lock lie.
"""

MANIFEST_HASH = "{hash}"
PROJECT = "{project}"

'''


def emit_python(params: Dict[str, Any], provenance: Dict[str, str], manifest: Dict[str, Any]) -> str:
    lines = [PY_HEADER.format(project=manifest.get("project", "project"), hash=content_hash(manifest))]
    for name in sorted(params):
        value = params[name]
        prov = provenance.get(name)
        comment = f"  # {prov}" if prov else ""
        if isinstance(value, str):
            lines.append(f'{name} = "{value}"{comment}')
        else:
            lines.append(f"{name} = {value!r}{comment}")
    lines.append("")
    lines.append("PARAMS = {")
    for name in sorted(params):
        lines.append(f'    "{name}": {name},')
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_params(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest, TOOL)
    rep = Report(TOOL, source="static", command="params", project=manifest.get("project"))
    mhash = content_hash(manifest)
    rep.set(manifest_hash=mhash)

    collected = collect_params(manifest, rep)
    rep.set(params=collected["params"], provenance=collected["provenance"])

    if args.out:
        write_json(args.out, {
            "schema": "hardware-electronics/cad-params",
            "version": "1.0",
            "manifest_hash": mhash,
            "project": manifest.get("project"),
            "params": collected["params"],
            "provenance": collected["provenance"],
        })
        rep.set(out=args.out)

    if args.out_py:
        d = os.path.dirname(os.path.abspath(args.out_py))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(args.out_py, "w", encoding="utf-8") as fh:
            fh.write(emit_python(collected["params"], collected["provenance"], manifest))
        rep.set(out_py=args.out_py)
        rep.note(
            "Import manifest_params in your CadQuery script instead of typing "
            "dimensions into it. A hard-coded number is a number the hash lock "
            "cannot invalidate."
        )

    return rep.emit(args.strict)


def cmd_envelope(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest, TOOL)
    rep = Report(TOOL, source="static", command="envelope", project=manifest.get("project"))
    env = collect_envelope(manifest)
    rep.set(manifest_hash=content_hash(manifest), envelope=env)

    locked = [c["id"] for c in env["components"] if c["orientation_locked"]]
    if locked:
        rep.info(
            "ORIENTATION_LOCKED",
            f"{locked} have locked orientations. CAD may NOT rotate them, whatever "
            f"the packing solver would prefer.",
            components=locked,
        )
    if env.get("material_constraint"):
        rep.info(
            "MATERIAL_VETO",
            "This assembly contains an antenna, so filled filaments are vetoed.",
        )
    return rep.emit(args.strict)


def cmd_respond(args: argparse.Namespace) -> int:
    """Scaffold a cad-response.json that is already correct in its skeleton."""
    manifest = load_json(args.manifest, TOOL)
    rep = Report(TOOL, source="static", command="respond", project=manifest.get("project"))
    mhash = content_hash(manifest)

    response: Dict[str, Any] = {
        "schema": "hardware-electronics/cad-response",
        "version": "1.0",
        "responds_to": mhash,
        "generated": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "accepted",
        "realised": {
            "envelope": {"interior": (manifest.get("envelope") or {}).get("interior")},
            "placements": {
                c["id"]: (c.get("placement") or {"x": 0, "y": 0, "z": 0, "rotation_z": 0})
                for c in manifest.get("components", []) or []
            },
            "channels": {
                r["id"]: dict(r["channel_min"])
                for r in manifest.get("cable_runs", []) or []
                if r.get("channel_min")
            },
            "clearances": {},
        },
        "assertions": [
            {"id": a["id"], "result": "not_evaluated", "value": None,
             "note": "REPLACE: evaluate this and report pass or fail. Silence is not a pass."}
            for a in manifest.get("assertions", []) or []
        ],
        "counter_constraints": [],
        "artifacts": {"stls": [], "previews": [], "scripts": [], "watertight": None},
    }

    if os.path.isfile(args.out) and not args.force:
        rep.error(
            "RESPONSE_EXISTS",
            f"{args.out} already exists.",
            fix="Pass --force to overwrite, but read it first: it may contain "
            "counter-constraints the electronics side has not seen yet.",
        )
        return rep.emit(args.strict)

    write_json(args.out, response)
    rep.set(out=args.out, manifest_hash=mhash, assertions=len(response["assertions"]))
    rep.note(
        "Every assertion is scaffolded as not_evaluated on purpose. Fill each one in "
        "with a real pass/fail and a measured value; handoff_lint.py treats an "
        "unreported blocking assertion as a failure, because silence is not a pass."
    )
    rep.note(
        "If the geometry cannot honour an electronics-owned number - a part that does "
        "not fit anywhere, an envelope that cannot shrink - add a counter_constraint "
        "rather than quietly adjusting it. The dependency runs both ways."
    )
    return rep.emit(args.strict)


def cmd_check(args: argparse.Namespace) -> int:
    """Pre-flight a response before handing it back to handoff_lint.py."""
    manifest = load_json(args.manifest, TOOL)
    response = load_json(args.response, TOOL)
    rep = Report(TOOL, source="static", command="check", project=manifest.get("project"))

    mhash = content_hash(manifest)
    rep.set(manifest_hash=mhash, responds_to=response.get("responds_to"))

    if response.get("responds_to") != mhash:
        rep.error(
            "RESPONSE_STALE",
            f"This response answers {response.get('responds_to')}, not {mhash}.",
            fix="Regenerate against the current manifest. A response to a different "
            "manifest is not an answer to this one.",
        )

    declared = {a["id"] for a in manifest.get("assertions", []) or []}
    reported = {a["id"]: a for a in response.get("assertions", []) or []}

    for aid in sorted(declared):
        r = reported.get(aid)
        if r is None:
            rep.error(
                "ASSERTION_UNREPORTED",
                f"Assertion {aid!r} is not in the response.",
                fix="Report every assertion. Silence is not a pass.",
                assertion=aid,
            )
        elif r.get("result") == "not_evaluated":
            rep.error(
                "ASSERTION_NOT_EVALUATED",
                f"Assertion {aid!r} is still the scaffolded not_evaluated placeholder.",
                fix="Evaluate it. Handing back a scaffold is handing back nothing.",
                assertion=aid,
            )

    for run in manifest.get("cable_runs", []) or []:
        cmin = run.get("channel_min")
        got = ((response.get("realised") or {}).get("channels") or {}).get(run["id"])
        if cmin and not got:
            rep.error(
                "CHANNEL_UNREPORTED",
                f"Cable run {run['id']!r} has a declared minimum but no realised value.",
                fix="Report what you actually built. The failure this catches is "
                "quiet: the model shrinks a channel to suit whatever else is in the "
                "way and nothing says the cable will not fit.",
                cable=run["id"],
            )

    for comp in manifest.get("components", []) or []:
        oc = comp.get("orientation_constraint") or {}
        if not oc.get("locked"):
            continue
        placed = ((response.get("realised") or {}).get("placements") or {}).get(comp["id"])
        original = comp.get("placement") or {}
        if placed and original:
            if float(placed.get("rotation_z", 0)) != float(original.get("rotation_z", 0)):
                rep.error(
                    "ORIENTATION_VIOLATED",
                    f"{comp['id']} has a LOCKED orientation but the response rotated it "
                    f"from {original.get('rotation_z', 0)} to {placed.get('rotation_z')}.",
                    fix=oc.get("reason")
                    or "CAD may not rotate a part whose orientation constraint is "
                    "locked. If the layout genuinely needs it, raise a "
                    "counter_constraint instead.",
                    component=comp["id"],
                )

    if rep.counts()["error"] == 0:
        rep.info(
            "RESPONSE_READY",
            "This response is structurally complete. Hand it to handoff_lint.py "
            "--check-response for the substantive checks.",
        )
    return rep.emit(args.strict)


def build_parser() -> argparse.ArgumentParser:
    p = base_parser("consume_manifest.py", "Bridge a component manifest into a CAD run.")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("params", help="Flatten the manifest into CAD parameters")
    a.add_argument("manifest")
    a.add_argument("--out", help="Write cad-params.json here")
    a.add_argument("--out-py", help="Write an importable manifest_params.py here")
    a.set_defaults(func=cmd_params)

    b = sub.add_parser("envelope", help="Emit the keep-out and containment budget")
    b.add_argument("manifest")
    b.set_defaults(func=cmd_envelope)

    c = sub.add_parser("respond", help="Scaffold a cad-response.json")
    c.add_argument("manifest")
    c.add_argument("--out", required=True)
    c.add_argument("--force", action="store_true")
    c.set_defaults(func=cmd_respond)

    d = sub.add_parser("check", help="Pre-flight a filled-in response")
    d.add_argument("manifest")
    d.add_argument("--response", required=True)
    d.set_defaults(func=cmd_check)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
