#!/usr/bin/env python3
"""pinmap_lint.py - pin, bus and address conflict validator.

Loads a pinmap.json plus a boards/*.json profile and refuses invalid allocations.

The reason a board ID is mandatory and has no default: GPIO 7 is the e-paper
panel power-enable on the CrowPanel 2.13 v1 and the battery-sense input on the
Heltec E290. A pin question answered without a board ID is a guess wearing a
number.

Every finding carries a stable ``code`` so the agent branches on the code, never
on the prose.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    Report,
    base_parser,
    load_board,
    load_json,
    load_part,
    validate_schema,
)

TOOL = "pinmap_lint"

#: Advisory findings a design may accept on purpose, with a written reason.
#: Everything else has to be fixed. Notably absent: ADC2_WITH_WIFI,
#: PIN_STRAPPING_PULL, WAKE_NOT_RTC and every conflict code - those are not
#: trade-offs, they are things that do not work.
ACKNOWLEDGEABLE = frozenset(
    {
        "JTAG_COST",
        "PIN_STRAPPING",
        "I2C_PULLUP_STACKED",
        "I2C_PULLUP_WEAK",
        "BOARD_SUPERSEDED",
        "BOARD_DRAFT",
        "BOARD_UNCORROBORATED",
        "CONNECTOR_FAMILY_DIFFERS",
    }
)

#: Source kinds that can corroborate a pin map. A product page or a marketplace
#: listing describes what somebody wants you to buy, not what is on the board.
INDEPENDENT_SOURCE_KINDS = frozenset(
    {"datasheet", "schematic", "board_definition", "variant_header", "community_firmware", "measurement"}
)

#: How many independent sources a pin map needs before this linter will trust it
#: silently. A conservative profile - one that over-reserves pins when unsure -
#: has a safe failure mode and needs fewer.
GPIO_MAP_MIN_SOURCES = 3
GPIO_MAP_MIN_SOURCES_CONSERVATIVE = 1


def _check_board_corroboration(board: Dict[str, Any], rep: Report) -> None:
    """Is there a stated reason to believe this board's pin map?

    The profile this skill shipped with claimed its GPIO map was "confirmed by at
    least three of: datasheet, schematic, variant header, community firmware" -
    in a prose note, which nothing could check. That is the same
    correct-and-unenforceable failure this skill exists to fix, so the claim is
    now machine-readable and checked here.
    """
    if board.get("status") == "superseded":
        return

    corr = board.get("corroboration") or {}
    sources = {s.get("id"): s for s in corr.get("sources", []) if s.get("id")}
    group = (corr.get("groups") or {}).get("gpio_map")

    if not corr or not group:
        rep.warn(
            "BOARD_UNCORROBORATED",
            f"Board profile {board['id']!r} declares no corroboration for its GPIO map, "
            f"so nothing states why its pin numbers should be believed.",
            fix="Run the board-profiles skill against it: "
            "profile_lint.py boards/" + str(board["id"]) + ".json --kind board. "
            "Until then, treat a clean pass here as 'consistent with an unverified "
            "profile' rather than 'correct'.",
            board=board["id"],
        )
        return

    independent: set = set()
    for sid in group.get("sources", []):
        s = sources.get(sid)
        if not s or s.get("kind") not in INDEPENDENT_SOURCE_KINDS:
            continue
        independent.add(str(s.get("derives_from") or sid))

    need = (
        GPIO_MAP_MIN_SOURCES_CONSERVATIVE
        if corr.get("conservative")
        else GPIO_MAP_MIN_SOURCES
    )
    if len(independent) < need:
        rep.warn(
            "BOARD_UNCORROBORATED",
            f"Board profile {board['id']!r} cites {len(independent)} independent "
            f"source(s) for its GPIO map; {need} is the threshold"
            + (" for a conservative profile" if corr.get("conservative") else "")
            + ".",
            fix="Add a genuinely independent source - a core variant header or an "
            "independent community firmware variant are the strongest. Two documents "
            "that copy each other count once.",
            board=board["id"],
            independent=len(independent),
            required=need,
        )
    else:
        rep.info(
            "BOARD_CORROBORATED",
            f"GPIO map corroborated by {len(independent)} independent source(s), "
            f"agreement {group.get('agreement', 'unstated')!r}.",
            board=board["id"],
        )

    unresolved = [
        c for c in (corr.get("contradictions") or []) if c.get("resolution") == "unresolved"
    ]
    for c in unresolved:
        rep.info(
            "BOARD_CONTRADICTION",
            f"Sources disagree about {c['field']}: "
            f"{[r.get('value') for r in c.get('readings', [])]} and nobody has settled it."
            + (f" Impact: {c['impact']}" if c.get("impact") else ""),
            fix=c.get("how_to_close")
            or "Report the disagreement rather than quoting either reading as fact.",
            field=c["field"],
        )



BUS_SIGNALS = {
    "i2c": ["sda", "scl"],
    "spi": ["sck", "mosi", "miso"],
    "i2s": ["bclk", "ws", "sd"],
    "uart": ["tx", "rx"],
    "onewire": ["data"],
}


def _as_pin(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip().upper().removeprefix("GPIO").removeprefix("IO").strip()
        if s.isdigit():
            return int(s)
    return None


def recommended_pullup(hz: float) -> int:
    return 2200 if hz > 100_000 else 4700


def parallel(resistors: List[float]) -> Optional[float]:
    vals = [r for r in resistors if r and r > 0]
    if not vals:
        return None
    return 1.0 / sum(1.0 / r for r in vals)


def collect_allocations(pm: Dict[str, Any], rep: Report) -> Dict[int, List[Dict[str, Any]]]:
    """Every claim on a physical pin, with where the claim came from."""
    alloc: Dict[int, List[Dict[str, Any]]] = {}

    def claim(pin: Any, owner: str, origin: str, **meta: Any) -> None:
        p = _as_pin(pin)
        if p is None:
            if pin is not None:
                rep.error(
                    "PIN_UNPARSEABLE",
                    f"{origin} names pin {pin!r}, which is not a GPIO number.",
                    fix="Use the integer GPIO number, e.g. 39 or \"GPIO39\".",
                    owner=owner,
                )
            return
        alloc.setdefault(p, []).append({"owner": owner, "origin": origin, **meta})

    for n in pm.get("nets", []) or []:
        if n.get("mode") == "nc":
            continue
        claim(
            n.get("pin"),
            n.get("net", "<unnamed>"),
            "nets",
            mode=n.get("mode", "bidir"),
            external_pull=n.get("external_pull", "none"),
            external_pull_ohm=n.get("external_pull_ohm"),
            logic_v=n.get("logic_v"),
            bus_ref=n.get("bus_ref"),
            shared=bool(n.get("shared")),
            part_ref=n.get("part_ref"),
        )

    for b in pm.get("buses", []) or []:
        kind = b.get("kind")
        bid = b.get("id", kind)
        for sig in BUS_SIGNALS.get(kind, []):
            if b.get(sig) is not None:
                claim(b[sig], f"{bid}.{sig}", "buses", bus=bid, mode="bidir")
        for dev in b.get("devices", []) or []:
            if dev.get("cs") is not None:
                claim(
                    dev["cs"],
                    f"{bid}.{dev.get('ref', '?')}.CS",
                    "buses",
                    bus=bid,
                    mode="output",
                    cs_for=dev.get("ref"),
                )

    for a in pm.get("analog_inputs", []) or []:
        claim(a.get("pin"), a.get("net", "<analog>"), "analog_inputs", mode="analog")

    return alloc


def check_conflicts(alloc: Dict[int, List[Dict[str, Any]]], rep: Report) -> None:
    for pin in sorted(alloc):
        claims = alloc[pin]
        if len(claims) < 2:
            continue
        # Claims that belong to the same declared bus are one allocation, not two.
        buses = {c.get("bus") or c.get("bus_ref") for c in claims}
        names = {c["owner"] for c in claims}
        if len(names) == 1:
            continue
        if len(buses) == 1 and None not in buses:
            continue
        if all(c.get("shared") for c in claims):
            rep.info(
                "PIN_SHARED_DECLARED",
                f"GPIO{pin} carries {len(claims)} declared-shared owners: "
                f"{', '.join(sorted(names))}.",
                pin=pin,
            )
            continue
        rep.error(
            "PIN_DOUBLE_BOOKED",
            f"GPIO{pin} is claimed by {len(claims)} different owners: "
            f"{', '.join(sorted(names))}.",
            fix="Move one of them to a free pin, or - if they genuinely share the "
            "pin (a diode-OR'd wake line, for instance) - mark every claim "
            "\"shared\": true so the sharing is deliberate and visible.",
            pin=pin,
            owners=sorted(names),
        )


def check_board_rules(
    pm: Dict[str, Any],
    board: Dict[str, Any],
    alloc: Dict[int, List[Dict[str, Any]]],
    rep: Report,
) -> None:
    valid: Set[int] = set(board.get("gpio_valid", []))
    consumed: Dict[str, str] = {str(k): v for k, v in (board.get("consumed") or {}).items()}
    strapping: Dict[str, str] = {str(k): v for k, v in (board.get("strapping") or {}).items()}
    input_only: Set[int] = set(board.get("input_only", []))
    rtc: Set[int] = set(board.get("rtc_capable", []))
    jtag: Set[int] = set(board.get("jtag", []))
    free_explicit = board.get("free")
    cond_free: Dict[str, str] = {str(k): v for k, v in (board.get("conditional_free") or {}).items()}
    contradicted: Dict[str, str] = {
        str(k): v for k, v in (board.get("contradicted_header_pins") or {}).items()
    }
    console = pm.get("console", "usb_cdc")

    for pin in sorted(alloc):
        owners = ", ".join(sorted({c["owner"] for c in alloc[pin]}))
        spin = str(pin)

        if valid and pin not in valid:
            rep.error(
                "PIN_NOT_ON_BOARD",
                f"GPIO{pin} ({owners}) does not exist or is not broken out on "
                f"{board['id']}.",
                fix="Pick a pin from free_pins in this report.",
                pin=pin,
            )
            continue

        if spin in consumed:
            rep.error(
                "PIN_RESERVED",
                f"GPIO{pin} is already consumed on {board['id']}: {consumed[spin]} "
                f"(you allocated {owners}).",
                fix="Pick a pin from free_pins. Taking a consumed pin does not free "
                "it; it breaks whatever already owns it.",
                pin=pin,
                consumed_by=consumed[spin],
                source=f"boards/{board['id']}.json#consumed",
            )
        elif free_explicit is not None and pin not in free_explicit and spin not in cond_free:
            rep.error(
                "PIN_NOT_FREE",
                f"GPIO{pin} ({owners}) is not in this board's enumerated free list "
                f"{sorted(free_explicit)}, and no condition is documented for it.",
                fix="The vendor reference for this board enumerates its free pins. "
                "A pin outside that list is unavailable for a reason the generic "
                "rules do not know. Pick one from free_pins.",
                pin=pin,
                source=f"boards/{board['id']}.json#free",
            )

        if spin in cond_free:
            cond = cond_free[spin]
            satisfied = not (
                pin in (43, 44) and board.get("family", "").startswith("ESP32") and console != "usb_cdc"
            )
            if satisfied:
                rep.info(
                    "PIN_CONDITIONALLY_FREE",
                    f"GPIO{pin} ({owners}) is free only under a condition: {cond}",
                    pin=pin,
                    condition=cond,
                )
            else:
                rep.error(
                    "PIN_CONDITION_UNMET",
                    f"GPIO{pin} ({owners}) is only free under a condition that this "
                    f"design does not meet: {cond}. console is {console!r}.",
                    fix="Set console to usb_cdc, or move the net.",
                    pin=pin,
                )

        if spin in contradicted:
            rep.error(
                "HEADER_PIN_CONTRADICTED",
                f"GPIO{pin} ({owners}): {contradicted[spin]}",
                fix="Use a different header pin. The vendor documentation contradicts "
                "itself here and the safe reading is the prohibition.",
                pin=pin,
            )

        if spin in strapping:
            rep.warn(
                "PIN_STRAPPING",
                f"GPIO{pin} ({owners}) is a strapping pin: {strapping[spin]}",
                fix="If you must use it, drive it only AFTER boot and never fit an "
                "external pull. Confirm the level it floats to at reset.",
                pin=pin,
                source=f"boards/{board['id']}.json#strapping",
            )
            for c in alloc[pin]:
                if c.get("external_pull", "none") not in ("none", None):
                    rep.error(
                        "PIN_STRAPPING_PULL",
                        f"GPIO{pin} ({c['owner']}) is a strapping pin and an external "
                        f"pull-{c['external_pull']} is declared on it. {strapping[spin]}",
                        fix="Remove the external pull. On ESP32-S3 GPIO45 this is not a "
                        "style point: an external pull-up switches flash to 1.8 V and "
                        "bricks boot.",
                        pin=pin,
                    )

        if pin in input_only:
            for c in alloc[pin]:
                if c.get("mode") in ("output", "output_od", "bidir"):
                    rep.error(
                        "PIN_INPUT_ONLY",
                        f"GPIO{pin} ({c['owner']}) is input-only on {board['id']} but is "
                        f"allocated as {c['mode']}.",
                        fix="Move the output to a full GPIO. Note these pins usually have "
                        "no internal pull resistors either, so an input here needs an "
                        "external one.",
                        pin=pin,
                    )

        if pin in jtag:
            rep.warn(
                "JTAG_COST",
                f"GPIO{pin} ({owners}) is a JTAG pin. Using it costs hardware JTAG "
                f"debugging.",
                fix="Accept it deliberately, or keep the pin free if you expect to need "
                "a debugger. This is a real cost, not an error.",
                pin=pin,
            )

    # deep-sleep wake sources
    for w in pm.get("wake_sources", []) or []:
        pin = _as_pin(w.get("pin"))
        if pin is None:
            continue
        if not rtc:
            rep.warn(
                "WAKE_RTC_UNKNOWN",
                f"{w.get('net')} on GPIO{pin} is declared a wake source, but the "
                f"{board['id']} profile does not enumerate RTC-capable pins.",
                fix="This profile deliberately does not guess. Confirm the low-power "
                "wake capability for this family before relying on it.",
                pin=pin,
            )
        elif pin not in rtc:
            rep.error(
                "WAKE_NOT_RTC",
                f"{w.get('net')} on GPIO{pin} cannot wake the chip from deep sleep: "
                f"only RTC-capable pins can, and on {board['id']} those are "
                f"{_compact(sorted(rtc))}.",
                fix=f"Move the wake source to an RTC-capable pin. On this board the "
                f"free or conditionally-free RTC pins are "
                f"{_compact(sorted(set(rtc) & _availability(board)))}.",
                pin=pin,
            )


def _compact(pins: List[int]) -> str:
    """GPIO0-21 reads better than a list of 22 numbers."""
    if not pins:
        return "none"
    runs: List[Tuple[int, int]] = []
    start = prev = pins[0]
    for p in pins[1:]:
        if p == prev + 1:
            prev = p
            continue
        runs.append((start, prev))
        start = prev = p
    runs.append((start, prev))
    return ", ".join(f"{a}-{b}" if b > a else str(a) for a, b in runs)


def _availability(board: Dict[str, Any]) -> Set[int]:
    free = board.get("free")
    if free is not None:
        s = set(free)
    else:
        s = set(board.get("gpio_valid", [])) - {int(k) for k in (board.get("consumed") or {})}
    s |= {int(k) for k in (board.get("conditional_free") or {})}
    return s


def check_adc(pm: Dict[str, Any], board: Dict[str, Any], rep: Report) -> None:
    adc1 = {int(k): v for k, v in (board.get("adc1") or {}).items()}
    adc2 = {int(k): v for k, v in (board.get("adc2") or {}).items()}
    radio = pm.get("radio") or {}
    wifi = bool(radio.get("wifi"))

    analog: List[Tuple[str, int]] = [
        (a.get("net", "<analog>"), _as_pin(a.get("pin")))
        for a in (pm.get("analog_inputs") or [])
    ]
    analog += [
        (n.get("net", "<analog>"), _as_pin(n.get("pin")))
        for n in (pm.get("nets") or [])
        if n.get("mode") == "analog"
    ]
    analog = [(n, p) for n, p in analog if p is not None]

    available = _availability(board)
    free_adc1 = sorted(set(adc1) & available)

    for net, pin in analog:
        if pin in adc2 and wifi:
            rep.error(
                "ADC2_WITH_WIFI",
                f"GPIO{pin} is {adc2[pin]}; adc2_get_raw() returns ESP_ERR_TIMEOUT "
                f"whenever the Wi-Fi driver is active, so {net} cannot be read at all "
                f"in this design.",
                fix=(
                    "Move the analog input to a free ADC1 channel"
                    if free_adc1
                    else "There is no free ADC1 channel on this board. The fix is "
                    "architectural, not a reassignment: use an I2C GPIO expander "
                    "(MCP23017) for discrete inputs, or a dedicated I2C ADC "
                    "(ADS1115) for a real analog signal."
                ),
                pin=pin,
                net=net,
                channel=adc2[pin],
                free_adc1=free_adc1,
                source=f"boards/{board['id']}.json#adc2",
            )
        elif pin not in adc1 and pin not in adc2:
            rep.error(
                "PIN_NOT_ANALOG",
                f"GPIO{pin} ({net}) is not an ADC channel on {board['id']}.",
                fix=f"ADC1 channels are GPIO{_compact(sorted(adc1))}.",
                pin=pin,
            )

    need_analog = bool(analog) or (pm.get("required_pins", {}) or {}).get("analog", 0) > 0
    if need_analog and adc1 and not free_adc1:
        rep.error(
            "NO_FREE_ADC1",
            f"This design needs an analog input and {board['id']} has no free ADC1 "
            f"channel: ADC1 is GPIO{_compact(sorted(adc1))} and every one is consumed.",
            fix="Use an I2C GPIO expander (MCP23017, parts/mcp23017-waveshare.json) for "
            "discrete inputs such as a keypad, or an I2C ADC for a genuine analog "
            "signal. Note this is an architectural change: the expander is 38 x 23 mm "
            "and will move the enclosure.",
            adc1=sorted(adc1),
            source=f"boards/{board['id']}.json#adc1",
        )


def check_buses(pm: Dict[str, Any], board: Dict[str, Any], rep: Report, search: List[str]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    board_logic = board.get("logic_v", 3.3)
    cs_seen: Dict[Tuple[str, int], str] = {}

    for b in pm.get("buses", []) or []:
        kind = b.get("kind")
        bid = b.get("id", kind)
        devices = b.get("devices", []) or []
        entry: Dict[str, Any] = {"kind": kind, "id": bid}
        for sig in BUS_SIGNALS.get(kind, []):
            if b.get(sig) is not None:
                entry[sig] = b[sig]
        if b.get("hz"):
            entry["hz"] = b["hz"]

        # ---- level compatibility, any bus kind
        for dev in devices:
            part = load_part(dev["part_ref"], TOOL, search) if dev.get("part_ref") else None
            dev_v = dev.get("logic_v") or (part or {}).get("logic_v")
            tolerant = (part or {}).get("level_tolerant_5v")
            bus_v = b.get("logic_v") or board_logic
            if dev_v and abs(float(dev_v) - float(bus_v)) > 0.3 and not tolerant:
                rep.error(
                    "LEVEL_MISMATCH",
                    f"{dev.get('ref')} runs at {dev_v} V on a {bus_v} V bus ({bid}) and "
                    f"is not documented as tolerant of the bus level.",
                    fix="Fit a bidirectional level shifter, or choose a part that runs "
                    "at the bus voltage. A level shifter is not optional between 5 V "
                    "and 3.3 V.",
                    bus=bid,
                    device=dev.get("ref"),
                )

        if kind == "i2c":
            hz = float(b.get("hz") or 100_000)
            addr_owner: Dict[str, str] = {}
            pullups: List[float] = []
            pullup_sources: List[str] = []

            if b.get("pullup_ohm"):
                pullups.append(float(b["pullup_ohm"]))
                pullup_sources.append(b.get("pullup_source") or "declared on bus")

            for dev in devices:
                part = load_part(dev["part_ref"], TOOL, search) if dev.get("part_ref") else None
                addr = (dev.get("addr") or "").lower()
                if addr:
                    if addr in addr_owner:
                        rep.error(
                            "I2C_ADDR_COLLISION",
                            f"{dev.get('ref')} and {addr_owner[addr]} both answer at "
                            f"{addr} on bus {bid}.",
                            fix="Strap one device to a different address, put one on a "
                            "second I2C bus, or fit an I2C multiplexer. Some parts "
                            "(the DRV2605L at 0x5A, for instance) have a fixed "
                            "address and cannot be moved.",
                            bus=bid,
                            addr=addr,
                            devices=[addr_owner[addr], dev.get("ref")],
                        )
                    else:
                        addr_owner[addr] = dev.get("ref", "?")
                    if part and part.get("i2c", {}).get("addresses"):
                        allowed = [a.lower() for a in part["i2c"]["addresses"]]
                        if addr not in allowed:
                            rep.error(
                                "I2C_ADDR_IMPOSSIBLE",
                                f"{dev.get('ref')} is declared at {addr}, but "
                                f"{part['id']} only answers at "
                                f"{', '.join(part['i2c']['addresses'])}.",
                                fix="Correct the address, or correct the part_ref.",
                                bus=bid,
                                device=dev.get("ref"),
                            )
                onboard = dev.get("onboard_pullup_ohm")
                if onboard is None and part:
                    onboard = (part.get("i2c") or {}).get("onboard_pullup_ohm")
                if onboard:
                    pullups.append(float(onboard))
                    pullup_sources.append(f"module:{dev.get('ref')}")

            eff = parallel(pullups)
            entry["devices"] = [
                {"ref": d.get("ref"), "addr": d.get("addr")} for d in devices
            ]
            entry["pullup_ohm_effective"] = round(eff, 1) if eff else None
            entry["pullup_sources"] = pullup_sources

            if eff is None:
                rep.warn(
                    "I2C_NO_PULLUP",
                    f"Bus {bid} has no pull-up declared anywhere: not on the bus, not "
                    f"on any module, not on the board profile.",
                    fix=f"An I2C bus with no pull-ups does not work. Fit "
                    f"{recommended_pullup(hz)} ohm to each line, or declare the "
                    f"pull-ups that are already fitted on your modules so this check "
                    f"can count them.",
                    bus=bid,
                )
            else:
                rec = recommended_pullup(hz)
                if len(pullups) >= 3:
                    rep.warn(
                        "I2C_PULLUP_STACKED",
                        f"Bus {bid} has {len(pullups)} pull-up sources in parallel "
                        f"({pullup_sources}), giving an effective {eff:.0f} ohm. "
                        f"Every breakout that ships its own 10k adds one.",
                        fix="Remove the pull-up resistors from all but one module, or "
                        "cut the solder jumpers where the module provides them. A bus "
                        "that is too stiff wastes current and stresses the drivers.",
                        bus=bid,
                        effective_ohm=round(eff, 1),
                    )
                if eff > rec * 2.5:
                    rep.warn(
                        "I2C_PULLUP_WEAK",
                        f"Bus {bid} runs at {hz / 1000:.0f} kHz with an effective "
                        f"{eff:.0f} ohm pull-up; about {rec} ohm is the usual target.",
                        fix="Rise time will be slow and the bus may be unreliable over "
                        "any real wire length. Add a parallel resistor or slow the bus.",
                        bus=bid,
                    )

        if kind == "spi":
            for dev in devices:
                if dev.get("cs") is None:
                    rep.error(
                        "SPI_CS_MISSING",
                        f"{dev.get('ref')} on SPI bus {bid} has no chip select.",
                        fix="Give every SPI device its own CS pin. SPI has no addressing.",
                        bus=bid,
                    )
                    continue
                key = (bid, int(dev["cs"]))
                if key in cs_seen:
                    rep.error(
                        "SPI_CS_SHARED",
                        f"{dev.get('ref')} and {cs_seen[key]} share CS GPIO{dev['cs']} "
                        f"on bus {bid}.",
                        fix="Give each device its own CS pin. Two devices on one CS will "
                        "both drive MISO and corrupt every transfer.",
                        bus=bid,
                        pin=dev["cs"],
                    )
                else:
                    cs_seen[key] = dev.get("ref", "?")
            entry["devices"] = [
                {"ref": d.get("ref"), "cs": d.get("cs")} for d in devices
            ]

        summary.append(entry)
    return summary


def check_budget(
    pm: Dict[str, Any], board: Dict[str, Any], alloc: Dict[int, List[Dict[str, Any]]], rep: Report
) -> None:
    req = pm.get("required_pins") or {}
    need = int(req.get("digital", 0)) + int(req.get("analog", 0))
    if not need:
        return
    available = _availability(board)
    used = set(alloc)
    remaining = sorted(available - used)
    if need > len(remaining):
        rep.error(
            "PIN_BUDGET_EXHAUSTED",
            f"This design declares it still needs {need} more pins"
            + (f" ({req['reason']})" if req.get("reason") else "")
            + f", and only {len(remaining)} are left on {board['id']}: "
            f"{remaining or 'none'}. You are {need - len(remaining)} short.",
            fix="This is an architectural shortfall, not a reassignment. Add an I2C "
            "GPIO expander, move to a board with more free pins, or drop a feature. "
            "Note that adding an expander changes the BOM, the power budget and the "
            "enclosure size.",
            needed=need,
            remaining=remaining,
            shortfall=need - len(remaining),
        )


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser(
        "pinmap_lint.py", "Validate a pin map against a board profile."
    )
    p.add_argument("pinmap", help="Path to pinmap.json")
    p.add_argument(
        "--board-dir",
        action="append",
        default=[],
        help="Extra directory to search for board and part profiles (project-local copies win).",
    )
    args = p.parse_args(argv)

    pm = load_json(args.pinmap, TOOL)
    search: List[str] = list(args.board_dir) + [os.path.dirname(os.path.abspath(args.pinmap))]

    board_id = pm.get("board")
    if not board_id:
        from hwlib import die

        die(
            TOOL,
            "BOARD_MISSING",
            "pinmap.json has no \"board\". This field is mandatory and has no default: "
            "GPIO numbers mean different things on different boards.",
        )

    board = load_board(board_id, TOOL, search)
    rep = Report(TOOL, source="static", board=board_id, board_status=board.get("status"))

    validate_schema(pm, "pinmap", rep)

    if board.get("status") == "superseded":
        rep.warn(
            "BOARD_SUPERSEDED",
            f"Board profile {board_id!r} is marked superseded"
            + (f" by {board['superseded_by']!r}" if board.get("superseded_by") else "")
            + ". Its pin facts are still true of that hardware, but they are almost "
            "certainly not the board you are holding.",
            fix="Confirm which revision is on the bench before trusting any pin number "
            "in this report.",
        )
    elif board.get("status") == "draft":
        rep.warn(
            "BOARD_DRAFT",
            f"Board profile {board_id!r} is a DRAFT. Its numbers have not been "
            f"corroborated, so every check in this report is only as good as an "
            f"uncorroborated profile.",
            fix="A clean pass against a draft profile is not evidence the design is "
            "right. Corroborate the profile with the board-profiles skill "
            "(profile_lint.py, verify_profile.py), or accept BOARD_DRAFT deliberately "
            "with a written reason.",
        )

    _check_board_corroboration(board, rep)

    alloc = collect_allocations(pm, rep)
    check_conflicts(alloc, rep)
    check_board_rules(pm, board, alloc, rep)
    check_adc(pm, board, rep)
    buses = check_buses(pm, board, rep, search)
    check_budget(pm, board, alloc, rep)

    rep.apply_acceptances(pm.get("accepted_findings"), ACKNOWLEDGEABLE)

    available = _availability(board)
    used = set(alloc)
    rep.set(
        free_pins=sorted(board["free"]) if board.get("free") is not None else sorted(available),
        free_pins_conditional=board.get("conditional_free") or {},
        allocated={
            str(pin): sorted({c["owner"] for c in claims}) for pin, claims in sorted(alloc.items())
        },
        unallocated=sorted(available - used),
        buses=buses,
    )

    if not board.get("input_only"):
        rep.note(
            f"PIN_INPUT_ONLY is not applicable on {board.get('family')}: this family has "
            "no input-only GPIOs. Rules written for the classic ESP32's GPIO34-39 do "
            "not transfer."
        )

    return rep.emit(args.strict)


if __name__ == "__main__":
    sys.exit(main())
