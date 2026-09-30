# Example: vendor sensor in a printed enclosure

A pill box whose lid is watched by an off-the-shelf Zigbee contact sensor. No
MCU, no firmware, no rails, no wiring, no bring-up.

**This is the shape most hobbyist projects actually are**, and it is the one a
skill built around a complicated project would quietly refuse to help with. The
entire electronics contribution here is three facts:

1. Which way round does the sensor go, and what does that cost the geometry.
2. What must the plastic not do to it.
3. What happens when it dies quietly.

## Run it

```powershell
$py = "..\..\.venv\Scripts\python.exe"
foreach ($p in 0,1,2,8,9) { & $py ..\..\hw.py check --phase $p --dir . }
```

All five exit 0. Phases 3–7 are explicitly skipped, each with a reason.

## Why this example exists

Writing it found a real bug. Phase 0 used to fail any project whose owner had no
multimeter — but this build has **nothing to meter**. No rails to balance, no
charge current to verify, no sleep current that is anyone's business but the
vendor's. Demanding an instrument here would have been the "every project is a
complicated project" failure, and it would have turned the skill away from the
most common case it has.

Phase 0 now checks whether any *metered* phase is still live:

```
NO_MULTIMETER_NOT_NEEDED
  every phase that needs one ([3, 6, 7]) is explicitly skipped,
  so no metered gate is in scope
```

Un-skip any of them and the requirement comes straight back. Calipers are still
required, because dimensions are still being printed around.

A second bug surfaced at phase 9: an audit over a manifest that declares *no*
open gates was being treated as an empty audit rather than a clean one. Those
are different things, and now they report differently.

## Orientation is the whole design

The reed switch sits against one of the sensor's 41 mm **long** faces, and the
manual says to align the marker lines on body and magnet. So the sensor has to
stand **on its edge** in the front wall — 41 mm across, 11 mm into the wall,
22 mm tall — with the marked face pointing straight up at the lid.

Laying it flat, which is the obvious thing to do and what anyone would print
first, puts the magnet off-axis.

That single fact drives the wall thickness, the boss geometry, the lid magnet
pocket, and about 13.8 mm of interior depth at the front. It is recorded as a
`locked` `orientation_constraint` with a `drives` list and a stated `cost`, so
the CAD side cannot rotate it to make a packing problem easier — and
`consume_manifest.py check` reports `ORIENTATION_VIOLATED` if a response tries.

## Three traps the manifest encodes

- **Ventilation.** The vendor manual explicitly warns against enclosing the
  sensor without it. A sealed boss is the obvious thing to print and it is the
  wrong thing to print.
- **Lift-out clearance.** The coin cell is in a screwless snap shell with no
  documented way to open it, so a battery change is *lift it out, swap it, drop
  it back in*. A design that traps the sensor has to be destroyed to change a
  CR1632.
- **The magnet is specified by release distance, not pull force.** A bigger
  magnet does not improve margin — it lengthens the release distance, so the box
  starts reporting "closed" while the lid is visibly ajar.

## Failure mode: silence

`bom_lint.py` refuses the BOM until a part marked `failure_mode: "silent"`
declares a `liveness_check`. This one has to, because its failure mode is
indistinguishable from the outcome it exists to report:

> A dead Zigbee sensor fails silently. Without a `last_seen` automation you would
> simply stop getting reminders and never find out why — and *not being nagged*
> looks exactly like *having taken your medication*.

## The open question this example makes concrete

The real constraint is **kinematic**, not static: the magnet-to-sensor gap
sweeps through the 22 mm release distance at roughly 19° of lid opening. That is
deliberate — a knock against the box should not register as "meds taken", but a
real open always should.

The manifest can *declare* this (`mate.dynamic: true`, `gap_release_mm`), and
`assembly_order` step 4 tells you to verify it by sweeping the hinge and watching
the coordinator log. But **nothing in this skill can evaluate a constraint
through a motion.** Checking the closed position and the fully-open position
tells you nothing about where the transition actually happens.

A boolean flag is not a solution to that; it is a note that the problem exists.
See the open questions in the skill README.

## Files

| File | Phase |
|---|---|
| `project.json` | 0 — five recorded skips, and no meter needed |
| `requirements.json` | 1 |
| `bom.json` | 2 — two rows, one of which can die silently |
| `component-manifest.json` | 8 — orientation, keep-outs, serviceability, assembly order |
| `measurements.jsonl` | 9 — everything measured, so the audit is clean rather than empty |

No `power.json`, no `pinmap.json`, no `netlist.json`. Not because they were
forgotten — because they do not exist for this build, and `project.json` says so.
