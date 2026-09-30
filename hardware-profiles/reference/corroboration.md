# Corroboration records

Load this before moving a profile out of `status: "draft"`, changing a GPIO map, or resolving contradictory sources. This is the policy for deciding how many independent sources support each load-bearing field group.

## Definition: independent source

| Situation | Count | Why | Source |
|---|---:|---|---|
| Two vendor pages with copied text. | 1 | Same authoring stream; duplicated prose is not new evidence. | (hardware-profiles task brief) |
| Product page plus generic FAQ. | 1 weak source, sometimes 0 for board-specific fields. | E290 FAQ named generic charger ICs while schematic showed LGS4056H. | (reference project A, docs/e290-hardware-reference.md) |
| Datasheet plus schematic from same vendor. | 2 weakly independent sources. | Different artefacts can disagree; schematic refdes/nets add evidence beyond prose. | (reference project A, docs/e290-hardware-reference.md) |
| Datasheet plus pinout PNG from same vendor. | Usually 1 weak source. | E290 PNG contained GPIO1/GPIO3 errors. | (reference project A, docs/e290-hardware-reference.md) |
| Arduino core variant header maintained outside the vendor PDF. | Independent candidate. | It is executable board support, but may still copy vendor files. | (reference project A, docs/e290-hardware-reference.md) |
| `boards.txt` board stanza. | Independent candidate for build settings. | E290 flash 8 MB in board definition matched runtime silicon. | (reference project A, docs/bring-up.md) |
| Meshtastic/ESPHome/Tasmota/CircuitPython board file. | Strong independent candidate. | Community firmware authors had to make the board operate. | (reference project A, docs/e290-hardware-reference.md) |
| Measurement on actual hardware. | Override for that field on that hardware. | Only measured values may be called verified. | (hardware-electronics, SKILL.md) |

## Independence is not provenance

| Term | Means | Does not mean |
|---|---|---|
| `datasheet` | Manufacturer document claim. | Independent of another manufacturer document. |
| `schematic` | Net or value read from schematic. | Populated on every shipped board. |
| `measured` | Instrument/API observed the actual hardware under stated conditions. | General truth for all revisions. |
| `vendor_claim` | Marketing/product-page claim. | Board-specific evidence if the page is boilerplate. |
| `seller_claimed` | Marketplace claim. | Safe input for CAD or power without measurement. |
| independent source | Separate evidence lineage. | Merely a different URL. |

## Corroboration record shape

| Field | Purpose | Example |
|---|---|---|
| `field_group` | What the sources support as a group. | `gpio_map`, `flash_size`, `battery_connector`, `mechanical_outline` |
| `claim` | Normalised value being considered. | `GPIO7 = VBAT_READ` |
| `profile_value` | Value written in JSON. | `consumed.7 = VBAT_READ` |
| `sources[]` | Evidence entries with provenance, citation, lineage, and agrees/disagrees. | Datasheet section, schematic refdes, variant header. |
| `independent_count` | Count after circular-copy collapse. | `3` for E290 GPIO map threshold. |
| `conflicts[]` | Disagreements retained, not hidden. | 18 uA vs 20 uA sleep current. |
| `resolution` | Why the profile value wins or remains unresolved. | `measured_silicon_overrides_docs` |
| `conservative` | Whether the profile only over-reserves uncertain resources. | `true` for pessimistic generic S3 flash/PSRAM pins. |
| `status_gate` | Whether this field group can leave draft. | `active_minimum_met` |

## Linter-enforced levels

| Level | Meaning | Typical result |
|---|---|---|
| `unresolved_conflict` | Sources disagree and no measured override or safe conservative choice exists. | Profile stays `draft` for that field group. |
| `single_claim` | One source lineage only. | Allowed for non-load-bearing notes; not enough for free-pin blessing. |
| `weak_corroboration` | Two weakly independent documents or one strong plus one weak. | May support warnings or conservative reservations. |
| `active_minimum_met` | Field-specific threshold is met after circular-copy collapse. | Field group may support an `active` profile. |
| `measured_override` | Hardware observation supersedes conflicting documents for the measured field. | Profile records supersession and conditions. |
| `conservative_active` | Profile may go active because uncertainty refuses resources rather than blesses them. | Generic profiles can reserve flash/PSRAM pins pessimistically. |

## Thresholds by field group

