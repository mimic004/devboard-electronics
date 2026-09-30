#!/usr/bin/env python3
"""power_budget.py - per-rail draw, duty cycle, runtime and charge sanity.

Output is ALWAYS ``"source": "simulated"``. Nothing in this file touches
hardware, and nothing it produces may be described as measured.

Two things this tool does that a spreadsheet does not:

  * it reports MARGIN, not a bare number, so a vendor-claim-dominated estimate is
    safe to act on rather than quietly authoritative;
  * it names which fraction of the average rests on which provenance, so you can
    see when 98% of a 35-day runtime estimate comes from a figure nobody has
    measured - and when two vendor documents disagree, it reports a RANGE.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwlib import (  # noqa: E402
    Report,
    base_parser,
    load_json,
    validate_schema,
)

TOOL = "power_budget"

#: Advisory findings a design may accept with a written reason. SLEEP_UNMEASURED
#: and AVERAGE_UNMEASURED are deliberately NOT here: the whole point of this tool
#: is that you cannot make an unmeasured runtime estimate look measured. You can
#: proceed on one - you just cannot silence the caveat.
ACKNOWLEDGEABLE = frozenset(
    {
        "RAIL_PEAK_COINCIDENT",
        "CHARGE_RATE_HIGH",
        "CHARGE_UNMEASURED",
        "RUNTIME_MARGIN_THIN",
        "NO_VENT",
    }
)


TRANSIENT_THRESHOLD_MA = 100.0
CHARGE_C_ERROR = 1.0
CHARGE_C_WARN = 0.7
DEFAULT_USABLE_FRACTION = 0.85


def _loads_by_rail(power: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for load in power.get("loads", []) or []:
        out.setdefault(load["rail"], []).append(load)
    return out


def check_rails(power: Dict[str, Any], rep: Report) -> List[Dict[str, Any]]:
    by_rail = _loads_by_rail(power)
    known = {r["id"] for r in power.get("rails", [])}
    summary: List[Dict[str, Any]] = []

    for rail_id in sorted(by_rail):
        if rail_id not in known:
            rep.error(
                "RAIL_UNKNOWN",
                f"Loads are assigned to rail {rail_id!r}, which is not declared in rails[].",
                fix="Declare the rail with its regulator and current rating, or fix the "
                "load's rail name.",
                rail=rail_id,
            )

    for rail in power.get("rails", []):
        loads = by_rail.get(rail["id"], [])
        sum_avg = sum(float(l.get("i_avg_ma", 0)) for l in loads)
        sum_peak = sum(float(l.get("i_peak_ma", l.get("i_avg_ma", 0))) for l in loads)
        rating = float(rail["rating_ma"])
        entry = {
            "id": rail["id"],
            "source": rail.get("source"),
            "rating_ma": rating,
            "sum_avg_ma": round(sum_avg, 3),
            "sum_peak_ma": round(sum_peak, 3),
            "headroom_avg_ma": round(rating - sum_avg, 3),
            "headroom_peak_ma": round(rating - sum_peak, 3),
            "loads": [l["id"] for l in loads],
        }
        summary.append(entry)

        if sum_avg > rating:
            rep.error(
                "RAIL_OVERDRAWN",
                f"Rail {rail['id']} ({rail.get('source', 'regulator')}) is rated "
                f"{rating:.0f} mA and its loads average {sum_avg:.1f} mA.",
                fix="Move a load to another rail, fit a bigger regulator, or reduce the "
                "duty cycle.",
                rail=rail["id"],
            )
        for load in loads:
            peak = float(load.get("i_peak_ma", load.get("i_avg_ma", 0)))
            if peak > rating:
                rep.error(
                    "RAIL_OVERDRAWN",
                    f"{load['id']} peaks at {peak:.0f} mA on rail {rail['id']}, which "
                    f"is rated {rating:.0f} mA ({rail.get('source', 'regulator')}).",
                    fix="Feed this load from the battery directly, with its own bulk "
                    "capacitance, and gate its rail with a load switch. A class-D "
                    "amplifier is the classic case: the average is harmless and the "
                    "peak browns out the whole board.",
                    rail=rail["id"],
                    load=load["id"],
                    peak_ma=peak,
                )
            elif sum_peak > rating:
                pass

        if sum_peak > rating and all(
            float(l.get("i_peak_ma", 0)) <= rating for l in loads
        ):
            rep.warn(
                "RAIL_PEAK_COINCIDENT",
                f"No single load exceeds rail {rail['id']}, but their peaks sum to "
                f"{sum_peak:.0f} mA against a {rating:.0f} mA rating.",
                fix="Either prove they cannot peak together and set "
                "simultaneous_peak false, or size for the sum.",
                rail=rail["id"],
            )

    for load in power.get("loads", []) or []:
        avg = float(load.get("i_avg_ma", 0))
        peak = float(load.get("i_peak_ma", avg))
        if peak - avg >= TRANSIENT_THRESHOLD_MA and not load.get("bulk_uf"):
            rep.error(
                "TRANSIENT_NO_BULK",
                f"{load['id']} swings {peak - avg:.0f} mA between average and peak and "
                f"declares no bulk capacitance.",
                fix="Add local bulk capacitance AT THE PART, not at the connector, and "
                "record it as bulk_uf. A 100 nF decoupling cap at every IC power pin "
                "plus one bulk electrolytic per rail is the baseline; a motor or a "
                "class-D amp needs its own on top of that.",
                load=load["id"],
                transient_ma=round(peak - avg, 1),
            )
        if load.get("inductive") and not load.get("flyback_diode"):
            rep.error(
                "INDUCTIVE_NO_FLYBACK",
                f"{load['id']} is an inductive load with no flyback diode declared.",
                fix="Every inductive load gets a flyback diode. Without one the "
                "switch-off spike goes somewhere, and where it goes is your MCU.",
                load=load["id"],
            )

    return summary


def compute_states(power: Dict[str, Any], rep: Report) -> Dict[str, Any]:
    loads = {l["id"]: l for l in power.get("loads", []) or []}
    states = power.get("states", []) or []

    duty_sum = sum(float(s.get("duty", 0)) for s in states)
    if abs(duty_sum - 1.0) > 0.001:
        rep.error(
            "DUTY_SUM",
            f"State duty cycles sum to {duty_sum:.4f}, not 1.0.",
            fix="The states must partition all of the time. Add an idle state, or fix "
            "the fractions.",
            duty_sum=round(duty_sum, 6),
        )

    rows: List[Dict[str, Any]] = []
    total = 0.0
    total_lo = 0.0
    total_hi = 0.0
    has_conflict = False

    for s in states:
        duty = float(s.get("duty", 0))
        if s.get("ma") is not None:
            ma = float(s["ma"])
        elif s.get("loads_active"):
            missing = [i for i in s["loads_active"] if i not in loads]
            if missing:
                rep.error(
                    "STATE_LOAD_UNKNOWN",
                    f"State {s['id']} activates unknown loads {missing}.",
                    fix="Declare them in loads[], or fix the ids.",
                    state=s["id"],
                )
            ma = sum(float(loads[i].get("i_avg_ma", 0)) for i in s["loads_active"] if i in loads)
        else:
            rep.error(
                "STATE_CURRENT_UNKNOWN",
                f"State {s['id']} declares neither ma nor loads_active.",
                fix="Give the state a current, or list which loads are on during it.",
                state=s["id"],
            )
            ma = 0.0

        conflict = s.get("conflict")
        lo = hi = ma
        if conflict and conflict.get("values"):
            has_conflict = True
            lo, hi = min(conflict["values"]), max(conflict["values"])

        contrib = duty * ma
        total += contrib
        total_lo += duty * lo
        total_hi += duty * hi

        rows.append(
            {
                "id": s["id"],
                "duty": duty,
                "ma": ma,
                "provenance": s.get("provenance", "assumed"),
                "contrib_ma": round(contrib, 6),
                "conflict": conflict,
            }
        )

    for r in rows:
        r["share_of_average"] = round(r["contrib_ma"] / total, 4) if total else 0.0

    return {
        "rows": rows,
        "average_ma": total,
        "average_ma_range": [total_lo, total_hi] if has_conflict else None,
        "has_conflict": has_conflict,
    }


def check_provenance(states: Dict[str, Any], rep: Report) -> Dict[str, Any]:
    """Say which fraction of the average rests on which kind of number.

    The point is not to shame the estimate. It is to make the sentence "runtime
    is 35 days" carry its own caveat mechanically, so nobody has to remember to
    add it.
    """
    rows = states["rows"]
    total = states["average_ma"]
    by_prov: Dict[str, float] = {}
    for r in rows:
        by_prov[r["provenance"]] = by_prov.get(r["provenance"], 0.0) + r["contrib_ma"]
    shares = {
        p: round(v / total, 4) if total else 0.0 for p, v in sorted(by_prov.items())
    }
    unmeasured = round(1.0 - shares.get("measured", 0.0), 4)

    if not rows or not total:
        return {"provenance_shares": shares, "unmeasured_share": unmeasured}

    if unmeasured >= 0.5:
        rep.warn(
            "AVERAGE_UNMEASURED",
            f"{unmeasured * 100:.1f}% of the average current comes from numbers nobody "
            f"has measured on this hardware: {shares}.",
            fix="This is a calculation, not a result. Say so in any summary, quote the "
            "margin alongside it, and measure the biggest contributor first.",
            shares=shares,
        )

    sleepish = min(rows, key=lambda r: r["ma"])
    if sleepish["provenance"] != "measured":
        rep.warn(
            "SLEEP_UNMEASURED",
            f"The lowest-current state {sleepish['id']!r} ({sleepish['ma']} mA) is "
            f"{sleepish['provenance']}, not measured, and contributes "
            f"{sleepish['share_of_average'] * 100:.1f}% of the average."
            + (
                f" Sources also disagree: "
                f"{sleepish['conflict'].get('note') or sleepish['conflict']['values']}."
                if sleepish.get("conflict")
                else ""
            ),
            fix="Meter it in series with the battery positive lead, on the uA range, "
            "with USB DISCONNECTED. Sleep current sets the long tail of every "
            "battery-life figure, and it is the number vendors are least careful about.",
            state=sleepish["id"],
            share=sleepish["share_of_average"],
            provenance=sleepish["provenance"],
        )

    dominant = max(rows, key=lambda r: r["contrib_ma"])
    if dominant["provenance"] != "measured" and dominant["id"] != sleepish["id"]:
        rep.info(
            "DOMINANT_STATE_UNMEASURED",
            f"State {dominant['id']!r} contributes "
            f"{dominant['share_of_average'] * 100:.1f}% of the average on a "
            f"{dominant['provenance']} figure.",
            fix="Measure this one second.",
            state=dominant["id"],
        )

    return {"provenance_shares": shares, "unmeasured_share": unmeasured}


def check_charge(power: Dict[str, Any], rep: Report) -> Dict[str, Any]:
    charge = power.get("charge") or {}
    batt = power.get("battery") or {}
    out: Dict[str, Any] = dict(charge)

    if not charge.get("ma"):
        return out

    ma = float(charge["ma"])
    chem = batt.get("chemistry")

    if chem in ("lipo", "liion", "lifepo4") and batt.get("protection") is False:
        if not batt.get("external_protection_ic"):
            rep.refuse(
                "CELL_UNPROTECTED",
                f"This design charges an unprotected {chem} cell and no external "
                f"protection IC is in the BOM.",
                fix="Use a protected cell, or add a protection IC and name it in "
                "battery.external_protection_ic. Charging an unprotected lithium cell "
                "is unsafe by construction, and this tool will not help design around "
                "it.",
            )

    if chem == "lifepo4" and charge.get("ic") and "4056" in str(charge["ic"]):
        rep.refuse(
            "CHEMISTRY_CHARGER_MISMATCH",
            f"A TP4056-class charger ({charge['ic']}) has a 4.2 V Li-ion termination "
            f"profile and must not be used on a LiFePO4 cell, which terminates around "
            f"3.6 V.",
            fix="Use a LiFePO4-specific charge IC.",
        )

    cap = batt.get("capacity_mah")
    if cap:
        c_rate = ma / float(cap)
        out["c_rate"] = round(c_rate, 3)
        if c_rate > CHARGE_C_ERROR:
            rep.error(
                "CHARGE_RATE_HIGH",
                f"Charging a {cap} mAh cell at {ma:.0f} mA is {c_rate:.2f} C, above the "
                f"{CHARGE_C_ERROR:.1f} C limit for ordinary pouch cells.",
                fix="Fit a larger cell, or reduce the charge current. If the current is "
                "set by a PROG resistor it is fixed in hardware and firmware cannot "
                "help - the cell has to move.",
                c_rate=round(c_rate, 3),
            )
        elif c_rate > CHARGE_C_WARN:
            rep.warn(
                "CHARGE_RATE_HIGH",
                f"{c_rate:.2f} C charge rate ({ma:.0f} mA into {cap} mAh) is above a "
                f"comfortable {CHARGE_C_WARN:.1f} C.",
                fix="Acceptable for many cells, but check the cell's own datasheet "
                "rather than assuming.",
                c_rate=round(c_rate, 3),
            )

    if charge.get("fixed_in_hardware"):
        min_cell = charge.get("min_cell_mah") or ma / CHARGE_C_ERROR
        out["min_cell_mah"] = min_cell
        rep.info(
            "CHARGE_FIXED_IN_HW",
            f"The charge current is fixed in hardware at {ma:.0f} mA"
            + (f" ({charge.get('source')})" if charge.get("source") else "")
            + f", so the MINIMUM CELL CAPACITY is a BOM constraint: do not fit a cell "
            f"smaller than about {min_cell:.0f} mAh.",
            fix="Carry min_cell_mah into the BOM. bom_lint.py --power will then reject "
            "an undersized cell automatically.",
            min_cell_mah=min_cell,
        )

    if charge.get("provenance") and charge["provenance"] != "measured":
        rep.warn(
            "CHARGE_UNMEASURED",
            f"The charge current is {charge['provenance']}, not measured, and it drives "
            f"a battery-safety decision.",
            fix="Meter the PROG resistor on the physical board and confirm the charge "
            "constant against the charge IC's own datasheet. Schematic is not silicon.",
        )

    return out


def compute_runtime(power: Dict[str, Any], states: Dict[str, Any], rep: Report) -> Dict[str, Any]:
    batt = power.get("battery") or {}
    cap = batt.get("capacity_mah")
    avg = states["average_ma"]
    out: Dict[str, Any] = {}

    if not cap or not avg:
        return out

    usable_frac = float(batt.get("usable_fraction", DEFAULT_USABLE_FRACTION))
    usable = float(cap) * usable_frac
    out.update(
        capacity_mah=float(cap),
        usable_fraction=usable_frac,
        usable_mah=round(usable, 1),
        runtime_h=round(usable / avg, 1),
        runtime_days=round(usable / avg / 24.0, 2),
    )

    if states["average_ma_range"]:
        lo, hi = states["average_ma_range"]
        out["runtime_days_range"] = [
            round(usable / hi / 24.0, 2) if hi else None,
            round(usable / lo / 24.0, 2) if lo else None,
        ]
        rep.info(
            "RUNTIME_IS_A_RANGE",
            f"Sources disagree on the dominant current, so the runtime is a RANGE of "
            f"{out['runtime_days_range'][0]}-{out['runtime_days_range'][1]} days, not a "
            f"point estimate of {out['runtime_days']} days.",
            fix="Quote the range. Collapsing it to one number invents precision that "
            "does not exist.",
        )

    target = (power.get("requirements") or {}).get("runtime_target_days")
    if target:
        margin = out["runtime_days"] / float(target)
        out["target_days"] = float(target)
        out["margin_x"] = round(margin, 2)
        min_margin = float((power.get("requirements") or {}).get("min_margin_x", 1.5))
        if out["runtime_days"] < float(target):
            rep.error(
                "RUNTIME_BELOW_TARGET",
                f"Calculated runtime {out['runtime_days']} days is below the "
                f"{target} day target.",
                fix="Reduce the duty cycle, gate a rail with a load switch, cut the "
                "sleep current, or fit a larger cell. Each of those is a concrete edit "
                "to power.json.",
                runtime_days=out["runtime_days"],
                target_days=target,
            )
        elif margin < min_margin:
            rep.warn(
                "RUNTIME_MARGIN_THIN",
                f"Runtime beats the target by only {margin:.2f}x, below the "
                f"{min_margin:.1f}x margin this project asked for - and the estimate "
                f"rests on unmeasured figures.",
                fix="Either measure the dominant current, or build in more headroom.",
                margin_x=round(margin, 2),
            )
        else:
            rep.info(
                "RUNTIME_MARGIN_OK",
                f"Calculated runtime {out['runtime_days']} days against a {target} day "
                f"target: {margin:.1f}x headroom. Report the margin, not just the "
                f"number - a bare figure hides how much of it is slack.",
                margin_x=round(margin, 2),
            )

    max_dis = batt.get("max_discharge_ma")
    if max_dis:
        peak_sum = sum(
            float(l.get("i_peak_ma", l.get("i_avg_ma", 0)))
            for l in power.get("loads", []) or []
            if l.get("simultaneous_peak", True)
        )
        out["simultaneous_peak_ma"] = round(peak_sum, 1)
        if peak_sum > float(max_dis):
            rep.error(
                "BROWNOUT_RISK",
                f"Simultaneous peak draw {peak_sum:.0f} mA exceeds the cell's "
                f"{max_dis} mA maximum discharge current.",
                fix="Stagger the peaks, add bulk capacitance to ride through them, or "
                "fit a cell with a higher discharge rating. A cell sagging below the "
                "brownout threshold resets the MCU mid-operation.",
                peak_ma=round(peak_sum, 1),
                max_discharge_ma=max_dis,
            )

    if batt.get("chemistry") in ("lipo", "liion") and batt.get("enclosure_sealed"):
        if not batt.get("vented"):
            rep.warn(
                "NO_VENT",
                "A lithium pouch cell is declared inside a sealed enclosure with no vent.",
                fix="Add a vent path. A cell that swells inside a sealed box has nowhere "
                "to go, and a cell pressed against sharp pin stubs or screw bosses is a "
                "puncture risk. If the enclosure must stay sealed, say so explicitly "
                "and design the cell restraint accordingly.",
            )

    return out


def main(argv: Optional[List[str]] = None) -> int:
    p: argparse.ArgumentParser = base_parser(
        "power_budget.py", "Rail balance, charge sanity, duty cycle and runtime."
    )
    p.add_argument("power", help="Path to power.json")
    args = p.parse_args(argv)

    power = load_json(args.power, TOOL)
    rep = Report(TOOL, source="simulated", project=power.get("project"))
    validate_schema(power, "power", rep)

    rails = check_rails(power, rep)
    states = compute_states(power, rep)
    prov = check_provenance(states, rep)
    charge = check_charge(power, rep)
    runtime = compute_runtime(power, states, rep)

    rep.set(
        rails=rails,
        states=[{k: v for k, v in r.items() if v is not None} for r in states["rows"]],
        average_ma=round(states["average_ma"], 4),
        average_ma_range=states["average_ma_range"],
        charge=charge,
        **prov,
        **runtime,
    )
    rep.apply_acceptances(power.get("accepted_findings"), ACKNOWLEDGEABLE)
    rep.note(
        "Every number in this report is CALCULATED, not measured. Report it as an "
        "estimate, quote the margin alongside it, and say which state dominates the "
        "average and what its provenance is."
    )
    return rep.emit(args.strict)


if __name__ == "__main__":
    sys.exit(main())
