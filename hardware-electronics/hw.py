#!/usr/bin/env python3
"""hw.py - thin dispatcher and phase gate runner.

    python hw.py phases                 list the nine phases and their gates
    python hw.py check --phase N        run phase N's gate over a project directory
    python hw.py pinmap  <args...>      -> pinmap_lint.py
    python hw.py bom     <args...>      -> bom_lint.py
    python hw.py power   <args...>      -> power_budget.py
    python hw.py handoff <args...>      -> handoff_lint.py
    python hw.py measure <args...>      -> measure_log.py
    python hw.py doctor                 what is installed, what is missing

A phase gate is a command with an exit code. The agent may not advance until the
gate exits 0, and it derives its recovery action from a finding ``code``, never
from prose. Phases are skippable only by writing an explicit record into
project.json ``skipped``, never silently - a project built entirely around a
vendor sensor with its own coin cell legitimately skips the power budget, and
that skip should be visible rather than inferred from an absence.
"""

from __future__ import annotations

import argparse
import os
import runpy
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    EXIT_OK,
    Report,
    load_json,
    validate_schema,
)

TOOL = "hw"
HERE = os.path.dirname(os.path.abspath(__file__))

MAX_AC_V = 50.0
MAX_DC_V = 120.0

PHASES: List[Dict[str, Any]] = [
    {"n": 0, "name": "Intake & safety triage", "produces": "project.json", "gate": "hw check --phase 0"},
    {"n": 1, "name": "Requirements & constraints", "produces": "requirements.json", "gate": "hw check --phase 1"},
    {"n": 2, "name": "Part selection & BOM", "produces": "bom.json", "gate": "bom_lint.py bom.json --strict"},
    {"n": 3, "name": "Power budget", "produces": "power.json", "gate": "power_budget.py power.json --strict"},
    {"n": 4, "name": "Pin map & bus allocation", "produces": "pinmap.json", "gate": "pinmap_lint.py pinmap.json --strict"},
    {"n": 5, "name": "Wiring artefact", "produces": "netlist.json + wiring.md", "gate": "wiring_render.py netlist.json --strict"},
    {"n": 6, "name": "Board bring-up", "produces": "bringup-<date>.json", "gate": "board_cli.py identify --board <id> --strict"},
    {"n": 7, "name": "Incremental peripheral tests", "produces": "probe-<peripheral>.json", "gate": "probe_client.py probes/<name>.json --strict"},
    {"n": 8, "name": "CAD handoff", "produces": "component-manifest.json", "gate": "handoff_lint.py component-manifest.json --strict"},
    {"n": 9, "name": "Integration & audit", "produces": "audit", "gate": "measure_log.py audit --manifest ... --strict"},
]

FILES = {
    "project": "project.json",
    "requirements": "requirements.json",
    "bom": "bom.json",
    "power": "power.json",
    "pinmap": "pinmap.json",
    "netlist": "netlist.json",
    "manifest": "component-manifest.json",
    "lock": "cad_lock.json",
    "response": "cad-response.json",
    "ledger": "measurements.jsonl",
}


def _delegate(script: str, argv: List[str]) -> int:
    """Run a sibling tool in-process so its JSON is the only thing on stdout."""
    path = os.path.join(HERE, script)
    if not os.path.isfile(path):
        rep = Report(TOOL, source="static")
        rep.error(
            "TOOL_NOT_BUILT",
            f"{script} is not present in this installation.",
            fix="This build ships milestones M0-M5. The serial and wiring tools "
            "(board_cli.py, probe_client.py, wiring_render.py) are not included.",
        )
        return rep.emit(False) or 2
    sys.argv = [path] + argv
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


# --------------------------------------------------------------------------
# phase 0
# --------------------------------------------------------------------------


