#!/usr/bin/env python3
"""profiles.py - thin dispatcher for the board-profiles tools.

    python profiles.py new     --kind board --id xiao_esp32c3 --family ESP32-C3
    python profiles.py lint    boards/xiao_esp32c3.json --strict
    python profiles.py lint    --all --parent <electronics-design>
    python profiles.py verify  against-silicon draft.json --identify id.json
    python profiles.py install draft.json
    python profiles.py audit   [--parent <electronics-design>]
    python profiles.py doctor
"""

from __future__ import annotations

import argparse
import os
import runpy
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proflib import (  # noqa: E402
    BOARD_GROUPS,
    PART_GROUPS,
    SOURCE_KINDS,
    Report,
    find_parent,
    load_json,
)

TOOL = "profiles"
HERE = os.path.dirname(os.path.abspath(__file__))

ALIASES = {
    "new": "new_profile.py",
    "lint": "profile_lint.py",
    "verify": "verify_profile.py",
}


def _delegate(script: str, argv: List[str]) -> int:
    path = os.path.join(HERE, script)
    sys.argv = [path] + argv
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """One-page view of what the parent skill currently believes, and why."""
    parent = find_parent(args.parent)
    rep = Report(TOOL, source="static", command="audit", parent=parent)
    if not parent:
        rep.error(
            "PARENT_NOT_FOUND",
            "Could not locate the electronics-design skill.",
            fix="Pass --parent with its path.",
        )
        rep.emit(args.strict)
        return 3

    rows: List[Dict[str, Any]] = []
    for kind, sub in (("board", "boards"), ("part", "parts")):
        d = os.path.join(parent, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json") or fn.startswith("_") or fn == "connectors.json":
                continue
            p = load_json(os.path.join(d, fn), TOOL)
            corr = p.get("corroboration") or {}
            groups = corr.get("groups") or {}
            spec = BOARD_GROUPS if kind == "board" else PART_GROUPS
            rows.append(
                {
                    "kind": kind,
                    "file": f"{sub}/{fn}",
                    "id": p.get("id"),
                    "status": p.get("status", "draft"),
                    "family": p.get("family"),
                    "sources": len(corr.get("sources") or []),
                    "groups_declared": sorted(groups),
                    "groups_expected": sorted(
                        g for g, s in spec.items()
                        if any(p.get(f) not in (None, {}, [], "") for f in s["fields"])
                    ),
                    "contradictions": len(corr.get("contradictions") or []),
                    "unresolved": len(
                        [c for c in (corr.get("contradictions") or [])
                         if c.get("resolution") == "unresolved"]
                    ),
                    "conservative": bool(corr.get("conservative")),
                }
            )

    drafts = [r for r in rows if r["status"] == "draft"]
    uncorroborated = [r for r in rows if not r["sources"] and r["status"] != "superseded"]
    unresolved = sum(r["unresolved"] for r in rows)

    rep.set(
        profiles=rows,
        count=len(rows),
        drafts=[r["id"] for r in drafts],
        uncorroborated=[r["id"] for r in uncorroborated],
        unresolved_contradictions=unresolved,
    )

    if drafts:
        rep.warn(
            "DRAFTS_INSTALLED",
            f"{len(drafts)} installed profile(s) are drafts: "
            f"{[r['id'] for r in drafts]}.",
            fix="Designs validated against these are warned, which is correct. "
            "Corroborate them or accept the warning deliberately.",
        )
    if uncorroborated:
        rep.error(
            "UNCORROBORATED_INSTALLED",
            f"{len(uncorroborated)} installed profile(s) cite no sources at all: "
            f"{[r['id'] for r in uncorroborated]}.",
            fix="Every one of these is validating designs right now with no stated "
            "reason to be believed. Add a corroboration record, even if it only says "
            "'general knowledge for this family, deliberately conservative'.",
        )
    if unresolved:
        rep.info(
            "UNRESOLVED_CONTRADICTIONS",
            f"{unresolved} recorded contradiction(s) across all profiles remain "
            f"unresolved.",
            fix="That is honest as long as they are reported to the user when the "
            "affected number is used. It stops being honest the moment one is quoted "
            "as fact.",
        )
    return rep.emit(args.strict)


def cmd_doctor(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="static", python=sys.version.split()[0], skill_root=HERE)
    tools = {
        n: os.path.isfile(os.path.join(HERE, n))
        for n in ("proflib.py", "profile_lint.py", "new_profile.py", "verify_profile.py")
    }
    rep.set(tools=tools)

    try:
        import jsonschema  # noqa: F401

        rep.set(jsonschema=True)
    except ImportError:
        rep.set(jsonschema=False)
        rep.warn(
            "JSONSCHEMA_MISSING",
            "jsonschema is not installed, so structural validation is skipped and every "
            "run is degraded.",
            fix="python -m pip install -r requirements.txt",
        )

    parent = find_parent(args.parent)
    rep.set(parent=parent)
    if parent:
        rep.info(
            "PARENT_FOUND",
            f"electronics-design found at {parent}. Profiles can be installed and "
            f"audited.",
        )
    else:
        rep.warn(
            "PARENT_NOT_FOUND",
            "electronics-design was not found.",
            fix="Authoring and linting still work anywhere; only install and audit need "
            "the parent. Pass --parent to point at it.",
        )

    rep.set(
        board_groups={g: s["min_independent"] for g, s in BOARD_GROUPS.items()},
        part_groups={g: s["min_independent"] for g, s in PART_GROUPS.items()},
        source_kinds={k: v["independent"] for k, v in SOURCE_KINDS.items()},
    )
    return rep.emit(args.strict)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ALIASES:
        return _delegate(ALIASES[argv[0]], argv[1:])
    if argv and argv[0] == "install":
        return _delegate("verify_profile.py", ["install"] + argv[1:])

    p = argparse.ArgumentParser(prog="profiles.py", description=__doc__ or "")
    p.add_argument("--strict", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("audit", help="What the parent skill believes, and why")
    a.add_argument("--parent")
    a.set_defaults(func=cmd_audit)

    d = sub.add_parser("doctor", help="What is installed and what the thresholds are")
    d.add_argument("--parent")
    d.set_defaults(func=cmd_doctor)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
