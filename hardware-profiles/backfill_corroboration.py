"""One-off migration: backfill corroboration records into the shipped profiles.

The DATA here is hand-written and reflects what each profile was actually built
from. Only the application is mechanical. Generating plausible corroboration
automatically would be precisely the dishonesty this pairing exists to prevent.

Run once, then delete. Kept in the repo only so the reasoning is auditable.
"""

from __future__ import annotations

import json
import os
import sys

# id -> corroboration record, written by hand from what each profile really used.
BOARDS = {
    "heltec_vision_master_e290": {
        "sources": [
            {"id": "ds", "kind": "datasheet", "ref": "Heltec Vision Master E290 datasheet, section 2.2 (pin map) and section 1.2 / table 3.2 (power)"},
            {"id": "sch", "kind": "schematic", "ref": "Heltec E290 schematic", "revision": "V0.3.1"},
            {"id": "arduino", "kind": "variant_header", "ref": "espressif/arduino-esp32 variants/heltec_vision_master_e290/pins_arduino.h"},
            {"id": "meshtastic", "kind": "community_firmware", "ref": "meshtastic/firmware variants/esp32s3/heltec_vision_master_e290/variant.h"},
            {"id": "silicon", "kind": "measurement", "ref": "esp_flash_get_size() via the bring-up sketch on COM7, 2026-09-17"},
            {"id": "product_page", "kind": "product_page", "ref": "Heltec product page and FAQ", "note": "Boilerplate shared across Heltec's ESP32 range. Contradicts the schematic on the charge IC. Recorded so its claims can be identified, not counted."},
        ],
        "groups": {
            "gpio_map": {
                "sources": ["ds", "sch", "arduino", "meshtastic"],
                "agreement": "full",
                "checked": "2026-09-17",
                "note": "Every GPIO assignment confirmed by at least three of these four. This was previously a prose note that nothing could check.",
            },
            "strapping": {"sources": ["ds", "sch", "arduino"], "agreement": "full", "checked": "2026-09-17"},
            "adc": {"sources": ["ds", "arduino"], "agreement": "full", "checked": "2026-09-17"},
            "rtc_wake": {"sources": ["ds", "meshtastic"], "agreement": "full", "checked": "2026-09-17"},
            "power": {"sources": ["sch", "ds"], "agreement": "partial", "checked": "2026-09-19", "note": "Charge path from the schematic; sleep current disputed between vendor documents."},
            "mechanical": {"sources": ["ds"], "agreement": "full", "checked": "2026-09-19"},
            "radio": {"sources": ["ds", "meshtastic"], "agreement": "conflicting", "checked": "2026-09-19"},
        },
        "conservative": False,
        "contradictions": [
            {
                "field": "power.sleep_current_ua",
                "readings": [
                    {"value": 18, "source": "ds", "note": "Table 3.2 and the product page"},
                    {"value": 20, "source": "ds", "note": "Section 1.2 body text"},
                ],
                "resolution": "unresolved",
                "impact": "Dominates the long tail of any battery-life estimate. power_budget.py reports a runtime RANGE rather than a point estimate because of this.",
                "how_to_close": "Meter in series with the battery positive lead, uA range, USB DISCONNECTED.",
            },
            {
                "field": "radio.antenna_2g4.connector",
                "readings": [
                    {"value": "U.FL", "source": "ds", "note": "Spec table"},
                    {"value": "spring antenna, no connector", "source": "product_page", "note": "Vendor FAQ"},
                ],
                "resolution": "unresolved",
                "impact": "Whether a second antenna port can be designed into an enclosure at all.",
                "how_to_close": "Physically inspect the board.",
            },
            {
                "field": "power.charge.ic",
                "readings": [
                    {"value": "LGS4056H", "source": "sch"},
                    {"value": "MCP73831 / TP4054", "source": "product_page", "note": "Generic boilerplate shared across Heltec's whole ESP32 range"},
                ],
                "resolution": "chosen",
                "resolved_value": "LGS4056H",
                "resolved_by": "The schematic names the part actually fitted; the FAQ page is boilerplate that is identical across unrelated Heltec products, so it is not a source about this board.",
                "impact": "Sets the charge-current formula and therefore the minimum safe cell capacity.",
            },
            {
                "field": "mcu.flash_mb",
                "readings": [
                    {"value": 16, "source": "product_page"},
                    {"value": 8, "source": "silicon"},
                ],
                "resolution": "measured",
                "resolved_value": 8,
                "resolved_by": "esp_flash_get_size() on the physical board. Silicon beats both documents.",
                "impact": "Partition layout. Believing 16 MB would silently truncate an OTA partition.",
            },
        ],
        "open_questions": [
            {"question": "Verify R18 on the physical board reads 2 kOhm.", "impact": "Confirms the charge current, which is a battery-safety number currently resting on a schematic reading.", "blocks_active": False},
            {"question": "Confirm the 1200/R_PROG charge constant against the LGS4056H datasheet.", "impact": "Same.", "blocks_active": False},
        ],
    },
    "esp32s3-generic": {
        "sources": [
            {"id": "espressif_ds", "kind": "datasheet", "ref": "Espressif ESP32-S3 datasheet and Technical Reference Manual: GPIO matrix, strapping pins, ADC bank map, RTC domain"},
            {"id": "ref_project_a", "kind": "community_firmware", "ref": "reference project A project notes (docs/pager-hardware-plan.md, docs/e290-hardware-reference.md) for the ADC2-with-Wi-Fi and RTC-pin consequences as encountered in practice"},
        ],
        "groups": {
            "gpio_map": {"sources": ["espressif_ds"], "agreement": "full", "note": "Family-level only. This profile describes the PART, not any particular board, and marks flash and PSRAM pins consumed on the assumption that a module fits both."},
            "strapping": {"sources": ["espressif_ds"], "agreement": "full"},
            "adc": {"sources": ["espressif_ds", "ref_project_a"], "agreement": "full"},
            "rtc_wake": {"sources": ["espressif_ds", "ref_project_a"], "agreement": "full"},
        },
        "conservative": True,
        "conservative_rationale": "This is a family fallback, not a board. It over-reserves: flash pins 26-32 and PSRAM pins 33-37 are marked consumed even though a module without PSRAM would free five of them, and nothing is ever listed in the authoritative free list. The failure mode is refusing a pin that would have worked, which is recoverable; the opposite would hand a designer a pin that breaks the flash bus.",
        "contradictions": [],
        "open_questions": [
            {"question": "Flash and PSRAM size are deliberately null. Read them off silicon per board.", "impact": "Partition layout.", "blocks_active": False}
        ],
    },
    "esp32-classic": {
        "sources": [
            {"id": "espressif_ds", "kind": "datasheet", "ref": "Espressif ESP32 datasheet and Technical Reference Manual: input-only GPIO34-39, ADC bank map, strapping pins, flash bus GPIO6-11"}
        ],
        "groups": {
            "gpio_map": {"sources": ["espressif_ds"], "agreement": "full", "note": "Family-level only."},
            "strapping": {"sources": ["espressif_ds"], "agreement": "full"},
            "adc": {"sources": ["espressif_ds"], "agreement": "full"},
            "rtc_wake": {"sources": ["espressif_ds"], "agreement": "full"},
        },
        "conservative": True,
        "conservative_rationale": "A family fallback that over-reserves: the flash bus GPIO6-11 is marked consumed unconditionally, and GPIO16/17 are only conditionally free because WROVER modules use them for PSRAM. Refusing a pin that a bare WROOM would have allowed is the safe direction.",
        "contradictions": [],
        "open_questions": [],
    },
    "rp2040-generic": {
        "sources": [
            {"id": "rp_ds", "kind": "datasheet", "ref": "Raspberry Pi RP2040 datasheet and Raspberry Pi Pico datasheet: GPIO count, ADC channels GPIO26-28, Pico-specific GPIO23/24/25/29 usage"}
        ],
        "groups": {
            "gpio_map": {"sources": ["rp_ds"], "agreement": "full", "note": "Pico-shaped. Other RP2040 boards expose different subsets."},
            "adc": {"sources": ["rp_ds"], "agreement": "full"},
        },
        "conservative": True,
        "conservative_rationale": "Deliberately incomplete rather than wrong. rtc_capable is left EMPTY instead of guessing, so pinmap_lint reports any wake source on this family as unverified rather than blessing it. Pico-specific pins 23/24/25/29 are marked consumed even though other RP2040 boards route them differently.",
        "contradictions": [],
        "open_questions": [
            {"question": "Low-power wake behaviour for this family has not been characterised, which is why rtc_capable is empty.", "impact": "Any deep-sleep wake design on RP2040 is flagged as unverified by pinmap_lint.", "blocks_active": False}
        ],
    },
}

