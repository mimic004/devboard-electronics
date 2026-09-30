# Reference corpus

Bench references, loaded on demand rather than pasted wholesale into every
conversation. Each file opens with a line saying when to load it.

| File | When |
|---|---|
| `esp32-gpio.md` | Any pin, strapping, ADC or wake question |
| `power-and-battery.md` | Cells, charging, runtime, sleep current, brownout |
| `buses-and-levels.md` | I2C/SPI, pull-ups, addresses, level shifting |
| `rf-and-antennas.md` | Antennas, keep-outs, bands, filament, range |
| `inputs-and-debounce.md` | Buttons, switches, encoders, plunger heights |
| `connectors-and-cables.md` | JST pitches, mating, polarity, AWG |
| `measurement-discipline.md` | How to prove a hardware claim |
| `bench-review.md` | **The pre-power-on checklist. Read before the first power-up, every time.** |

## About the citations

Every non-obvious claim in these files is attributed, because the whole point of
this skill is that an unattributed number is indistinguishable from a guess.

Two of the sources are private hardware builds this corpus was derived from:

| Label | What it was |
|---|---|
| **reference project A** | An ESP32-S3 handheld pager — 2.9" e-paper panel, SX1262 LoRa, MCP23017 keypad expander, I2S mic and amplifier, haptic motor, LiPo cell, printed two-part shell |
| **reference project B** | A printed pill box whose lid is watched by an off-the-shelf Zigbee contact sensor |

Neither is public, so those citations cannot be followed. **Read them as "this
came from a real build" rather than "look it up."** That distinction is what
matters: the alternative provenance for most of these facts would have been a
datasheet table or a product page, and several of the sharpest lessons here —
the 29 ms e-paper refresh, the 16 MB flash that measured 8 MB, the tactile
switches that were 1.9 mm too tall — exist precisely because a document was
wrong and hardware said otherwise.

Anything sourced from a manufacturer datasheet, a schematic revision, a core
variant header or general engineering practice is cited as such and can be
checked normally.

## What is deliberately not here

Numbers that could not be sourced are stated as qualitative rules instead, and
say so. You will find "keep it well clear" rather than an invented millimetre
figure in a few places — a made-up number that looks authoritative is worse
than an honest rule of thumb, because it will be designed around.
