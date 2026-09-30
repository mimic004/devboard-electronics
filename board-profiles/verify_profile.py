#!/usr/bin/env python3
"""verify_profile.py - check a profile against evidence, then install it.

Documents corroborate each other. Only hardware settles an argument.

    against-silicon   compare the profile to a board_cli.py identify result
    against-sweep     compare the free/consumed map to a probe gpio sweep
    install           lint, then copy into the parent skill's boards/ or parts/

The sweep check is the sharp one. A pin the profile calls free that reads HELD
is driven by something on the board that no document mentioned - which is
exactly the failure mode a pin map cannot have, because the design that
allocates it will validate clean and then fight the hardware.

Nothing here writes a `measurement` source unless it was given a real result
from a real run. A recorded transcript stays recorded; there is no flag that
promotes it.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proflib import (  # noqa: E402
    Report,
    base_parser,
    compact,
    die,
    find_parent,
    int_keys,
    load_json,
    parent_dir,
    write_json,
)

TOOL = "verify_profile"


def _source_entry(sid: str, ref: str, kind: str = "measurement") -> Dict[str, Any]:
    return {
        "id": sid,
        "kind": kind,
        "ref": ref,
        "retrieved": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def cmd_against_silicon(args: argparse.Namespace) -> int:
    profile = load_json(args.profile, TOOL)
    ident = load_json(args.identify, TOOL)

    rep = Report(
        TOOL,
        source=ident.get("source", "unknown"),
        command="against-silicon",
        profile=os.path.basename(args.profile),
        id=profile.get("id"),
    )

    if ident.get("source") != "hardware":
        rep.warn(
            "EVIDENCE_NOT_HARDWARE",
            f"The identify result reports source={ident.get('source')!r}, so it did not "
            f"come off silicon.",
            fix="A replayed transcript can prove the PARSER works. It cannot corroborate "
            "a board profile, and this tool will not record it as a measurement.",
        )

    chip = ident.get("chip") or {}
    flash = ident.get("flash") or {}
    agreements: List[str] = []
    disagreements: List[Dict[str, Any]] = []

    want_family = (profile.get("family") or "").upper().replace("-", "")
    got_family = (chip.get("family") or "").upper().replace("-", "")
    if want_family and got_family:
        if want_family == got_family:
            agreements.append("family")
        else:
            disagreements.append(
                {"field": "family", "profile": profile.get("family"), "silicon": chip.get("family")}
            )

    want_flash = (profile.get("mcu") or {}).get("flash_mb")
    got_flash = flash.get("size_mb")
    if got_flash is not None:
        if want_flash is None:
            rep.info(
                "FLASH_LEARNED",
                f"The profile had no flash size; silicon reports {got_flash} MB.",
                fix="Record it as mcu.flash_mb with flash_mb_provenance 'measured'. Do "
                "not copy the figure from the listing - one real board was sold as "
                "16 MB and reports 8.",
                silicon=got_flash,
            )
            agreements.append("flash.size_mb (learned)")
        elif float(want_flash) == float(got_flash):
            agreements.append("flash.size_mb")
        else:
            disagreements.append(
                {"field": "mcu.flash_mb", "profile": want_flash, "silicon": got_flash}
            )

    for d in disagreements:
        rep.error(
            "PROFILE_CONTRADICTED_BY_SILICON",
            f"{d['field']}: the profile says {d['profile']!r}, the chip reports "
            f"{d['silicon']!r}.",
            fix="Silicon wins. Correct the profile and record the supersession - this "
            "is not a tie between two documents, it is a document losing to the part. "
            "If the chip is not the one this profile describes, you are holding a "
            "different board.",
            **d,
        )

    rep.set(agreements=agreements, disagreements=disagreements, chip=chip, flash=flash)

    if args.write and not disagreements and ident.get("source") == "hardware":
        corr = profile.setdefault("corroboration", {"sources": [], "groups": {}})
        sid = f"silicon_{_dt.date.today().isoformat()}"
        if not any(s.get("id") == sid for s in corr.setdefault("sources", [])):
            corr["sources"].append(
                _source_entry(
                    sid,
                    f"board_cli.py identify on {ident.get('port', 'the board')}: "
                    f"{chip.get('family')}, flash {flash.get('size_mb')} MB",
                )
            )
        for group in ("gpio_map",):
            g = corr.setdefault("groups", {}).setdefault(
                group, {"sources": [], "agreement": "full"}
            )
            if sid not in g["sources"]:
                g["sources"].append(sid)
            g["checked"] = _dt.date.today().isoformat()
        write_json(args.profile, profile)
        rep.set(written=args.profile)
        rep.info(
            "CORROBORATION_ADDED",
            f"Added measurement source {sid!r}. Note this corroborates chip IDENTITY, "
            f"not the pin map: esptool can tell you which part it is, not what the "
            f"board wired to it.",
            fix="Use against-sweep for pin availability, and documents for function.",
        )
    elif args.write:
        rep.warn(
            "NOT_WRITTEN",
            "Nothing was written: either silicon disagreed with the profile, or the "
            "evidence was not from hardware.",
            fix="Resolve the disagreement first. Writing corroboration over a "
            "contradiction would record confidence you do not have.",
        )

    return rep.emit(args.strict)


def cmd_against_sweep(args: argparse.Namespace) -> int:
    profile = load_json(args.profile, TOOL)
    sweep = load_json(args.sweep, TOOL)

    rep = Report(
        TOOL,
        source=sweep.get("source", "unknown"),
        command="against-sweep",
        profile=os.path.basename(args.profile),
        id=profile.get("id"),
    )

    meas = sweep.get("measurements") or {}
    frees = {int(str(v).split()[0]) for v in (meas.get("frees") or []) if str(v).split()}
    helds = {int(str(v).split()[0]) for v in (meas.get("helds") or []) if str(v).split()}

    if not frees and not helds:
        die(
            TOOL,
            "SWEEP_EMPTY",
            "The sweep result contains no free or held pins. Run "
            "`probe_client.py` against a spec whose command is `PROBE gpio sweep`.",
            3,
        )

    valid: Set[int] = set(profile.get("gpio_valid") or [])
    consumed = int_keys(profile.get("consumed"))
    cond = int_keys(profile.get("conditional_free"))
    declared_free = (
        set(profile.get("free") or []) if profile.get("free") is not None else (valid - consumed)
    )

    # The dangerous direction: profile says free, hardware says something drives it.
    blessed_but_held = sorted((declared_free & helds) - cond)
    if blessed_but_held:
        rep.error(
            "PROFILE_BLESSES_HELD_PIN",
            f"The profile calls GPIO{compact(blessed_but_held)} free, but the sweep "
            f"reports them HELD - something on the board is driving them.",
            fix="Move them to consumed with whatever you can determine about the owner, "
            "even if that is only 'driven on-board, owner unidentified'. This is the "
            "direction of error that matters: a design will allocate one of these, "
            "validate clean, and then fight the hardware.",
            pins=blessed_but_held,
        )

    # The safe direction: profile says consumed, hardware says free.
    reserved_but_free = sorted(consumed & frees)
    if reserved_but_free:
        rep.warn(
            "PROFILE_OVER_RESERVES",
            f"The profile marks GPIO{compact(reserved_but_free)} consumed, but the "
            f"sweep found them free.",
            fix="This is the SAFE direction - the profile refuses a pin that would have "
            "worked - so it is not a fault. Common causes: the pin is consumed only "
            "when a peripheral is enabled, or the profile was conservative. Either "
            "confirm and relax it, or record why it stays reserved.",
            pins=reserved_but_free,
        )

    unknown = sorted((frees | helds) - valid)
    if unknown:
        rep.warn(
            "SWEEP_FOUND_UNLISTED_PINS",
            f"The sweep exercised GPIO{compact(unknown)}, which gpio_valid does not "
            f"list.",
            fix="Either gpio_valid is incomplete or the sweep probed pins this part "
            "does not have. Both are worth resolving before the profile is trusted.",
            pins=unknown,
        )

    rep.set(
        sweep_free=sorted(frees),
        sweep_held=sorted(helds),
        profile_free=sorted(declared_free),
        profile_consumed=sorted(consumed),
        blessed_but_held=blessed_but_held,
        reserved_but_free=reserved_but_free,
    )

    if sweep.get("source") != "hardware":
        rep.warn(
            "EVIDENCE_NOT_HARDWARE",
            f"The sweep reports source={sweep.get('source')!r}.",
            fix="A replayed sweep tests this comparison, not the board. It will not be "
            "recorded as corroboration.",
        )
    elif args.write and not blessed_but_held:
        corr = profile.setdefault("corroboration", {"sources": [], "groups": {}})
        sid = f"gpio_sweep_{_dt.date.today().isoformat()}"
        if not any(s.get("id") == sid for s in corr.setdefault("sources", [])):
            corr["sources"].append(
                _source_entry(sid, f"probe.ino gpio sweep on {sweep.get('port', 'the board')}")
            )
        g = corr.setdefault("groups", {}).setdefault(
            "gpio_map", {"sources": [], "agreement": "full"}
        )
        if sid not in g["sources"]:
            g["sources"].append(sid)
        g["checked"] = _dt.date.today().isoformat()
        if reserved_but_free:
            g["agreement"] = "partial"
        write_json(args.profile, profile)
        rep.set(written=args.profile)

    return rep.emit(args.strict)


def cmd_install(args: argparse.Namespace) -> int:
    parent = find_parent(args.parent)
    rep = Report(TOOL, source="static", command="install", parent=parent)

    if not parent:
        rep.error(
            "PARENT_NOT_FOUND",
            "Could not locate the electronics-design skill.",
            fix="Pass --parent with its path.",
        )
        rep.emit(args.strict)
        return 3

    profile = load_json(args.profile, TOOL)
    schema = str(profile.get("schema", ""))
    kind = "board" if "board" in schema else "part" if "part" in schema else None
    if kind is None:
        die(TOOL, "KIND_UNKNOWN", f"{args.profile} declares no recognisable schema field.")

    pid = profile.get("id")
    if not pid:
        die(TOOL, "NO_ID", "The profile has no id, so it has no filename and no lookup key.")

    # Lint before installing. An unlinted profile is exactly what this skill exists
    # to prevent from reaching the parent.
    import subprocess

    lint = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile_lint.py"),
         args.profile, "--kind", kind],
        capture_output=True,
        text=True,
    )
    lint_rc = lint.returncode
    rep.set(lint_exit=lint_rc)

    if lint_rc != 0 and not args.force:
        rep.error(
            "LINT_FAILED",
            f"profile_lint.py exited {lint_rc}, so this profile was NOT installed.",
            fix="Fix the findings first. Installing a profile that fails its own linter "
            "means every design validated against it inherits the problem silently. "
            "--force exists for deliberate exceptions and says so in the output.",
        )
        rep.emit(args.strict)
        return lint_rc

    status = profile.get("status", "draft")
    if status == "draft":
        rep.warn(
            "INSTALLING_DRAFT",
            "This profile is a draft. It will be installed, and the parent skill will "
            "warn on every design that uses it.",
            fix="That is the intended behaviour - a draft profile is usable and "
            "visibly provisional. Corroborate it to make the warning go away honestly.",
        )

    dest_dir = parent_dir(parent, kind)
    dest = os.path.join(dest_dir, f"{pid}.json")
    existed = os.path.isfile(dest)

    if existed and not args.force:
        old = load_json(dest, TOOL)
        rep.error(
            "PROFILE_EXISTS",
            f"{dest} already exists (status {old.get('status')!r}).",
            fix="Pass --force to replace it, but diff them first. Overwriting a "
            "corroborated profile with a draft is a downgrade nobody will notice.",
            existing_status=old.get("status"),
        )
        rep.emit(args.strict)
        return 1

    if existed and args.force:
        old = load_json(dest, TOOL)
        if old.get("status") == "active" and status == "draft":
            rep.warn(
                "DOWNGRADE",
                f"Replacing an ACTIVE profile with a DRAFT one.",
                fix="Make sure that is what you want. Every design validated against "
                "this board will start being warned.",
            )
        backup = dest + ".bak"
        shutil.copy2(dest, backup)
        rep.set(backup=backup)

    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(args.profile, dest)
    rep.set(installed=dest, kind=kind, id=pid, status=status, replaced=existed)
    rep.info(
        "INSTALLED",
        f"{pid} installed as a {kind} profile in {parent}.",
        fix=f"Verify with: pinmap_lint.py <a pinmap using board {pid}> --strict",
    )
    return rep.emit(args.strict)


def build_parser() -> argparse.ArgumentParser:
    p = base_parser("verify_profile.py", "Check a profile against evidence, then install it.")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("against-silicon", help="Compare to a board_cli.py identify result")
    a.add_argument("profile")
    a.add_argument("--identify", required=True, help="JSON output of board_cli.py identify")
    a.add_argument("--write", action="store_true", help="Record the measurement as corroboration")
    a.set_defaults(func=cmd_against_silicon)

    b = sub.add_parser("against-sweep", help="Compare free/consumed to a probe gpio sweep")
    b.add_argument("profile")
    b.add_argument("--sweep", required=True, help="JSON output of probe_client.py for a gpio sweep")
    b.add_argument("--write", action="store_true")
    b.set_defaults(func=cmd_against_sweep)

    c = sub.add_parser("install", help="Lint, then copy into the parent skill")
    c.add_argument("profile")
    c.add_argument("--parent")
    c.add_argument("--force", action="store_true")
    c.set_defaults(func=cmd_install)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