| Field group | Active threshold | Why | Source |
|---|---|---|---|
| GPIO map that marks pins free or reserved for board functions. | 3 independent sources, or measured hardware plus enough documents to identify the net. | A wrong free pin becomes a false clean pass in `pinmap_lint.py`. | (hardware-profiles task brief); (hardware-electronics, boards/heltec_vision_master_e290.json) |
| GPIO map that only over-reserves uncertain pins. | Weaker corroboration may pass with `conservative: true`. | Safe failure mode is refusing a pin that may have worked. | (hardware-profiles task brief) |
| Mechanical dimension used by CAD. | One direct measurement can beat any number of documents. | Calipers on the actual part answer the fit question. | (hardware-electronics, reference/measurement-discipline.md); (reference project B, README.md) |
| Flash size / memory capacity. | Board definition plus silicon measurement when conflict exists. | E290 product claim lost to runtime 8 MB. | (reference project A, docs/bring-up.md) |
| Charge-current setting. | Exact schematic revision plus resistor/constant validation if safety-relevant. | E290 rev V0.3.1 located R18=2 kOhm on PROG. | (reference project A, docs/e290-hardware-reference.md) |
| Connector pitch/pinout. | Schematic plus physical inspection or measurement before plugging power. | Polarity is not standardised; E290 battery pitch differs from QuickLink. | (reference project A, docs/bom.md); (hardware-electronics, parts/connectors.json) |
| Sleep current. | Measurement for runtime estimates; vendor claims may remain as claims. | E290 has 18 uA and 20 uA vendor conflict. | (reference project A, docs/e290-hardware-reference.md) |
| Antenna connector/existence. | Physical inspection or photo/teardown when vendor docs conflict. | E290 U.FL vs spring-antenna conflict remains unresolved. | (reference project A, docs/e290-hardware-reference.md) |
| I2C address of IC/module. | IC datasheet/module schematic; one source may be enough for fixed silicon address if exact part identity is solid. | DRV2605L fixed 0x5A; MCP23017 has strap range. | (hardware-electronics, parts/drv2605l-adafruit2305.json); (hardware-electronics, parts/mcp23017-waveshare.json) |

## Why GPIO needs a higher bar

| Reason | Consequence | Example |
|---|---|---|
| Validators trust profiles. | A wrong profile can make a wrong design look clean. | The task thesis names `pinmap_lint.py` as the confidence amplifier. (hardware-profiles task brief) |
| Same GPIO number can mean opposite things. | Generic family facts cannot answer board questions. | GPIO7 CrowPanel panel power-enable vs E290 VBAT_READ. (hardware-electronics, reference/esp32-gpio.md) |
| Board functions hide behind headers. | Broken-out is not free. | E290 header carries LoRa, e-ink, USB, battery, and strap nets. (hardware-electronics, boards/heltec_vision_master_e290.json) |
| Wrong free-pin blessing has an unsafe failure mode. | User may solder to a consumed net or brick boot. | GPIO45 strap pull-up can switch S3 flash voltage. (hardware-electronics, reference/esp32-gpio.md) |
| Over-reservation fails safely. | User loses a possible pin but avoids damage or false pass. | `esp32s3-generic` reserves flash/PSRAM pessimistically. (hardware-electronics, boards/esp32s3-generic.json) |

## Why mechanical measurement may need only one source

| Claim | Rule | Source |
|---|---|---|
| Calipers on actual part answer fit. | One measured dimension beats many seller claims for CAD. | (hardware-electronics, reference/measurement-discipline.md) |
| Fit coupons expose printer/material effects. | Seller dimensions still need a printed fit check when they drive plastic. | (reference project B, README.md) |
| Slotted holes do not locate. | Do not invent a hole diameter or locating post from a slot drawing. | (reference project A, docs/e290-hardware-reference.md) |
| Endpoint sweep is not bounded. | If the best fit is the edge of the sweep, measure farther that way. | (hardware-electronics, reference/measurement-discipline.md) |
| Measured on one sample is scoped. | Record board/part identity and conditions; do not generalise to all revisions. | (hardware-electronics, reference/measurement-discipline.md) |

## The `conservative: true` escape

| Allowed with `conservative: true` | Never allowed |
|---|---|
| Marking a pin unavailable because a conflict is unresolved. | Marking a pin free on weak evidence. |
| Reserving flash/PSRAM pins on a generic module profile. | Exposing memory-bus pins because a diagram does not label them. |
| Warning that an antenna connector is unresolved. | Adding an enclosure antenna cutout as if the connector exists. |
| Treating a header pin as consumed when it may be an onboard net. | Blessing a header pin when documents contradict each other. |
| Keeping status active for a profile whose uncertain fields only refuse use. | Leaving draft for any profile that blesses uncertain resources. |

### Safe failure mode test

| Question | If yes | If no |
|---|---|---|
| Does the profile only remove choices? | `conservative_active` may be possible. | Need stronger corroboration. |
| Could the user damage hardware by following the profile? | Must not rely on `conservative: true`. | Continue. |
| Could the linter report a clean pass for a wrong pin? | Must not go active. | Continue. |
| Is the unresolved field visible in `conflicts[]`? | Continue. | Record the conflict first. |
| Is there a path to close it by measurement or source? | Include `how_to_close`. | Explain why it remains unclosed. |

## Worked example: E290 GPIO map

