#!/usr/bin/env python3
"""measure_log.py - the provenance ledger.

An append-only record of every number the project depends on, plus an audit that
refuses to pass while a number that will be soldered to a cell or printed around
is still somebody's guess.

This is the honesty machine. It exists because the failure mode in electronics
is not a crash: a wrong number does not error, it gets ordered, soldered,
printed around, and discovered three weeks later.

  record   append a value with its provenance
  get      read the current (latest) value for a key
  list     dump the ledger
  audit    fail while any verify_before_build key is below 'measured'
  report   the two-tier 'verified on hardware' vs 'not yet run' table
  sweep    record a fit-test sweep and catch a range bounded from the wrong end

RULES THIS TOOL ENFORCES

  * Only 'measured' may be called verified. Everything else is a calculation, a
    claim, or a guess with a price attached.
  * A 'measured' entry requires a named instrument. There is no flag that fakes
    one.
  * Promotion happens here or not at all. No validator may promote a provenance
    tag on its own.
  * A sweep whose winner sits at either END of the tested range was bounded from
    the wrong end and needs a second round.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    EXIT_FAIL,
    EXIT_OK,
    EXIT_REFUSED,
    PROVENANCE_LADDER,
    Report,
    WEAK_PROVENANCE,
    base_parser,
    die,
    load_json,
    provenance_rank,
)

TOOL = "measure_log"
DEFAULT_LEDGER = "measurements.jsonl"


# --------------------------------------------------------------------------
# ledger io
# --------------------------------------------------------------------------


def read_ledger(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    entries: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                die(TOOL, "LEDGER_CORRUPT", f"{path}:{lineno} is not valid JSON: {exc}")
    return entries


def append_ledger(path: str, entry: Dict[str, Any]) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=False) + "\n")


def latest(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Last write wins, which is why the ledger is append-only and timestamped."""
    out: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        key = e.get("key")
        if key:
            out[key] = e
    return out


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# record
# --------------------------------------------------------------------------


