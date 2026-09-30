#!/usr/bin/env python3
"""run_cad_model.py - run a CadQuery script without trusting its exit code.

## The trap this exists for

On Windows, CadQuery scripts routinely exit with **-1073740940** (0xC0000374,
heap corruption) or **-1073741819** (0xC0000005, access violation) *on success*.
The work is finished and the STL is already written; OpenCASCADE then crashes
during interpreter teardown, after the useful part of the run is over.

The CAD skill's own `run_cadquery_model.py` does:

    result["success"] = proc.returncode == 0
    if result["success"]:
        ...discover the STL files...

so under the teardown crash **every successful build reports failure with an
empty `stls` list**. That defect is real and it is upstream, in a third-party
skill this one deliberately does not modify.

## What this does instead

Two independent success signals, neither of which is `returncode`:

1. **A stdout sentinel.** If the script's last meaningful stdout line is
   ``HWEL_RESULT {json}``, that JSON is the result. Add one line to your script:

       print("HWEL_RESULT " + json.dumps({"stls": ["front.stl"], "ok": True}))

   A missing sentinel is the failure signal; a nonzero exit *with* a valid
   sentinel is a **pass**.

2. **Fresh artefacts.** Failing that, any STL/3MF/STEP written after the run
   started counts as evidence the script got where it was going.

A nonzero exit code with no sentinel and no fresh files is a genuine failure and
is reported as one. The teardown crash codes are recognised by number and
reported as `TEARDOWN_CRASH`, at info level, so nobody spends an afternoon on
them.

This file imports nothing from CadQuery. It only runs a subprocess.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hwlib import Report, base_parser  # noqa: E402

TOOL = "run_cad_model"

SENTINEL = "HWEL_RESULT"

#: Windows NTSTATUS values seen from an OpenCASCADE teardown crash AFTER the
#: geometry was already exported. Treated as noise, never as failure on their own.
TEARDOWN_CODES = {
    -1073740940: "0xC0000374 STATUS_HEAP_CORRUPTION",
    -1073741819: "0xC0000005 STATUS_ACCESS_VIOLATION",
    3221226356: "0xC0000374 STATUS_HEAP_CORRUPTION",
    3221225477: "0xC0000005 STATUS_ACCESS_VIOLATION",
}

ARTEFACT_EXTS = (".stl", ".3mf", ".step", ".stp")


def parse_sentinel(stdout: str) -> Optional[Dict[str, Any]]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith(SENTINEL):
            continue
        payload = line[len(SENTINEL):].strip()
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return {"_malformed": payload}
        return data if isinstance(data, dict) else {"_malformed": payload}
    return None


def fresh_artefacts(directory: str, since: float) -> List[str]:
    out: List[str] = []
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if not f.lower().endswith(ARTEFACT_EXTS):
                continue
            path = os.path.join(root, f)
            try:
                if os.path.getmtime(path) >= since - 1.0:
                    out.append(path)
            except OSError:
                continue
    return sorted(out, key=lambda p: -os.path.getmtime(p))


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser(
        "run_cad_model.py", "Run a CadQuery script and judge it by its output, not its exit code."
    )
    p.add_argument("script", help="Path to the CadQuery .py file")
    p.add_argument("--python", help="Interpreter to run it with (default: this one)")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--expect-stl", action="append", help="Filename that must exist afterwards. Repeatable.")
    p.add_argument("--args", nargs=argparse.REMAINDER, help="Arguments passed through to the script")
    args = p.parse_args(argv)

    script = os.path.abspath(args.script)
    script_dir = os.path.dirname(script) or "."
    rep = Report(TOOL, source="simulated", script=args.script)

    if not os.path.isfile(script):
        rep.error("SCRIPT_MISSING", f"No such script: {script}")
        return rep.emit(args.strict)

    interpreter = args.python or sys.executable
    argv_run = [interpreter, script] + (args.args or [])
    started = time.time()

    try:
        proc = subprocess.run(
            argv_run, capture_output=True, text=True, timeout=args.timeout, cwd=script_dir
        )
    except FileNotFoundError as exc:
        rep.error("INTERPRETER_MISSING", f"Cannot launch {interpreter}: {exc}")
        return rep.emit(args.strict)
    except subprocess.TimeoutExpired:
        rep.error(
            "TIMEOUT",
            f"The script did not finish within {args.timeout}s.",
            fix="A CadQuery script that hangs is usually a boolean on degenerate "
            "geometry, not a slow machine.",
        )
        rep.emit(args.strict)
        return 3

    elapsed = round(time.time() - started, 2)
    sentinel = parse_sentinel(proc.stdout)
    artefacts = fresh_artefacts(script_dir, started)

    rep.set(
        returncode=proc.returncode,
        elapsed_s=elapsed,
        sentinel=sentinel,
        fresh_artifacts=artefacts,
        stdout=proc.stdout[-4000:],
        stderr=proc.stderr[-2000:],
    )

    teardown = proc.returncode in TEARDOWN_CODES
    if teardown:
        rep.info(
            "TEARDOWN_CRASH",
            f"The process exited {proc.returncode} ({TEARDOWN_CODES[proc.returncode]}). "
            f"That is an OpenCASCADE teardown crash AFTER the work was done, not a "
            f"failure. Read stdout, not the exit code.",
            fix="No action. This is the documented behaviour of CadQuery on this "
            "platform, and it is why this runner ignores returncode entirely.",
            returncode=proc.returncode,
        )

    if sentinel is not None and "_malformed" in sentinel:
        rep.error(
            "SENTINEL_MALFORMED",
            f"Found a {SENTINEL} line but its payload is not JSON: "
            f"{sentinel['_malformed'][:200]}",
            fix=f'Emit exactly: print("{SENTINEL} " + json.dumps({{...}}))',
        )
        sentinel = None

    if sentinel is not None:
        rep.set(stls=sentinel.get("stls", artefacts), result=sentinel)
        if sentinel.get("ok") is False:
            rep.error(
                "SCRIPT_REPORTED_FAILURE",
                f"The script's own {SENTINEL} says it failed: "
                f"{sentinel.get('error', 'no reason given')}",
                fix="Fix the cause. Do not wrap a failing fillet in try/except to "
                "silently shrink the radius - a fillet failure means the geometry or "
                "the radius is wrong.",
            )
        else:
            rep.info(
                "SENTINEL_OK",
                f"The script reported success through {SENTINEL}, which is the signal "
                f"this runner trusts.",
            )
    elif artefacts:
        rep.set(stls=[a for a in artefacts if a.lower().endswith(".stl")])
        rep.warn(
            "NO_SENTINEL",
            f"No {SENTINEL} line, but {len(artefacts)} artefact(s) were written during "
            f"the run, so the script got where it was going.",
            fix=f'Add one line to the script so success stops being inferred:\n'
            f'    print("{SENTINEL} " + json.dumps({{"ok": True, "stls": [...]}}))\n'
            f"Inference from file timestamps is a fallback, not a contract.",
        )
    else:
        rep.error(
            "NO_OUTPUT",
            "No sentinel and no freshly written geometry. The script did not produce "
            "anything."
            + (f" Exit code {proc.returncode}." if not teardown else ""),
            fix="Read stdout and stderr. Note that a nonzero exit code alone proves "
            "nothing on this platform - but nothing written does.",
        )

    for want in args.expect_stl or []:
        hit = [a for a in artefacts if os.path.basename(a) == os.path.basename(want)]
        if hit:
            rep.info("EXPECTED_STL_PRESENT", f"{want} was written.", stl=hit[0])
        else:
            rep.error(
                "EXPECTED_STL_MISSING",
                f"{want} was not written during this run.",
                fix="An old file on disk from a previous run does not count. This "
                "check is deliberately timestamp-based.",
                expected=want,
            )

    return rep.emit(args.strict)


if __name__ == "__main__":
    sys.exit(main())
