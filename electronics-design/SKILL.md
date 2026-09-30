---
name: electronics-design
description: "Use this skill when the user is designing, specifying, wiring, bringing up, or debugging a hobbyist electronics project built from modules and dev boards. Triggers: any mention of ESP32, ESP32-S3, ESP8266, RP2040, Pico, Arduino, STM32, nRF52, Seeed XIAO, Heltec, Adafruit/SparkFun breakout, Raspberry Pi GPIO; any peripheral bus or part (I2C, SPI, I2S, UART, GPIO expander, MCP23017, level shifter, SX1262, LoRa, e-paper/e-ink panel, OLED, MEMS microphone, MAX98357A, DRV2605L haptic, reed switch, Hall sensor, tactile switch, vibration motor, piezo, load cell, relay module); any power question (LiPo, 18650, coin cell, CR2032, battery life, mAh, charge current, TP4056, boost/buck converter, LDO, load switch, deep sleep current, power budget, brownout); any of pin map, pinout, strapping pin, ADC2, bus conflict, I2C address collision, pull-up resistor, decoupling cap, debounce, bill of materials, BOM, JST connector, breadboard, protoboard, bring-up, flashing, esptool, arduino-cli, COM port, serial monitor, logic analyzer, multimeter; and any request to fit electronics into a 3D-printed enclosure (component keep-outs, antenna clearance, connector cutouts, cable routing, mounting bosses for a PCB). Also fires when the user describes a physical gadget they intend to build and power. Do NOT use for: embedded application firmware that already exists in a repository (that is ordinary coding work); PCB layout, schematic capture, KiCad/Altium/EasyEDA files, gerbers, or board fabrication; anything connected to mains/line voltage or above 50 V AC / 120 V DC; automotive, aviation, medical, industrial-control, or any other safety-critical or life-safety system; EMC, RED/FCC certification, or regulatory compliance sign-off; SPICE/analog circuit simulation; repairing or reverse-engineering commercial equipment; and pure software questions about a protocol with no physical build attached."
---

# Hardware electronics: modules, dev boards and the numbers between them

## Why this skill is shaped the way it is

Software fails loudly. Electronics does not.

A wrong number in a circuit does not crash. It gets ordered, soldered, printed
around, and discovered three weeks later. So the core artefact here is not a
wiring diagram — it is a **provenance ledger of every number**, plus validators
that refuse to proceed while a number that will be cut into plastic or soldered
to a cell is still somebody's guess.

Two failures set the bar:

- **The implausible success.** On one board, with the panel power-enable line
  low, every e-paper refresh *appeared to succeed* — in 29 ms. Nothing errored.
  The fault was only found by comparing the duration against a plausible refresh
  time. **A check that only asks "did it return without error" is worse than
  useless: it manufactures false confidence.** Every smoke test here carries
  plausibility bounds, and an implausibly-good result is a FAIL.
- **The silent death.** A dead Zigbee sensor fails silently. Without a liveness
  alert you simply stop getting reminders and never find out why. Any component
  whose failure mode is silence requires a declared liveness check.

> A number this skill computed is a **calculation**. A number from a datasheet is
> a **claim**. A number a seller typed into a listing is a **guess with a price
> attached**. Only a number read off an instrument, on the user's actual
> hardware, on a stated date, is a **measurement** — and only a measurement may
> be called verified.

## Setup

```powershell
cd "$env:APPDATA\com.github.githubapp\app-skills\electronics-design"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe hw.py doctor
```

Python **3.12**, not 3.13+. This skill needs no OpenCASCADE, but it must not
create a venv the paired `parametric-3d-printing` skill cannot use.

Always invoke as `.\.venv\Scripts\python.exe <tool>.py`, never bare `python` —
the system Python is often newer. Quote every path; they contain spaces.

## The provenance ladder

The single most important table in this skill. Every number in a project carries
one of these tags, and `measure_log.py` is the only place a value may be
promoted.