def cmd_record(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static", command="record", ledger=args.ledger)

    if args.provenance not in PROVENANCE_LADDER:
        die(
            TOOL,
            "PROVENANCE_UNKNOWN",
            f"{args.provenance!r} is not a provenance value. "
            f"Use one of: {', '.join(PROVENANCE_LADDER)}",
        )

    if args.provenance == "measured" and not args.instrument:
        rep.refuse(
            "MEASURED_WITHOUT_INSTRUMENT",
            "A 'measured' entry requires --instrument naming what read the value. "
            "There is no flag that fakes a measurement.",
            fix="Re-run with --instrument, e.g. --instrument \"Fluke 117, uA range, "
            "in series with battery +, USB disconnected\".",
            key=args.key,
        )
        rep.set(recorded=False)
        return rep.emit(args.strict)

    entries = read_ledger(args.ledger)
    current = latest(entries).get(args.key)

    value: Any = args.value
    try:
        value = float(args.value)
        if value.is_integer() and "." not in args.value:
            value = int(value)
    except (TypeError, ValueError):
        pass

    entry: Dict[str, Any] = {
        "ts": now_iso(),
        "key": args.key,
        "value": value,
        "provenance": args.provenance,
    }
    if args.unit:
        entry["unit"] = args.unit
    if args.instrument:
        entry["instrument"] = args.instrument
    if args.operator:
        entry["operator"] = args.operator
    if args.note:
        entry["note"] = args.note

    if current is not None:
        entry["supersedes"] = {
            "value": current.get("value"),
            "provenance": current.get("provenance"),
            "ts": current.get("ts"),
        }
        old_rank = provenance_rank(current.get("provenance"))
        new_rank = provenance_rank(args.provenance)
        if new_rank < old_rank and not args.allow_demotion:
            rep.refuse(
                "PROVENANCE_DEMOTION",
                f"{args.key} is currently {current.get('provenance')!r} "
                f"({current.get('value')}); writing {args.provenance!r} would weaken it.",
                fix="If the stronger value was wrong, say so explicitly with "
                "--allow-demotion and a --note explaining what was discovered.",
                key=args.key,
                was=current.get("provenance"),
                now=args.provenance,
            )
            rep.set(recorded=False)
            return rep.emit(args.strict)
        if new_rank > old_rank:
            rep.info(
                "PROMOTED",
                f"{args.key}: {current.get('provenance')} -> {args.provenance}.",
                key=args.key,
                was=current.get("value"),
                now=value,
            )

    append_ledger(args.ledger, entry)
    rep.set(recorded=True, entry=entry)
    if args.provenance in WEAK_PROVENANCE:
        rep.note(
            f"{args.key} is now {args.provenance}. It may NOT be described as "
            "verified, tested, confirmed or working. Permitted vocabulary: "
            "designed, expected, calculated, per datasheet, not yet run."
        )
    return rep.emit(args.strict)


# --------------------------------------------------------------------------
# get / list
# --------------------------------------------------------------------------


def cmd_get(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static", command="get", key=args.key, ledger=args.ledger)
    entries = read_ledger(args.ledger)
    cur = latest(entries).get(args.key)
    if cur is None:
        rep.error(
            "KEY_UNKNOWN",
            f"No ledger entry for {args.key!r}.",
            fix="Record it, or check the key spelling against `measure_log.py list`.",
            key=args.key,
        )
        rep.set(found=False)
        return rep.emit(args.strict)
    rep.set(
        found=True,
        entry=cur,
        verified=cur.get("provenance") == "measured",
        history=[e for e in entries if e.get("key") == args.key],
    )
    return rep.emit(args.strict)


def cmd_list(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static", command="list", ledger=args.ledger)
    entries = read_ledger(args.ledger)
    cur = latest(entries)
    rep.set(
        count=len(entries),
        keys=len(cur),
        current={k: cur[k] for k in sorted(cur)},
    )
    return rep.emit(args.strict)


# --------------------------------------------------------------------------
# gates
# --------------------------------------------------------------------------


def _gates_from_manifest(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    gates: List[Dict[str, Any]] = []
    for g in manifest.get("open_gates", []) or []:
        gates.append(
            {
                "key": g.get("key"),
                "provenance": g.get("provenance"),
                "assumed": g.get("assumed"),
                "unit": g.get("unit"),
                "verify_before_build": g.get("verify_before_build", True),
                "how_to_close": g.get("how_to_close"),
                "impact": g.get("impact"),
                "conflict": g.get("conflict"),
                "origin": "manifest.open_gates",
            }
        )
    for comp in manifest.get("components", []) or []:
        fp = comp.get("footprint") or {}
        vb = fp.get("verify_before")
        if vb in (None, "none"):
            continue
        prov = fp.get("provenance")
        weak_axes = []
        if isinstance(prov, dict):
            weak_axes = [a for a, p in prov.items() if p in WEAK_PROVENANCE]
        elif isinstance(prov, str) and prov in WEAK_PROVENANCE:
            weak_axes = ["footprint"]
        for axis in weak_axes:
            gates.append(
                {
                    "key": f"{comp['id']}.footprint.{axis}",
                    "provenance": prov if isinstance(prov, str) else prov[axis],
                    "assumed": fp.get(axis if axis != "footprint" else "l"),
                    "unit": "mm",
                    "verify_before_build": vb in ("print", "order", "solder", "assembly"),
                    "how_to_close": (
                        "Calipers on the physical part."
                        + (
                            " A fit coupon is required for this part before committing a full print."
                            if fp.get("fit_coupon_required")
                            else ""
                        )
                    ),
                    "impact": f"Drives CAD parameters for {comp['id']}.",
                    "accepted_risk": fp.get("accepted_risk"),
                    "origin": f"manifest.components.{comp['id']}.footprint",
                }
            )
    return [g for g in gates if g.get("key")]


def _gates_from_bom(bom: Dict[str, Any]) -> List[Dict[str, Any]]:
    gates: List[Dict[str, Any]] = []
    for row in bom.get("rows", []) or []:
        fp = row.get("footprint") or {}
        vb = fp.get("verify_before")
        if vb in (None, "none"):
            continue
        prov = fp.get("provenance")
        axes: Dict[str, str] = {}
        if isinstance(prov, dict):
            axes = {a: p for a, p in prov.items() if p in WEAK_PROVENANCE}
        elif isinstance(prov, str) and prov in WEAK_PROVENANCE:
            axes = {a: prov for a in ("l", "w", "h", "d") if fp.get(a) is not None}
        for axis, p in axes.items():
            gates.append(
                {
                    "key": f"{row['id']}.footprint.{axis}",
                    "provenance": p,
                    "assumed": fp.get(axis),
                    "unit": "mm",
                    "verify_before_build": True,
                    "how_to_close": f"Calipers on the physical part, {axis} axis.",
                    "impact": "BOM dimension with a verify_before gate.",
                    "origin": f"bom.rows.{row['id']}",
                }
            )
    return gates


def cmd_audit(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static", command="audit", ledger=args.ledger)
    entries = read_ledger(args.ledger)
    cur = latest(entries)

    gates: List[Dict[str, Any]] = []
    sources: List[str] = []
    if args.manifest:
        sources.append(args.manifest)
        gates += _gates_from_manifest(load_json(args.manifest, TOOL))
    if args.bom:
        sources.append(args.bom)
        gates += _gates_from_bom(load_json(args.bom, TOOL))
    if args.gates:
        sources.append(args.gates)
        extra = load_json(args.gates, TOOL)
        gates += extra if isinstance(extra, list) else extra.get("gates", [])

    rep.set(sources=sources)

    if not sources:
        rep.warn(
            "NO_GATES_DECLARED",
            "Nothing was audited: no manifest, no BOM and no gates file was given.",
            fix="Pass --manifest, --bom or --gates. An audit that examined nothing is "
            "not a pass.",
        )
    elif not gates:
        rep.info(
            "AUDIT_NO_OPEN_GATES",
            f"{len(sources)} source(s) were examined and none declared a number that "
            f"still needs verifying. Every dimension carries a provenance the build "
            f"can stand on.",
            fix="This is a legitimate clean audit, not an empty one. It stays clean "
            "only while nothing is substituted: a new part with a seller-claimed "
            "dimension reopens a gate here.",
        )

    # de-duplicate on key, strongest declaration wins
    merged: Dict[str, Dict[str, Any]] = {}
    for g in gates:
        k = g["key"]
        if k not in merged or g.get("verify_before_build"):
            merged[k] = {**merged.get(k, {}), **g}

    open_gates: List[Dict[str, Any]] = []
    closed: List[Dict[str, Any]] = []

    for key in sorted(merged):
        g = merged[key]
        rec = cur.get(key)
        rec_prov = rec.get("provenance") if rec else None
        effective = rec_prov or g.get("provenance")
        row = {
            "key": key,
            "declared_provenance": g.get("provenance"),
            "ledger_provenance": rec_prov,
            "effective_provenance": effective,
            "value": (rec or {}).get("value", g.get("assumed")),
            "unit": (rec or {}).get("unit", g.get("unit")),
            "origin": g.get("origin"),
        }
        if effective == "measured":
            row["instrument"] = (rec or {}).get("instrument")
            row["ts"] = (rec or {}).get("ts")
            closed.append(row)
            continue

        if not g.get("verify_before_build", True):
            row["waived"] = "not marked verify_before_build"
            closed.append(row)
            continue

        accepted = g.get("accepted_risk")
        if accepted:
            row["accepted_risk"] = accepted
            closed.append(row)
            rep.warn(
                "RISK_ACCEPTED",
                f"{key} is still {effective!r} and is being built around under an "
                f"accepted risk recorded by {accepted.get('who')}.",
                fix="This is legitimate, but it is not a measurement. Do not describe "
                "it as verified.",
                key=key,
            )
            continue

        open_gates.append(row)
        rep.error(
            "GATE_OPEN",
            f"{key} is {effective!r}, not 'measured', and the build depends on it."
            + (f" Conflict: {g['conflict']}" if g.get("conflict") else ""),
            fix=g.get("how_to_close") or "Measure it and record it with measure_log.py record.",
            key=key,
            value=row["value"],
            unit=row["unit"],
            impact=g.get("impact"),
            origin=g.get("origin"),
        )

    rep.set(
        gates_total=len(merged),
        gates_open=len(open_gates),
        gates_closed=len(closed),
        open=open_gates,
        closed=closed,
    )
    if open_gates:
        rep.note(
            "Every open gate above is a number that will be ordered, soldered or "
            "printed around while still being a guess. Close it with an instrument, "
            "or record an explicit accepted_risk naming who accepted it and why."
        )
    return rep.emit(args.strict)


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static", command="report", ledger=args.ledger)
    entries = read_ledger(args.ledger)
    cur = latest(entries)

    verified: List[Dict[str, Any]] = []
    unverified: List[Dict[str, Any]] = []
    for key in sorted(cur):
        e = cur[key]
        (verified if e.get("provenance") == "measured" else unverified).append(e)

    lines: List[str] = []
    lines.append("## Verified on hardware")
    lines.append("")
    if verified:
        lines.append("| Key | Value | Instrument | When |")
        lines.append("| --- | --- | --- | --- |")
        for e in verified:
            val = f"{e.get('value')}{(' ' + e['unit']) if e.get('unit') else ''}"
            lines.append(
                f"| `{e['key']}` | {val} | {e.get('instrument', '-')} | {e.get('ts', '-')} |"
            )
    else:
        lines.append("Nothing. No number in this project has been read off an instrument yet.")
    lines.append("")
    lines.append("## Not yet measured")
    lines.append("")
    if unverified:
        lines.append("| Key | Value | Provenance | May be called verified? |")
        lines.append("| --- | --- | --- | --- |")
        for e in unverified:
            val = f"{e.get('value')}{(' ' + e['unit']) if e.get('unit') else ''}"
            lines.append(f"| `{e['key']}` | {val} | {e.get('provenance')} | no |")
    else:
        lines.append("Nothing outstanding in the ledger.")
    lines.append("")
    lines.append(
        "> A number this skill computed is a **calculation**. A number from a "
        "datasheet is a **claim**. A number a seller typed into a listing is a "
        "**guess with a price attached**. Only a number read off an instrument, on "
        "this hardware, on a stated date, is a **measurement**."
    )

    rep.set(
        verified_count=len(verified),
        unverified_count=len(unverified),
        verified=verified,
        unverified=unverified,
        report_markdown="\n".join(lines),
    )
    if unverified:
        rep.warn(
            "UNVERIFIED_PRESENT",
            f"{len(unverified)} value(s) in the ledger are below 'measured'.",
            fix="Reproduce the two-tier table above verbatim in any summary you write. "
            "Do not paraphrase it into a single confident list.",
        )
    return rep.emit(args.strict)


# --------------------------------------------------------------------------
# sweep
# --------------------------------------------------------------------------


def cmd_sweep(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static", command="sweep", ledger=args.ledger, key=args.key)

    try:
        values = sorted(float(v) for v in args.values)
        winner = float(args.winner)
    except ValueError:
        die(TOOL, "SWEEP_UNPARSEABLE", "--values and --winner must all be numbers.")

    if winner not in values:
        die(
            TOOL,
            "SWEEP_WINNER_NOT_TESTED",
            f"The winning value {winner} is not in the tested set {values}.",
        )

    rep.set(tested=values, winner=winner, span=[values[0], values[-1]])

    if len(values) < 2:
        rep.error(
            "SWEEP_TOO_SMALL",
            "A sweep of one value is not a sweep.",
            fix="Test at least three values, and make sure the winner is not at an end.",
        )
    elif winner in (values[0], values[-1]):
        end = "smallest" if winner == values[0] else "largest"
        rep.error(
            "SWEEP_BOUNDED_WRONG",
            f"The winning value {winner} is the {end} value tested, so the range was "
            f"bounded from the wrong end. The true optimum may lie beyond it and was "
            f"never tried.",
            fix=f"Run a second round extending past {winner} in the {end} direction, "
            "then re-record.",
            key=args.key,
            winner=winner,
            tested=values,
        )
    else:
        rep.info(
            "SWEEP_BRACKETED",
            f"{winner} is bracketed by {values[values.index(winner) - 1]} and "
            f"{values[values.index(winner) + 1]}. The optimum is inside the tested range.",
            key=args.key,
        )

    if args.record:
        if not args.instrument:
            rep.refuse(
                "MEASURED_WITHOUT_INSTRUMENT",
                "Recording a sweep result as 'measured' requires --instrument.",
                fix="Name the coupon and the tool, e.g. --instrument \"printed fit "
                "coupon B, calipers\".",
            )
            return rep.emit(args.strict)
        if rep.counts()["error"] and not args.force:
            rep.note(
                "Not recorded: the sweep failed its own check. Fix the bounding "
                "problem first, or pass --force with a note explaining why the "
                "result stands anyway."
            )
        else:
            entry = {
                "ts": now_iso(),
                "key": args.key,
                "value": winner,
                "unit": args.unit or "mm",
                "provenance": "measured",
                "instrument": args.instrument,
                "note": args.note or f"Fit sweep over {values}; winner {winner}.",
                "sweep": {"tested": values, "winner": winner},
            }
            append_ledger(args.ledger, entry)
            rep.set(recorded=True, entry=entry)

    return rep.emit(args.strict)


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = base_parser("measure_log.py", __doc__ or "")
    p.add_argument("--ledger", default=DEFAULT_LEDGER, help=f"Path to the ledger (default {DEFAULT_LEDGER})")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("record", help="Append a value with its provenance")
    r.add_argument("--key", required=True)
    r.add_argument("--value", required=True)
    r.add_argument("--unit")
    r.add_argument(
        "--provenance",
        required=True,
        metavar="{" + ",".join(PROVENANCE_LADDER) + "}",
        help="Where the number came from. Only 'measured' may be called verified.",
    )
    r.add_argument("--instrument", help="Required for 'measured'. Name what read the value.")
    r.add_argument("--operator")
    r.add_argument("--note")
    r.add_argument("--allow-demotion", action="store_true")
    r.set_defaults(func=cmd_record)

    g = sub.add_parser("get", help="Read the current value for a key")
    g.add_argument("--key", required=True)
    g.set_defaults(func=cmd_get)

    ls = sub.add_parser("list", help="Dump the ledger")
    ls.set_defaults(func=cmd_list)

    a = sub.add_parser("audit", help="Fail while a build-critical number is unmeasured")
    a.add_argument("--manifest")
    a.add_argument("--bom")
    a.add_argument("--gates")
    a.set_defaults(func=cmd_audit)

    rp = sub.add_parser("report", help="Two-tier verified / not-yet-measured table")
    rp.set_defaults(func=cmd_report)

    s = sub.add_parser("sweep", help="Record a fit sweep and check its bounding")
    s.add_argument("--key", required=True)
    s.add_argument("--values", required=True, nargs="+")
    s.add_argument("--winner", required=True)
    s.add_argument("--unit")
    s.add_argument("--record", action="store_true")
    s.add_argument("--instrument")
    s.add_argument("--note")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_sweep)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
