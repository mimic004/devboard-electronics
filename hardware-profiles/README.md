# hardware-profiles

Authoring and auditing the board and component profiles that the
[`hardware-electronics`](../hardware-electronics/) skill validates designs
against. Together they complement
**[flowful-ai/cad-skill](https://github.com/flowful-ai/cad-skill)**: that skill
builds the enclosure, `hardware-electronics` designs what goes inside it, and
this one guarantees the board data underneath is worth believing.

## The problem

`hardware-electronics` validates a **design**. This skill validates the **data
that validation rests on**.

A board profile is a liability if it is wrong. `pinmap_lint.py` will check a pin
map against a wrong profile and report a clean pass — and nothing surfaces until
something is soldered. So the question here is not "what shape is the JSON" but
**"why should anyone believe it?"**

That question used to be answered in prose. The Heltec E290 profile claimed its
GPIO map was *"confirmed by at least three of: datasheet §2.2, the schematic,
`pins_arduino.h`, and Meshtastic's `variant.h`"* — in a note that nothing could
check. That is the same correct-and-unenforceable failure the parent skill was
built to prevent, repeated inside the parent skill's own data. This skill makes
it machine-readable and enforced.

## Install

```powershell
cd "$env:APPDATA\com.github.githubapp\app-skills\hardware-profiles"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe profiles.py doctor
```

Works standalone for authoring and linting. `install` and `audit` need the
parent skill, which it locates automatically.

## Tools

| Tool | Does |
|---|---|
| `profiles.py` | Dispatcher: `new`, `lint`, `verify`, `install`, `audit`, `doctor` |
| `new_profile.py` | Scaffolds an **empty** draft plus the family research checklist |
| `profile_lint.py` | Self-consistency + research hygiene; `--all` lints the installation |
| `verify_profile.py` | Against silicon, against a GPIO sweep, then install |
| `proflib.py` | Source-kind table, corroboration thresholds, shared plumbing |

## The corroboration record

Per field group: who says so, do they agree, what is still disputed.

**Independence is the whole game.** Two documents that copy each other are one
source — mark the derived one `derives_from` and it stops inflating the count.
Product pages, FAQs, marketplace listings and pinout images never count at all.

| Group | Independent sources needed |
|---|---|
| `gpio_map` | 3 |
| `strapping`, `adc`, `rtc_wake`, `power` | 2 |
| `mechanical`, part `footprint` | 1 — one caliper measurement beats any number of documents |

A **conservative** profile — one that over-reserves pins when unsure — fails
safe, so it may go active on one source if it says so and argues why. A profile
may never *bless* pins as free on weak evidence.

`templates/corroboration.example.json` is a fully annotated worked record.

## What it caught

Running it against the profiles that already shipped found, in my own work:

- Three profiles whose `id` violated the parent's own board schema — because
  nothing ever validated a board profile against that schema.
- A consumed-pin rule that was too strict to let a profile document *why* a pin
  is absent.
- A haptic **driver** IC flagged for a missing orientation axis, which belongs
  to the motor it drives, not to the IC.
- Four of five board profiles carrying no machine-checkable reason to be
  believed at all.

All four are fixed. `profiles.py audit` now reports 10 profiles, 0 drafts,
0 uncorroborated, and 2 honestly unresolved contradictions.

## The parent patch

`pinmap_lint.py` now reports:

| Code | When |
|---|---|
| `BOARD_DRAFT` | The profile has not been corroborated |
| `BOARD_UNCORROBORATED` | No corroboration record, or too few independent sources |
| `BOARD_CORROBORATED` | Info: how many sources, and their agreement |
| `BOARD_CONTRADICTION` | An unresolved disagreement follows the board into the design report |

Both are acknowledgeable with a written reason, so a design can proceed against
a draft profile deliberately rather than accidentally.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

33 tests. No hardware, no network.

## Non-goals

No project design — that is the parent skill. No firmware, no PCB layout. No
buying advice: this records what a part *is* and holds no opinion about whether
you should own one. No live pricing or stock. No network access at design time;
research happens at authoring time and what ships is vendored data.

## Licence

MIT. See `LICENSE`.
