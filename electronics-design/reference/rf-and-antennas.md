# RF and antenna constraints

Load this when a design includes Wi-Fi, Bluetooth, Zigbee, LoRa, U.FL, a PCB antenna, an antenna channel, or an enclosure material choice near a radio. Use it before ordering a regional radio variant or printing plastic around an antenna.

## RF provenance rules

| Claim | Minimum provenance | Notes |
|---|---|---|
| Regional radio band | Part number/order option, not firmware setting. | E290 LoRa band is locked at order time. (reference project A, docs/bom.md) |
| Antenna connector type | Physical inspection if vendor docs conflict. | E290 2.4 GHz antenna docs conflict between U.FL and spring antenna. (reference project A, docs/e290-hardware-reference.md) |
| Range | measured in the installed location. | Desk tests near the coordinator do not prove real range. (reference project B, README.md) |
| Enclosure material RF effect | measured or well-established material rule. | Plain PLA/PETG is acceptable for 2.4 GHz in reference project B; filled filament is not. (reference project B, README.md) |
| Keep-out clearance | Board/antenna module datasheet or explicit project constraint. | reference project A reserves an antenna channel and keeps it away from battery, speaker magnet, motor. (reference project A, docs/pager-hardware-plan.md) |

## Order-time band lock

| Radio | Band option | Can firmware change it later? | Source |
|---|---|---|---|
| Heltec E290 LoRa | 433 MHz | No. Order the correct regional variant. | reference project A, docs/bom.md |
| Heltec E290 LoRa | 470-510 MHz | No. Order the correct regional variant. | reference project A, docs/bom.md |
| Heltec E290 LoRa | 863-870 MHz | No. Order the correct regional variant. | reference project A, docs/bom.md |
| Heltec E290 LoRa | 902-928 MHz | No. reference project A chose the US 902-928 MHz version, listed as HT-VME290-HF in its BOM. | reference project A, docs/bom.md |

### Band-selection checklist

| Check | Pass condition |
|---|---|
| Region named | The design records country/region as an input, not an afterthought. |
| Variant chosen | BOM names the band variant before ordering. |
| Antenna matched | Antenna frequency range covers the ordered band. |
| Gateway matched | PC-side or coordinator radio uses the same band. |
| Legality not asserted | The skill does not provide regulatory sign-off; it only records design inputs. |

## Never transmit without an antenna

| Rule | Why | Source |
|---|---|---|
| Do not transmit on LoRa without an antenna connected. | RF power can reflect into the transmitter output stage. | reference project A, docs/bring-up.md; general RF practice |
| Do not treat receive-only tests as proof transmit is safe. | TX stresses the RF path differently. | general RF practice |
| Use a dummy load if intentionally testing without an antenna. | It gives the transmitter a load. | general RF practice |
| Put this in bring-up ordering. | LoRa was deferred in reference project A; the warning remains part of bring-up. | reference project A, docs/bring-up.md |

## Antenna keep-outs

| Keep-out item | Rule | Source |
|---|---|---|
| Conductors | Keep metal, copper pours, screws, foil, shields, and wires out of the antenna near field unless the antenna design calls for them. | general RF layout practice |
| Ground plane | Respect the antenna's required ground-plane relationship and clearance; do not guess from another antenna. | general RF layout practice |
| Battery | Keep pouch cells and their foil/lead structure away from antenna channels. | reference project A, docs/pager-hardware-plan.md |
| Speaker magnet | Keep magnetic/metal speaker structures away from antenna channels. | reference project A, docs/pager-hardware-plan.md |
| Motors | Keep motor cans, magnets, and noisy leads away from antennas. | reference project A, docs/pager-hardware-plan.md |
| User hand/body | Test in the way the object will be held or worn. | general RF practice; reference project B in-place range-test rule |
| Enclosure ribs | Do not later add conductive inserts, heat-set inserts, or carbon-filled reinforcement through an RF keep-out. | general RF/mechanical practice |

### reference project A antenna-channel lesson

| Decision | Reason | Source |
|---|---|---|
| Reserve the LoRa antenna channel in v1 even though LoRa is a stretch goal. | Retrofitting an antenna path into a finished shell is painful; leaving the channel costs little. | reference project A, docs/pager-hardware-plan.md |
| Keep GPIO8-14 free. | They are LoRa SPI/control lines; raiding them forecloses the stretch goal. | reference project A, docs/pager-hardware-plan.md |
| Keep header pin 11 unused. | E290 docs contradict it; GPIO14 is LoRa DIO1/IRQ. | reference project A, docs/e290-hardware-reference.md |
| Keep antenna away from LiPo, speaker magnet, and motor. | Those are called out as keep-out targets in the design plan. | reference project A, docs/pager-hardware-plan.md |

## U.FL / I-PEX micro-coax handling

| Rule | Why | Attribution |
|---|---|---|
| Treat U.FL as fragile. | It is a small board connector, not a panel connector. | general RF connector practice |
| Limit mating cycles. | Micro-coax connectors wear; check connector datasheet for the exact rating. | general RF connector practice |
| Press straight down, lift straight up. | Rocking peels pads or deforms the shell. | general RF connector practice |
| Provide strain relief for the coax. | Cable pull should not load the connector. | general mechanical/RF practice |
| Do not route coax across sharp printed edges. | Vibration and bends damage shield/dielectric. | general cable practice |
| Record whether the connector actually exists. | E290 2.4 GHz U.FL is unconfirmed because Heltec docs conflict. | reference project A, docs/e290-hardware-reference.md |

## Filament and enclosure material

