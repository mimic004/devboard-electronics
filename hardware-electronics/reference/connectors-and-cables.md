# Connectors and cables

Load this when choosing JST-style connectors, battery leads, signal harnesses, cable channels, bend radius, or wire gauge. Use it before ordering cells or printing connector cutouts.

## Connector provenance rules

| Claim | Minimum evidence | Source |
|---|---|---|
| Connector pitch | Schematic, datasheet, mating housing marking, or caliper check. | reference project A, docs/e290-hardware-reference.md |
| Connector series | Exact series/housing, not just "JST". | general connector rule |
| Battery polarity | measured at the exact connector before first connection. | reference project A, docs/bom.md; docs/bring-up.md |
| Mating compatibility | Both series and pitch match; visual similarity is insufficient. | reference project A, docs/bom.md |
| Cable channel fit | Measure the actual plug boot and bend, not just USB spec. | reference project A, docs/bom.md |
| Cross-plug prevention | Physical connector differences recorded as a design feature. | reference project A, docs/bom.md |

## JST-style pitch and mating table

Many sellers misuse "JST" as a generic word. Treat the table as a recognition and review aid; confirm exact housing/contacts before buying.

| Family / label | Nominal pitch | Common use in hobby builds | Mates with | Does not mate with | Notes |
|---|---:|---|---|---|---|
| JST-PH | 2.0 mm | Hobby LiPo packs, small power leads. | Matching PH 2.0 header/housing. | SH, GH, ZH, XH. | A JST-PH 2.0 battery lead will not fit the E290 1.25 mm battery socket. (reference project A, docs/bom.md) |
| JST-SH | 1.0 mm | Small signal cables, Qwiic/STEMMA QT-like ecosystems. | Matching SH 1.0 header/housing. | PH 2.0, 1.25 mm housings, GH. | E290 QuickLink is documented as SH1.0-4P. (reference project A, docs/e290-hardware-reference.md) |
| "SH1.25" seller/vendor label | 1.25 mm | Battery sockets in some product docs/listings. | Only the exact 1.25 mm housing that matches the board. | PH 2.0 and SH 1.0. | E290 docs call JP1 1.25X2P-LiPo / SH1.25-2P; verify physical housing before crimping. (reference project A, docs/bom.md; docs/e290-hardware-reference.md) |
| JST-GH | 1.25 mm | Locking compact wire-to-board in drones/modules. | Matching GH 1.25. | SH1.0, PH2.0, ZH1.5. | Same pitch as some 1.25 labels does not prove mating. |
| JST-ZH | 1.5 mm | Small battery/signal connectors. | Matching ZH 1.5. | PH2.0, SH1.0, GH1.25, XH2.5. | Less common on current sensor breakouts but still seen in small harnesses. |
| JST-XH | 2.5 mm | Larger low-cost wire-to-board, balance leads, general power. | Matching XH 2.5. | PH2.0 even though both are near 2 mm class. | Too large for many handheld enclosures. |

## PH is not SH

| Fact | Consequence | Source |
|---|---|---|
| The E290 battery socket is 2-pin 1.25 mm pitch. | Common JST-PH 2.0 LiPo leads do not mate. | reference project A, docs/bom.md; docs/e290-hardware-reference.md |
| Almost every hobby LiPo ships with JST-PH 2.0 in reference project A's sourcing note. | Buy a cell terminated in 1.25 mm, use an adapter, or re-crimp. | reference project A, docs/bom.md |
| PH 2.0 and SH/1.25 families differ in pitch and housing. | Do not force, shave, or bend connector housings to fit. | general connector rule |
| Connector mismatch is a BOM linter error in the skill plan. | Mating must be checked before ordering and before CAD channels are cut. | skill plan §4.3 |

## Polarity is not standardised

| Rule | Why | Source |
|---|---|---|
| Meter polarity before first connection. | Two-pin battery connector polarity is not guaranteed by series or color. | reference project A, docs/bom.md |
| Meter the board connector and the battery lead. | Adapter leads can cross or preserve polarity. | general bench rule |
| Mark the harness after measuring. | Avoid future reversed reconnects. | general bench rule |
| Do not rely on red/black alone. | Seller harness colors can be wrong or reversed at the housing. | general bench rule |
| Record the reading as `measured`. | Polarity is a safety-critical measurement. | skill plan §8.2 |

## Deliberate connector diversity

