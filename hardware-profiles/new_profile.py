#!/usr/bin/env python3
"""new_profile.py - scaffold a board or part profile you have not researched yet.

The scaffold is deliberately *empty and honest*. It ships as
``"status": "draft"``, it carries a corroboration record with no sources in it,
and it embeds the research checklist for the family so the next step is obvious.

It does NOT guess. A scaffolder that pre-fills a plausible ESP32-S3 pin map is
how you get a profile that looks researched and is not - and the whole point of
this skill is that a wrong profile is worse than a missing one, because the
paired linter will validate a design against it and report a clean pass.

    new_profile.py --kind board --id xiao_esp32c3 --family ESP32-C3 --out boards/
    new_profile.py --kind part  --id bme280_breakout --class sensor_module
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proflib import (  # noqa: E402
    BOARD_GROUPS,
    PART_GROUPS,
    Report,
    base_parser,
    die,
    write_json,
)

TOOL = "new_profile"

#: What to go and read, per family. These are pointers, not data: the scaffolder
#: refuses to fill in pin numbers it has not been told.
FAMILY_CHECKLIST: Dict[str, List[str]] = {
    "ESP32": [
        "Espressif ESP32 datasheet: GPIO matrix, strapping pins, ADC1/ADC2 channel map.",
        "arduino-esp32 variants/<board>/pins_arduino.h for the board's own assignments.",
        "The board definition in boards.txt - it beats the datasheet for board facts.",
        "CONFIRM: GPIO34-39 are input-only on this family and have NO internal pulls.",
        "CONFIRM: ADC2 is unusable while Wi-Fi is active. Say so in notes.",
        "CONFIRM: which flash pins are broken out. GPIO6-11 usually are not.",
    ],
    "ESP32-S3": [
        "Espressif ESP32-S3 datasheet and TRM: strapping 0/3/45/46, ADC1 = GPIO1-10.",
        "arduino-esp32 variants/<board>/pins_arduino.h.",
        "An independent community firmware variant if one exists - strongest source.",
        "CONFIRM: this family has NO input-only GPIOs. If your draft lists any, it was copied from a classic ESP32.",
        "CONFIRM: RTC-capable range (GPIO0-21) - a wake pin outside it never wakes.",
        "CONFIRM: flash and PSRAM pin consumption. No pinout diagram draws them.",
        "CONFIRM: GPIO45 selects VDD_SPI voltage at boot. An external pull-up can brick boot.",
    ],
    "ESP32-C3": [
        "Espressif ESP32-C3 datasheet: single core, RISC-V, different strapping set from the S3.",
        "arduino-esp32 variants/<board>/pins_arduino.h.",
        "CONFIRM: the ADC bank layout for THIS part, not the S3's.",
        "CONFIRM: USB-Serial-JTAG pin pair.",
        "CONFIRM: flash pin consumption.",
    ],
    "RP2040": [
        "Raspberry Pi RP2040 datasheet and the specific board's datasheet.",
        "The CircuitPython or MicroPython board definition, which enumerates real pins.",
        "CONFIRM: which GPIOs are broken out on THIS board - the die has more than most boards expose.",
        "CONFIRM: ADC is GPIO26-28 (plus 29 on some boards, often on an internal divider).",
        "NOTE: any pin can be any function via the PIO, which makes conflict checking MORE important, not less.",
        "This profile family deliberately leaves rtc_capable empty rather than guessing.",
    ],
    "nRF52": [
        "Nordic nRF52 series datasheet for the specific variant.",
        "The Zephyr or Adafruit board definition file.",
        "CONFIRM: which pins are consumed by the on-module crystal and DCDC inductors.",
        "CONFIRM: NFC pins default to NFC, not GPIO, until a config word is changed.",
    ],
    "STM32": [
        "ST datasheet for the exact part number - pin maps differ across the same family.",
        "The CubeMX pinout for the package you actually have.",
        "CONFIRM: package matters. The same die in a different package exposes different pins.",
    ],
    "AVR": [
        "Microchip datasheet for the exact part.",
        "The Arduino variant pins_arduino.h for the board.",
    ],
}

GENERIC_CHECKLIST = [
    "Find the manufacturer datasheet and cite the section, not just the document.",
    "Find the schematic and cite its REVISION. A schematic without one cannot be re-checked.",
    "Find the toolchain's board definition and variant header.",
    "Look for an independent community firmware variant - it is the strongest documentary source.",
    "Record every disagreement between sources. Do not average them.",
    "Mark anything you could not establish as an open question with its impact.",
]

PART_CHECKLIST = [
    "Measure the footprint with calipers. One measurement outranks every document.",
    "State height_includes explicitly - body, plunger top, or over a fitted connector.",
    "For I2C parts: the full address range, the default, and whether it is selectable at all.",
    "Record on-module pull-up resistors even when the answer is none.",
    "Record 5 V tolerance explicitly rather than implying it from the supply range.",
    "Decide failure_mode honestly. If the part can die without erroring, it is silent, and that forces a liveness check.",
    "If the part has a functional axis - a port, a cone, a sensing face, a pole - record the orientation constraint.",
]


def scaffold_board(args: argparse.Namespace) -> Dict[str, Any]:
    family = args.family or ""
    return {
        "schema": "hardware-electronics/board",
        "version": "1.0",
        "id": args.id,
        "display_name": args.display_name or "",
        "status": "draft",
        "superseded_by": None,
        "family": family,
        "mcu": {
            "family": family,
            "cores": None,
            "flash_mb": None,
            "flash_mb_provenance": "UNKNOWN - read it off silicon with board_cli.py identify. Do not believe the listing.",
            "psram_mb": None,
            "psram_note": "",
        },
        "fqbn": None,
        "fqbn_note": "Prefer the vendor board definition and change nothing. The intuitive manual guesses routinely contradict it.",
        "logic_v": 3.3,
        "gpio_valid": [],
        "input_only": [],
        "strapping": {},
        "rtc_capable": [],
        "adc1": {},
        "adc2": {},
        "usb": [],
        "jtag": [],
        "consumed": {},
        "free": None,
        "conditional_free": {},
        "contradicted_header_pins": {},
        "onboard_i2c": {},
        "power": {},
        "radio": {},
        "pin_notes": {},
        "notes": [
            "SCAFFOLD. Nothing in this file has been researched yet. Every list is "
            "empty on purpose: an empty list is honest, and a plausible guess is not.",
        ],
        "sources": [],
        "corroboration": {
            "sources": [],
            "groups": {},
            "conservative": False,
            "contradictions": [],
            "open_questions": [
                {
                    "question": q,
                    "impact": "Blocks corroboration of the group this belongs to.",
                    "blocks_active": True,
                }
                for q in (FAMILY_CHECKLIST.get(family) or GENERIC_CHECKLIST)
            ],
        },
    }


def scaffold_part(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "schema": "hardware-electronics/part",
        "version": "1.0",
        "id": args.id,
        "description": args.display_name or "",
        "vendor": "",
        "mpn": "",
        "status": "draft",
        "class": args.part_class or "other",
        "footprint": {
            "shape": "rect",
            "l": None,
            "w": None,
            "h": None,
            "height_includes": "unknown",
            "provenance": "assumed",
        },
        "electrical": {},
        "logic_v": None,
        "level_tolerant_5v": None,
        "i2c": {},
        "keepouts": [],
        "orientation_constraint": {},
        "failure_mode": "unknown",
        "traps": [],
        "notes": [
            "SCAFFOLD. Nothing here has been measured or researched. The footprint is "
            "null rather than a plausible round number, because a plausible round "
            "number is how a part ends up printed around at the wrong size.",
        ],
        "sources": [],
        "corroboration": {
            "sources": [],
            "groups": {},
            "conservative": False,
            "contradictions": [],
            "open_questions": [
                {"question": q, "impact": "Blocks corroboration.", "blocks_active": True}
                for q in PART_CHECKLIST
            ],
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser(
        "new_profile.py", "Scaffold an empty, honest, draft profile."
    )
    p.add_argument("--kind", choices=["board", "part"], required=True)
    p.add_argument("--id", required=True, help="lowercase_with_underscores")
    p.add_argument("--display-name")
    p.add_argument("--family", help=f"One of: {', '.join(sorted(FAMILY_CHECKLIST))}")
    p.add_argument("--class", dest="part_class", help="Part class, for --kind part")
    p.add_argument("--out", help="Directory or file path to write to. Prints to stdout when omitted.")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)

    if not re.fullmatch(r"[a-z0-9_.-]+", args.id):
        die(
            TOOL,
            "BAD_ID",
            f"{args.id!r} is not a valid id. Use lowercase letters, digits, "
            "underscores, dots and hyphens - it becomes a filename and a lookup key.",
        )

    rep = Report(TOOL, source="static", kind=args.kind, id=args.id, status="draft")

    if args.kind == "board":
        profile = scaffold_board(args)
        checklist = FAMILY_CHECKLIST.get(args.family or "")
        if args.family and not checklist:
            rep.warn(
                "FAMILY_UNKNOWN",
                f"No research checklist for family {args.family!r}, so a generic one "
                f"was used.",
                fix=f"Known families: {', '.join(sorted(FAMILY_CHECKLIST))}. Add one to "
                "new_profile.py if you will author several of these.",
            )
        elif not args.family:
            rep.warn(
                "NO_FAMILY",
                "No --family given, so the generic checklist was used and no "
                "family-specific traps are listed.",
                fix="Pass --family. Most wrong profiles are wrong because a rule from "
                "one family was applied to another.",
            )
        groups = sorted(BOARD_GROUPS)
    else:
        profile = scaffold_part(args)
        if not args.part_class:
            rep.warn(
                "NO_CLASS",
                "No --class given, so the part is scaffolded as \"other\".",
                fix="Set it: the class is what triggers the orientation check for parts "
                "with a functional axis.",
            )
        groups = sorted(PART_GROUPS)

    out_path = None
    if args.out:
        out_path = (
            os.path.join(args.out, f"{args.id}.json") if os.path.isdir(args.out) else args.out
        )
        if os.path.isfile(out_path) and not args.force:
            rep.error(
                "PROFILE_EXISTS",
                f"{out_path} already exists.",
                fix="Pass --force to overwrite, but read it first - you may be about to "
                "discard research someone already did.",
            )
            return rep.emit(args.strict)
        write_json(out_path, profile)

    rep.set(
        out=out_path,
        profile=None if out_path else profile,
        groups_to_corroborate=groups,
        generated=_dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    rep.info(
        "SCAFFOLD_IS_EMPTY",
        "Every field is empty or null on purpose. Fill them in from real sources; do "
        "not let a plausible guess stand in for research.",
        fix="Work through corroboration.open_questions, then run profile_lint.py. The "
        "profile stays at status \"draft\" - and gets flagged by every design that uses "
        "it - until its groups are corroborated.",
    )
    rep.note(
        "Next: profile_lint.py "
        + (out_path or f"{args.id}.json")
        + " --kind "
        + args.kind
    )
    return rep.emit(args.strict)


if __name__ == "__main__":
    sys.exit(main())
