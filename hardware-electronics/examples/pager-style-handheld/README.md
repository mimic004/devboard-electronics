# Example: pager-style handheld

An ESP32-S3 message pager with a 2.9" e-paper panel, an I2C keypad expander, a
speaker, a haptic motor and a piezo, in a printed two-part shell.

**This is the CAD-handoff example.** It is also deliberately mid-flight: phase 3
fails, because two numbers the build depends on are still unmeasured and the
skill will not pretend otherwise.

## Run it

```powershell
$py = "..\..\.venv\Scripts\python.exe"

& $py ..\..\hw.py check --phase 0 --dir .   # 0
& $py ..\..\hw.py check --phase 1 --dir .   # 0
& $py ..\..\hw.py check --phase 2 --dir .   # 0
& $py ..\..\hw.py check --phase 3 --dir .   # 1  <- on purpose, see below
& $py ..\..\hw.py check --phase 4 --dir .   # 0
& $py ..\..\hw.py check --phase 5 --dir .   # 0  -> writes wiring.md
& $py ..\..\hw.py check --phase 6 --dir .   # 1  <- needs the board on the desk
& $py ..\..\hw.py check --phase 7 --dir .   # 1  <- needs the board on the desk
& $py ..\..\hw.py check --phase 8 --dir .   # 0
& $py ..\..\hw.py check --phase 9 --dir .   # 1  <- on purpose
```

## Why phases 3 and 9 fail

They should. `component-manifest.json` declares two `open_gates`:

- **`mainboard.sleep_current_ua`** — the vendor's own documents say 18 µA in one
  place and 20 µA in another, and nobody has measured it. `power_budget.py`
  reports the runtime as a **range** (35.67–35.73 days) rather than a point
  estimate, flags `SLEEP_UNMEASURED`, and says that 100% of the average current
  comes from numbers nobody has measured on this hardware.
- **`mainboard.charge.prog_resistor_ohm`** — verified in a schematic revision,
  not on the physical board. It sets the charge current, which sets the minimum
  safe cell capacity. This is a battery-safety number with `schematic`
  provenance, and `CHARGE_UNMEASURED` says so.

The estimate is still useful: 35.7 days against a 3-day target is **11.9×
headroom**, and that margin is what makes an unmeasured estimate safe to act on.
The tool reports the margin rather than just the number, precisely so that
sentence can be written honestly.

`SLEEP_UNMEASURED` is deliberately **not** acceptable via `accepted_findings`.
You may proceed on an unmeasured estimate. You may not silence the caveat.

## Phase 4: six free pins, six audio signals, nothing to spare

The board has exactly six free GPIOs. The I2S microphone and the I2S amplifier
need exactly six. Three of them are JTAG pins, so the pin map accepts
`JTAG_COST` with a written reason — the cost is real, it is being paid
knowingly, and USB-Serial-JTAG still covers flashing and the console.

The keypad is behind an MCP23017 because **there is no free ADC1 channel** on
this board, which kills the resistor-ladder idea outright. See
`tests/fixtures/pinmap_resistor_ladder.json` for what that failure looks like.
The expander is 38 × 23 mm, and adopting it is what grew the body from
105 × 72 to 110 × 76 mm. One pin decision moved the enclosure on two axes.

## Phase 5: the connection table

`netlist.json` describes the harness as a graph. `wiring_render.py` checks it —
every net has two ends, every pin is either connected or explicitly `nc`, every
IC declares decoupling, every powered part reaches ground, every conductor is
thick enough for its peak — and then writes `wiring.md`: one row per wire, with
a checkbox column, because a half-built harness is indistinguishable from a
finished one without it.

The diagram is secondary and degrades rather than failing. With Graphviz
installed you get `wiring.svg`; without it, `wiring.mmd`. The netlist accepts
`GRAPHVIZ_MISSING` with a written reason for exactly that.

## Phases 6 and 7: what a board on the desk would do

```powershell
& $py ..\..\board_cli.py backup   --out factory.bin --port COM7   # FIRST. Irreversible otherwise.
& $py ..\..\board_cli.py identify --board heltec_vision_master_e290 --strict
& $py ..\..\board_cli.py build    --sketch ..\..\firmware\probe --fqbn esp32:esp32:heltec_vision_master_e290
& $py ..\..\board_cli.py flash    --sketch ..\..\firmware\probe --fqbn esp32:esp32:heltec_vision_master_e290 --port COM7
& $py ..\..\probe_client.py probes\i2c.json          --port COM7 --strict
& $py ..\..\probe_client.py probes\epaper-panel.json --port COM7 --strict
```