| Choice | Design virtue | Source |
|---|---|---|
| Battery uses 1.25 mm connector while signals use SH1.0. | Battery cannot be cross-plugged into a signal connector. | reference project A, docs/bom.md |
| QuickLink uses SH1.0-4P for I2C signals. | Separates low-current signals from battery power. | reference project A, docs/e290-hardware-reference.md |
| Different nets use physically different housings. | Cross-plugging becomes mechanically impossible. | skill plan §4.3 |
| Same connector reused on different nets | Requires labels, keyed housings, pinout discipline, or linter warning. | skill plan §4.3 |

## E290 connector facts

Board-specific facts below apply only to the Heltec Vision Master E290.

| Connector | Description | Source | Design consequence |
|---|---|---|---|
| USB-C | Top short edge; data-capable when shell channel reaches it. | reference project A, docs/e290-hardware-reference.md; docs/bom.md | No external USB breakout needed if channel is correct. |
| Battery JP1 | One 2-pin 1.25 mm LiPo connector. | reference project A, docs/e290-hardware-reference.md | Buy matching cell/adapter; meter polarity. |
| QuickLink | SH1.0-4P, VDD_3V3, SDA GPIO39, SCL GPIO38, GND. | reference project A, docs/e290-hardware-reference.md | Good for I2C expander/haptic; pin order from schematic must be metered before crimping. |
| E-ink FPC/ZIF | 24-pin detachable panel connection. | reference project A, docs/e290-hardware-reference.md | Do not casually extend; high-voltage analog and SPI traces are involved. |
| 2x20 header | Underside, 9.00 mm tall. | reference project A, docs/e290-hardware-reference.md; docs/bring-up.md | Removing it enables slim enclosure but should happen only after board is powered and checked. |
| U.FL LoRa | Near LoRa module; exact XY not dimensioned in docs. | reference project A, docs/e290-hardware-reference.md | Reserve channel; inspect board before final CAD. |

## USB-C channel lesson from reference project A

| Dimension / finding | Value | Source |
|---|---:|---|
| Board USB edge to inner wall | 9.02 mm in the 110 mm body. | reference project A, docs/bom.md |
| Wall thickness contribution | 2.0 mm. | reference project A, docs/bom.md |
| Receptacle below outer surface | 11.02 mm. | reference project A, docs/bom.md |
| Plug shell length | About 6.5 mm for USB-C metal shell. | reference project A, docs/bom.md |
| Required solution | Channel the whole plug travels down. | reference project A, docs/bom.md |
| Final channel | 13.00 x 6.00 mm, 11.22 mm deep in one note; later height 6.26 mm. | reference project A, docs/bom.md |
| Plug boot accepted | Up to 12.60 x 5.86 mm in the source design. | reference project A, docs/bom.md |
| Spec max comparison | Width covered; height 0.64 mm short of tallest legal cable. | reference project A, docs/bom.md |
| Quiet failure | If the battery bay overlaps the channel, the model can shrink the channel instead of telling you the cable will not fit. | reference project A, docs/bom.md |

### USB-C review rules

| Rule | Reason |
|---|---|
| Measure the actual cable boot. | Legal/ordinary USB-C shells vary, and bulky braided cables may not fit. |
| Preserve data pins if flashing/debugging matters. | reference project A removed an earlier charge-only breakout because it forced OTA-only flashing. (reference project A, docs/bom.md) |
| Try a data-capable USB cable first when nothing enumerates. | Cable-first was the better default on E290; button dance was not needed. (reference project A, docs/bring-up.md) |
| Do not assume a panel-mount pigtail fits. | reference project A found common styles require cutouts too large for an 18 mm handheld. (reference project A, docs/bom.md) |

## Bend radius

| Cable / harness | Practical rule | Attribution |
|---|---|---|
| Silicone hookup wire | Use generous service loops; avoid sharp printed corners. | general cable practice |
| Micro-coax / U.FL pigtail | Larger bend radius than the cable diameter suggests; follow antenna vendor datasheet where available. | general RF cable practice |
| Flat-flex/FPC | Do not crease; follow panel/module datasheet. | general FPC practice |
| Battery pouch leads | Avoid repeated flex at pouch exit and connector crimp. | general LiPo handling |
| USB cable in channel | Channel must accommodate plug boot and the entry path, not just metal shell. | reference project A, docs/bom.md |
| Hinge/parting-line harness | Prefer spring/pogo contacts or connectors so halves separate without flexing wires. | reference project A, docs/pager-hardware-plan.md |

### Cable-channel checklist

