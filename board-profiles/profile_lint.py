#!/usr/bin/env python3
"""profile_lint.py - validate a board or part profile before it is trusted.

Two separate jobs, and the second is the one that matters.

**Self-consistency.** Does the profile contradict itself? An ADC channel on a
pin that does not exist, a pin that is both free and consumed, an RTC range
wider than the GPIO range. These are cheap to check and embarrassing to ship.

**Research hygiene.** Is there any reason to believe it? A profile is a
liability if it is wrong, because the paired skill's ``pinmap_lint.py`` will
validate a design against it and report a clean pass. So a profile may not leave
``status: "draft"`` until its load-bearing field groups are corroborated by
enough INDEPENDENT sources - and two vendor pages copying each other are one
source, not two.

Also catches the family copy-paste, which is the trap that produces a profile
that looks entirely plausible and is wrong throughout: an ESP32-S3 profile
listing GPIO34-39 as input-only has been copied from a classic ESP32.

    profile_lint.py boards/xiao_esp32c3.json --kind board --strict
    profile_lint.py parts/bme280.json --kind part
    profile_lint.py --all --parent "C:\\path\\to\\electronics-design"
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proflib import (  # noqa: E402
    BOARD_GROUPS,
    PART_GROUPS,
    Report,
    SOURCE_KINDS,
    base_parser,
    compact,
    count_independent,
    die,
    find_parent,
    int_keys,
    is_independent_kind,
    load_json,
    validate_schema,
)

TOOL = "profile_lint"

#: Advisory findings a profile may accept with a written reason. Notably absent:
#: every self-consistency error, CORROBORATION_INSUFFICIENT and FAMILY_MISMATCH.
#: Those are not preferences.
ACKNOWLEDGEABLE = frozenset(
    {
        "SOURCE_WEAK_ONLY",
        "GROUP_UNCORROBORATED",
        "CONTRADICTION_UNRESOLVED",
        "NO_PIN_NOTES",
        "NO_DISPLAY_NAME",
        "OPEN_QUESTION",
    }
)

#: Families with no input-only GPIOs. A profile that claims otherwise has been
#: copied from a different part.
NO_INPUT_ONLY_FAMILIES = {"ESP32-S3", "ESP32S3", "ESP32-C3", "ESP32C3", "RP2040"}

#: Families where ADC2 is unusable while the radio is active.
ADC2_RADIO_CONFLICT_FAMILIES = {"ESP32", "ESP32-S2", "ESP32-S3"}


# --------------------------------------------------------------------------
# self-consistency
# --------------------------------------------------------------------------


def check_board_consistency(p: Dict[str, Any], rep: Report) -> None:
    valid: Set[int] = set(p.get("gpio_valid") or [])
    if not valid:
        rep.error(
            "NO_GPIO_VALID",
            "gpio_valid is empty, so nothing can be checked against it.",
            fix="List every GPIO number this board actually exposes. This is the "
            "field every other pin check is measured against.",
        )
        return

    def subset(name: str, pins: Set[int], where: str = "") -> None:
        stray = sorted(pins - valid)
        if stray:
            rep.error(
                "PIN_NOT_IN_GPIO_VALID",
                f"{name} names GPIO{compact(stray)}, which are not in gpio_valid.",
                fix="Either the pin exists and gpio_valid is incomplete, or it does "
                "not and this entry is wrong. Both are worth knowing before a design "
                "is validated against this profile." + (f" {where}" if where else ""),
                field=name,
                pins=stray,
            )

    consumed = int_keys(p.get("consumed"))
    cond_free = int_keys(p.get("conditional_free"))
    free = set(p.get("free") or []) if p.get("free") is not None else set()
    adc1 = int_keys(p.get("adc1"))
    adc2 = int_keys(p.get("adc2"))

    # `consumed` is the one field where naming a pin outside gpio_valid is
    # INFORMATIVE rather than contradictory: documenting that GPIO6-11 are the
    # flash bus and are not broken out tells the reader why they will not find
    # them, which is more useful than silence.
    absent_documented = sorted(consumed - valid)
    if absent_documented:
        rep.info(
            "CONSUMED_DOCUMENTS_ABSENT_PIN",
            f"consumed documents GPIO{compact(absent_documented)}, which gpio_valid "
            f"does not list.",
            fix="Read as documentation of a pin that does not exist on this board, not "
            "as an allocation. If any of these IS exposed, add it to gpio_valid - "
            "otherwise nothing can ever allocate it.",
            pins=absent_documented,
        )

    subset("conditional_free", cond_free)
    subset("free", free)
    subset("adc1", adc1)
    subset("adc2", adc2)
    subset("strapping", int_keys(p.get("strapping")))
    subset("rtc_capable", set(p.get("rtc_capable") or []))
    subset("input_only", set(p.get("input_only") or []))
    subset("usb", set(p.get("usb") or []))
    subset("jtag", set(p.get("jtag") or []))
    subset("contradicted_header_pins", int_keys(p.get("contradicted_header_pins")))

    both = sorted(free & consumed)
    if both:
        rep.error(
            "PIN_FREE_AND_CONSUMED",
            f"GPIO{compact(both)} appear in both free and consumed.",
            fix="A pin is one or the other. If it is conditionally available, move it "
            "to conditional_free with the condition written out.",
            pins=both,
        )

    both = sorted(cond_free & consumed)
    if both:
        rep.error(
            "PIN_CONDITIONAL_AND_CONSUMED",
            f"GPIO{compact(both)} are both consumed and conditionally free.",
            fix="Decide which. A consumed pin is not available under any condition; a "
            "conditionally free one needs its condition stated, not its owner.",
            pins=both,
        )

    overlap = sorted(adc1 & adc2)
    if overlap:
        rep.error(
            "ADC_BANK_OVERLAP",
            f"GPIO{compact(overlap)} are listed on BOTH ADC1 and ADC2.",
            fix="A channel belongs to one bank. This matters because ADC2 is unusable "
            "while the radio is active and ADC1 is not, so getting the bank wrong "
            "produces a design that reads fine on the bench and times out in service.",
            pins=overlap,
        )

    onboard = p.get("onboard_i2c") or {}
    for key in ("sda", "scl"):
        pin = onboard.get(key)
        if pin is not None and int(pin) not in valid:
            rep.error(
                "PIN_NOT_IN_GPIO_VALID",
                f"onboard_i2c.{key} is GPIO{pin}, which is not in gpio_valid.",
                field=f"onboard_i2c.{key}",
            )

    if p.get("free") is not None:
        derived = valid - consumed
        blessed = free - derived
        if blessed:
            rep.error(
                "FREE_CLAIMS_CONSUMED_PIN",
                f"The enumerated free list blesses GPIO{compact(sorted(blessed))}, "
                f"which the consumed map says are taken.",
                fix="The free list is authoritative when present, which is exactly why "
                "it must not contradict consumed. Blessing a taken pin is the "
                "dangerous direction of error: it hands a designer a pin that will "
                "break something else.",
                pins=sorted(blessed),
            )

    if not p.get("free") and not consumed:
        rep.warn(
            "NO_PIN_AVAILABILITY_DATA",
            "The profile declares neither a free list nor any consumed pins, so every "
            "GPIO will be treated as available.",
            fix="Absence of evidence is not availability. At minimum record the flash "
            "and PSRAM pins - no pinout diagram ever draws them, and they are consumed "
            "on every module.",
        )


def check_family_sanity(p: Dict[str, Any], rep: Report) -> None:
    """Catch the profile copied from the wrong part.

    This is the trap that produces something entirely plausible and wrong
    throughout, because every individual field looks like a real pin number.
    """
    family = (p.get("family") or "").upper().replace(" ", "")
    input_only = set(p.get("input_only") or [])

    if family in NO_INPUT_ONLY_FAMILIES and input_only:
        rep.error(
            "FAMILY_MISMATCH",
            f"This profile says family {p.get('family')!r} but lists "
            f"GPIO{compact(sorted(input_only))} as input-only. That family has no "
            f"input-only GPIOs.",
            fix="This is the classic wrong-family copy-paste: GPIO34-39 are input-only "
            "on the CLASSIC ESP32 and on nothing else. If the family is right, delete "
            "input_only and re-check every other field in this file, because a profile "
            "that was copied is rarely copied in only one place.",
            family=p.get("family"),
            input_only=sorted(input_only),
        )

    if family.startswith("ESP32") and family not in ("ESP32",):
        strap = int_keys(p.get("strapping"))
        if 12 in strap and 45 not in strap:
            rep.warn(
                "FAMILY_STRAPPING_SUSPECT",
                f"GPIO12 is listed as a strapping pin on {p.get('family')!r}. GPIO12 "
                f"(MTDI) is the classic-ESP32 flash-voltage strap; the S3's equivalent "
                f"is GPIO45.",
                fix="Confirm the strapping set against this family's own datasheet. A "
                "strapping list carried between families is worse than none, because "
                "it protects the wrong pin and leaves the dangerous one unguarded.",
            )

    if family in ADC2_RADIO_CONFLICT_FAMILIES and p.get("adc2"):
        notes = " ".join(p.get("notes") or []).lower()
        pin_notes = " ".join(str(v) for v in (p.get("pin_notes") or {}).values()).lower()
        if "adc2" not in notes and "adc2" not in pin_notes:
            rep.warn(
                "ADC2_CAVEAT_MISSING",
                "This family's ADC2 is unusable while the radio is active, and the "
                "profile never says so.",
                fix="Add it to notes. A designer reading only this file will see a list "
                "of analog-capable pins and no reason not to use them, and the failure "
                "appears only once Wi-Fi comes up.",
            )

    rtc = set(p.get("rtc_capable") or [])
    valid = set(p.get("gpio_valid") or [])
    if rtc and valid and rtc == valid:
        rep.warn(
            "RTC_RANGE_SUSPECT",
            "Every GPIO is listed as RTC-capable.",
            fix="That is true of very few parts. If it is genuinely true here, say so "
            "in notes; otherwise this looks like a range that was copied rather than "
            "looked up, and a wake source on a non-RTC pin produces a device that "
            "sleeps and never wakes.",
        )


def check_part_consistency(p: Dict[str, Any], rep: Report) -> None:
    fp = p.get("footprint") or {}
    shape = fp.get("shape")
    if shape in ("rect", "box") and not (fp.get("l") and fp.get("w")):
        rep.error(
            "FOOTPRINT_INCOMPLETE",
            f"{p.get('id')}: a {shape} footprint needs l and w.",
            fix="Without dimensions nothing can build a pocket around this part.",
        )
    if shape in ("circle", "cylinder") and not fp.get("d"):
        rep.error(
            "FOOTPRINT_INCOMPLETE",
            f"{p.get('id')}: a {shape} footprint needs d.",
            fix="Declare round parts as round. A circle described by its bounding box "
            "reserves 21% more area than it occupies, all of it in the corners.",
        )
    if fp.get("h") and not fp.get("height_includes"):
        rep.warn(
            "HEIGHT_CONVENTION_MISSING",
            f"{p.get('id')} gives a height of {fp['h']} mm without saying what it "
            f"includes.",
            fix="Set height_includes. For a W x L x H part the third figure is often "
            "the overall height to the top of the plunger or shaft, not the body - "
            "getting that wrong on a tactile switch made a set of them about 1.9 mm "
            "too tall, which is enough to hold every key permanently pressed.",
        )

    i2c = p.get("i2c") or {}
    addrs = [a.lower() for a in (i2c.get("addresses") or [])]
    default = (i2c.get("default") or "").lower()
    if addrs and default and default not in addrs:
        rep.error(
            "I2C_DEFAULT_NOT_IN_RANGE",
            f"{p.get('id')}: default address {i2c['default']} is not in the declared "
            f"address list {i2c['addresses']}.",
            fix="One of the two is wrong, and a design validated against this will "
            "believe whichever it reads first.",
        )
    if len(addrs) == 1 and not i2c.get("address_select"):
        rep.warn(
            "I2C_FIXED_ADDRESS_UNSTATED",
            f"{p.get('id')} answers at exactly one address and does not say whether "
            f"that is selectable.",
            fix="Say so explicitly. A fixed address cannot be moved, so two of the part "
            "on one bus is a redesign rather than a solder-jumper change.",
        )

    if p.get("failure_mode") == "silent" and not (p.get("liveness_check") or {}).get("how"):
        rep.error(
            "SILENT_WITHOUT_LIVENESS",
            f"{p.get('id')} is declared to fail silently and offers no liveness check.",
            fix="A part whose failure mode is silence needs something watching it. "
            "Record how, here, so every BOM that uses this part inherits the "
            "requirement instead of rediscovering it.",
        )

    axis_classes = {
        "transducer", "sensor_module", "microphone", "antenna", "magnet", "motor",
    }
    if p.get("class") in axis_classes and not p.get("orientation_constraint"):
        rep.warn(
            "ORIENTATION_UNRECORDED",
            f"{p.get('id')} is class {p.get('class')!r}, which usually has a functional "
            f"axis, and records no orientation constraint.",
            fix="If it has one, record it here so every project inherits it. Orientation "
            "is the most under-recorded electronics fact that drives geometry.",
        )

    if p.get("class") in ("expander", "amplifier", "haptic", "module") and (i2c or p.get("bus")):
        if (i2c.get("onboard_pullup_ohm") is None) and i2c:
            rep.warn(
                "ONBOARD_PULLUP_UNRECORDED",
                f"{p.get('id')} sits on an I2C bus and does not say whether it carries "
                f"its own pull-up resistors.",
                fix="Record it even if the answer is none. Stacked module pull-ups are "
                "counted by the bus check, and a part that silently adds 10k makes the "
                "count wrong for every design that uses it.",
            )


# --------------------------------------------------------------------------
# research hygiene
# --------------------------------------------------------------------------


def _group_is_substantive(gname: str, p: Dict[str, Any]) -> bool:
    """Does this group carry real claims, or only capability flags?

    A radio block saying ``{"wifi": true, "ble": true}`` states what the part can
    do, which nobody disputes. A radio block naming a band, a connector or an
    antenna type is a claim about a specific board, and vendor sources contradict
    each other about exactly those.
    """
    if gname != "radio":
        return True
    radio = p.get("radio") or {}
    substantive_keys = {"lora", "antenna", "antenna_2g4", "band_mhz", "connector", "zigbee"}
    for k, v in radio.items():
        if k in substantive_keys and isinstance(v, (dict, list)):
            return True
        if k in ("band_mhz", "connector", "antenna"):
            return True
    return False


def check_corroboration(p: Dict[str, Any], kind: str, rep: Report) -> Dict[str, Any]:
    groups_spec = BOARD_GROUPS if kind == "board" else PART_GROUPS
    corr = p.get("corroboration")
    status = p.get("status", "draft")

    if not corr:
        if status == "superseded":
            rep.info(
                "CORROBORATION_NOT_REQUIRED",
                "Superseded profiles are retained for their historical pin facts and "
                "are not corroborated. The paired linter already warns on any design "
                "that uses one.",
            )
            return {"present": False}
        rep.error(
            "CORROBORATION_MISSING",
            "No corroboration record, so there is no stated reason to believe anything "
            "in this profile.",
            fix="Add one. Run `new_profile.py --kind "
            + kind
            + "` to see the shape, or keep status at \"draft\" - but understand that a "
            "draft profile will be flagged by every design validated against it.",
        )
        return {"present": False}

    validate_schema(corr, "corroboration", rep)

    sources = {s["id"]: s for s in corr.get("sources", []) if s.get("id")}
    conservative = bool(corr.get("conservative"))

    if conservative and not corr.get("conservative_rationale"):
        rep.error(
            "CONSERVATIVE_UNJUSTIFIED",
            "conservative is true but no rationale is given.",
            fix="Say what this profile over-reserves and why over-reserving is the safe "
            "direction here. Conservatism lowers the corroboration bar, so it has to be "
            "argued rather than asserted.",
        )

    weak_only = [
        sid for sid, s in sources.items() if not is_independent_kind(s.get("kind"))
    ]
    if weak_only and len(weak_only) == len(sources):
        rep.warn(
            "SOURCE_WEAK_ONLY",
            f"Every source is of a kind that never counts toward corroboration: "
            f"{sorted({sources[s]['kind'] for s in weak_only})}.",
            fix="Find a datasheet, a schematic, a core variant header or an independent "
            "community firmware variant. Product pages and listings describe what "
            "someone wants you to buy, not what is on the board.",
        )

    # circular citation
    for sid, s in sources.items():
        parent = s.get("derives_from")
        if parent and parent not in sources:
            rep.error(
                "SOURCE_PARENT_UNKNOWN",
                f"Source {sid!r} derives_from {parent!r}, which is not in the sources "
                f"list.",
                fix="Add the upstream source, or drop the claim. An unresolvable "
                "derivation cannot be de-duplicated, so it inflates the independent "
                "count.",
                source=sid,
            )
        if parent == sid:
            rep.error(
                "SOURCE_SELF_DERIVED",
                f"Source {sid!r} derives from itself.",
                source=sid,
            )

    results: Dict[str, Any] = {"present": True, "conservative": conservative, "groups": {}}
    declared = corr.get("groups", {})

    for gname, spec in groups_spec.items():
        present = any(p.get(f) not in (None, {}, [], "") for f in spec["fields"])
        g = declared.get(gname)

        if not present:
            continue
        if not _group_is_substantive(gname, p):
            if g is None:
                rep.info(
                    "GROUP_NOT_SUBSTANTIVE",
                    f"{gname} carries only capability flags, not claims a source could "
                    f"contradict, so it is not required to be corroborated.",
                    group=gname,
                )
            continue

        need = spec["min_independent"]
        if conservative:
            need = 1

        if not g:
            (rep.error if status == "active" else rep.warn)(
                "GROUP_UNCORROBORATED",
                f"The profile carries {gname} data but declares no corroboration for it. "
                f"{spec['why']}",
                fix=f"Add corroboration.groups.{gname} naming the sources actually "
                f"consulted for those fields. Citing a datasheet for the pin map does "
                f"not corroborate the power section.",
                group=gname,
            )
            results["groups"][gname] = {"independent": 0, "required": need, "ok": False}
            continue

        used = [sources[s] for s in g.get("sources", []) if s in sources]
        missing = [s for s in g.get("sources", []) if s not in sources]
        if missing:
            rep.error(
                "GROUP_SOURCE_UNKNOWN",
                f"Group {gname!r} cites source id(s) {missing} that are not declared.",
                fix="Every group source must appear in the top-level sources list.",
                group=gname,
            )

        n = count_independent(used)
        ok = n >= need
        results["groups"][gname] = {
            "independent": n,
            "required": need,
            "agreement": g.get("agreement"),
            "ok": ok,
        }

        if not ok:
            severity = rep.error if status == "active" else rep.warn
            severity(
                "CORROBORATION_INSUFFICIENT"
                if status == "active"
                else "GROUP_UNCORROBORATED",
                f"{gname}: {n} independent source(s), {need} required"
                + (" (lowered because this profile is conservative)" if conservative else "")
                + f". {spec['why']}",
                fix="Find another genuinely independent source, or leave the profile at "
                "status \"draft\" so designs validated against it are warned. Note that "
                "two documents sharing an upstream count once: mark the derived one with "
                "derives_from.",
                group=gname,
                independent=n,
                required=need,
            )

        if g.get("agreement") == "conflicting" and not corr.get("contradictions"):
            rep.error(
                "CONFLICT_UNRECORDED",
                f"Group {gname!r} is marked conflicting but no contradiction is recorded.",
                fix="Write down BOTH readings and which sources gave them. Never average "
                "a disagreement into one confident number.",
                group=gname,
            )

    for c in corr.get("contradictions", []) or []:
        if c.get("resolution") == "unresolved":
            rep.warn(
                "CONTRADICTION_UNRESOLVED",
                f"{c['field']}: sources disagree "
                f"({[r.get('value') for r in c.get('readings', [])]}) and nobody has "
                f"settled it."
                + (f" Impact: {c['impact']}" if c.get("impact") else ""),
                fix=c.get("how_to_close")
                or "Measure it, or present the disagreement to the user rather than "
                "picking a side. An unresolved contradiction is honest; a silently "
                "chosen one is not.",
                field=c["field"],
            )
        elif c.get("resolution") == "chosen" and not c.get("resolved_by"):
            rep.error(
                "CONTRADICTION_CHOSEN_BLINDLY",
                f"{c['field']}: one reading was adopted with no stated reason.",
                fix="Say who chose and why. 'chosen' is weaker than 'measured' and must "
                "look weaker.",
                field=c["field"],
            )

    for q in corr.get("open_questions", []) or []:
        if q.get("blocks_active") and status == "active":
            rep.error(
                "OPEN_QUESTION_BLOCKS_ACTIVE",
                f"An open question marked as blocking is unanswered while the profile is "
                f"active: {q['question']}",
                fix="Answer it or move the profile back to draft.",
            )
        else:
            rep.info("OPEN_QUESTION", q["question"], impact=q.get("impact"))

    return results


def check_status(p: Dict[str, Any], corr_result: Dict[str, Any], rep: Report) -> None:
    status = p.get("status", "draft")

    if status == "superseded" and not p.get("superseded_by"):
        rep.error(
            "SUPERSEDED_WITHOUT_SUCCESSOR",
            "status is superseded but superseded_by is empty.",
            fix="Name the profile that replaces it. A superseded profile with no "
            "successor is just an abandoned one, and the next reader cannot tell which "
            "to use.",
        )

    if status == "active":
        bad = [g for g, r in (corr_result.get("groups") or {}).items() if not r["ok"]]
        if bad:
            rep.error(
                "ACTIVE_WITHOUT_CORROBORATION",
                f"status is active but these groups are under-corroborated: {bad}.",
                fix="Either corroborate them or set status to \"draft\". Active means a "
                "design may be validated against this file without a warning, and that "
                "is a promise about the data, not a stage of your workflow.",
                groups=bad,
            )
    elif status == "draft":
        rep.info(
            "PROFILE_IS_DRAFT",
            "This profile is a draft. Any design validated against it will be flagged, "
            "which is correct until its numbers have been corroborated.",
            fix="Corroborate the load-bearing groups and set status to \"active\".",
        )

    if not p.get("sources") and not p.get("corroboration"):
        rep.warn(
            "NO_SOURCES",
            "The profile cites nothing at all.",
            fix="Even a note saying 'general knowledge for this family' is better than "
            "silence, because it tells the next reader what to re-check.",
        )


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


def lint_one(path: str, kind: Optional[str], strict: bool) -> int:
    p = load_json(path, TOOL)

    if kind is None:
        schema = str(p.get("schema", ""))
        if "board" in schema:
            kind = "board"
        elif "part" in schema:
            kind = "part"
        else:
            die(
                TOOL,
                "KIND_UNKNOWN",
                f"Cannot tell whether {path} is a board or a part profile. Pass --kind.",
            )

    rep = Report(
        TOOL,
        source="static",
        profile=os.path.basename(path),
        kind=kind,
        id=p.get("id"),
        status=p.get("status", "draft"),
        family=p.get("family"),
    )

    validate_schema(p, kind, rep)

    if not p.get("display_name") and kind == "board":
        rep.warn(
            "NO_DISPLAY_NAME",
            "No display_name, so this board will be referred to only by its id.",
            fix="Add the name printed on the silkscreen or the shop listing, so a human "
            "can tell whether it is the thing in their hand.",
        )

    if kind == "board":
        check_board_consistency(p, rep)
        check_family_sanity(p, rep)
    else:
        check_part_consistency(p, rep)

    corr_result = check_corroboration(p, kind, rep)
    check_status(p, corr_result, rep)

    rep.set(corroboration=corr_result)
    rep.apply_acceptances(p.get("accepted_findings"), ACKNOWLEDGEABLE)
    return rep.emit(strict)


def lint_all(parent: str, strict: bool) -> int:
    rep = Report(TOOL, source="static", command="all", parent=parent)
    worst = 0
    summary: List[Dict[str, Any]] = []

    for kind, sub in (("board", "boards"), ("part", "parts")):
        d = os.path.join(parent, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json") or fn.startswith("_") or fn == "connectors.json":
                continue
            path = os.path.join(d, fn)
            p = load_json(path, TOOL)
            sub_rep = Report(TOOL, source="static")
            if kind == "board":
                check_board_consistency(p, sub_rep)
                check_family_sanity(p, sub_rep)
            else:
                check_part_consistency(p, sub_rep)
            corr = check_corroboration(p, kind, sub_rep)
            check_status(p, corr, sub_rep)
            sub_rep.apply_acceptances(p.get("accepted_findings"), ACKNOWLEDGEABLE)

            counts = sub_rep.counts(strict)
            worst = max(worst, sub_rep.exit_code(strict))
            summary.append(
                {
                    "profile": f"{sub}/{fn}",
                    "id": p.get("id"),
                    "status": p.get("status"),
                    "errors": counts["error"],
                    "warnings": counts["warning"],
                    "corroborated": all(
                        g["ok"] for g in (corr.get("groups") or {}).values()
                    )
                    if corr.get("groups")
                    else None,
                    "codes": sorted({f["code"] for f in sub_rep.findings if f["severity"] != "info"}),
                }
            )
            for f in sub_rep.findings:
                if f["severity"] in ("error", "refusal"):
                    rep.add({**f, "profile": f"{sub}/{fn}"})

    rep.set(profiles=summary, count=len(summary))
    bad = [s for s in summary if s["errors"]]
    if bad:
        rep.note(
            f"{len(bad)} of {len(summary)} installed profiles have errors. A design "
            "validated against one of them gets a confident answer built on it."
        )
    rep.emit(strict)
    return worst


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser(
        "profile_lint.py", "Validate a board or part profile for consistency and research hygiene."
    )
    p.add_argument("profile", nargs="?", help="Path to the profile JSON")
    p.add_argument("--kind", choices=["board", "part"], help="Inferred from the schema field when omitted")
    p.add_argument("--all", action="store_true", help="Lint every profile installed in the parent skill")
    p.add_argument("--parent", help="Path to the electronics-design skill")
    args = p.parse_args(argv)

    if args.all:
        parent = find_parent(args.parent)
        if not parent:
            die(
                TOOL,
                "PARENT_NOT_FOUND",
                "Could not locate the electronics-design skill. Pass --parent.",
                3,
            )
        return lint_all(parent, args.strict)

    if not args.profile:
        die(TOOL, "NO_INPUT", "Give a profile path, or --all with --parent.")

    return lint_one(args.profile, args.kind, args.strict)


if __name__ == "__main__":
    sys.exit(main())