| provenance | Meaning | May be called "verified"? |
|---|---|---|
| `assumed` | someone's guess | **no** |
| `inferred` | derived from other numbers | **no** |
| `seller_claimed` | marketplace listing, no manufacturer | **no** |
| `vendor_claim` | marketing or product-page figure | **no** |
| `simulated` | computed by a tool in this skill | **no** |
| `datasheet` | manufacturer document, cited | no |
| `schematic` | read off a schematic revision, cited | no |
| `measured` | instrument + date + operator recorded | **yes** |

**Vocabulary rule.** You are forbidden from writing "tested", "verified",
"confirmed" or "working" about anything without a `measurements.jsonl` entry to
point at. For everything else the permitted words are: *designed*, *expected*,
*calculated*, *per datasheet*, *not yet run*.

Run `measure_log.py report` and reproduce its two-tier table verbatim in any
summary. Do not paraphrase it into one confident list.

## The nine phases

Each phase has a machine-checkable gate. **Do not advance until the gate exits
0.** Derive the recovery action from the finding `code`, never from the prose.

| # | Phase | Produces | Gate |
|---|---|---|---|
| 0 | Intake & safety triage | `project.json` | `hw.py check --phase 0` |
| 1 | Requirements & constraints | `requirements.json` | `hw.py check --phase 1` |
| 2 | Part selection & BOM | `bom.json` | `bom_lint.py bom.json --strict` |
| 3 | Power budget | `power.json` | `power_budget.py power.json --strict` |
| 4 | Pin map & bus allocation | `pinmap.json` | `pinmap_lint.py pinmap.json --strict` |
| 5 | Wiring artefact | `netlist.json` → `wiring.md` | `wiring_render.py netlist.json --strict` |
| 6 | Board bring-up | chip identity vs profile | `board_cli.py identify --board <id> --strict` |
| 7 | Incremental peripheral tests | `probes/*.json` | `probe_client.py probes/<name>.json --strict` |
| 8 | CAD handoff | `component-manifest.json` | `handoff_lint.py component-manifest.json --strict` |
| 9 | Integration & audit | audit result | `measure_log.py audit --manifest ... --strict` |

`hw.py check --phase N --dir <project>` runs the right gate for you and defaults
to strict. Phases 6 and 7 need a board on the desk: the gate tells you the exact
command rather than pretending it can pass without one.

### Ordering that matters

- **Phase 2 before 3 and 4.** The part choice sets the rails and the pin count.
  One real project drew the pin map first, discovered its resistor-ladder keypad
  was impossible, adopted a 38 × 23 mm I2C expander instead, and that single pin
  decision grew the enclosure by 5 mm on two axes.
- **Phase 6 before 8.** Do not print around a board you have not yet held.
- **Phase 7 is strictly one peripheral at a time.** Bringing up an I2S mic and an
  I2S amp together and getting silence tells you nothing.
- **Phase 8 is bidirectional.** CAD can discover that a part in your BOM does not
  fit anywhere, and that finding has to come back. See `cad-response.json`.

### Skipping a phase

Phases are skippable **only** by writing an explicit record into `project.json`:

```json
"skipped": [{"phase": 3, "reason": "The only active part is a vendor sensor with its own coin cell."}]
```

Never silently. An absent artefact and a deliberate skip look identical from the
outside, and only one of them is safe.

## Hard refusals

The tools return **exit 4** and stop. Do not work around them.

| Refuse | Redirect to |
|---|---|
| Mains or line voltage; anything above **50 V AC / 120 V DC**; fixed building wiring; opening a mains PSU | A licensed electrician, or a certified module the user never opens |
| Life-safety and safety-critical: medical devices or dosing, smoke/CO/gas detection as a **primary** alarm, automotive brake/steering/airbag, aviation, firearms, lifting or load-bearing | Certified commercial equipment. A *redundant secondary* indicator is allowed only if the user states a certified primary exists |
| Charging unprotected cells; designing around a charge current the user cannot verify; soldering directly to a pouch cell; charging LiFePO4 on a Li-ion profile | Protected cells, a charge IC with a datasheet, and a metered PROG resistor |
| Defeating a safety device, bypassing a fuse or thermal cutout, uprating a protection component | — |
| Regulatory sign-off: FCC/CE/RED claims, "is this legal to transmit?" | The skill flags band, duty-cycle and power as design inputs, and says plainly that it cannot advise on legality |

