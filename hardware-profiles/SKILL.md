---
name: hardware-profiles
description: "Use this skill when adding, researching, correcting or auditing a BOARD or COMPONENT profile for the hardware-electronics skill. Triggers: any request to add support for a dev board or breakout that is not already profiled (Seeed XIAO, Adafruit Feather/QT Py, SparkFun Thing Plus, Waveshare, Lolin, Wemos, M5Stack, Heltec, LilyGO, Raspberry Pi Pico, Arduino Nano/Uno variants, custom boards); any mention of boards/*.json, parts/*.json, board profile, part profile, pin map research, pinout research, datasheet reconciliation, variant header, pins_arduino.h, boards.txt, board definition, BOARD_UNKNOWN, BOARD_DRAFT, BOARD_UNCORROBORATED, PROFILE_MISMATCH; any question of the form 'is there a profile for X', 'my board isn't supported', 'where do I find the pinout for X', 'which source should I trust', 'the datasheet and the product page disagree'; and any request to add a sensor, expander, amplifier, motor driver, display, connector or other component so that a project can reference it. Also fires when auditing whether the installed profiles are trustworthy. Do NOT use for: designing or validating an actual project (that is hardware-electronics - pin maps, power budgets, BOMs, CAD handoff); writing firmware; PCB layout or schematic capture; buying advice or part recommendations; and anything to do with mains voltage or safety-critical systems."
---

# Board and component profiles: the data a design is validated against

## Why this is a separate skill

`hardware-electronics` validates a **design**. This skill validates the **data
that validation rests on**.

A board profile is a liability if it is wrong. `pinmap_lint.py` will happily
check a pin map against a wrong profile and report a clean pass — and the
failure will not surface until something is soldered. So the question this skill
answers is not "what shape is the JSON" but **"why should anyone believe it?"**

That question used to be answered in prose. The Heltec E290 profile claimed its
GPIO map was *"confirmed by at least three of: datasheet section 2.2, the
schematic, `arduino-esp32` `pins_arduino.h`, and `meshtastic` `variant.h`"* — a
note in a string that nothing could check. That is exactly the
correct-and-unenforceable failure the parent skill exists to prevent, repeated
inside the parent skill's own data. This skill makes it machine-readable.

> A profile that nobody checked is not neutral. It is a confident answer with
> nothing behind it, and it will be believed.

## Setup

```powershell
cd "$env:APPDATA\com.github.githubapp\app-skills\hardware-profiles"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe profiles.py doctor
```

The skill works standalone — you can author and lint a profile anywhere. Only
`install` and `audit` need the parent skill, which it locates automatically.

## The corroboration record

Every profile carries one. It answers three questions per field group:

| | |
|---|---|
| **Who says so?** | `sources` — each with a `kind` and a `ref` you can re-check |
| **Do they agree?** | `groups.<name>.agreement`: `full`, `partial`, `conflicting` |
| **What is still disputed?** | `contradictions`, with BOTH readings recorded |

### Independence is the whole game

Counting sources is easy and useless. **Two documents that copy each other are
one source.** A vendor FAQ restating a datasheet corroborates nothing; mark it
`derives_from` and it stops inflating the count.

| Source kind | Counts? | What it is good for |
|---|---|---|
| `measurement` | ✅ | Settles arguments outright |
| `community_firmware` | ✅ | Strongest document. Its author had to make the board work |
| `variant_header` | ✅ | What the toolchain actually compiles against |
| `board_definition` | ✅ | Beats the datasheet for board-level facts |
| `schematic` | ✅ | Cite the revision or it cannot be re-checked |
| `datasheet` | ✅ | Authoritative about the part, not always about the board |
| `pinout_image` | ❌ | Never draws the pins flash and PSRAM consume |
| `faq` / `product_page` | ❌ | Frequently boilerplate shared across a whole range |
| `listing` | ❌ | A guess with a price attached |

### Thresholds

| Group | Independent sources | Why |
|---|---|---|
| `gpio_map` | 3 | A wrong pin map does not crash. It validates a design that cannot work |
| `strapping` | 2 | An external pull on the wrong pin can prevent boot permanently |
| `adc` | 2 | A channel on the wrong bank silently times out once the radio is up |
| `rtc_wake` | 2 | A wake source on a non-RTC pin sleeps and never wakes |
| `power` | 2 | Charge current drives battery-safety decisions |
| `mechanical` | 1 | One measurement with calipers beats any number of documents |
| `footprint` (parts) | 1 | Same |

### The conservative escape

A profile that **over-reserves** — marks a pin consumed when unsure — fails
safe: it refuses a pin that would have worked. That is recoverable, so such a
profile may go active on **one** source, provided it says so and argues why.

