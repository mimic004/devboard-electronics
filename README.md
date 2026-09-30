# devboard-electronics

Two paired agent skills for hobbyist electronics built from **dev boards and
breakout modules joined by wire** — not PCB design. Built to complement
**[flowful-ai/cad-skill](https://github.com/flowful-ai/cad-skill)**, Nicolas
Chourrout's parametric CAD skill, which turns a described object into a CadQuery
script, an STL and a preview.

That skill builds the **plastic**. These build the **electronics that has to fit
inside it**, and the contract between the two.

| Skill | Answers |
|---|---|
| [`devboard-electronics/`](devboard-electronics/) | Will this design work? Pin maps, power budgets, BOMs, bring-up, and a hash-locked handoff to CAD |
| [`devboard-profiles/`](devboard-profiles/) | Why should we believe the board data it was checked against? |

## Why these exist

Software fails loudly. Electronics does not.

A wrong number in a circuit does not crash. It gets ordered, soldered, printed
around, and discovered three weeks later. So the core artefact is not a wiring
diagram — it is a **provenance ledger of every number**, plus validators that
refuse to proceed while a figure that will be cut into plastic or soldered to a
cell is still somebody's guess.

> A number a tool computed is a **calculation**. A number from a datasheet is a
> **claim**. A number a seller typed into a listing is a **guess with a price
> attached**. Only a number read off an instrument, on your hardware, on a
> stated date, is a **measurement** — and only a measurement may be called
> verified.

Two real failures set the bar:

- **The implausible success.** With a panel power-enable line low, every e-paper
  refresh *appeared to succeed* — in 29 ms. Nothing errored. The fault was only
  found by comparing the duration against a plausible refresh time. **A check
  that only asks "did it return without error" manufactures false confidence.**
  Every smoke test here carries plausibility bounds, and an implausibly *good*
  result is a FAIL.
- **The silent death.** A dead Zigbee sensor fails silently. You simply stop
  getting reminders and never find out why. Any component whose failure mode is
  silence must declare a liveness check before the BOM gate will pass.

## How they fit with `cad-skill`

Peers, not parent and child. A request naming both — *"a printed case for my
ESP32 weather station"* — starts in `devboard-electronics`, which produces a
`component-manifest.json`, and then hands that to the CAD skill.

**Electronics owns what is true about the part; CAD owns what is true about the
plastic.**

| Number | Owner |
|---|---|
| Part identity, variant, dimensions, tolerance, **provenance** | electronics |
| Orientation constraint — CAD **may not rotate** a part whose axis is `locked` | electronics |
| Keep-outs: mechanical, acoustic, RF, thermal, magnetic | electronics |
| Cable bundle diameter, bend radius; channel **minimum** | electronics |
| Placement, wall thickness, ribs, bosses, fillets, print clearance | CAD |
| Envelope | CAD proposes; **electronics vetoes** if the parts do not fit |
| Window size | electronics owns the active-area requirement; CAD owns the realised cut |

The handoff is hash-locked, so a change on one side invalidates the other *by
name*:

```
edit the BOM  ->  manifest regenerated  ->  content_hash changes
                                                  |
                      cad_lock.json holds the OLD hash
                                                  |
        handoff_lint.py --check-lock  ->  exit 1, HASH_STALE

  components[2].footprint.d  20 -> 28
  cad_parameters: ["spk_d"]
  verdict: REPRINT pager_p2_back_shell.stl
```

The hash deliberately ignores prose: editing a comment must not force a reprint,
editing a dimension must.

### `cad_bridge/` — the CAD side, without forking the CAD skill

`cad-skill` is licensed separately (PolyForm Noncommercial), so **it is not
modified**. [`devboard-electronics/cad_bridge/`](devboard-electronics/cad_bridge/)
holds the integration instead:

- `consume_manifest.py` — flattens a manifest into parameters a CadQuery script
  *imports* rather than restating, scaffolds the reply, and pre-flights it.
- `run_cad_model.py` — runs a CadQuery script **without trusting its exit code**.

That last one matters. On Windows, CadQuery scripts routinely exit
`-1073740940` (heap corruption) or `-1073741819` (access violation) **on
success** — OpenCASCADE crashes during teardown, after the STL is already
written. A wrapper that reads `returncode == 0` as success will report every
successful build as a failure with an empty file list. `run_cad_model.py` judges
a run by a stdout sentinel and by freshly written artefacts instead.

Integration is a project instruction, not a fork. See
[`cad_bridge/README.md`](devboard-electronics/cad_bridge/README.md).

## Install

These are Claude Code / Copilot-style agent skills: a directory containing a
`SKILL.md` with YAML frontmatter. This repository holds **two** of them, so
clone it and copy both directories into your skills folder.

```bash
# Claude Code
git clone https://github.com/mimic004/devboard-electronics /tmp/devboard
cp -r /tmp/devboard/devboard-electronics ~/.claude/skills/
cp -r /tmp/devboard/devboard-profiles    ~/.claude/skills/
```

```powershell
# GitHub Copilot app (Windows)
$dst = "$env:APPDATA\com.github.githubapp\app-skills"
git clone https://github.com/mimic004/devboard-electronics $env:TEMP\devboard
Copy-Item "$env:TEMP\devboard\devboard-electronics" $dst -Recurse
Copy-Item "$env:TEMP\devboard\devboard-profiles"    $dst -Recurse
```

Install them **side by side**: `devboard-profiles` locates its peer by looking
for a sibling directory, so it can lint and audit the profiles the other skill
ships with.

Then, in each skill directory:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt   # .venv\Scripts\pip.exe on Windows
python hw.py doctor                          # or: python profiles.py doctor
```

**Python 3.12, not 3.13+.** Neither skill needs OpenCASCADE, but they must not
create a venv `cad-skill` cannot share.

## What you get

`devboard-electronics` runs nine gated phases. Each gate is a command with an
exit code; the agent derives its next action from a stable finding `code`, never
from prose.

| # | Phase | Gate |
|---|---|---|
| 0 | Intake & safety triage | `hw.py check --phase 0` |
| 1 | Requirements | `hw.py check --phase 1` |
| 2 | BOM | `bom_lint.py --strict` |
| 3 | Power budget | `power_budget.py --strict` |
| 4 | Pin map & buses | `pinmap_lint.py --strict` |
| 5 | Wiring artefact | `wiring_render.py --strict` |
| 6 | Board bring-up | `board_cli.py identify --board <id> --strict` |
| 7 | Peripheral probes | `probe_client.py <spec> --strict` |
| 8 | CAD handoff | `handoff_lint.py --strict` |
| 9 | Audit | `measure_log.py audit --strict` |

Phases are skippable **only** with a recorded reason. A project with a vendor
sensor on its own coin cell legitimately skips the power budget; an absent
artefact and a deliberate skip look identical from the outside, and only one of
them is safe.

Three worked examples cover three genuinely different project shapes — a
battery sensor, a vendor module in a printed box, and a full CAD handoff. The
middle one is the most common hobbyist case and the one a skill built only for
complicated projects would refuse.

## Safety

Refuses mains and anything above 50 V AC / 120 V DC; refuses life-safety and
safety-critical applications; refuses to design around charging an unprotected
lithium cell. A medication **reminder** is in scope. A dispenser is not.

## A note on the citations

The reference documentation cites two private hardware builds these skills were
derived from:

| Label | What it was |
|---|---|
| **reference project A** | An ESP32-S3 handheld pager: e-paper panel, LoRa, I2C keypad expander, speaker, haptic, LiPo, printed two-part shell |
| **reference project B** | A printed pill box whose lid is watched by an off-the-shelf Zigbee contact sensor |

Neither is public, so those citations cannot be followed. Read them as *"this
came from a real build"* rather than *"look it up"* — which is the distinction
that matters, since the alternative was a datasheet or a product page. Every
claim sourced from a manufacturer document, a schematic or general engineering
practice is cited as such and can be checked normally.

## Tests

```bash
cd devboard-electronics && python -m pytest tests -q   # 141 tests
cd devboard-profiles    && python -m pytest tests -q   #  51 tests
```

No hardware, no network. Serial sessions and `esptool` output are replayed from
recorded transcripts, and a replayed run reports `"source": "recorded"` — it can
never be mistaken for a measurement.

Each test reproduces a specific real mistake: a resistor-ladder keypad on an
ADC2 pin that stops working once Wi-Fi is up, a 2.0 mm cell lead against a
1.25 mm socket, a class-D amplifier on a 600 mA LDO, a 20 mm speaker silently
substituted for a 28 mm one, a profile claiming 8 MB of flash against silicon
reporting 16 MB, and that 29 ms e-paper refresh.

## Non-goals

No PCB layout, schematic capture or gerbers — this assumes modules and dev
boards joined by wire. No application firmware; the only firmware here is a
vendored bring-up probe. No SPICE. No mains or certification work. No live
pricing or sourcing. **No geometry** — these skills emit constraints and never
import a CAD kernel, which is exactly what lets `cad_bridge/` work around the
CAD skill's exit-code behaviour without inheriting its dependency pins.

## Licence

MIT — see [LICENSE](LICENSE). `cad-skill` is licensed separately under PolyForm
Noncommercial; nothing here modifies or redistributes it.