| Evidence | Lineage | Contribution | Source |
|---|---|---|---|
| Datasheet section 2.2. | Vendor document. | Board pin/function table. | (reference project A, docs/e290-hardware-reference.md) |
| Schematic. | Vendor electrical drawing. | Nets for e-ink, LoRa, battery sense, QuickLink, straps. | (reference project A, docs/e290-hardware-reference.md) |
| `espressif/arduino-esp32` variant header. | Board support package. | Executable pin constants. | (reference project A, docs/e290-hardware-reference.md) |
| Meshtastic variant file. | Independent community firmware. | Practical board map. | (reference project A, docs/e290-hardware-reference.md) |
| Bring-up `g` command. | Measured hardware for free-pin behaviour. | GPIO17/40/41/42/47/48 reported free on the actual board. | (reference project A, docs/bring-up.md) |

| Field | Resolution |
|---|---|
| `GPIO1 = E-Ink SDI`, `GPIO3 = E-Ink CS` | Datasheet/schematic/firmware agreement beats pinout PNG. |
| `GPIO7 = VBAT_READ` | Board-specific profile prevents CrowPanel GPIO7 meaning from leaking in. |
| `GPIO17 free but ADC2_CH6` | Digital/I2S usable; not a Wi-Fi-time analog input. |
| `GPIO40/41/42 free` | Usable only with recorded JTAG cost. |
| `GPIO47/48 free` | Digital spares; not RTC wake capable. |
| `GPIO43/44 conditional` | Free only with USB CDC console; 44 cannot wake S3. |

## Worked example: memory conflict

| Source | Claim | Status | Resolution |
|---|---|---|---|
| Product/datasheet prose. | Flash 16 MB. | Conflict. | Loses to board definition and silicon. |
| Arduino board definition. | Flash 8 MB. | Supported by runtime. | Profile uses 8 MB. |
| Runtime `esp_flash_get_size()`. | Flash 8 MB. | `measured`. | Silicon beats documents. |
| Runtime PSRAM report without `BOARD_HAS_PSRAM`. | 0 usable. | Not a measured PSRAM size. | Profile leaves PSRAM size unmeasured. |

Source: (reference project A, docs/e290-hardware-reference.md); (reference project A, docs/bring-up.md)

## Worked example: vendor-document conflict

| Field | Claim A | Claim B | Profile action |
|---|---|---|---|
| Sleep current | 18 uA in table/product page. | 20 uA in datasheet text. | Record conflict; require measured deep-sleep current for runtime estimate. |
| 2.4 GHz antenna | U.FL in spec table/Meshtastic. | Spring antenna/no connector in FAQ. | Record unresolved; inspect physical board before enclosure RF cutout. |
| Sensor connector | SH2.0-4P product page. | SH1.0-4P datasheet/Meshtastic. | Prefer stronger sources but meter/inspect before crimping. |
| Charge IC | MCP73831/TP4054 FAQ. | LGS4056H schematic. | FAQ is boilerplate; schematic wins. |

Source: (reference project A, docs/e290-hardware-reference.md)

## Circular-citation trap

| Step | Bad count | Correct count |
|---|---:|---:|
| Vendor product page says `GPIO1 = CS`. | 1 | 1 weak |
| Pinout PNG repeats the product page. | 2 | 1 weak |
| Blog copies the PNG. | 3 | 1 weak |
| Community firmware copied Arduino variant without board bring-up notes. | 4 | 2 only if lineage differs; otherwise still circular. |
| Schematic shows `GPIO3 = CS`. | conflict | Add conflict; do not average. |
| Meshtastic variant independently uses `GPIO3 = CS`. | resolution candidate | Count as independent if lineage is separate. |

### How to detect circularity

| Signal | Action |
|---|---|
| Identical wording, same typo, same wrong label. | Collapse to one lineage. |
| Same image redistributed. | Collapse to image lineage. |
| Firmware file cites same vendor header. | Mark derivative unless evidence shows independent bring-up. |
| Values appear only after one upstream commit. | Count commit lineage once. |
| Source has no board-specific path or refdes. | Downgrade to weak or boilerplate. |

## Conflict handling

| Conflict type | Required action |
|---|---|
| Document vs measured hardware. | Use measured value for scoped hardware; retain superseded claim. |
| Datasheet vs schematic. | Prefer schematic for nets/refdes; keep datasheet conflict visible. |
| Board definition vs datasheet. | Prefer board definition for build settings; measure silicon when possible. |
| Product page vs schematic. | Treat product page as weak; check for boilerplate. |
| Community firmware vs vendor docs. | Investigate lineage; do not assume either is right. |
| Listing vs calipers. | Use measurement; listing remains `seller_claimed`. |

## Corroboration checklist

| Check | Pass condition |
|---|---|
| Field groups defined | Sources support named groups, not a vague profile. |
| Lineage recorded | Each source says who likely authored it and whether it copies another. |
| Count collapsed | `independent_count` excludes circular copies. |
| Conflicts retained | Losing claims stay in the record with why they lost. |
| Threshold matched | GPIO-free blessings meet the higher threshold. |
| Conservative escape justified | It only refuses uncertain resources. |
| Measurement scoped | Hardware observations include date, method, board identity, and conditions. |
| Draft gate clear | No active profile has unresolved load-bearing blessings. |
