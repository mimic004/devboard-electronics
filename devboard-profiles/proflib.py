"""Shared plumbing for the devboard-profiles tools.

Same contract as the paired ``devboard-electronics`` skill: exactly one JSON
object on stdout, stable finding codes, ``--strict`` promotes warnings, and the
exit codes mean the same things.

    0  pass
    1  validation failure (read ``findings`` and fix)
    2  bad invocation / missing input / unparseable schema
    3  unreachable (a source or a board could not be consulted)
    4  refused - an honesty rule blocked the operation

Deliberately standalone. This skill must be runnable against a profile that is
not yet installed anywhere, including on a machine where the parent skill is
absent, so it does not import from it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Set

VERSION = "0.1.0"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_UNREACHABLE = 3
EXIT_REFUSED = 4

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.join(SKILL_ROOT, "schemas")
TEMPLATE_DIR = os.path.join(SKILL_ROOT, "templates")

# --------------------------------------------------------------------------
# source reliability
# --------------------------------------------------------------------------

#: Source kinds, weakest to strongest, and what each is worth.
#:
#: The ordering is about how hard it is for the source to be wrong without
#: anyone noticing. A marketplace listing is typed by someone selling you the
#: thing; a community firmware variant file was written by someone who had to
#: make the board actually work and would have heard about it if it did not.
SOURCE_KINDS: Dict[str, Dict[str, Any]] = {
    "listing": {
        "rank": 0,
        "independent": False,
        "label": "marketplace listing",
        "note": "A guess with a price attached. Never sufficient on its own.",
    },
    "product_page": {
        "rank": 1,
        "independent": False,
        "label": "vendor product page",
        "note": "Frequently boilerplate shared across a whole product range. "
        "Check whether the same text appears on a sibling product before counting it.",
    },
    "faq": {
        "rank": 1,
        "independent": False,
        "label": "vendor FAQ or wiki",
        "note": "Same boilerplate risk as a product page.",
    },
    "pinout_image": {
        "rank": 2,
        "independent": False,
        "label": "pinout diagram image",
        "note": "Useful for orientation, unreliable for detail. It never draws the "
        "pins consumed by flash and PSRAM.",
    },
    "datasheet": {
        "rank": 3,
        "independent": True,
        "label": "manufacturer datasheet",
        "note": "Authoritative about the part, not always about the board.",
    },
    "schematic": {
        "rank": 4,
        "independent": True,
        "label": "board schematic",
        "note": "Cite the revision. A schematic without a revision cannot be "
        "re-checked and may describe hardware you do not have.",
    },
    "board_definition": {
        "rank": 4,
        "independent": True,
        "label": "core board definition (boards.txt / board JSON)",
        "note": "Beats the datasheet for board-level facts: it is what the toolchain "
        "actually compiles against.",
    },
    "variant_header": {
        "rank": 4,
        "independent": True,
        "label": "core variant header (pins_arduino.h and similar)",
        "note": "Strong. Someone had to make the board work with these numbers.",
    },
    "community_firmware": {
        "rank": 4,
        "independent": True,
        "label": "independent community firmware variant",
        "note": "Strongest documentary source, because it is maintained by people "
        "who did not write the vendor's documents and would have complained.",
    },
    "measurement": {
        "rank": 5,
        "independent": True,
        "label": "measured on hardware",
        "note": "The only kind that settles a disagreement outright.",
    },
}

#: Field groups a board profile can be corroborated for. The thresholds differ
#: because the cost of being wrong differs.
BOARD_GROUPS: Dict[str, Dict[str, Any]] = {
    "gpio_map": {
        "min_independent": 3,
        "fields": ["gpio_valid", "consumed", "free", "conditional_free", "pin_notes"],
        "why": "A wrong pin map is the failure this whole pairing exists to prevent. "
        "It does not crash - it validates a design that cannot work.",
    },
    "strapping": {
        "min_independent": 2,
        "fields": ["strapping", "input_only"],
        "why": "An external pull on the wrong strapping pin can prevent boot "
        "permanently, and the symptom is a board that simply never starts.",
    },
    "adc": {
        "min_independent": 2,
        "fields": ["adc1", "adc2"],
        "why": "An ADC channel listed on the wrong bank silently returns timeouts "
        "once the radio is up.",
    },
    "rtc_wake": {
        "min_independent": 2,
        "fields": ["rtc_capable"],
        "why": "A wake source on a non-RTC pin produces a device that sleeps and "
        "never wakes, which looks like a flat battery.",
    },
    "power": {
        "min_independent": 2,
        "fields": ["power"],
        "why": "Charge current and rail ratings drive battery-safety decisions.",
    },
    "mechanical": {
        "min_independent": 1,
        "fields": ["mechanical", "display"],
        "why": "One measurement with calipers beats any number of documents, so a "
        "single measured source is enough here.",
    },
    "radio": {
        "min_independent": 1,
        "fields": ["radio"],
        "why": "Band and antenna facts, which are usually vendor-stated and often "
        "contradictory.",
    },
}

PART_GROUPS: Dict[str, Dict[str, Any]] = {
    "footprint": {
        "min_independent": 1,
        "fields": ["footprint"],
        "why": "A dimension being printed around. One caliper measurement outranks "
        "every document, and a seller-claimed figure outranks nothing.",
    },
    "electrical": {
        "min_independent": 1,
        "fields": ["electrical", "logic_v", "level_tolerant_5v"],
        "why": "Voltage limits and peak current drive rail and shifter decisions.",
    },
    "addressing": {
        "min_independent": 1,
        "fields": ["i2c"],
        "why": "A fixed I2C address cannot be moved, so a wrong one is a redesign.",
    },
}


def source_rank(kind: Optional[str]) -> int:
    return SOURCE_KINDS.get(kind or "", {}).get("rank", -1)


def is_independent_kind(kind: Optional[str]) -> bool:
    return bool(SOURCE_KINDS.get(kind or "", {}).get("independent"))


def count_independent(sources: List[Dict[str, Any]]) -> int:
    """Count sources that are genuinely independent of each other.

    Two documents that derive from the same upstream are ONE source however many
    times they are cited, so anything carrying ``derives_from`` is folded into
    its parent. A source of a non-independent kind never counts at all.
    """
    seen: Set[str] = set()
    for s in sources:
        if not is_independent_kind(s.get("kind")):
            continue
        root = s.get("derives_from") or s.get("id") or s.get("ref") or s.get("kind")
        seen.add(str(root))
    return len(seen)


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------

SEVERITIES = ("info", "warning", "error", "refusal")


def finding(code: str, severity: str, message: str, fix: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    if severity not in SEVERITIES:
        raise ValueError(f"bad severity {severity!r}")
    f: Dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if fix:
        f["fix"] = fix
    for k, v in extra.items():
        if v is not None:
            f[k] = v
    return f


class Report:
    def __init__(self, tool: str, source: str = "static", **fields: Any) -> None:
        self.tool = tool
        self.source = source
        self.fields: Dict[str, Any] = dict(fields)
        self.findings: List[Dict[str, Any]] = []
        self.notes: List[str] = []

    def add(self, f: Dict[str, Any]) -> None:
        self.findings.append(f)

    def error(self, code: str, message: str, fix: Optional[str] = None, **x: Any) -> None:
        self.add(finding(code, "error", message, fix, **x))

    def warn(self, code: str, message: str, fix: Optional[str] = None, **x: Any) -> None:
        self.add(finding(code, "warning", message, fix, **x))

    def info(self, code: str, message: str, fix: Optional[str] = None, **x: Any) -> None:
        self.add(finding(code, "info", message, fix, **x))

    def refuse(self, code: str, message: str, fix: Optional[str] = None, **x: Any) -> None:
        self.add(finding(code, "refusal", message, fix, **x))

    def note(self, text: str) -> None:
        self.notes.append(text)

    def set(self, **fields: Any) -> None:
        self.fields.update(fields)

    def counts(self, strict: bool = False) -> Dict[str, int]:
        c = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            sev = f["severity"]
            if strict and sev == "warning":
                sev = "error"
            c[sev] += 1
        return c

    def exit_code(self, strict: bool = False) -> int:
        c = self.counts(strict)
        if c["refusal"]:
            return EXIT_REFUSED
        if c["error"]:
            return EXIT_FAIL
        return EXIT_OK

    def to_dict(self, strict: bool = False) -> Dict[str, Any]:
        code = self.exit_code(strict)
        out: Dict[str, Any] = {
            "tool": self.tool,
            "version": VERSION,
            "ok": code == EXIT_OK,
            "source": self.source,
            "strict": bool(strict),
        }
        out.update(self.fields)
        out["findings"] = self.findings
        out["counts"] = self.counts(strict)
        if self.notes:
            out["notes"] = self.notes
        return out

    def emit(self, strict: bool = False) -> int:
        code = self.exit_code(strict)
        sys.stdout.write(json.dumps(self.to_dict(strict), indent=2) + "\n")
        return code

    def apply_acceptances(self, accepted: Optional[Dict[str, str]], allowed: frozenset) -> None:
        """Downgrade advisory findings a profile author accepted on purpose.

        Not a mute switch: only advisory codes qualify, the reason must be real,
        and an acceptance that never fired is itself reported.
        """
        if not accepted:
            return
        fired = {f["code"] for f in self.findings}
        for code, reason in accepted.items():
            if code not in allowed:
                self.error(
                    "ACCEPTANCE_NOT_PERMITTED",
                    f"{code!r} cannot be accepted. Only advisory codes may be: "
                    f"{', '.join(sorted(allowed))}.",
                    fix="Fix the underlying problem. A profile that is wrong is not a "
                    "preference.",
                    accepted_code=code,
                )
            elif not reason or len(str(reason).strip()) < 10:
                self.error(
                    "ACCEPTANCE_UNEXPLAINED",
                    f"{code!r} is accepted with no real reason.",
                    fix="Write down why. An unexplained acceptance is indistinguishable "
                    "from not having noticed.",
                    accepted_code=code,
                )
            elif code not in fired:
                self.warn(
                    "ACCEPTANCE_STALE",
                    f"{code!r} is declared accepted but did not fire.",
                    fix="Remove it. A stale acceptance swallows the finding on the day "
                    "the condition comes back.",
                    accepted_code=code,
                )
            else:
                for f in self.findings:
                    if f["code"] == code and f["severity"] == "warning":
                        f["severity"] = "info"
                        f["accepted"] = True
                        f["accepted_reason"] = reason


def die(tool: str, code: str, message: str, exit_code: int = EXIT_USAGE) -> "NoReturn":  # type: ignore[valid-type]
    payload = {
        "tool": tool,
        "version": VERSION,
        "ok": False,
        "source": "static",
        "findings": [finding(code, "error", message)],
        "counts": {"info": 0, "warning": 0, "error": 1, "refusal": 0},
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    sys.exit(exit_code)


# --------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------


def load_json(path: str, tool: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        die(tool, "INPUT_MISSING", f"No such file: {path}")
    except json.JSONDecodeError as exc:
        die(tool, "INPUT_UNPARSEABLE", f"{path} is not valid JSON: {exc}")
    except OSError as exc:
        die(tool, "INPUT_UNREADABLE", f"Cannot read {path}: {exc}")


def write_json(path: str, data: Any) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def validate_schema(data: Any, schema_name: str, report: Report) -> bool:
    path = os.path.join(SCHEMA_DIR, f"{schema_name}.schema.json")
    if not os.path.isfile(path):
        report.note(f"schema {schema_name} not found; skipped structural validation")
        return True
    try:
        import jsonschema  # type: ignore
    except ImportError:
        report.note(
            "jsonschema is not installed, so only semantic checks ran. A missing "
            "linter is a degraded run, not a clean one."
        )
        return True
    with open(path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    validator = jsonschema.Draft202012Validator(schema)
    errs = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    for e in errs:
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        report.error(
            "SCHEMA_INVALID",
            f"{loc}: {e.message}",
            fix=f"Fix the field to match schemas/{schema_name}.schema.json.",
            path=loc,
        )
    return not errs


# --------------------------------------------------------------------------
# locating the parent skill
# --------------------------------------------------------------------------

PARENT_NAME = "devboard-electronics"


def find_parent(explicit: Optional[str] = None) -> Optional[str]:
    """Locate an installed devboard-electronics skill, if there is one.

    This skill is useful without the parent - you can author and lint a profile
    anywhere - so a missing parent is never fatal, only limiting.
    """
    if explicit:
        return explicit if os.path.isdir(explicit) else None
    candidates = [
        os.path.join(os.path.dirname(SKILL_ROOT), PARENT_NAME),
        os.path.join(os.environ.get("APPDATA", ""), "com.github.githubapp", "app-skills", PARENT_NAME),
    ]
    for c in candidates:
        if c and os.path.isdir(c) and os.path.isfile(os.path.join(c, "SKILL.md")):
            return c
    return None


def parent_dir(parent: str, kind: str) -> str:
    return os.path.join(parent, "boards" if kind == "board" else "parts")


# --------------------------------------------------------------------------
# pin helpers
# --------------------------------------------------------------------------


def int_keys(d: Optional[Dict[str, Any]]) -> Set[int]:
    out: Set[int] = set()
    for k in (d or {}):
        try:
            out.add(int(k))
        except (TypeError, ValueError):
            continue
    return out


def compact(pins: Iterable[int]) -> str:
    """GPIO0-21 reads better than twenty-two numbers."""
    pins = sorted(set(pins))
    if not pins:
        return "none"
    runs = []
    start = prev = pins[0]
    for p in pins[1:]:
        if p == prev + 1:
            prev = p
            continue
        runs.append((start, prev))
        start = prev = p
    runs.append((start, prev))
    return ", ".join(f"{a}-{b}" if b > a else str(a) for a, b in runs)


def base_parser(prog: str, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=description)
    p.add_argument(
        "--strict",
        action="store_true",
        help="Promote warnings to errors. Intended default before installing a profile.",
    )
    return p