The reverse is never allowed. A profile may not *bless* pins as free on weak
evidence, because that hands a designer a pin that breaks something else.

## Status

| Status | Means | Parent skill's reaction |
|---|---|---|
| `draft` | Not yet corroborated | `BOARD_DRAFT` warning on every design that uses it |
| `active` | Load-bearing groups meet their thresholds | Silent, plus `BOARD_CORROBORATED` info |
| `superseded` | Retained for historical pin facts | `BOARD_SUPERSEDED` warning |

Draft is a perfectly good place to be. It is visibly provisional, which is the
honest state for a board you have read about but not held.

## Workflow

```powershell
$py = ".\.venv\Scripts\python.exe"

# 1. Scaffold. Deliberately EMPTY - it does not guess a pin map.
& $py profiles.py new --kind board --id xiao_esp32c3 --family ESP32-C3 --out .\drafts\

# 2. Research. Work through corroboration.open_questions.
#    reference/sourcing.md says where to look, per family.

# 3. Lint, repeatedly.
& $py profiles.py lint .\drafts\xiao_esp32c3.json --kind board --strict

# 4. Check it against the actual part, if you have one.
& $py profiles.py verify against-silicon .\drafts\xiao_esp32c3.json --identify id.json --write
& $py profiles.py verify against-sweep   .\drafts\xiao_esp32c3.json --sweep sweep.json --write

# 5. Install. Refuses if the profile fails its own linter.
& $py profiles.py install .\drafts\xiao_esp32c3.json

# 6. Audit what the parent now believes.
& $py profiles.py audit
```

## Hard rules

1. **Never invent a pin number.** The scaffolder ships empty lists on purpose.
   An empty list is honest; a plausible guess is indistinguishable from research
   and will be treated as such by everyone downstream, including you in a month.
2. **Never smooth a contradiction.** When sources disagree, record both readings
   and mark it `unresolved`. Do not average, do not silently pick. If you must
   pick, use `chosen` and say who chose and why — it will look weaker than
   `measured`, which is correct.
3. **Absence of evidence is not availability.** A pin no document mentions is
   not free. Flash and PSRAM consume pins that no pinout diagram draws.
4. **Silicon beats the board definition beats the datasheet.** In that order,
   every time.
5. **A citation you cannot re-check is not a citation.** Cite the section, the
   file path, the schematic revision, or the instrument and date.

## The trap that produces a plausible, wrong profile

Copying one from the wrong family. An ESP32-S3 profile that lists GPIO34–39 as
input-only has been copied from a classic ESP32 — and a profile that was copied
is rarely copied in only one place. `profile_lint.py` reports this as
`FAMILY_MISMATCH` and tells you to re-check every other field in the file.

See `reference/common-traps.md` for the rest.

## Tools

| Tool | Does |
|---|---|
| `profiles.py` | Dispatcher: `new`, `lint`, `verify`, `install`, `audit`, `doctor` |
| `new_profile.py` | Scaffolds an empty draft with the family research checklist |
| `profile_lint.py` | Self-consistency + research hygiene. `--all` lints the whole installation |
| `verify_profile.py` | Against silicon, against a GPIO sweep, then install |
| `proflib.py` | Shared plumbing, source-kind table, thresholds |

Exit codes match the parent: 0 pass, 1 validation failure, 2 bad invocation,
3 unreachable, 4 refused. One JSON object on stdout; branch on `code`.

### Accepting a finding

Advisory findings can be accepted with a written reason in
`accepted_findings`. Self-consistency errors, `FAMILY_MISMATCH` and
`CORROBORATION_INSUFFICIENT` cannot. A profile that is wrong is not a
preference.

## On-demand reference

| File | When |
|---|---|
| `reference/sourcing.md` | Where authoritative data lives, ranked, per family |
| `reference/corroboration.md` | **What independent actually means.** Read this first |
| `reference/common-traps.md` | The mistakes that produce a plausible, wrong profile |
| `reference/part-profiles.md` | Authoring a component rather than a board |

## Relationship to `hardware-electronics`

Peers. This skill writes and checks `boards/*.json` and `parts/*.json`; that
skill consumes them. It warns (`BOARD_DRAFT`, `BOARD_UNCORROBORATED`) when asked
to validate a design against a profile nobody has checked, and surfaces
unresolved contradictions into the design report so a disputed number cannot be
quoted as fact.

## Non-goals

No project design — that is the parent skill. No firmware. No PCB layout. No
buying advice or part recommendations: this skill records what a part *is*, and
holds no opinion about whether you should own one. No live sourcing, pricing or
stock. No network fetching at design time: research happens when a profile is
authored, and what ships is vendored data.