| Check | Pass condition |
|---|---|
| Bundle diameter known | Conductors plus insulation and sleeving fit the channel. |
| Bend radius respected | No cable exits a connector into an immediate sharp bend. |
| Slack declared | Assembly/disassembly has enough slack without pinching. |
| Avoids keep-outs | Cable does not cross antenna, speaker, motor, or screw keep-outs. |
| Strain relief present | Connector solder joints do not carry pull load. |
| Service path planned | Battery/sensor can be unplugged or removed without destructive disassembly. |

## AWG vs current table

These are conservative hobby-enclosure planning values for short internal wiring, not regulatory ampacity. Use the wire manufacturer's datasheet for final limits, temperature rise, bundle size, and insulation rating.

| AWG | Typical role in small electronics | Conservative planning current | Notes |
|---:|---|---:|---|
| 30 | Signal wires, I2C, button matrix, low-current LEDs. | <=0.5 A short internal runs | reference project A BOM uses 30 AWG silicone hookup wire for tidy internal routing. (reference project A, docs/bom.md) |
| 28 | Small battery/sensor leads, moderate modules. | <=1 A short internal runs | Common in small JST harnesses; check voltage drop. |
| 26 | Motors, small speakers, power to modules. | <=2 A short internal runs | Often more robust for repeated handling. |
| 24 | Higher-current power in small devices. | <=3 A short internal runs | Larger bend radius and connector compatibility matter. |
| 22 | Bench power leads / larger loads. | <=5 A short internal runs | Often too bulky for small printed enclosures. |
| 20 | Higher-current bench/enclosure wiring. | >5 A only with datasheet and thermal review | Usually outside tiny wearable/module builds. |

## Wire-gauge review

| Load | Review item | Source |
|---|---|---|
| MAX98357A amp | Peak current can approach about 1 A into 4 Ω; do not feed through weak rail or hair-thin long lead. | reference project A, docs/e290-hardware-reference.md |
| Vibration motor | Start current around 100-156 mA in reference project A plan. | reference project A, docs/pager-hardware-plan.md |
| LoRa TX | E290 table lists up to 220 mA at 20 dBm. | reference project A, docs/e290-hardware-reference.md |
| USB power | Cable/connector must handle charge current and data path if used for flashing. | general USB/power rule; reference project A USB-channel lesson |
| Battery lead | Must handle charger current and load peaks; connector polarity must be metered. | reference project A, docs/bom.md |

## Crimping and adapters

| Rule | Why | Attribution |
|---|---|---|
| Buy pre-crimped leads when possible for tiny housings. | Small contacts are easy to under-crimp without the correct tool. | general bench practice |
| Do not solder directly to a LiPo pouch tab. | Pouch-cell heat/mechanical safety. | general LiPo safety |
| Re-crimp only with matching contacts and tool. | Pitch alone does not define the contact. | general connector rule |
| Adapter lead must be polarity-checked. | PH-to-1.25 adapters may cross or preserve polarity. | reference project A, docs/bom.md |
| Label both ends of removable harnesses. | Prevents cross-plugging when identical connectors are unavoidable. | general assembly practice |

## Connector failure modes

| Symptom | Likely cause | First check |
|---|---|---|
| Battery will not plug in | Wrong series/pitch, especially PH 2.0 vs 1.25 mm. | Compare pitch and housing; do not force. |
| Board dead on battery | Reversed polarity, no protection, bad crimp, wrong adapter. | Meter connector polarity and voltage. |
| USB charges but will not flash | Charge-only cable or charge-only breakout. | Try known data-capable cable first. |
| Intermittent sensor | Unlatched tiny connector, poor crimp, no strain relief. | Tug-test gently and inspect crimps. |
| Cable fits before assembly but not after | Bend radius/channel/slack ignored. | Check channel path with final shell. |
| RF range worsens | Coax strained or antenna cable routed near metal/battery/motor. | Inspect antenna connector and routing. |

## Connector checklist

| Check | Pass condition |
|---|---|
| Series and pitch named | Not just "JST"; exact mating family is recorded. |
| Mating checked | Counterpart connector/housing is known to mate. |
| Polarity metered | Battery/power connectors have measured polarity at the exact plug. |
| Cross-plug reviewed | Different nets cannot be swapped, or labels/keying mitigate it. |
| Current adequate | Wire gauge and connector rating cover peak load and charge current. |
| Bend and slack planned | Cable path fits the enclosure with service slack. |
| Strain relief provided | Connector solder joints and tiny U.FLs are not load-bearing. |
| CAD driven by real plug | Openings/channels are based on the actual cable boot, not idealized connector drawings. |