| Material near antenna | Rule | Source |
|---|---|---|
| Plain PLA | Acceptable for reference project B Zigbee; no measurable difference was expected/observed in that project documentation. | reference project B, README.md |
| Plain PETG | Acceptable rule in reference project B; reference project A chose transparent yellow PETG for RF-transparent enclosure concept. | reference project B, README.md; reference project A, docs/pager-hardware-plan.md |
| Carbon-fiber-filled filament | Do not use near a 2.4 GHz antenna. | reference project B, README.md |
| Metal-filled filament | Do not use near a 2.4 GHz antenna. | reference project B, README.md |
| Glass-filled filament | Avoid near antenna keep-outs in this skill. | skill plan §5.2; general filler caution |
| Conductive paint/foil | Treat as metal. | general RF practice |
| Heat-set inserts | Keep out of antenna keep-out volumes. | general RF/mechanical practice |

### Material-note wording

| Bad wording | Better wording |
|---|---|
| "Plastic is RF transparent." | "Plain PLA/PETG is acceptable for these hobby 2.4 GHz enclosure cases; filled or conductive materials are not." |
| "This case will not affect range." | "Range must be tested in place after assembly." |
| "Carbon fiber looks fine." | "Do not print carbon-fiber-filled material near the antenna." |

## PCB antennas and installed orientation

| Item | Rule | Source |
|---|---|---|
| PCB meander antenna location | Identify which end/edge carries the antenna before designing pockets or bosses. | reference project B, README.md |
| Magnet near sensor | reference project B magnet covers only the middle 20 mm of the 41 mm sensor body, staying clear of the short-end antenna. | reference project B, README.md |
| Sensor orientation | Orientation was dictated by the reed switch and marker lines; RF clearance had to coexist with that geometry. | reference project B, README.md |
| Reset/range-test access | Leave the reset button accessible so range can be tested without disassembly. | reference project B, README.md |
| Vents | Aqara manual warning led to vents in the back wall. | reference project B, README.md |

## Range test in place

| Step | Action | Source |
|---|---|---|
| 1 | Assemble the device as it will be used, including lid, sensor, battery, and enclosure material. | reference project B range-test instruction |
| 2 | Put it where it will actually live or be worn. | reference project B: range-test in place, not on desk next to coordinator. |
| 3 | Trigger the vendor's range-test action if available. | reference project B uses a reset-button press for Aqara range test. |
| 4 | Watch the coordinator/system receive the event. | A transition is evidence; idle state is not. |
| 5 | Repeat after moving batteries, magnets, motors, or antenna routing. | general RF practice |

### Desk-test limitations

| Desk result | What it proves | What it does not prove |
|---|---|---|
| Pairs next to coordinator | Pairing flow and basic radio function. | Range through walls or in the final enclosure. |
| Works with lid open | Sensor/radio can talk in a favorable orientation. | Works closed, worn, shelved, or behind objects. |
| Works before battery/motor installed | Radio path before metal/magnetic masses were added. | Final RF performance. |
| Works over USB | Firmware and serial path. | Battery-powered RF current and brownout behavior. |

## Wi-Fi / Bluetooth coexistence notes

| Item | Rule | Attribution |
|---|---|---|
| ESP32 antenna area | Keep clear of metal and dense wiring; follow module keep-out. | general Espressif module practice |
| USB cable during tests | A cable can act as a ground/radiator and change behavior. | general RF bench practice |
| Battery-powered test | Repeat range/current tests on battery if the final product is battery powered. | general bench practice |
| Audio/motor noise | Route motor and class-D speaker wiring away from antenna and RF feed paths. | general layout practice; reference project A layout concerns |

## LoRa-specific design notes

| Item | Rule | Source |
|---|---|---|
| Gateway | reference project A LoRa stretch goal needs a second LoRa node at the PC as USB serial gateway. | reference project A, docs/pager-hardware-plan.md |
| Transport | Wi-Fi and LoRa must be two transports for one logical session, not two independent action paths. | reference project A, docs/pager-hardware-plan.md |
| Degraded mode | LoRa-only means status/answers may work while voice is unavailable; UI must say so. | reference project A, docs/pager-hardware-plan.md |
| TX current | E290 table lists LoRa TX from 150 mA at 5 dBm to 220 mA at 20 dBm. | reference project A, docs/e290-hardware-reference.md |
| Airtime/regulatory | Skill may flag as a design input; it cannot certify legality. | skill plan §8.1 |

## RF failure modes

| Symptom | Likely RF/mechanical cause | First action |
|---|---|---|
| Pairs only near coordinator | Antenna detuned, enclosure material, shielding, or poor location. | Range-test in place with enclosure assembled. |
| Works until held/worn | Body/hand absorption or antenna orientation. | Test in real use orientation. |
| LoRa TX resets board | TX current brownout, not necessarily RF stack bug. | Measure rail during TX. |
| Zigbee sensor stops reporting | Battery, range, or silent sensor failure. | Liveness automation and battery alert. (reference project B, README.md) |
| Range worsens after reprint | Material/filler/inserts/ribs changed near antenna. | Compare material and keep-out changes. |
| U.FL intermittent | Connector/cable strain or limited mating life. | Inspect connector and strain relief; avoid repeated mating. |

## RF checklist

| Check | Pass condition |
|---|---|
| Regional band locked | BOM names exact LoRa band before order. |
| Antenna present for TX | No transmit test runs without antenna or dummy load. |
| Connector physically inspected | U.FL/spring/PCB antenna contradiction resolved before CAD port. |
| Keep-out recorded | Battery, speaker magnet, motor, screws, inserts, wires excluded as required. |
| Filament allowed | No carbon-, metal-, or glass-filled material near antenna. |
| Range test in place | Final location/orientation tested with a transition. |
| Liveness check | Silent radio sensors have offline and battery alerts. |
| Brownout separated from RF | TX current measured before blaming protocol. |