**The boundary is real and it is narrow.** A medication *reminder* that watches a
lid and nags a phone is in scope. A dispenser or a dose controller is a refusal.

## When to insist on a meter instead of a calculation

Non-negotiable. Ask for the reading; do not proceed on arithmetic.

1. **Battery connector polarity, before the first connection.** Polarity is not
   standardised and the housing tells you nothing.
2. **The charge-current resistor.** Schematic is not silicon.
3. **Deep-sleep current** — in series with the battery positive lead, µA range,
   **USB disconnected**. It dominates every runtime estimate.
4. **Battery-sense calibration**, on battery power. On USB the charger holds BAT
   at its float voltage whether a cell is fitted or not; one real divider read
   4.201 V with **no cell present**. That is not a calibration check.
5. **Rail voltage under load**, for anything with a >100 mA transient.
6. **Continuity and shorts before first power-on**, on any hand-wired assembly.
7. **Any dimension that will be printed around**, with calipers, whenever its
   provenance is `seller_claimed` or `assumed`.

If the user has no multimeter, say so at **phase 0**, not phase 9. `hw.py check
--phase 0` reports which gates are reachable with the tools they actually own.

## Three prohibitions

1. **Never widen a plausibility band to make a test pass.** The band is the
   requirement, not the score.
2. **Never promote a provenance tag without a `measurements.jsonl` entry.** The
   ledger is append-only and there is no other path from `assumed` to `measured`.
3. **Never retry a failed hardware step blindly.** A retry that sometimes works
   is a wiring fault, not a flake. Report the failure; do not paper over it.

And one corollary, from e-ink: **evidence must be a change you watched happen.**
A static demo image proves nothing — the factory picture survives a dead driver,
a wiped flash and an unpowered board. A steady-state observation never proves a
subsystem is alive. Demand a transition: a counter that increments, a level that
moves when you change the input.

## Order one, test the fit, then order ten

Any component whose dimensions are `seller_claimed` or `assumed` and that drives
CAD carries `"fit_coupon_required": true`, and `handoff_lint.py --strict` refuses
the handoff until the ledger promotes that dimension to `measured`.

Bound a sweep from **both** ends. If the winning value sits at either end of the
range you tested, you bounded it from the wrong end and the true optimum may lie
beyond it. `measure_log.py sweep` reports `SWEEP_BOUNDED_WRONG` and demands a
second round.

## Rules of thumb

| Topic | Rule |
|---|---|
| Decoupling | 100 nF at every IC power pin, plus one bulk electrolytic per rail. Place it **at the pin**, not at the connector |
| Transients | Any load whose peak exceeds its average by ≥100 mA needs declared local bulk capacitance |
| I2C pull-ups | ~4k7 at 100 kHz, ~2k2 at 400 kHz — **and count the ones already fitted on your modules.** Three stacked 10k breakouts make a bus too stiff |
| Debounce | 10–50 ms. 15 ms measured sufficient on one real keypad |
| CMOS inputs | Never leave one floating |
| Inductive loads | Every one gets a flyback diode |
| Level shifting | A shifter is not optional between 5 V and 3.3 V |
| ADC2 on ESP32 | Unusable while Wi-Fi is active. `adc2_get_raw()` returns `ESP_ERR_TIMEOUT` |
| Deep-sleep wake | ESP32-S3: only GPIO0–21 are RTC-capable |
| Strapping pins | ESP32-S3: 0, 3, 45, 46. An external pull-up on GPIO45 switches flash to 1.8 V and bricks boot |
| Antennas | Never transmit without one connected. No carbon-, glass- or metal-filled filament near one. Range-test in place, not on the desk |
| Connectors | Pitch is the fact; the family name is marketing. JST-PH 2.0 does not mate with a 1.25 mm socket |

## A pin question is never answerable without a board ID