`identify --board` is a **check**, not a reading: if the chip reports a different
flash size from the profile it exits 1 and names the field.

`probes/epaper-panel.json` is the interesting one. It declares a 300–3000 ms
plausibility band on `busy_ms` and a precondition that GPIO18 (Vext) must be
high and settled. Replay the recorded failure without any hardware:

```powershell
& $py ..\..\probe_client.py probes\epaper-panel.json `
      --transcript ..\..\tests\fixtures\transcript_panel_29ms.json
```

```
PRECONDITION_FAILED   GPIO18 is still 'low', not 'high' - it never changed
IMPLAUSIBLE_SUCCESS   busy_ms = 29 against a [300, 3000] ms band
```

The probe reported `ok`. Every line of that transcript says success. The only
thing wrong with it is that it is physically impossible — and the precondition
check found the cause one layer down.

## Phase 8: the contract

`component-manifest.json` carries everything CAD needs and nothing it owns:

- **Orientation locks with reasons.** The speaker radiates along −Z toward the
  grille; the piezo needs its rim clamped and its centre free; the board's FPC
  points +X and that sets the *sign* of the display-window offset. Flipping the
  board without also flipping `win_offset_x` doubles the error to 6.10 mm and
  clips the display — and nothing about the model looks wrong while it does it.
- **A conditional keep-out that actually resolves.** `header_zone` applies only
  if the 2×20 header is *not* removed. `assembly.header_removed` is `true`, so
  the keep-out reports `KEEPOUT_INACTIVE` instead of being silently ignored.
- **Keep-outs with their own offsets.** The LoRa antenna channel runs along one
  edge, not concentric with the board.
- **Round parts declared round.** Describing a disc by its bounding box reserves
  21% more area than it occupies, all of it in the corners — exactly where a
  round part has to live.
- **Cable channel minima.** Electronics states the minimum; CAD implements at
  least it and reports the realised value back. The failure mode this prevents
  is quiet: the model just shrinks the channel to suit whatever else is in the
  way, and nothing tells you the cable will not fit.
- **An assembly order with the irreversible step explained.** Remove the header
  *late*: the board has to be known good first, and bulk-desoldering 40 pins
  lifts pads.

## The reverse channel

`cad-response.json` carries two `counter_constraints`, both acknowledged:

- The piezo was 27 mm in the BOM. A CAD-side search over the real back-shell
  footprints found the largest free disc anywhere was **15.6 mm** once the
  battery, speaker and expander had taken their space. **The BOM moved, not the
  enclosure.**
- No arrangement fitted in a 105 × 72 mm body. Re-solved at 94, 98 and 102 mm
  too. 110 mm is the floor.

`handoff_lint.py --check-response` fails while any counter-constraint is
unacknowledged. Set one back to `"acknowledged": false` and watch.

## The invalidation loop

```powershell
# Edit component-manifest.json: change the speaker's footprint.d from 20 to 28.
& $py ..\..\handoff_lint.py component-manifest.json --check-lock cad_lock.json
```

```
HASH_STALE
  components[2].footprint.d  20 -> 28
  cad_parameters: ["spk_d"]
  affects_stls:   ["pager_p2_back_shell.stl"]
  verdict:        REPRINT pager_p2_back_shell.stl
```

That is the whole point of the exercise. Now edit a `reason` or a `note` field
instead: the hash does not move, the lock stays fresh, and nothing reprints.
Editing a comment must not force a reprint; editing a dimension must.

## Files

| File | Phase |
|---|---|
| `project.json` | 0 |
| `requirements.json` | 1 |
| `bom.json` | 2 |
| `power.json` | 3 |
| `pinmap.json` | 4 |
| `netlist.json` | 5 — the harness as a graph |
| `wiring.md` / `wiring.dot` / `wiring.mmd` | 5 — generated; `wiring.md` is the one you take to the bench |
| `probes/i2c.json` | 7 — exact address set plus timing bounds |
| `probes/epaper-panel.json` | 7 — the 300–3000 ms plausibility band |
| `component-manifest.json` | 8 — the contract |
| `cad_lock.json` | 8 — parameter → script → STL map |
| `cad-response.json` | 8 — the CAD skill's reply |
| `measurements.jsonl` | 9 — the ledger, with two gates still open |
