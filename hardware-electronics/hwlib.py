"""Shared plumbing for every hardware-electronics tool.

Every tool in this skill obeys the same contract:

  * exactly ONE JSON object on stdout, nothing else
  * human-readable detail lives in ``findings`` and ``notes``, never in prose on stderr
  * ``--strict`` promotes warnings to errors
  * exit codes are stable and machine-branchable

    0  pass
    1  validation failure (read ``findings`` and fix)
    2  bad invocation / missing input / unparseable schema
    3  timeout or hardware not reachable
    4  refused - a safety rule or an honesty rule blocked the operation

Nothing here imports CadQuery, trimesh or any geometry kernel. This skill emits
constraints; the paired ``parametric-3d-printing`` skill builds solids.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

VERSION = "0.1.0"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_UNREACHABLE = 3
EXIT_REFUSED = 4

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.join(SKILL_ROOT, "schemas")
BOARD_DIR = os.path.join(SKILL_ROOT, "boards")
PARTS_DIR = os.path.join(SKILL_ROOT, "parts")

# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------

#: Ordered weakest-to-strongest. Index into this list is the only ordering that
#: matters; ``measured`` is the only rung that may be described as verified.
PROVENANCE_LADDER: List[str] = [
    "assumed",
    "inferred",
    "seller_claimed",
    "vendor_claim",
    "simulated",
    "datasheet",
    "schematic",
    "measured",
]

#: Provenance values that may never be reported to the user as "verified",
#: "tested", "confirmed" or "working".
UNVERIFIED_PROVENANCE = frozenset(PROVENANCE_LADDER) - {"measured"}

#: Provenance values so weak that printing plastic around them, or ordering ten
#: of them, requires an explicit measurement or an accepted-risk record first.
WEAK_PROVENANCE = frozenset({"assumed", "inferred", "seller_claimed", "vendor_claim"})


def provenance_rank(p: Optional[str]) -> int:
    """Rank a provenance tag. Unknown or missing tags rank below ``assumed``."""
    if p is None:
        return -1
    try:
        return PROVENANCE_LADDER.index(p)
    except ValueError:
        return -1


def is_verified(p: Optional[str]) -> bool:
    return p == "measured"


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------

SEVERITIES = ("info", "warning", "error", "refusal")


def finding(
    code: str,
    severity: str,
    message: str,
    fix: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build one finding.

    ``code`` is the stable identifier the agent branches on. ``message`` explains
    what is wrong; ``fix`` says what to do about it. Never put the fix inside the
    message - the agent is expected to read them separately.
    """
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
    """Accumulates findings and emits the single stdout JSON object."""

    def __init__(self, tool: str, source: str = "simulated", **fields: Any) -> None:
        if source not in ("hardware", "simulated", "recorded", "static"):
            raise ValueError(f"bad source {source!r}")
        self.tool = tool
        self.source = source
        self.fields: Dict[str, Any] = dict(fields)
        self.findings: List[Dict[str, Any]] = []
        self.notes: List[str] = []

    # -- mutation ---------------------------------------------------------
    def add(self, f: Dict[str, Any]) -> None:
        self.findings.append(f)

    def error(self, code: str, message: str, fix: Optional[str] = None, **extra: Any) -> None:
        self.add(finding(code, "error", message, fix, **extra))

    def warn(self, code: str, message: str, fix: Optional[str] = None, **extra: Any) -> None:
        self.add(finding(code, "warning", message, fix, **extra))

    def info(self, code: str, message: str, fix: Optional[str] = None, **extra: Any) -> None:
        self.add(finding(code, "info", message, fix, **extra))

    def refuse(self, code: str, message: str, fix: Optional[str] = None, **extra: Any) -> None:
        """A safety or honesty rule blocked the operation. Exit 4; the agent stops."""
        self.add(finding(code, "refusal", message, fix, **extra))

    def note(self, text: str) -> None:
        self.notes.append(text)

    def set(self, **fields: Any) -> None:
        self.fields.update(fields)

    # -- verdict ----------------------------------------------------------
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
        sys.stdout.write(json.dumps(self.to_dict(strict), indent=2, sort_keys=False))
        sys.stdout.write("\n")
        return code

    # -- deliberate acceptance --------------------------------------------
    def apply_acceptances(
        self,
        accepted: Optional[Dict[str, str]],
        allowed: frozenset,
    ) -> None:
        """Downgrade named advisory findings that the design has accepted on purpose.

        This is not a mute switch. Only codes on the ``allowed`` list may be
        accepted, every acceptance needs a written reason, and accepting a code
        that never fired is itself reported - a stale acceptance hides the day
        the condition comes back.

        Errors and refusals can never be accepted here. Widening a band to make
        a check pass is the electronics equivalent of wrapping a fillet in
        try/except to silently shrink the radius.
        """
        if not accepted:
            return
        fired = {f["code"] for f in self.findings}
        for code, reason in accepted.items():
            if code not in allowed:
                self.error(
                    "ACCEPTANCE_NOT_PERMITTED",
                    f"{code!r} is not an acceptable finding. Only advisory codes may be "
                    f"accepted: {', '.join(sorted(allowed))}.",
                    fix="Fix the underlying problem. An error is not a preference.",
                    accepted_code=code,
                )
                continue
            if not reason or len(str(reason).strip()) < 10:
                self.error(
                    "ACCEPTANCE_UNEXPLAINED",
                    f"{code!r} is accepted with no real reason given.",
                    fix="Write down why the cost is worth paying. An unexplained "
                    "acceptance is indistinguishable from not having noticed.",
                    accepted_code=code,
                )
                continue
            if code not in fired:
                self.warn(
                    "ACCEPTANCE_STALE",
                    f"{code!r} is declared as accepted but did not fire.",
                    fix="Remove the acceptance. A stale one will silently swallow the "
                    "finding on the day the condition comes back.",
                    accepted_code=code,
                )
                continue
            for f in self.findings:
                if f["code"] == code and f["severity"] == "warning":
                    f["severity"] = "info"
                    f["accepted"] = True
                    f["accepted_reason"] = reason