def phase0(project_dir: str, strict: bool) -> int:
    rep = Report(TOOL, source="static", phase=0, phase_name=PHASES[0]["name"])
    path = os.path.join(project_dir, FILES["project"])
    if not os.path.isfile(path):
        rep.error(
            "PHASE_INPUT_MISSING",
            f"No {FILES['project']} in {project_dir}.",
            fix="Write project.json first: what is being built, the highest voltage "
            "anywhere in it, whether it is safety-critical, and what test equipment "
            "the user actually owns.",
        )
        return rep.emit(strict)

    proj = load_json(path, TOOL)
    validate_schema(proj, "project", rep)

    vc = proj.get("voltage_class") or {}
    max_v = float(vc.get("max_v", 0))
    kind = vc.get("kind", "dc")
    limit = MAX_AC_V if kind == "ac" else MAX_DC_V

    if vc.get("mains_involved"):
        rep.refuse(
            "MAINS_REFUSED",
            "This project involves mains or line voltage.",
            fix="This skill does not work on mains wiring, fixed building installations "
            "or anything inside a mains PSU. Use a licensed electrician, or a certified "
            "off-the-shelf module that is never opened. Everything downstream of an "
            "isolated, certified supply is in scope.",
        )
    elif max_v > limit:
        rep.refuse(
            "VOLTAGE_REFUSED",
            f"{max_v} V {kind.upper()} is above this skill's limit of "
            f"{MAX_AC_V:.0f} V AC / {MAX_DC_V:.0f} V DC.",
            fix="Above that limit the failure modes are lethal rather than expensive, "
            "and the right answer is a qualified person rather than a better checklist.",
        )
    else:
        rep.info("VOLTAGE_OK", f"{max_v} V {kind.upper()} is within the safe working limit.")

    app = proj.get("application") or {}
    if app.get("safety_critical"):
        if app.get("certified_primary_exists") and app.get("redundant_secondary_only"):
            rep.warn(
                "SAFETY_SECONDARY_ONLY",
                f"This is a {app.get('safety_category', 'safety-critical')} application "
                f"and is proceeding ONLY as a redundant secondary indicator alongside a "
                f"certified primary.",
                fix="Every artefact must say so. Nothing here may be presented as the "
                "primary protection, and no failure of this device may be the only "
                "thing standing between the user and harm.",
            )
        else:
            rep.refuse(
                "SAFETY_CRITICAL_REFUSED",
                f"This is a {app.get('safety_category', 'safety-critical')} application: "
                f"{app.get('description', '')}",
                fix="Use certified commercial equipment. This skill may assist with a "
                "redundant SECONDARY indicator only when a certified primary already "
                "exists - set certified_primary_exists and redundant_secondary_only. "
                "The boundary is real: a medication REMINDER that watches a lid and "
                "nags a phone is in scope; a dispenser or a dose controller is not.",
            )

    tools = proj.get("tools") or {}
    skipped_phases = {s.get("phase") for s in (proj.get("skipped") or [])}

    #: Phases whose gates can only be closed with an instrument. If every one of
    #: them is explicitly skipped there is nothing to meter, and demanding a
    #: multimeter would be the "every project is a reference project A" failure: a pill box
    #: watched by a vendor sensor on its own coin cell has no rails, no charge
    #: current and no sleep current, and refusing to help with it would rule out
    #: the far more common hobbyist case.
    METERED_PHASES = {3, 6, 7}
    needs_meter = bool(METERED_PHASES - skipped_phases)

    if not tools.get("multimeter"):
        if needs_meter:
            rep.error(
                "NO_MULTIMETER",
                "No multimeter is declared, and this project still has live phases "
                f"{sorted(METERED_PHASES - skipped_phases)} that can only be closed "
                "with one: connector polarity, charge current, sleep current, "
                "battery-sense calibration, rail voltage under load and pre-power-on "
                "continuity all need an instrument.",
                fix="Say this to the user NOW, at phase 0, not at phase 9. Either get "
                "a meter, or agree up front which numbers will stay unverified and "
                "record them as accepted risks. A twenty-pound meter is cheaper than "
                "one ruined board.",
                live_metered_phases=sorted(METERED_PHASES - skipped_phases),
            )
        else:
            rep.info(
                "NO_MULTIMETER_NOT_NEEDED",
                "No multimeter is declared, but every phase that needs one "
                f"({sorted(METERED_PHASES)}) is explicitly skipped, so no metered "
                "gate is in scope. Nothing here is powered by this design.",
                fix="If any of those phases is later un-skipped, the requirement comes "
                "back. Dimensions being printed around still need calipers.",
            )
    if tools.get("multimeter") and not tools.get("multimeter_ua_range") and 3 not in skipped_phases:
        rep.warn(
            "NO_UA_RANGE",
            "The meter has no microamp range, so deep-sleep current cannot be measured.",
            fix="Sleep current usually dominates a battery-life estimate. Without it, "
            "runtime stays a calculation built on a vendor claim.",
        )
    if not tools.get("calipers"):
        rep.warn(
            "NO_CALIPERS",
            "No calipers declared, so no part dimension can be promoted to 'measured'.",
            fix="Any dimension being printed around will stay at seller_claimed or "
            "assumed, and handoff_lint.py will demand an accepted_risk record for each.",
        )

    for s in proj.get("skipped", []) or []:
        rep.info(
            "PHASE_SKIPPED",
            f"Phase {s['phase']} is explicitly skipped: {s['reason']}",
            phase=s["phase"],
        )

    rep.set(
        voltage_class=vc,
        safety_critical=bool(app.get("safety_critical")),
        tools=tools,
        skipped_phases=sorted(p for p in skipped_phases if p is not None),
        reachable_gates={
            "measured_dimensions": bool(tools.get("calipers")),
            "measured_currents": bool(tools.get("multimeter")),
            "measured_sleep_current": bool(tools.get("multimeter_ua_range")),
            "metered_gates_in_scope": needs_meter,
        },
    )
    return rep.emit(strict)


