# hardware-electronics

A skill for hobbyist electronics built from modules and dev boards: pin maps,
power budgets, bills of materials, bring-up, and a hash-locked handoff to
**[flowful-ai/cad-skill](https://github.com/flowful-ai/cad-skill)**.

That skill builds the plastic. This one builds the electronics that has to fit
inside it, and owns the contract between the two. Its peer,
[`hardware-profiles`](../hardware-profiles/), owns the board and component data
this skill validates designs against.

## The problem it solves

Software fails loudly. Electronics does not. A wrong number does not crash — it
gets ordered, soldered, printed around, and discovered three weeks later.

So the core artefact is not a wiring diagram. It is a **provenance ledger of
every number**, plus validators that refuse to proceed while a number that will
be cut into plastic or soldered to a cell is still somebody's guess.

Only a number read off an instrument, on your hardware, on a stated date, may be
called verified. Everything else is a calculation, a claim, or a guess with a
price attached — and the tools will keep saying so until you measure it.

## Install

```powershell
cd "$env:APPDATA\com.github.githubapp\app-skills\hardware-electronics"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe hw.py doctor
```

Python 3.12, not 3.13+ — this skill needs no OpenCASCADE, but it must not create
a venv the paired CAD skill cannot use.

## What ships here

All nine phases, M0–M9 of the design plan, plus the CAD-side bridge.

| Tool | What it does |
|---|---|
| `hw.py` | Phase gate runner and dispatcher |
| `measure_log.py` | The provenance ledger: record, audit, report, fit sweeps |
| `pinmap_lint.py` | Pin, bus, address, strapping, ADC and wake-source conflicts |
| `bom_lint.py` | Connector mating, variants locked at order, seller-claimed dimensions, silent-failure parts |
| `power_budget.py` | Rail balance, charge sanity, duty cycles, honest runtimes |
| `wiring_render.py` | Netlist → connection table + graph; dangling nets, decoupling, ground, wire gauge |
| `board_cli.py` | detect / identify / build / flash / monitor / backup / record, as JSON |
| `probe_client.py` | Drives the probe sketch and judges the answer against plausibility bands |
| `handoff_lint.py` | The CAD contract: keep-outs, containment, orientation, hash lock |
| `serial_io.py` | Port enumeration, no-reset open, recorded transports |
| `hwlib.py` | Shared plumbing: findings, exit codes, canonical hashing, 2D geometry |
| `cad_bridge/consume_manifest.py` | Manifest → CAD parameters; scaffolds and pre-flights the reply |
| `cad_bridge/run_cad_model.py` | Runs CadQuery without trusting its exit code |
| `firmware/probe/probe.ino` | Vendored line-protocol probe sketch (9% flash, 7% RAM) |

Data, not prose: `boards/*.json`, `parts/*.json`, `schemas/*.json`.
Prose, loaded on demand: `reference/*.md`.

## Quick start

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py hw.py phases
& $py hw.py check --phase 0 --dir examples\esp32s3-lipo-sensor
& $py pinmap_lint.py examples\pager-style-handheld\pinmap.json --strict
& $py measure_log.py --ledger examples\pager-style-handheld\measurements.jsonl report

# no hardware needed - replay the 29 ms e-paper failure
& $py probe_client.py examples\pager-style-handheld\probes\epaper-panel.json `
      --transcript tests\fixtures\transcript_panel_29ms.json
```

## Tool contract

One JSON object on stdout. Detail in `findings` and `notes`, never prose on
stderr. Every finding carries a stable `code`; branch on the code, not the
wording. `--strict` promotes warnings to errors.

| Exit | Meaning |
|---|---|
| 0 | pass |
| 1 | validation failure |
| 2 | bad invocation or unparseable input |
| 3 | timeout or hardware unreachable |
| 4 | refused — a safety or honesty rule blocked it |

## Examples

Three deliberately different shapes, because a skill that only serves the
complicated case refuses the common one.

- **`examples/esp32s3-lipo-sensor/`** — a complete battery-powered sensor that
  passes every design-phase gate, including a power budget where every figure
  was measured. Two phases explicitly skipped, with reasons.
- **`examples/vendor-sensor-enclosure/`** — a vendor Zigbee sensor in a printed
  pill box. No MCU, no firmware, no rails, no wiring; five recorded skips. The
  entire electronics contribution is orientation, keep-outs and a liveness
  check. Writing it found two real bugs.
- **`examples/pager-style-handheld/`** — the full contract. A manifest with
  keep-outs, orientation locks, cable channels and assertions; a populated
  `cad_lock.json`; a `cad-response.json` carrying acknowledged
  counter-constraints; a netlist and its connection table; two probe specs.
  Phase 3 **fails on purpose**: the sleep current and the charge resistor are
  still unmeasured, and the skill will not pretend otherwise.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

135 tests, **no hardware required**. Serial sessions and esptool output are
replayed from recorded transcripts, and a replayed run reports
`"source": "recorded"` — it can never be mistaken for a measurement.

Each test reproduces a specific real mistake: a resistor-ladder keypad on an
unusable ADC2 pin, a 2.0 mm cell lead against a 1.25 mm socket, a class-D
amplifier on a 600 mA LDO, a 20 mm speaker silently substituted for a 28 mm one,
a board profile claiming 8 MB of flash against silicon reporting 16 MB, and an
e-paper refresh that "succeeded" in 29 ms with the panel controller unpowered.

## Pairing with the CAD skill

[`flowful-ai/cad-skill`](https://github.com/flowful-ai/cad-skill) (which installs
as `parametric-3d-printing`) is licensed separately under PolyForm
Noncommercial, so it is **not modified**. `cad_bridge/` holds the CAD side of the
contract instead:

- `consume_manifest.py` turns the manifest into parameters a CadQuery script
  imports, scaffolds `cad-response.json`, and pre-flights the filled-in reply.
- `run_cad_model.py` runs a CadQuery script **without trusting its exit code** —
  necessary because OpenCASCADE crashes during teardown *after* a successful
  export, and a wrapper reading `returncode == 0` treats that as a build failure
  with an empty file list.

Integration is a project instruction, not a fork. See `cad_bridge/README.md`.

## Citations

Reference documentation cites two private builds this skill was derived from:
**reference project A** (an ESP32-S3 e-paper handheld) and **reference project
B** (a Zigbee sensor in a printed enclosure). Neither is public, so those
citations cannot be followed — read them as "this came from a real build"
rather than "look it up". Everything sourced from a manufacturer document or
general practice is cited normally.

## Known gaps

Honest, and deliberately not smoothed over.

- **Kinematic constraints are declarable but not checkable.** A reed switch that
  releases at 22 mm, swept through a hinge's travel, is an electronics constraint
  evaluated through a *motion*. The manifest can say `mate.dynamic: true` and
  `gap_release_mm`, and `assembly_order` can tell you to verify it — but nothing
  here evaluates a constraint across a range of positions. Checking the closed
  and fully-open positions says nothing about where the transition happens. A
  boolean flag is a note that the problem exists, not a solution to it. See
  `examples/vendor-sensor-enclosure/`.
- **Five board profiles.** `esp32s3-generic`, `esp32-classic`, `rp2040-generic`,
  `heltec_vision_master_e290` and the superseded `crowpanel_213_v1`. Each new one
  is real research and a liability if it is wrong, so they are added on demand
  rather than guessed at in bulk. `pinmap_lint.py` refuses an unknown board
  rather than falling back to a generic answer.
- **The probe sketch is ESP32-only.** A generic Arduino-core probe would cover
  RP2040 and AVR but would lose the strapping, RTC-pin, PSRAM and deep-sleep
  checks that are most of its value. The line protocol is documented so a
  project-specific probe can be driven by the same client — see
  `firmware/probe/README.md`.
- **No rework guidance.** Header removal, desoldering discipline and "a board
  that has never been powered on should not be modified" live in the pager
  example's `assembly_order` rather than in a reference document. Whether that
  deserves `reference/rework.md` or is mission creep is unresolved.
- **The skill description is long** (~1900 characters) because it enumerates
  every trigger term. If triggering ever proves unreliable, that is the first
  thing to shorten.

## Safety

Refuses mains and anything above 50 V AC / 120 V DC; refuses life-safety and
safety-critical applications; refuses to design around charging an unprotected
lithium cell. A medication *reminder* is in scope. A dispenser is not.

## Licence

MIT. See `LICENSE`.