def die(tool: str, code: str, message: str, exit_code: int = EXIT_USAGE) -> "NoReturn":  # type: ignore[valid-type]
    """Emit a well-formed failure object and exit. Used for bad invocation."""
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
    """Load JSON or exit 2. Paths may contain spaces; callers must quote them."""
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
    os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=False)
        fh.write("\n")


def load_board(board_id: str, tool: str, search: Iterable[str] = ()) -> Dict[str, Any]:
    """Load a board profile.

    Project-local copies win over the vendored ones, because the vendoring rule
    says a project copies the profiles it uses so it stays runnable standalone -
    and a profile corrected by a bring-up measurement lives in the project.
    """
    candidates = [os.path.join(d, f"{board_id}.json") for d in list(search) + [BOARD_DIR]]
    for path in candidates:
        if os.path.isfile(path):
            return load_json(path, tool)
    known = sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(BOARD_DIR)
        if f.endswith(".json") and not f.startswith("_")
    )
    die(
        tool,
        "BOARD_UNKNOWN",
        f"No board profile {board_id!r}. Vendored profiles: {', '.join(known)}. "
        "A pin question must never be answered without a board ID - GPIO numbers "
        "mean different things on different boards.",
    )


def load_part(part_id: str, tool: str, search: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    for d in list(search) + [PARTS_DIR]:
        path = os.path.join(d, f"{part_id}.json")
        if os.path.isfile(path):
            return load_json(path, tool)
    return None


# --------------------------------------------------------------------------
# schema validation (optional dependency, degrades instead of exploding)
# --------------------------------------------------------------------------


def validate_schema(data: Any, schema_name: str, report: Report) -> bool:
    """Validate against ``schemas/<name>.schema.json``.

    If ``jsonschema`` is absent the tool still runs its semantic checks and says
    so in ``notes``. A missing linter is a degraded run, not a clean one.
    """
    path = os.path.join(SCHEMA_DIR, f"{schema_name}.schema.json")
    if not os.path.isfile(path):
        report.note(f"schema {schema_name} not found at {path}; skipped structural validation")
        return True
    try:
        import jsonschema  # type: ignore
    except ImportError:
        report.note(
            "jsonschema is not installed, so only semantic checks ran. "
            "Install requirements.txt for structural validation."
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
# canonical hashing
# --------------------------------------------------------------------------

#: Keys excluded from the content hash. Editing a comment must not force a
#: reprint; editing a dimension must.
HASH_EXCLUDED_KEYS = frozenset(
    {
        "reason",
        "reasons",
        "note",
        "notes",
        "why",
        "warning",
        "warnings",
        "explanation",
        "message",
        "description",
        "comment",
        "substitution_trap",
        "generated",
        "generator",
        "content_hash",
        "supplier_url",
        "supplier",
        "unit_cost_usd",
        "source",
        "sources",
        "how_to_close",
        "impact",
        "accepted_findings",
        "why_not_screws",
        "why_not_chamber",
        "dynamic_note",
        "action_required",
    }
)


def canonicalise(obj: Any) -> Any:
    """Strip prose and ordering noise so the hash tracks geometry, not wording."""
    if isinstance(obj, dict):
        return {
            k: canonicalise(v)
            for k, v in sorted(obj.items())
            if k not in HASH_EXCLUDED_KEYS
        }
    if isinstance(obj, list):
        return [canonicalise(v) for v in obj]
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    return obj


def content_hash(obj: Any) -> str:
    blob = json.dumps(canonicalise(obj), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def diff_canonical(old: Any, new: Any, prefix: str = "") -> List[Dict[str, Any]]:
    """Field-level diff of two canonicalised structures.

    Used by ``HASH_STALE`` to name exactly which numbers moved, so the agent can
    trace them to cad_parameters, to scripts, to STLs, to what must reprint.
    """
    changes: List[Dict[str, Any]] = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            p = f"{prefix}.{key}" if prefix else key
            if key not in old:
                changes.append({"path": p, "was": None, "now": new[key]})
            elif key not in new:
                changes.append({"path": p, "was": old[key], "now": None})
            else:
                changes.extend(diff_canonical(old[key], new[key], p))
    elif isinstance(old, list) and isinstance(new, list):
        for i in range(max(len(old), len(new))):
            p = f"{prefix}[{i}]"
            if i >= len(old):
                changes.append({"path": p, "was": None, "now": new[i]})
            elif i >= len(new):
                changes.append({"path": p, "was": old[i], "now": None})
            else:
                changes.extend(diff_canonical(old[i], new[i], p))
    elif old != new:
        changes.append({"path": prefix, "was": old, "now": new})
    return changes


# --------------------------------------------------------------------------
# 2D geometry - plan view with a Z-range filter
# --------------------------------------------------------------------------
#
# Deliberately 2D. Full 3D solid intersection would drag in a geometry kernel,
# which is the exact dependency this skill exists without. A plan-view check
# with a Z-range filter caught every real conflict the reference projects had.


def _shape_bbox(shape: Dict[str, Any], cx: float, cy: float) -> Optional[tuple]:
    kind = shape.get("shape")
    if kind in ("rect", "box"):
        l, w = shape.get("l"), shape.get("w")
        if l is None or w is None:
            return None
        return (cx - l / 2.0, cy - w / 2.0, cx + l / 2.0, cy + w / 2.0)
    if kind in ("circle", "cylinder"):
        d = shape.get("d")
        if d is None:
            return None
        r = d / 2.0
        return (cx - r, cy - r, cx + r, cy + r)
    if kind == "polygon":
        pts = shape.get("points") or []
        if not pts:
            return None
        xs = [cx + p[0] for p in pts]
        ys = [cy + p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def _poly_of(shape: Dict[str, Any], cx: float, cy: float, rot_deg: float = 0.0) -> List[tuple]:
    import math

    kind = shape.get("shape")
    if kind in ("rect", "box"):
        l, w = float(shape["l"]), float(shape["w"])
        pts = [(-l / 2, -w / 2), (l / 2, -w / 2), (l / 2, w / 2), (-l / 2, w / 2)]
    elif kind == "polygon":
        pts = [(float(p[0]), float(p[1])) for p in shape["points"]]
    elif kind in ("circle", "cylinder"):
        r = float(shape["d"]) / 2.0
        n = 48
        pts = [
            (r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n))
            for i in range(n)
        ]
    else:
        return []
    a = math.radians(rot_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


def _sat_overlap(p1: List[tuple], p2: List[tuple]) -> bool:
    """Separating-axis test on two convex-ish polygons."""
    import math

    for poly in (p1, p2):
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            ax, ay = -(y2 - y1), (x2 - x1)
            norm = math.hypot(ax, ay)
            if norm == 0:
                continue
            ax, ay = ax / norm, ay / norm
            a_lo = min(ax * x + ay * y for x, y in p1)
            a_hi = max(ax * x + ay * y for x, y in p1)
            b_lo = min(ax * x + ay * y for x, y in p2)
            b_hi = max(ax * x + ay * y for x, y in p2)
            if a_hi <= b_lo + 1e-9 or b_hi <= a_lo + 1e-9:
                return False
    return True


def shapes_overlap(
    s1: Dict[str, Any],
    c1: Dict[str, Any],
    s2: Dict[str, Any],
    c2: Dict[str, Any],
) -> bool:
    """Do two placed shapes overlap in plan view?

    ``c1``/``c2`` are placements: ``{"x":.., "y":.., "z":.., "rotation_z":..}``.

    Round parts are treated as ROUND. Describing a 35 mm circle by its bounding
    box reserves 21% more area than it occupies, all of it in the corners -
    which is exactly where a round part usually has to live.
    """
    import math

    x1, y1 = float(c1.get("x", 0.0)), float(c1.get("y", 0.0))
    x2, y2 = float(c2.get("x", 0.0)), float(c2.get("y", 0.0))
    r1, r2 = float(c1.get("rotation_z", 0.0)), float(c2.get("rotation_z", 0.0))

    k1, k2 = s1.get("shape"), s2.get("shape")
    round1 = k1 in ("circle", "cylinder")
    round2 = k2 in ("circle", "cylinder")

    # circle/circle is exact and cheap
    if round1 and round2:
        return math.hypot(x2 - x1, y2 - y1) < (float(s1["d"]) + float(s2["d"])) / 2.0 - 1e-9

    # cheap reject on bounding boxes first
    b1 = _shape_bbox(s1, x1, y1)
    b2 = _shape_bbox(s2, x2, y2)
    if b1 and b2:
        if b1[2] <= b2[0] + 1e-9 or b2[2] <= b1[0] + 1e-9:
            return False
        if b1[3] <= b2[1] + 1e-9 or b2[3] <= b1[1] + 1e-9:
            return False

    p1 = _poly_of(s1, x1, y1, r1)
    p2 = _poly_of(s2, x2, y2, r2)
    if not p1 or not p2:
        return False
    return _sat_overlap(p1, p2)


def z_ranges_overlap(s1: Dict[str, Any], c1: Dict[str, Any], s2: Dict[str, Any], c2: Dict[str, Any]) -> bool:
    """Two things at the same X/Y but different heights do not collide."""
    h1, h2 = s1.get("h"), s2.get("h")
    if h1 is None or h2 is None:
        return True  # unknown height -> assume they share the space
    z1 = float(c1.get("z", 0.0))
    z2 = float(c2.get("z", 0.0))
    return not (z1 + float(h1) <= z2 + 1e-9 or z2 + float(h2) <= z1 + 1e-9)


def shape_within(shape: Dict[str, Any], place: Dict[str, Any], envelope: Dict[str, Any]) -> bool:
    """Is a placed shape inside an L x W interior, origin at the centre?"""
    l, w = envelope.get("l"), envelope.get("w")
    if l is None or w is None:
        return True
    bbox = _shape_bbox(shape, float(place.get("x", 0.0)), float(place.get("y", 0.0)))
    if bbox is None:
        return True
    rot = float(place.get("rotation_z", 0.0))
    if rot % 180.0 != 0.0:
        pts = _poly_of(shape, float(place.get("x", 0.0)), float(place.get("y", 0.0)), rot)
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bbox = (min(xs), min(ys), max(xs), max(ys))
    return (
        bbox[0] >= -l / 2.0 - 1e-6
        and bbox[2] <= l / 2.0 + 1e-6
        and bbox[1] >= -w / 2.0 - 1e-6
        and bbox[3] <= w / 2.0 + 1e-6
    )


# --------------------------------------------------------------------------
# argparse helper
# --------------------------------------------------------------------------


def base_parser(prog: str, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=description)
    p.add_argument(
        "--strict",
        action="store_true",
        help="Promote warnings to errors. This is the intended default for a gate.",
    )
    return p
