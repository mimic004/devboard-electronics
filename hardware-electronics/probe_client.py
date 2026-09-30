#!/usr/bin/env python3
"""probe_client.py - drives probe.ino and judges the answer.

The judging is the point. A probe that only asks "did it return without error"
manufactures false confidence, which is worse than no check at all: on one real
board, with the panel power-enable line low, every e-paper refresh appeared to
succeed in 29 ms. Nothing errored. The controller was unpowered the whole time.

So every measurement is compared against a declared **plausibility band**, and a
result that is implausibly GOOD fails:

    IMPLAUSIBLE_SUCCESS  elapsed 29 ms against a [300, 3000] ms band

Three rules enforced here:

  * Never widen a band to make a test pass. The band is the requirement.
  * A steady-state observation never proves a subsystem is alive. When a spec
    declares ``requires_transition``, something must have MOVED.
  * Never retry a failed hardware step blindly. Retries are off by default,
    because a retry that sometimes works is a wiring fault, not a flake.

Usage:
    probe_client.py <probe-spec.json> [--port COM7] [--strict]
    probe_client.py <probe-spec.json> --transcript recorded.json
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    EXIT_UNREACHABLE,
    Report,
    base_parser,
    load_json,
    validate_schema,
)
from serial_io import (  # noqa: E402
    AmbiguousPort,
    NoPortFound,
    RecordedTransport,
    SerialTransport,
    SerialUnavailable,
    Transport,
    load_transcript,
    pick_port,
)

TOOL = "probe_client"

LINE_RE = re.compile(r"^probe\.([a-z0-9_]+)\.([a-z0-9_]+)\s+(.*)$", re.I)
DONE_RE = re.compile(r"^probe\.done\s+([a-z0-9_]+)\s+(ok|fail)\s*$", re.I)
ERROR_RE = re.compile(r"^probe\.error\s+(.*)$", re.I)


def _num(text: str) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def read_response(
    tr: Transport, timeout: float
) -> Tuple[Dict[str, Any], List[str], Optional[str], List[str]]:
    """Collect lines until ``probe.done``, or until the timeout expires.

    Returns ``(measurements, addresses, result, raw_lines)``. A missing
    ``probe.done`` is itself a finding: a probe that never terminated did not
    pass.
    """
    measurements: Dict[str, Any] = {}
    addresses: List[str] = []
    raw: List[str] = []
    result: Optional[str] = None

    deadline = time.time() + timeout
    while time.time() < deadline:
        line = tr.read_line(timeout=min(1.0, max(0.05, deadline - time.time())))
        if line is None:
            if result is not None:
                break
            continue
        line = line.strip()
        if not line:
            continue
        raw.append(line)

        done = DONE_RE.match(line)
        if done:
            result = done.group(2).lower()
            break

        err = ERROR_RE.match(line)
        if err:
            measurements.setdefault("errors", []).append(err.group(1))
            continue

        m = LINE_RE.match(line)
        if not m:
            continue
        _, key, value = m.group(1), m.group(2).lower(), m.group(3).strip()

        if key == "found":
            addresses.append(value.lower())
            continue
        if key in ("edge", "xfer", "free", "held"):
            measurements.setdefault(key + "s", []).append(value)
            continue

        n = _num(value)
        measurements[key] = n if n is not None else value

    return measurements, addresses, result, raw


def check_plausibility(spec: Dict[str, Any], measurements: Dict[str, Any], rep: Report) -> None:
    bands = spec.get("plausibility") or {}
    if not bands:
        rep.warn(
            "NO_PLAUSIBILITY_BAND",
            f"The spec for {spec.get('peripheral')!r} declares no plausibility bounds, "
            f"so this run can only tell you whether the call returned without error.",
            fix="Add a plausibility block. A check that only asks 'did it error' is "
            "the check that let a 29 ms e-paper refresh report success while the "
            "panel controller was unpowered.",
        )
        return

    for key, band in bands.items():
        if key not in measurements:
            rep.error(
                "MEASUREMENT_MISSING",
                f"The spec bounds {key!r} but the probe never reported it.",
                fix="Either the probe does not emit that measurement, or it failed "
                "before reaching it. An absent measurement is not a passing one.",
                measurement=key,
            )
            continue

        value = measurements[key]
        if not isinstance(value, (int, float)):
            rep.error(
                "MEASUREMENT_NOT_NUMERIC",
                f"{key} came back as {value!r}, which cannot be compared to a band.",
                measurement=key,
            )
            continue

        lo, hi = band.get("min"), band.get("max")
        if lo is not None and value < float(lo):
            rep.error(
                "IMPLAUSIBLE_SUCCESS",
                f"{key} = {value} against a plausibility band of "
                f"[{lo}, {hi}]. It is too GOOD to be true, so treat it as a FAULT. "
                f"{band['why']}",
                fix="Do not widen the band. Look for the missing precondition: an "
                "unpowered rail, an unasserted enable line, a floating busy signal "
                "that was never driven. A result that cannot physically happen did "
                "not happen.",
                measurement=key,
                value=value,
                band=[lo, hi],
            )
        elif hi is not None and value > float(hi):
            rep.error(
                "IMPLAUSIBLE_SLOW",
                f"{key} = {value} against a plausibility band of [{lo}, {hi}]. "
                f"{band['why']}",
                fix="Something is retrying, timing out or running at the wrong clock. "
                "Do not widen the band.",
                measurement=key,
                value=value,
                band=[lo, hi],
            )
        else:
            rep.info(
                "MEASUREMENT_PLAUSIBLE",
                f"{key} = {value}, inside [{lo}, {hi}].",
                measurement=key,
                value=value,
            )


def check_expectations(
    spec: Dict[str, Any],
    result: Optional[str],
    measurements: Dict[str, Any],
    addresses: List[str],
    rep: Report,
) -> None:
    expect = spec.get("expect") or {}

    if result is None:
        rep.error(
            "PROBE_NEVER_FINISHED",
            "No probe.done line arrived before the timeout.",
            fix="The probe hung or the board stopped talking. Every busy-wait in the "
            "sketch has a timeout, so a hang here usually means the board reset or "
            "the port died - not that the peripheral is slow.",
        )
    else:
        want = (expect.get("result") or "ok").lower()
        if result != want:
            rep.error(
                "RESULT_MISMATCH",
                f"Probe reported {result!r}; the spec expects {want!r}."
                + (f" Errors: {measurements['errors']}" if measurements.get("errors") else ""),
                fix="Read the probe's own diagnosis line before changing anything. "
                "Do NOT simply retry: a retry that sometimes works is a wiring fault, "
                "not a flake.",
                result=result,
            )

    want_addrs = expect.get("i2c_addresses")
    if want_addrs is not None:
        got = sorted({a.lower() for a in addresses})
        want = sorted({a.lower() for a in want_addrs})
        if got != want:
            missing = [a for a in want if a not in got]
            extra = [a for a in got if a not in want]
            rep.error(
                "I2C_SET_MISMATCH",
                f"Bus answered {got or 'nothing'}; the spec expects exactly {want}."
                + (f" Missing: {missing}." if missing else "")
                + (f" Unexpected: {extra}." if extra else ""),
                fix="The expected set is EXACT, not a superset. An unexpected device "
                "is as interesting as a missing one - it usually means an address "
                "strap is wrong or two parts collide. A bus that answers nothing at "
                "all usually means no pull-ups, the wrong pins, or an unpowered rail.",
                found=got,
                expected=want,
                missing=missing,
                unexpected=extra,
            )
        else:
            rep.info("I2C_SET_EXACT", f"Bus answered exactly {got}.", found=got)

    for key, want_value in (expect.get("values") or {}).items():
        got = measurements.get(key)
        if got is None:
            rep.error("MEASUREMENT_MISSING", f"Expected {key} was never reported.", measurement=key)
        elif str(got).lower() != str(want_value).lower():
            rep.error(
                "VALUE_MISMATCH",
                f"{key} = {got!r}, expected {want_value!r}.",
                measurement=key,
            )


def check_transition(spec: Dict[str, Any], measurements: Dict[str, Any], rep: Report) -> None:
    """A steady-state observation never proves a subsystem is alive.

    E-ink retains its last image with no power: a static demo picture survives a
    dead driver, a wiped flash and an unpowered board. Only a change you watched
    happen counts as evidence.
    """
    rt = spec.get("requires_transition")
    if not rt:
        return
    key = rt.get("measurement")
    value = measurements.get(key)
    if value is None:
        rep.error(
            "TRANSITION_UNPROVEN",
            f"The spec requires a transition in {key!r}, which was never reported.",
            fix=rt.get("why")
            or "Demand a change you can watch: a counter that increments, a level "
            "that moves when you change the input.",
            measurement=key,
        )
        return
    moved = bool(value) if not isinstance(value, (int, float)) else float(value) > 0
    if rt.get("must_change", True) and not moved:
        rep.error(
            "TRANSITION_UNPROVEN",
            f"{key} = {value}: nothing moved, so nothing was proven.",
            fix=rt.get("why")
            or "A steady state is not evidence. E-ink keeps its last image with no "
            "power at all; a static demo picture survives a dead driver, a wiped "
            "flash and an unpowered board. Close the gate by watching a change.",
            measurement=key,
            value=value,
        )
    else:
        rep.info("TRANSITION_OBSERVED", f"{key} = {value}: something changed.", measurement=key)


def open_transport(args: argparse.Namespace, rep: Report) -> Optional[Transport]:
    if args.transcript:
        rep.source = "recorded"
        rep.note(
            "This run replayed a recorded transcript. No serial port was opened, so "
            "nothing here may be described as measured."
        )
        return RecordedTransport(load_transcript(args.transcript))

    try:
        port, candidates = pick_port(args.port)
    except SerialUnavailable as exc:
        rep.error("TOOL_MISSING", str(exc), fix="Install requirements.txt.")
        return None
    except NoPortFound as exc:
        rep.error("NO_PORT", str(exc), fix="Try a data-capable USB cable first.")
        return None
    except AmbiguousPort as exc:
        rep.error(
            "AMBIGUOUS_PORT",
            str(exc),
            fix="Pass --port. Guessing between candidates is how you probe the wrong "
            "board.",
            candidates=exc.candidates,
        )
        return None

    rep.set(port=port, port_candidates=candidates)
    try:
        return SerialTransport(port, baud=args.baud, reset=args.reset)
    except Exception as exc:
        rep.error(
            "PORT_BUSY",
            f"Could not open {port}: {exc}",
            fix="Close any serial monitor holding the port.",
        )
        return None


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser(
        "probe_client.py", "Drive probe.ino and judge the result against a spec."
    )
    p.add_argument("spec", help="Path to a probe-spec.json")
    p.add_argument("--port")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--reset", action="store_true", help="Opt in to resetting the board first")
    p.add_argument("--transcript", help="Replay a recorded session instead of opening a port")
    p.add_argument(
        "--allow-retry",
        action="store_true",
        help="Permit one retry. Off by default: a retry that sometimes works is a "
        "wiring fault, not a flake.",
    )
    args = p.parse_args(argv)

    spec = load_json(args.spec, TOOL)
    rep = Report(
        TOOL,
        source="recorded" if args.transcript else "hardware",
        peripheral=spec.get("peripheral"),
        command=spec.get("command"),
    )
    validate_schema(spec, "probe-spec", rep)

    if not spec.get("command"):
        rep.error("SPEC_NO_COMMAND", "The spec declares no command to send.")
        return rep.emit(args.strict)

    tr = open_transport(args, rep)
    if tr is None:
        rep.emit(args.strict)
        return EXIT_UNREACHABLE

    pre = spec.get("preconditions") or []
    if not pre and "busy" in str(spec.get("command", "")):
        rep.warn(
            "NO_PRECONDITIONS",
            "A busy-line probe with no declared preconditions.",
            fix="Most implausible successes are a missing precondition, not a flake. "
            "Declare the enable line and its settle time.",
        )

    attempts = 2 if args.allow_retry else 1
    measurements: Dict[str, Any] = {}
    addresses: List[str] = []
    result: Optional[str] = None
    raw: List[str] = []

    with tr:
        for gpio_pre in pre:
            if gpio_pre.get("gpio") is not None and gpio_pre.get("level"):
                want_level = str(gpio_pre["level"]).lower()
                cmd = f"PROBE rail {gpio_pre['gpio']} {want_level}"
                tr.write_line(cmd)
                pre_meas, _, pre_result, pre_raw = read_response(
                    tr, timeout=float(spec.get("timeout_s", 30))
                )
                raw.extend(pre_raw)

                if pre_result != "ok":
                    rep.error(
                        "PRECONDITION_FAILED",
                        f"Precondition {cmd!r} did not report ok.",
                        fix="The peripheral is not powered or enabled. Running the "
                        "probe now would measure nothing and report success.",
                        precondition=cmd,
                    )
                else:
                    # "It returned ok" is not the same as "the line moved". A rail
                    # that reports success while sitting at the wrong level is the
                    # exact condition behind an implausibly fast peripheral success.
                    after = str(pre_meas.get("after", "")).lower()
                    if after and after != want_level:
                        rep.error(
                            "PRECONDITION_FAILED",
                            f"{cmd!r} returned ok but GPIO{gpio_pre['gpio']} is still "
                            f"{after!r}, not {want_level!r}"
                            + (
                                " - it never changed."
                                if str(pre_meas.get("changed", "")).lower() == "no"
                                else "."
                            ),
                            fix=gpio_pre.get("note")
                            or "The enable line is not actually being driven. Anything "
                            "measured after this point is measuring an unpowered "
                            "peripheral, and it will look like a fast success.",
                            precondition=cmd,
                            expected=want_level,
                            actual=after,
                        )
                if gpio_pre.get("settle_ms"):
                    time.sleep(float(gpio_pre["settle_ms"]) / 1000.0)

        for attempt in range(attempts):
            tr.write_line(spec["command"])
            measurements, addresses, result, lines = read_response(
                tr, timeout=float(spec.get("timeout_s", 30))
            )
            raw.extend(lines)
            if result == (spec.get("expect", {}).get("result") or "ok"):
                break
            if attempt + 1 < attempts:
                rep.warn(
                    "RETRIED",
                    "The probe failed and was retried because --allow-retry was given.",
                    fix="If the retry succeeds, that is not a pass. An intermittent "
                    "hardware step is a wiring fault: reseat, reflow, or re-meter it.",
                )

    rep.set(
        result=result,
        measurements=measurements,
        i2c_addresses=addresses,
        transcript=getattr(tr, "transcript", raw),
    )

    check_expectations(spec, result, measurements, addresses, rep)
    check_plausibility(spec, measurements, rep)
    check_transition(spec, measurements, rep)

    if rep.source == "hardware" and rep.counts()["error"] == 0:
        rep.info(
            "RECORD_THIS",
            "This ran against real hardware and passed. Promote the numbers that "
            "matter with measure_log.py record --provenance measured, naming this "
            "probe as the instrument.",
        )

    return rep.emit(args.strict)


if __name__ == "__main__":
    sys.exit(main())