GPIO 7 is the **panel power-enable** on the CrowPanel 2.13 v1 and **VBAT_READ**
on the Heltec E290. An agent that greps a repository for "GPIO 7" gets a
confidently wrong answer.

`pinmap_lint.py` therefore requires `"board"` and has no default. Vendored
profiles live in `boards/`:

| id | status |
|---|---|
| `esp32s3-generic` | active, deliberately pessimistic about flash and PSRAM |
| `esp32-classic` | active |
| `rp2040-generic` | active |
| `heltec_vision_master_e290` | active, fully specified |
| `crowpanel_213_v1` | **superseded** — retained as the counter-example |

Copy the profiles a project uses into the project directory so it stays runnable
standalone; project-local copies win over the vendored ones.

## The pairing contract with `parametric-3d-printing`

They are **peers, not parent and child.** A request naming both ("a printed case
for my ESP32 weather station") starts here, produces `component-manifest.json`,
and then invokes the CAD skill with that manifest as input.

**Electronics owns what is true about the part; CAD owns what is true about the
plastic.**

| Number | Owner |
|---|---|
| Part identity, MPN, variant (band, voltage, pitch) | electronics |
| Component dimensions, tolerance and **provenance** | electronics — CAD must not round, pad or "clean up" |
| Orientation constraint (functional axis) | electronics — CAD **may not rotate** a part whose constraint is `locked` |
| Keep-out volumes (mechanical, acoustic, RF, thermal, magnetic) | electronics |
| Connector type, mating, polarity status | electronics |
| Cable conductors, bundle diameter, bend radius, slack | electronics |
| Cable **channel** cross-section | electronics states the minimum; CAD implements ≥ it and reports back |
| Rail voltages, currents, thermal dissipation | electronics |
| Failure mode and liveness requirement | electronics |
| Placement X/Y/Z/rotation | CAD |
| Envelope | CAD proposes; **electronics vetoes** if the parts do not fit |
| Wall thickness, ribs, bosses, clips, fillets | CAD |
| Print clearance, interference, shrinkage | CAD — electronics must **not** add its own; double-clearancing is a real failure |
| Grille and vent geometry | CAD implements; electronics owns the open-area requirement |
| Material choice | CAD — but electronics owns the material *constraint* as a veto |
| Window size | electronics owns the active-area requirement; CAD owns the realised cut |

### The invalidation loop

```
electronics edits BOM -> manifest regenerated -> content_hash changes
                                                      |
                          cad_lock.json holds the OLD hash
                                                      |
              handoff_lint.py --check-lock -> exit 1, HASH_STALE
                                                      |
   names: which fields moved, which cad_parameters they feed, which STL
   they affect, therefore what must reprint
```

The hash covers geometry and deliberately ignores prose. Editing a comment must
not force a reprint; editing a dimension must.

The reverse channel matters just as much. `cad-response.json` carries
`counter_constraints`: one real project's BOM said a 20–27 mm piezo, a CAD-side
search over the actual footprints found the largest free disc anywhere was
15.6 mm, and **the BOM moved, not the enclosure**. `handoff_lint.py
--check-response` fails while any counter-constraint is unacknowledged.

## Bring-up and probing

`board_cli.py` and `probe_client.py` both carry an honest `source`: a run that
opened a serial port or questioned real silicon says `"hardware"`, one replaying
a recorded transcript says `"recorded"`. **There is no flag that turns the
second into the first.**

Three behaviours are not negotiable:

- **Bluetooth COM ports are excluded from auto-detect**, and more than one
  candidate is an *error* demanding `--port`. Never a coin flip.
- **DTR and RTS are deasserted before the port opens, and reset is opt-in.** Many
  ESP32 boards auto-reset on DTR, and a reset restarts setup — watching must not
  disturb the device.
- **`backup` before the first `flash` to an unseen board.** Factory firmware is
  unrecoverable once overwritten, and nothing warns you at the time.

`identify --board <id>` is the self-correction hook: **if silicon disagrees with
the profile, it exits 1 and names the field.** That is how one project's "16 MB
flash" became "8 MB" — the chip was asked, and the documentation lost. Without
`--board` you have a reading, not a check.

### The probe protocol

`firmware/probe/probe.ino` is vendored, compiles in about 9% flash / 7% RAM, and
speaks a line protocol so the host parses facts instead of scraping English:

```
> PROBE i2c 39 38 100000
< probe.i2c.found 0x20
< probe.i2c.elapsed_ms 41
< probe.done i2c ok
```

Every probe spec declares **plausibility bounds**, and `probe_client.py` fails a
result that is implausibly *good*:

```
IMPLAUSIBLE_SUCCESS  busy_ms = 29 against a [300, 3000] ms band
```

That is the 29 ms e-paper refresh, reproduced from a recorded transcript. The
sketch's `PROBE busy` waits for the busy line to **assert** before waiting for it
to **release**, which is what turns "never started" from a silent success into an
explicit failure. Preconditions are verified by *level*, not by return value: a
rail that reports `ok` while still sitting low is caught.

One peripheral at a time. Bringing up an I2S mic and an I2S amp together and
getting silence tells you nothing.

## The CAD bridge

`parametric-3d-printing` is third-party and licensed separately, so the CAD half
of the contract lives in `cad_bridge/` and **does not modify that skill**.

| Command | What it does |
|---|---|
| `consume_manifest.py params <m> --out-py manifest_params.py` | Flattens the manifest into parameters a CadQuery script *imports* instead of restating |
| `consume_manifest.py envelope <m>` | The keep-out and containment budget, as data |
| `consume_manifest.py respond <m> --out cad-response.json` | Scaffolds the reply, every assertion `not_evaluated` |
| `consume_manifest.py check <m> --response <r>` | Pre-flights it: unevaluated assertions, unreported channels, rotated locked parts |
| `run_cad_model.py <script.py>` | Runs CadQuery **without trusting the exit code** |

That last one matters. CadQuery scripts here exit **-1073740940** or
**-1073741819** *on success* — OpenCASCADE crashes during teardown after the STL
is already written. The CAD skill's own wrapper sets
`success = proc.returncode == 0` and gates file discovery on it, so under that
crash every successful build reports failure with an empty `stls` list.
`run_cad_model.py` judges a run by a stdout sentinel (`HWEL_RESULT {json}`) and by
freshly written artefacts instead. A nonzero exit *with* a valid sentinel is a
pass.

Integration is a project instruction, not a fork — see `cad_bridge/README.md`.

## Commands

`--strict` promotes warnings to errors and is the intended default for a gate.

```powershell
$py = ".\.venv\Scripts\python.exe"

# phases
& $py hw.py phases
& $py hw.py check --phase 0 --dir "C:\path\to\project"
& $py hw.py doctor

# the provenance ledger
& $py measure_log.py --ledger measurements.jsonl record --key e290.flash.size_mb `
    --value 8 --unit MB --provenance measured `
    --instrument "esp_flash_get_size() on COM7"
& $py measure_log.py --ledger measurements.jsonl audit --manifest component-manifest.json --strict
& $py measure_log.py --ledger measurements.jsonl report
& $py measure_log.py --ledger measurements.jsonl sweep --key clip.interference `
    --values 3.0 3.2 3.4 3.6 --winner 3.0

# validators
& $py pinmap_lint.py pinmap.json --strict
& $py bom_lint.py bom.json --power power.json --manifest component-manifest.json --strict --render bom.md
& $py power_budget.py power.json --strict
& $py wiring_render.py netlist.json --out-dir . --strict
& $py handoff_lint.py component-manifest.json --bom bom.json --check-lock cad_lock.json `
    --check-response cad-response.json --strict
& $py handoff_lint.py component-manifest.json --write-lock cad_lock.json

# bring-up and probing
& $py board_cli.py detect
& $py board_cli.py backup   --out factory.bin --port COM7        # unseen board, FIRST
& $py board_cli.py identify --board heltec_vision_master_e290 --strict
& $py board_cli.py build    --sketch firmware\probe --fqbn esp32:esp32:heltec_vision_master_e290
& $py board_cli.py flash    --sketch firmware\probe --fqbn <fqbn> --port COM7
& $py board_cli.py monitor  --seconds 30 --expect "probe\.ready"
& $py board_cli.py record   --out transcript.json --send "PROBE i2c 39 38 100000"
& $py probe_client.py probes\i2c.json --port COM7 --strict
& $py probe_client.py probes\epaper-panel.json --transcript transcript.json

# the CAD bridge
& $py cad_bridge\consume_manifest.py params component-manifest.json --out-py manifest_params.py
& $py cad_bridge\run_cad_model.py pager_enclosure.py --expect-stl back.stl
& $py cad_bridge\consume_manifest.py respond component-manifest.json --out cad-response.json
& $py cad_bridge\consume_manifest.py check   component-manifest.json --response cad-response.json
```

## Exit codes

| Exit | Meaning |
|---|---|
| 0 | pass |
| 1 | validation failure — read `findings` and fix |
| 2 | bad invocation, missing input, unparseable schema |
| 3 | timeout or hardware not reachable |
| 4 | **refused** — a safety or honesty rule blocked the operation |

Every tool emits exactly one JSON object on stdout. Detail lives in `findings`
and `notes`, never in prose on stderr. Every finding carries a stable `code`;
branch on the code.

### Accepting an advisory finding

Some findings are costs, not faults — losing hardware JTAG to free three pins,
for example. Those may be accepted with a written reason:

```json
"accepted_findings": {"JTAG_COST": "Audio needs six pins and the board has six free. USB-Serial-JTAG still covers flashing and the console."}
```

This is not a mute switch. Only advisory codes can be accepted, the reason must
be real, accepting a code that never fired is itself reported, and the findings
that cost a reprint or hide an unmeasured number **cannot be accepted at all**.

## On-demand reference

Load these when the topic comes up; do not paste them wholesale.

| File | When |
|---|---|
| `reference/esp32-gpio.md` | any pin, strapping, ADC or wake question |
| `reference/power-and-battery.md` | cells, charging, runtime, sleep current, brownout |
| `reference/buses-and-levels.md` | I2C/SPI, pull-ups, addresses, level shifting |
| `reference/rf-and-antennas.md` | antennas, keep-outs, bands, filament, range |
| `reference/inputs-and-debounce.md` | buttons, switches, encoders, plunger heights |
| `reference/connectors-and-cables.md` | JST pitches, mating, polarity, AWG |
| `reference/measurement-discipline.md` | how to prove a hardware claim |
| `reference/bench-review.md` | **the pre-power-on checklist. Read it before the first power-up, every time.** |
| `firmware/probe/README.md` | the probe line protocol, and how to write a project-specific probe that `probe_client.py` can still drive |
| `cad_bridge/README.md` | wiring the CAD skill to the manifest without forking it |

## Worked examples

- `examples/esp32s3-lipo-sensor/` — a complete project that passes every
  design-phase gate, including a fully measured power budget. Read this first.
- `examples/vendor-sensor-enclosure/` — **the shape most hobbyist projects
  actually are**: a vendor module in a printed box, no MCU, no firmware, no
  rails, five recorded skips. Read this to see the skill degrade gracefully.
- `examples/pager-style-handheld/` — the full CAD handoff: manifest, lock,
  `cad-response.json` with acknowledged counter-constraints, a netlist and
  connection table, two probe specs, and two open gates that make phase 3 fail
  on purpose. Read this for the contract.

A project is not required to be complicated. Phases are skippable with a
recorded reason, and phase 0 works out which gates are even reachable with the
tools the user owns: if nothing in the build is powered, it does not demand a
multimeter.

## Non-goals

No PCB design, layout, gerbers or DRC. No application firmware — the only
firmware here is the vendored bring-up probe. No SPICE or analog simulation. No
mains, safety-critical or certification work. No live pricing or sourcing
automation. No geometry — this skill emits constraints and never imports a CAD
kernel, which is exactly what lets `cad_bridge/` work around the CAD skill's
exit-code trap without inheriting its version pins. No parts recommendation
engine: it validates your choice and names the traps, and holds no opinion about
which brand of MEMS microphone is best.