# --------------------------------------------------------------------------
# phase 1
# --------------------------------------------------------------------------


def _find_nulls(obj: Any, path: str = "") -> List[str]:
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if v is None:
                out.append(p)
            else:
                out.extend(_find_nulls(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            if v is None:
                out.append(p)
            else:
                out.extend(_find_nulls(v, p))
    return out


def _find_untagged(obj: Any, path: str = "") -> List[str]:
    """A dict with a numeric 'value' and no 'provenance' is an untagged number."""
    out: List[str] = []
    if isinstance(obj, dict):
        if "value" in obj and "provenance" not in obj:
            out.append(path or "<root>")
        for k, v in obj.items():
            out.extend(_find_untagged(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_find_untagged(v, f"{path}[{i}]"))
    return out


def phase1(project_dir: str, strict: bool) -> int:
    rep = Report(TOOL, source="static", phase=1, phase_name=PHASES[1]["name"])
    path = os.path.join(project_dir, FILES["requirements"])
    if not os.path.isfile(path):
        rep.error(
            "PHASE_INPUT_MISSING",
            f"No {FILES['requirements']} in {project_dir}.",
            fix="Write requirements.json. Every must-fit dimension, runtime target and "
            "environmental limit needs a value AND a provenance tag. No nulls, no bare "
            "prose - a requirement without provenance is a wish.",
        )
        return rep.emit(strict)

    req = load_json(path, TOOL)
    validate_schema(req, "requirements", rep)

    nulls = _find_nulls(req)
    if nulls:
        rep.error(
            "REQUIREMENT_NULL",
            f"{len(nulls)} field(s) are null: {nulls[:12]}"
            + (" ..." if len(nulls) > 12 else ""),
            fix="Fill them in, or delete the key. A null is an unanswered question "
            "dressed as an answer. Ask the user for the specific missing field BY NAME.",
            fields=nulls,
        )

    untagged = _find_untagged(req)
    if untagged:
        rep.error(
            "REQUIREMENT_UNTAGGED",
            f"{len(untagged)} value(s) carry no provenance: {untagged}",
            fix="Tag each one. Even 'assumed' is an answer; silence is not.",
            fields=untagged,
        )

    for mf in req.get("must_fit", []) or []:
        if not mf.get("provenance"):
            rep.error(
                "REQUIREMENT_UNTAGGED",
                f"must_fit {mf.get('id')!r} has no provenance.",
                fix="Say where the limit came from - a measured pocket, a datasheet, or "
                "a guess.",
            )

    rep.set(
        must_fit=len(req.get("must_fit", []) or []),
        has_runtime_target=bool((req.get("runtime") or {}).get("target_days")),
    )
    return rep.emit(strict)


# --------------------------------------------------------------------------
# generic phase dispatch
# --------------------------------------------------------------------------


def _exists(project_dir: str, key: str) -> Optional[str]:
    p = os.path.join(project_dir, FILES[key])
    return p if os.path.isfile(p) else None





def cmd_check(args: argparse.Namespace) -> int:
    d = args.dir
    n = args.phase
    strict = True if args.strict or not args.lenient else False

    if n == 0:
        return phase0(d, strict)
    if n == 1:
        return phase1(d, strict)
    if n == 2:
        f = _exists(d, "bom")
        if not f:
            return _missing(2, FILES["bom"], d, strict)
        extra = []
        if _exists(d, "power"):
            extra += ["--power", _exists(d, "power")]
        if _exists(d, "manifest"):
            extra += ["--manifest", _exists(d, "manifest")]
        return _delegate("bom_lint.py", [f] + extra + (["--strict"] if strict else []))
    if n == 3:
        f = _exists(d, "power")
        if not f:
            return _missing(3, FILES["power"], d, strict)
        return _delegate("power_budget.py", [f] + (["--strict"] if strict else []))
    if n == 4:
        f = _exists(d, "pinmap")
        if not f:
            return _missing(4, FILES["pinmap"], d, strict)
        return _delegate("pinmap_lint.py", [f] + (["--strict"] if strict else []))
    if n == 5:
        f = _exists(d, "netlist")
        if not f:
            return _missing(5, FILES["netlist"], d, strict)
        return _delegate(
            "wiring_render.py", [f, "--out-dir", d] + (["--strict"] if strict else [])
        )
    if n == 6:
        rep = Report(TOOL, source="static", phase=6, phase_name=PHASES[6]["name"])
        rep.error(
            "PHASE_NEEDS_HARDWARE",
            "Phase 6 is a bring-up against real silicon and cannot be gated from a "
            "project directory alone.",
            fix="Run it directly, naming the board so the reading becomes a CHECK:\n"
            "  board_cli.py backup --out factory.bin        (unseen board, FIRST)\n"
            "  board_cli.py identify --board <id> --strict\n"
            "A profile mismatch exits 1 and names the field. Record the result with "
            "measure_log.py so phase 9 can see it.",
        )
        return rep.emit(strict)
    if n == 7:
        probes = os.path.join(d, "probes")
        specs = (
            sorted(
                os.path.join(probes, f)
                for f in os.listdir(probes)
                if f.endswith(".json")
            )
            if os.path.isdir(probes)
            else []
        )
        rep = Report(TOOL, source="static", phase=7, phase_name=PHASES[7]["name"])
        if not specs:
            rep.error(
                "PHASE_INPUT_MISSING",
                f"No probe specs in {probes}.",
                fix="Write one spec per peripheral, each with a plausibility band. "
                "One peripheral at a time: bringing up an I2S mic and an I2S amp "
                "together and getting silence tells you nothing.",
            )
            return rep.emit(strict)
        rep.set(specs=specs)
        rep.error(
            "PHASE_NEEDS_HARDWARE",
            f"{len(specs)} probe spec(s) found. Each must be run against the board "
            f"one at a time; this gate cannot run them for you.",
            fix="For each spec: probe_client.py <spec> --port COMn --strict\n"
            "An implausibly GOOD result is a FAIL, not a pass. Do not widen a band "
            "to make one go green.",
        )
        return rep.emit(strict)
    if n == 8:
        f = _exists(d, "manifest")
        if not f:
            return _missing(8, FILES["manifest"], d, strict)
        extra = []
        if _exists(d, "bom"):
            extra += ["--bom", _exists(d, "bom")]
        if _exists(d, "lock"):
            extra += ["--check-lock", _exists(d, "lock")]
        if _exists(d, "response"):
            extra += ["--check-response", _exists(d, "response")]
        return _delegate("handoff_lint.py", [f] + extra + (["--strict"] if strict else []))
    if n == 9:
        argv = ["--ledger", os.path.join(d, FILES["ledger"])]
        if strict:
            argv.append("--strict")
        argv.append("audit")
        if _exists(d, "manifest"):
            argv += ["--manifest", _exists(d, "manifest")]
        if _exists(d, "bom"):
            argv += ["--bom", _exists(d, "bom")]
        return _delegate("measure_log.py", argv)

    rep = Report(TOOL, source="static")
    rep.error("PHASE_UNKNOWN", f"Phase {n} does not exist. Phases run 0 to 9.")
    return rep.emit(strict)


def _missing(n: int, fname: str, d: str, strict: bool) -> int:
    ph = PHASES[n]
    rep = Report(TOOL, source="static", phase=n, phase_name=ph["name"])
    rep.error(
        "PHASE_INPUT_MISSING",
        f"No {fname} in {d}, so phase {n} ({ph['name']}) cannot be gated.",
        fix=f"Produce {fname} first. If this phase genuinely does not apply to this "
        f"project, record it in project.json under \"skipped\" with a reason - never "
        f"just leave the file out. An absent artefact and a deliberate skip look "
        f"identical from the outside, and only one of them is safe.",
    )
    return rep.emit(strict)


def cmd_phases(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static")
    rep.set(
        phases=[
            {**p, "built": p.get("built", True)} for p in PHASES
        ],
        note="A gate is a command with an exit code. Do not advance on prose.",
    )
    return rep.emit(args.strict)


def cmd_doctor(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static", python=sys.version.split()[0], skill_root=HERE)
    tools = {}
    for name in (
        "measure_log.py",
        "pinmap_lint.py",
        "bom_lint.py",
        "power_budget.py",
        "handoff_lint.py",
        "wiring_render.py",
        "board_cli.py",
        "probe_client.py",
        "serial_io.py",
        os.path.join("cad_bridge", "consume_manifest.py"),
        os.path.join("cad_bridge", "run_cad_model.py"),
        os.path.join("firmware", "probe", "probe.ino"),
    ):
        tools[name.replace("\\", "/")] = os.path.isfile(os.path.join(HERE, name))
    rep.set(tools=tools)

    optional: Dict[str, Any] = {}
    for mod, why in (
        ("jsonschema", "structural validation of every input file"),
        ("serial", "board_cli.py and probe_client.py (pyserial)"),
        ("esptool", "chip identity and factory flash backup"),
    ):
        try:
            __import__(mod)
            optional[mod] = True
        except ImportError:
            optional[mod] = False
            rep.warn(
                "PYTHON_DEP_MISSING",
                f"{mod} is not installed, so {why} is unavailable.",
                fix="python -m pip install -r requirements.txt",
                module=mod,
            )
    rep.set(python_deps=optional)

    import shutil as _sh

    binaries = {
        "arduino-cli": _sh.which("arduino-cli")
        or (
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "arduino-cli", "arduino-cli.exe")
            if os.path.isfile(
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "arduino-cli", "arduino-cli.exe")
            )
            else None
        ),
        "dot": _sh.which("dot"),
    }
    rep.set(binaries=binaries)
    if not binaries["arduino-cli"]:
        rep.info(
            "ARDUINO_CLI_MISSING",
            "arduino-cli was not found. It is an external binary, not a pip package, "
            "so requirements.txt cannot supply it.",
            fix="Install from https://arduino.github.io/arduino-cli/ . Only build and "
            "flash need it; identify, monitor and backup use esptool.",
        )
    if not binaries["dot"]:
        rep.info(
            "GRAPHVIZ_MISSING",
            "Graphviz `dot` was not found, so wiring_render.py will emit Mermaid text "
            "instead of an SVG.",
            fix="Optional. The connection table is the artefact that gets used at the "
            "bench and it does not need Graphviz.",
        )

    if sys.version_info >= (3, 13):
        rep.warn(
            "PYTHON_TOO_NEW",
            f"Python {sys.version.split()[0]}. This skill itself runs fine, but the "
            f"paired parametric-3d-printing skill needs OpenCASCADE wheels that do not "
            f"exist for 3.13+.",
            fix="Use Python 3.12 for the shared venv so both skills can run in it.",
        )

    boards = sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(os.path.join(HERE, "boards"))
        if f.endswith(".json") and not f.startswith("_")
    )
    parts = sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(os.path.join(HERE, "parts"))
        if f.endswith(".json") and not f.startswith("_")
    )
    rep.set(boards=boards, parts=parts)
    return rep.emit(args.strict)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    aliases = {
        "pinmap": "pinmap_lint.py",
        "bom": "bom_lint.py",
        "power": "power_budget.py",
        "handoff": "handoff_lint.py",
        "measure": "measure_log.py",
        "board": "board_cli.py",
        "probe": "probe_client.py",
        "wiring": "wiring_render.py",
        "cad": os.path.join("cad_bridge", "consume_manifest.py"),
        "runcad": os.path.join("cad_bridge", "run_cad_model.py"),
    }
    if argv and argv[0] in aliases:
        return _delegate(aliases[argv[0]], argv[1:])

    p = argparse.ArgumentParser(prog="hw.py", description=__doc__ or "")
    p.add_argument("--strict", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="Run a phase gate")
    c.add_argument("--phase", type=int, required=True)
    c.add_argument("--dir", default=".", help="Project directory (default: cwd)")
    c.add_argument(
        "--lenient",
        action="store_true",
        help="Do NOT promote warnings to errors. Gates default to strict for a reason.",
    )
    c.set_defaults(func=cmd_check)

    ph = sub.add_parser("phases", help="List the nine phases and their gates")
    ph.set_defaults(func=cmd_phases)

    d = sub.add_parser("doctor", help="Report what is installed and what is missing")
    d.set_defaults(func=cmd_doctor)

    args = p.parse_args(argv)
    if not hasattr(args, "lenient"):
        args.lenient = False
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
