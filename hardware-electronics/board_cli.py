#!/usr/bin/env python3
"""board_cli.py - detect, identify, build, flash, monitor and back up a board.

Everything here emits JSON and carries an honest ``source``. A command that
opened a serial port or ran a tool against real silicon says ``"hardware"``; one
replaying a recorded transcript says ``"recorded"``. There is no flag that turns
the second into the first.

The load-bearing behaviour is ``identify``'s ``profile_match`` block: **if
silicon disagrees with the board profile, exit 1 and name the field.** That is
how "16 MB flash" became "8 MB flash" on a real project - the chip was asked,
and the documentation lost.

Subcommands:

    board_cli.py detect
    board_cli.py identify [--port COM7] [--board <id>] [--transcript f.json]
    board_cli.py build    --sketch <dir> --fqbn <fqbn>
    board_cli.py flash    --sketch <dir> --fqbn <fqbn> [--port COM7]
    board_cli.py monitor  [--port COM7] [--seconds 45] [--reset] [--expect RE]
    board_cli.py backup   --out factory.bin [--port COM7]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    EXIT_UNREACHABLE,
    Report,
    base_parser,
    die,
    load_board,
    load_json,
    write_json,
)
from serial_io import (  # noqa: E402
    AmbiguousPort,
    NoPortFound,
    RecordedCommands,
    SerialTransport,
    SerialUnavailable,
    find_arduino_cli,
    list_ports,
    pick_port,
)

TOOL = "board_cli"

GENERIC_FQBNS = (
    "esp32:esp32:esp32s3",
    "esp32:esp32:esp32",
    "esp32:esp32:esp32c3",
)


# --------------------------------------------------------------------------
# subprocess plumbing
# --------------------------------------------------------------------------


def _run(argv: List[str], recorded: Optional[RecordedCommands], timeout: int = 180) -> Tuple[str, str, int, str]:
    """Run a command, or replay it. Returns (stdout, stderr, rc, source)."""
    if recorded is not None:
        hit = recorded.match(argv)
        if hit is None:
            return "", f"no recorded output for: {' '.join(argv)}", 127, "recorded"
        return hit[0], hit[1], hit[2], "recorded"
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return "", f"{exc}", 127, "hardware"
    except subprocess.TimeoutExpired:
        return "", f"timed out after {timeout}s", 124, "hardware"
    return proc.stdout, proc.stderr, proc.returncode, "hardware"


def _esptool_argv(port: Optional[str], *args: str) -> List[str]:
    argv = [sys.executable, "-m", "esptool"]
    if port:
        argv += ["--port", port]
    return argv + list(args)


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def parse_chip(text: str) -> Dict[str, Any]:
    """Pull chip identity out of esptool output.

    Deliberately tolerant: esptool's wording moves between releases, and a
    parser that hard-fails on a cosmetic change is worse than one that reports
    which fields it could not find.
    """
    out: Dict[str, Any] = {}

    m = re.search(r"Chip is ([A-Za-z0-9\-]+)", text)
    if m:
        out["family"] = m.group(1)
    m = re.search(r"revision\s+(v?[\d.]+)", text, re.I)
    if m:
        out["revision"] = m.group(1)
    m = re.search(r"Crystal is (\d+)\s*MHz", text, re.I)
    if m:
        out["crystal_mhz"] = int(m.group(1))
    m = re.search(r"^MAC:\s*([0-9a-fA-F:]{17})", text, re.M)
    if m:
        out["mac"] = m.group(1).lower()
    m = re.search(r"Features:\s*(.+)", text)
    if m:
        out["features"] = [f.strip() for f in m.group(1).split(",") if f.strip()]

    if "features" in out:
        ps = [f for f in out["features"] if "psram" in f.lower()]
        if ps:
            out["psram_feature"] = ps[0]
    return out


def parse_flash(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    m = re.search(r"Detected flash size:\s*(\d+)\s*MB", text, re.I)
    if m:
        out["size_mb"] = int(m.group(1))
    m = re.search(r"Manufacturer:\s*(\w+)", text)
    if m:
        out["vendor_id"] = "0x" + m.group(1).lower()
    m = re.search(r"Device:\s*(\w+)", text)
    if m:
        out["device_id"] = "0x" + m.group(1).lower()
    m = re.search(r"flash mode:\s*(\w+)", text, re.I)
    if m:
        out["mode"] = m.group(1).lower()
    return out


def parse_esptool_version(text: str) -> Optional[str]:
    m = re.search(r"esptool(?:\.py)?\s+v?([\d.]+)", text, re.I)
    return m.group(1) if m else None


def parse_sketch_usage(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    m = re.search(r"Sketch uses\s+([\d,]+)\s+bytes\s+\((\d+)%\)", text)
    if m:
        out["flash_bytes"] = int(m.group(1).replace(",", ""))
        out["flash_pct"] = int(m.group(2))
    m = re.search(r"Global variables use\s+([\d,]+)\s+bytes\s+\((\d+)%\)", text)
    if m:
        out["ram_bytes"] = int(m.group(1).replace(",", ""))
        out["ram_pct"] = int(m.group(2))
    return out


def count_warnings(text: str) -> int:
    return len(re.findall(r"\bwarning:", text, re.I))


# --------------------------------------------------------------------------
# profile match - the self-correction hook
# --------------------------------------------------------------------------


def match_profile(
    board: Dict[str, Any], chip: Dict[str, Any], flash: Dict[str, Any], rep: Report
) -> Dict[str, Any]:
    mismatches: List[Dict[str, Any]] = []
    confirmed: List[str] = []

    want_family = (board.get("family") or "").upper().replace("-", "")
    got_family = (chip.get("family") or "").upper().replace("-", "")
    if want_family and got_family:
        if want_family == got_family:
            confirmed.append("family")
        else:
            mismatches.append(
                {"field": "family", "profile": board.get("family"), "silicon": chip.get("family")}
            )

    want_flash = (board.get("mcu") or {}).get("flash_mb")
    got_flash = flash.get("size_mb")
    if want_flash is not None and got_flash is not None:
        if float(want_flash) == float(got_flash):
            confirmed.append("flash.size_mb")
        else:
            mismatches.append(
                {"field": "flash.size_mb", "profile": want_flash, "silicon": got_flash}
            )

    for mm in mismatches:
        rep.error(
            "PROFILE_MISMATCH",
            f"{mm['field']}: the board profile says {mm['profile']!r} but the "
            f"silicon reports {mm['silicon']!r}.",
            fix="Silicon wins. Update boards/"
            + board["id"]
            + ".json and record the supersession in the ledger:\n"
            "  measure_log.py record --key "
            + f"{board['id']}.{mm['field']} --value {mm['silicon']} "
            "--provenance measured --instrument \"esptool on the physical board\"\n"
            "A documentation figure that disagrees with the chip is not a tie.",
            field=mm["field"],
            profile=mm["profile"],
            silicon=mm["silicon"],
        )

    return {
        "board": board["id"],
        "ok": not mismatches,
        "mismatches": mismatches,
        "confirmed": sorted(confirmed),
    }


def psram_block(board: Dict[str, Any], chip: Dict[str, Any]) -> Dict[str, Any]:
    """A PSRAM reading of zero is usually expected, not a fault.

    ``BOARD_HAS_PSRAM`` is frequently undefined by a board definition, so the
    core never initialises SPIRAM and the runtime reports nothing. Saying that
    out loud stops an agent from chasing a non-problem.
    """
    note = (board.get("mcu") or {}).get("psram_note")
    return {
        "feature_string": chip.get("psram_feature"),
        "profile_mb": (board.get("mcu") or {}).get("psram_mb"),
        "explanation": note
        or "A runtime PSRAM size of 0 usually means BOARD_HAS_PSRAM was never "
        "defined by the board definition, so the core never initialised SPIRAM.",
        "to_measure": "Rebuild with -DBOARD_HAS_PSRAM and read ESP.getPsramSize() "
        "at runtime. esptool's feature string describes the package, not what the "
        "firmware actually initialised.",
    }


# --------------------------------------------------------------------------
# port selection
# --------------------------------------------------------------------------


def resolve_port(explicit: Optional[str], rep: Report) -> Optional[str]:
    try:
        port, candidates = pick_port(explicit)
    except SerialUnavailable as exc:
        rep.error("TOOL_MISSING", str(exc), fix="Install requirements.txt.")
        return None
    except NoPortFound as exc:
        rep.error(
            "NO_PORT",
            str(exc),
            fix="Try a data-capable USB cable first. Only if that fails, hold BOOT "
            "while tapping RESET. On many boards the button dance is not needed at "
            "all and a bad cable is the entire problem.",
        )
        return None
    except AmbiguousPort as exc:
        rep.error(
            "AMBIGUOUS_PORT",
            str(exc),
            fix="Pass --port explicitly. Guessing between two candidates is how you "
            "flash the wrong board.",
            candidates=exc.candidates,
        )
        return None
    rep.set(port=port, port_candidates=candidates)
    return port


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_detect(args: argparse.Namespace) -> int:
    rep = Report(TOOL, source="hardware", command="detect")
    try:
        ports = list_ports()
        hidden = [p for p in list_ports(include_bluetooth=True) if p["bluetooth"]]
    except SerialUnavailable as exc:
        rep.source = "static"
        rep.error("TOOL_MISSING", str(exc), fix="Install requirements.txt.")
        return rep.emit(args.strict)

    rep.set(ports=ports, bluetooth_filtered=hidden, count=len(ports))
    if not ports:
        rep.error(
            "NO_PORT",
            "No non-Bluetooth serial port found.",
            fix="Try a DATA-capable USB cable first - charge-only cables enumerate "
            "nothing. Only then hold BOOT while tapping RESET.",
        )
    elif len(ports) > 1:
        rep.warn(
            "AMBIGUOUS_PORT",
            f"{len(ports)} candidate ports. Any command that talks to a board will "
            f"require --port.",
            fix="Unplug the other device, or name the port.",
        )
    if hidden:
        rep.info(
            "BLUETOOTH_FILTERED",
            f"{len(hidden)} Bluetooth serial port(s) were excluded: "
            f"{', '.join(p['port'] for p in hidden)}.",
            fix="These enumerate whether or not anything is paired, and connecting "
            "to one wastes a long timeout.",
        )
    return rep.emit(args.strict)


def cmd_identify(args: argparse.Namespace) -> int:
    recorded = RecordedCommands(load_json(args.transcript, TOOL)) if args.transcript else None
    rep = Report(TOOL, source="recorded" if recorded else "hardware", command="identify")

    port = None
    if recorded is None:
        port = resolve_port(args.port, rep)
        if port is None:
            return rep.emit(args.strict) or EXIT_UNREACHABLE
    else:
        rep.set(port=args.port or "recorded")
        rep.note(
            "This run replayed a recorded transcript. Nothing was read off silicon, "
            "so nothing here may be described as measured."
        )

    chip_out, chip_err, chip_rc, _ = _run(_esptool_argv(port, "chip-id"), recorded)
    flash_out, flash_err, flash_rc, _ = _run(_esptool_argv(port, "flash-id"), recorded)
    blob = chip_out + "\n" + flash_out

    if chip_rc == 127 or flash_rc == 127:
        rep.error(
            "TOOL_MISSING",
            "esptool could not be run. " + (chip_err or flash_err).strip(),
            fix="python -m pip install -r requirements.txt, then retry. esptool is a "
            "pip package; arduino-cli is not.",
        )
        return rep.emit(args.strict)

    if chip_rc != 0 or flash_rc != 0:
        rep.error(
            "BOARD_UNREACHABLE",
            f"esptool did not complete (chip-id rc={chip_rc}, flash-id rc={flash_rc}).",
            fix="Check the cable is data-capable, then hold BOOT while tapping RESET. "
            "Close any serial monitor holding the port.",
            stderr=(chip_err + flash_err).strip()[:2000],
        )
        rep.set(raw_stdout=blob)
        rep.emit(args.strict)
        return EXIT_UNREACHABLE

    chip = parse_chip(blob)
    flash = parse_flash(blob)
    rep.set(
        chip=chip,
        flash=flash,
        toolchain={"esptool": parse_esptool_version(blob), "arduino_cli_path": find_arduino_cli()},
        raw_stdout=blob.strip(),
    )

    if not chip.get("family"):
        rep.warn(
            "CHIP_UNPARSED",
            "Could not read a chip family out of esptool's output.",
            fix="esptool's wording changes between releases. Read raw_stdout and, if "
            "the format has moved, update parse_chip().",
        )

    if args.board:
        board = load_board(args.board, TOOL)
        rep.set(profile_match=match_profile(board, chip, flash, rep), psram=psram_block(board, chip))
        if board.get("status") == "superseded":
            rep.warn(
                "BOARD_SUPERSEDED",
                f"Profile {args.board!r} is marked superseded.",
                fix="Confirm which revision is actually on the bench.",
            )
    else:
        rep.warn(
            "NO_PROFILE_COMPARED",
            "No --board was given, so nothing was compared against a profile.",
            fix="Pass --board to turn this from a reading into a CHECK. A reading "
            "that is never compared cannot catch a wrong assumption.",
        )

    if flash.get("size_mb") and args.board:
        rep.info(
            "RECORD_THIS",
            f"Promote the flash size to measured: measure_log.py record --key "
            f"{args.board}.flash.size_mb --value {flash['size_mb']} --unit MB "
            f"--provenance measured --instrument \"esptool flash-id on "
            f"{port or 'the board'}\"",
        )

    return rep.emit(args.strict)


def cmd_build(args: argparse.Namespace) -> int:
    recorded = RecordedCommands(load_json(args.transcript, TOOL)) if args.transcript else None
    rep = Report(TOOL, source="recorded" if recorded else "hardware", command="build", fqbn=args.fqbn)

    cli = find_arduino_cli()
    if cli is None and recorded is None:
        rep.error(
            "TOOL_MISSING",
            "arduino-cli was not found on PATH or at "
            "%LOCALAPPDATA%\\arduino-cli\\arduino-cli.exe.",
            fix="Install it from https://arduino.github.io/arduino-cli/ . It is a "
            "binary, not a pip package, so requirements.txt cannot supply it.",
        )
        return rep.emit(args.strict)

    if any(args.fqbn.startswith(g) and ":" not in args.fqbn[len(g):] for g in GENERIC_FQBNS):
        rep.warn(
            "GENERIC_FQBN",
            f"{args.fqbn!r} is a generic dev-module FQBN.",
            fix="Prefer the vendor board definition and change nothing. The intuitive "
            "manual guesses - OPI PSRAM, the largest flash size on the menu - "
            "routinely contradict the board definition, and the flash guess is often "
            "measured wrong.",
        )

    argv = [cli or "arduino-cli", "compile", "--fqbn", args.fqbn, "--warnings", "all", args.sketch]
    out, err, rc, _ = _run(argv, recorded, timeout=900)
    usage = parse_sketch_usage(out)
    warnings = count_warnings(out + err)

    rep.set(sketch=args.sketch, usage=usage, warning_count=warnings, returncode=rc,
            raw_stdout=out.strip()[:4000])

    if rc != 0:
        rep.error(
            "BUILD_FAILED",
            f"arduino-cli compile exited {rc}.",
            fix="Read raw_stdout. Do not flash a board with a build you have not seen "
            "succeed.",
            stderr=err.strip()[:2000],
        )
    elif warnings:
        rep.info(
            "BUILD_WARNINGS",
            f"{warnings} compiler warning(s).",
            fix="Vendor cores often emit many warnings from their own vendored IDF "
            "headers. Prefer the stock esp32:esp32 core where both exist.",
        )
    return rep.emit(args.strict)


def cmd_flash(args: argparse.Namespace) -> int:
    recorded = RecordedCommands(load_json(args.transcript, TOOL)) if args.transcript else None
    rep = Report(TOOL, source="recorded" if recorded else "hardware", command="flash", fqbn=args.fqbn)

    cli = find_arduino_cli()
    if cli is None and recorded is None:
        rep.error(
            "TOOL_MISSING",
            "arduino-cli was not found.",
            fix="Install it from https://arduino.github.io/arduino-cli/ .",
        )
        return rep.emit(args.strict)

    port = args.port
    if recorded is None:
        port = resolve_port(args.port, rep)
        if port is None:
            return rep.emit(args.strict) or EXIT_UNREACHABLE

    backup = args.backup or os.path.join(os.path.dirname(os.path.abspath(args.sketch)), "factory.bin")
    if not os.path.isfile(backup) and not args.no_backup_check:
        rep.warn(
            "NO_FACTORY_BACKUP",
            f"No factory flash backup at {backup}.",
            fix="Run `board_cli.py backup --out factory.bin` FIRST if this board has "
            "not been flashed before. Factory demo firmware cannot be recovered once "
            "it is overwritten, and the loss is permanent and silent - the board just "
            "never does its demo again.",
        )

    argv = [cli or "arduino-cli", "upload", "--fqbn", args.fqbn, "--port", port or "", args.sketch]
    out, err, rc, _ = _run(argv, recorded, timeout=600)
    rep.set(sketch=args.sketch, returncode=rc, raw_stdout=out.strip()[:4000])

    if rc != 0:
        rep.error(
            "FLASH_FAILED",
            f"arduino-cli upload exited {rc}.",
            fix="Close any serial monitor holding the port, then retry. If it still "
            "fails, hold BOOT while tapping RESET to force the download stub.",
            stderr=err.strip()[:2000],
        )
    return rep.emit(args.strict)


def cmd_monitor(args: argparse.Namespace) -> int:
    transcript_file = args.transcript
    if transcript_file:
        rep = Report(TOOL, source="recorded", command="monitor")
        data = load_json(transcript_file, TOOL)
        lines = list(data.get("banner", []))
        for ex in data.get("exchanges", []):
            lines.extend(ex.get("rx", []))
        rep.note("Replayed a recorded transcript. Nothing was read off hardware.")
    else:
        rep = Report(TOOL, source="hardware", command="monitor")
        port = resolve_port(args.port, rep)
        if port is None:
            return rep.emit(args.strict) or EXIT_UNREACHABLE
        try:
            tr = SerialTransport(port, baud=args.baud, reset=args.reset)
        except SerialUnavailable as exc:
            rep.error("TOOL_MISSING", str(exc))
            return rep.emit(args.strict)
        except Exception as exc:
            rep.error(
                "PORT_BUSY",
                f"Could not open {port}: {exc}",
                fix="Something else is holding the port - usually a serial monitor or "
                "a previous run.",
            )
            rep.emit(args.strict)
            return EXIT_UNREACHABLE

        lines = []
        import time as _t

        deadline = _t.time() + args.seconds
        with tr:
            while _t.time() < deadline:
                line = tr.read_line(timeout=min(1.0, max(0.05, deadline - _t.time())))
                if line is not None:
                    lines.append(line)

        if not args.reset:
            rep.info(
                "NO_RESET",
                "The board was NOT reset. Watching must not disturb the device: a "
                "reset restarts setup and can disconnect someone who is mid-"
                "configuration.",
                fix="Pass --reset only when you actually want to restart it.",
            )

    rep.set(lines=lines, line_count=len(lines))

    for pattern in args.expect or []:
        if any(re.search(pattern, ln) for ln in lines):
            rep.info("EXPECT_MATCHED", f"Saw a line matching {pattern!r}.", pattern=pattern)
        else:
            rep.error(
                "EXPECT_MISSING",
                f"No line matched {pattern!r} in {len(lines)} line(s).",
                fix="Either the firmware did not get there, or the board never "
                "started. Silence is not a pass.",
                pattern=pattern,
            )

    if not lines:
        rep.warn(
            "NO_OUTPUT",
            "The board sent nothing at all.",
            fix="Check the baud rate, then check that the firmware actually prints. "
            "A silent port proves nothing about whether the board is running.",
        )
    return rep.emit(args.strict)


def cmd_backup(args: argparse.Namespace) -> int:
    recorded = RecordedCommands(load_json(args.transcript, TOOL)) if args.transcript else None
    rep = Report(TOOL, source="recorded" if recorded else "hardware", command="backup")

    port = args.port
    if recorded is None:
        port = resolve_port(args.port, rep)
        if port is None:
            return rep.emit(args.strict) or EXIT_UNREACHABLE

    size = args.size or "ALL"
    argv = _esptool_argv(port, "read-flash", "0", size, args.out)
    out, err, rc, _ = _run(argv, recorded, timeout=900)
    rep.set(out=args.out, returncode=rc, raw_stdout=out.strip()[:2000])

    if rc != 0:
        rep.error(
            "BACKUP_FAILED",
            f"esptool read-flash exited {rc}.",
            fix="Do not flash this board until the backup succeeds. Factory firmware "
            "is unrecoverable once overwritten.",
            stderr=err.strip()[:2000],
        )
    elif recorded is None and not os.path.isfile(args.out):
        rep.error(
            "BACKUP_EMPTY",
            f"esptool reported success but {args.out} does not exist.",
            fix="A success with no artefact is not a success.",
        )
    else:
        rep.info(
            "BACKUP_OK",
            f"Factory flash saved to {args.out}. Keep it: this is the only copy.",
        )
    return rep.emit(args.strict)


def cmd_record(args: argparse.Namespace) -> int:
    """Capture a session to a transcript so it can be replayed in tests."""
    rep = Report(TOOL, source="hardware", command="record")
    port = resolve_port(args.port, rep)
    if port is None:
        return rep.emit(args.strict) or EXIT_UNREACHABLE

    try:
        tr = SerialTransport(port, baud=args.baud, reset=args.reset)
    except Exception as exc:
        rep.error("PORT_BUSY", f"Could not open {port}: {exc}")
        rep.emit(args.strict)
        return EXIT_UNREACHABLE

    exchanges = []
    with tr:
        for cmd in args.send or []:
            tr.write_line(cmd)
            rx: List[str] = []
            while True:
                line = tr.read_line(timeout=args.timeout)
                if line is None:
                    break
                rx.append(line)
                if line.startswith("probe.done") or line.startswith("probe.error"):
                    break
            exchanges.append({"tx": cmd, "rx": rx})

    data = {
        "schema": "hardware-electronics/serial-transcript",
        "version": "1.0",
        "port": port,
        "recorded": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "banner": [],
        "exchanges": exchanges,
    }
    write_json(args.out, data)
    rep.set(out=args.out, exchanges=len(exchanges))
    return rep.emit(args.strict)


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = base_parser("board_cli.py", "Detect, identify, build, flash, monitor and back up.")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("detect", help="List serial ports, Bluetooth excluded")
    d.set_defaults(func=cmd_detect)

    i = sub.add_parser("identify", help="Read chip and flash identity off silicon")
    i.add_argument("--port")
    i.add_argument("--board", help="boards/<id>.json to compare the silicon against")
    i.add_argument("--transcript", help="Replay recorded tool output instead of running esptool")
    i.set_defaults(func=cmd_identify)

    b = sub.add_parser("build", help="Compile a sketch")
    b.add_argument("--sketch", required=True)
    b.add_argument("--fqbn", required=True)
    b.add_argument("--transcript")
    b.set_defaults(func=cmd_build)

    f = sub.add_parser("flash", help="Upload a sketch")
    f.add_argument("--sketch", required=True)
    f.add_argument("--fqbn", required=True)
    f.add_argument("--port")
    f.add_argument("--backup", help="Path the factory backup should already exist at")
    f.add_argument("--no-backup-check", action="store_true")
    f.add_argument("--transcript")
    f.set_defaults(func=cmd_flash)

    m = sub.add_parser("monitor", help="Watch the serial output without disturbing the board")
    m.add_argument("--port")
    m.add_argument("--baud", type=int, default=115200)
    m.add_argument("--seconds", type=float, default=45.0)
    m.add_argument("--reset", action="store_true", help="Opt in to resetting the board first")
    m.add_argument("--expect", action="append", help="Regex that must appear. Repeatable.")
    m.add_argument("--transcript")
    m.set_defaults(func=cmd_monitor)

    k = sub.add_parser("backup", help="Dump the factory flash BEFORE the first upload")
    k.add_argument("--out", required=True)
    k.add_argument("--port")
    k.add_argument("--size", help="Bytes to read, or ALL")
    k.add_argument("--transcript")
    k.set_defaults(func=cmd_backup)

    r = sub.add_parser("record", help="Capture a serial session to a replayable transcript")
    r.add_argument("--out", required=True)
    r.add_argument("--port")
    r.add_argument("--baud", type=int, default=115200)
    r.add_argument("--reset", action="store_true")
    r.add_argument("--timeout", type=float, default=5.0)
    r.add_argument("--send", action="append", help="Line to send. Repeatable.")
    r.set_defaults(func=cmd_record)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SerialUnavailable as exc:
        die(TOOL, "TOOL_MISSING", str(exc))


if __name__ == "__main__":
    sys.exit(main())