PARTS = {
    "mcp23017-waveshare": {
        "sources": [
            {"id": "microchip", "kind": "datasheet", "ref": "Microchip MCP23017 datasheet: address range 0x20-0x27, supply range, interrupt behaviour"},
            {"id": "ref_project_a", "kind": "community_firmware", "ref": "reference project A docs/bom.md and docs/pager-hardware-plan.md: 38 x 23 mm module footprint and the resulting enclosure growth"},
        ],
        "groups": {
            "addressing": {"sources": ["microchip"], "agreement": "full"},
            "electrical": {"sources": ["microchip"], "agreement": "full"},
            "footprint": {"sources": ["ref_project_a"], "agreement": "full", "note": "Module outline, not the IC. Height is over fitted terminals and is tagged assumed in the profile."},
        },
        "conservative": False,
        "contradictions": [],
        "open_questions": [
            {"question": "Module height is tagged assumed. Measure with calipers before designing a pocket around it.", "impact": "Enclosure interior depth.", "blocks_active": False}
        ],
    },
    "max98357a-adafruit3006": {
        "sources": [
            {"id": "maxim", "kind": "datasheet", "ref": "Maxim MAX98357A datasheet: supply range, peak output current into a low-impedance load"},
            {"id": "ref_project_a", "kind": "community_firmware", "ref": "reference project A docs/e290-hardware-reference.md: do not power this from the board's 600 mA 3V3 LDO"},
        ],
        "groups": {
            "electrical": {"sources": ["maxim", "ref_project_a"], "agreement": "full"},
            "footprint": {"sources": ["maxim"], "agreement": "full", "note": "Breakout outline is vendor_claim in the profile; height is tagged assumed."},
        },
        "conservative": False,
        "contradictions": [],
        "open_questions": [],
    },
    "sph0645lm4h-adafruit3421": {
        "sources": [
            {"id": "knowles", "kind": "datasheet", "ref": "Knowles SPH0645LM4H datasheet: bottom-port construction, supply range"},
            {"id": "ref_project_a", "kind": "community_firmware", "ref": "reference project A docs/pager-hardware-plan.md: mic-to-speaker and mic-to-motor separation assertions"},
        ],
        "groups": {
            "electrical": {"sources": ["knowles"], "agreement": "full"},
            "footprint": {"sources": ["knowles"], "agreement": "full", "note": "Breakout dimensions are vendor_claim; height is tagged assumed."},
        },
        "conservative": False,
        "contradictions": [],
        "open_questions": [],
    },
    "drv2605l-adafruit2305": {
        "sources": [
            {"id": "ti", "kind": "datasheet", "ref": "TI DRV2605L datasheet: fixed 0x5A address, supply range"},
            {"id": "ref_project_a", "kind": "community_firmware", "ref": "reference project A docs/bom.md: coin ERM motor start current roughly 100-156 mA, needs local bulk capacitance"},
        ],
        "groups": {
            "addressing": {"sources": ["ti"], "agreement": "full", "note": "Fixed address. Two on one bus needs a multiplexer."},
            "electrical": {"sources": ["ti", "ref_project_a"], "agreement": "full"},
            "footprint": {"sources": ["ti"], "agreement": "full", "note": "Breakout outline is vendor_claim."},
        },
        "conservative": False,
        "contradictions": [],
        "open_questions": [],
    },
    "aqara-mccgq11lm": {
        "sources": [
            {"id": "manual", "kind": "datasheet", "ref": "Aqara MCCGQ11LM manual: marker-line alignment requirement, ventilation warning"},
            {"id": "ref_project_b", "kind": "measurement", "ref": "reference project B project: body measured 41 x 22 x 11 mm with calipers; reed switch located against a 41 mm face"},
        ],
        "groups": {
            "footprint": {"sources": ["ref_project_b"], "agreement": "full", "note": "Measured, which outranks any document for a dimension."},
            "electrical": {"sources": ["manual"], "agreement": "full", "note": "Self-powered from its own CR1632; contributes nothing to a host power budget."},
        },
        "conservative": False,
        "contradictions": [],
        "open_questions": [
            {"question": "The magnet release gap is kinematic in a hinged application and nothing in this pairing can evaluate a constraint through a motion.", "impact": "The lid angle at which the state changes must be verified by sweeping the hinge, not by checking two static positions.", "blocks_active": False}
        ],
    },
}


def main() -> int:
    root = sys.argv[1]
    changed = []
    for sub, table in (("boards", BOARDS), ("parts", PARTS)):
        for pid, corr in table.items():
            path = os.path.join(root, sub, f"{pid}.json")
            if not os.path.isfile(path):
                print(f"SKIP missing {path}")
                continue
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            data["corroboration"] = corr
            if sub == "parts" and "status" not in data:
                data["status"] = "active"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            changed.append(f"{sub}/{pid}.json")
    print(f"backfilled {len(changed)} profiles")
    for c in changed:
        print("  " + c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
