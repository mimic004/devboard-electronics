# Sourcing hardware profiles

Load this when creating or reviewing a board or part profile source list. It ranks where authoritative data usually lives, what each source can and cannot support, and how to cite evidence so another agent can re-check it.

## Core sourcing rules

| Rule | Meaning | Source |
|---|---|---|
| Use the parent provenance ladder exactly. | `assumed`, `inferred`, `seller_claimed`, `vendor_claim`, `simulated`, `datasheet`, `schematic`, `measured`; only `measured` may be called verified. | (electronics-design, SKILL.md) |
| A profile is data, not prose. | A wrong board profile lets `pinmap_lint.py` bless a wrong pin map; the E290 GPIO corroboration used to live only in a prose `notes` string. | (electronics-design, boards/_schema.json); (electronics-design, boards/heltec_vision_master_e290.json) |
| Always name the exact board. | GPIO7 is panel power-enable on CrowPanel 2.13 v1 and VBAT_READ on Heltec E290. | (electronics-design, boards/crowpanel_213_v1.json); (electronics-design, boards/heltec_vision_master_e290.json) |
| The board definition beats the datasheet, and silicon beats both. | E290 flash was claimed as 16 MB in prose, encoded as 8 MB in the board definition, and measured as 8 MB at runtime. | (reference project A, docs/e290-hardware-reference.md); (reference project A, docs/bring-up.md) |
| A product page may be boilerplate. | Heltec FAQ named MCP73831/TP4054 generically; E290 schematic shows LGS4056H. | (reference project A, docs/e290-hardware-reference.md) |
| Cite enough identity to re-check later. | File path, section/table, revision, commit or package version, board revision, and measurement conditions are part of the evidence. | (electronics-design, reference/measurement-discipline.md) |

## Reliability ladder for board profiles

| Rank | Source class | Best for | Bad for | Citation minimum |
|---:|---|---|---|---|
| 1 | `measured` silicon or bench observation | Flash size, live pin state, actual current, connector polarity, fit dimensions, wake behaviour. | Explaining why a vendor made a choice; broad family limits unless measured across samples. | Instrument/API, date, board ID/revision, firmware build, conditions. (electronics-design, reference/measurement-discipline.md) |
| 2 | Board definition / build system | Flash/PSRAM settings, USB mode, FQBN, enabled peripherals, variant binding. | Mechanical dimensions; undocumented nets; uninitialised PSRAM size. | Package/core, version, file path such as `boards.txt`, FQBN, option line. (reference project A, docs/e290-hardware-reference.md) |
| 3 | Schematic, exact revision | Nets, charge IC, resistor values, connector pin order, power gates, hidden consumers. | Physical connector orientation unless drawing is unambiguous; assembled dimensions; variant stock substitutions. | Vendor, title, revision, page/sheet, refdes and net name. (reference project A, docs/e290-hardware-reference.md) |
| 4 | Manufacturer datasheet | Official pin tables, mechanical drawings, ratings, module variants. | Marketing copy conflicts; stale revision history; pinout PNGs; board options not reflected in build definition. | Vendor, document title, revision/date, section/table/page. (reference project A, docs/e290-hardware-reference.md) |
| 5 | Vendor SDK / HAL / variant header | Pin constants the vendor's examples actually compile against. | Values copied from older docs; example-only aliases; boards not in package. | Repo/package, version or commit, path, symbol name. (reference project A, docs/e290-hardware-reference.md) |
| 6 | Independent community firmware | Practical pin maps made by people who had to make hardware function. | Circular copies from Arduino core; board revisions outside the firmware's target. | Project, commit/release, path, board ID, symbol. (reference project A, docs/e290-hardware-reference.md) |
| 7 | FCC filings / teardown photos | Antenna presence, module markings, connector existence, component identity. | Runtime settings, pin multiplexing, firmware defaults, exact values hidden under shields. | Filing ID or photo source, image/page, board side, visible marking. (general engineering knowledge) |
| 8 | Marketplace listing / product page | Ordering variant, rough dimensions, included accessories, seller-only names. | Memory sizes, current, connector family, IC identity, dimensions that drive CAD. | Seller/vendor, page title, date accessed, exact claim. Tag `seller_claimed` or `vendor_claim`. (electronics-design, SKILL.md) |

## Source classes in detail

| Source | Treat as | Use it for | Do not use it for | Re-check citation |
|---|---|---|---|---|
| Manufacturer datasheet | `datasheet` | MCU family limits, official signal tables, drawing dimensions, rated voltages. | Conflict resolution when board definition or silicon disagrees. | Document title, revision, section/table; quote only the field. |
| Schematic | `schematic` | Nets that no pinout diagram shows: flash, PSRAM, charge IC, divider enables, connector pins. | Assuming shipped population if BOM alternatives exist. | Schematic revision matters: E290 rev V0.3.1 settled R18 as 2 kOhm on PROG. (reference project A, docs/e290-hardware-reference.md) |
| Arduino `variants/<board>/pins_arduino.h` | source-specific corroboration | Default pin aliases, board-specific constants, display/LoRa/I2C definitions. | Power/current/mechanical facts. | Package name/version, path, symbol names. |
| Arduino `boards.txt` | source-specific corroboration | FQBN, flash size, PSRAM mode, USB defaults, build flags. | Evidence that hardware physically has usable PSRAM. | Core version and exact board stanza. |
| Vendor SDK / HAL header | source-specific corroboration | Vendor example constants, reset pins, panel command paths. | Treating example success as physical measurement. | Repo/release, file path, macro name. |
| Meshtastic / ESPHome / Tasmota / CircuitPython board files | independent source candidate | Practical pin maps, wake lines, buses, RF chips, board aliases. | Blind counting when they copied the same upstream header. | Project, commit/release, path, symbol. |
| Board profile JSON | profile data | Machine-readable fields the validators consume. | Original evidence; profile JSON is not its own source. | Profile id/version and its sources list. |
| FCC / teardown photo | visual evidence | Whether a connector, antenna, module marking, or charge IC is present. | Current, flash size, firmware setup. | Filing/photo identity and visible marking. |
| Product page / listing | `vendor_claim` / `seller_claimed` | Order code, regional band, approximate package, included accessories. | Load-bearing pin maps, capacities, connector pitch, dimensions without measurement. | Page title/date and exact wording. |

## Per-family authoritative pin-data pointers

| Family | First place to look | Second place | Community cross-check | Common non-document check |
|---|---|---|---|---|
| ESP32 / ESP32-S3 / ESP32-C3 | Espressif Arduino core `variants/<board>/pins_arduino.h` plus `boards.txt`. | Exact schematic and Espressif datasheet/TRM family restrictions. | Meshtastic, ESPHome, Tasmota, CircuitPython definitions for the same board. | `board_cli.py identify` for flash; firmware GPIO probe for free pins. (electronics-design, SKILL.md) |
| RP2040 | Board vendor schematic plus Pico/RP2040 datasheets for generic limits. | Arduino/Mbed/CircuitPython board definition for named boards. | CircuitPython board directory and Pico SDK board headers. | Physical breakout and flash package markings; measure board-specific dimensions. (electronics-design, boards/rp2040-generic.json) |
| nRF52 | Board vendor schematic and Nordic board definitions in Zephyr/nRF Connect SDK. | Manufacturer datasheet for package pins and low-power features. | Zephyr board devicetree, Arduino variant, CircuitPython board files. | Current must be measured in the target sleep mode. (general engineering knowledge) |
| STM32 | CubeMX `.ioc` or board support package plus schematic. | ST datasheet/reference manual for alternate-function availability. | Zephyr devicetree, Arduino variant, PlatformIO board JSON. | Boot straps and oscillator population on the actual board. (general engineering knowledge) |
| AVR | Arduino variant/pins file for board labels. | Schematic and Microchip/Atmel datasheet for port pins and timers. | PlatformIO board JSON and community core variant files. | Measure voltage domain and oscillator if timing matters. (general engineering knowledge) |

## ESP32-family source ordering

| Field group | Preferred evidence | Why |
|---|---|---|
| GPIO map | Datasheet table + schematic + Arduino variant + independent firmware variant. | E290's map is supported by at least three of these four sources. (electronics-design, boards/heltec_vision_master_e290.json) |
| Flash size | Board definition, then measured runtime flash size. | E290 product prose lost to `boards.txt` and runtime 8 MB reading. (reference project A, docs/bring-up.md) |
| PSRAM | Board definition for init mode; runtime build that enables PSRAM for size. | E290 reports 0 because `BOARD_HAS_PSRAM` is not defined; that is not a measured size. (reference project A, docs/e290-hardware-reference.md) |
| USB pins/mode | `boards.txt`, variant header, schematic. | Native USB consumes GPIO19/20 on E290. (electronics-design, boards/heltec_vision_master_e290.json) |
| Straps and RTC | Family datasheet plus exact board consumers. | S3 GPIO0/3/45/46 straps and GPIO0-21 RTC range are not optional; E290 commits all four straps. (electronics-design, reference/esp32-gpio.md) |
| ADC usability | Family rules plus board reservations. | ADC2 with Wi-Fi is a design trap; E290 has no free ADC1 channel. (electronics-design, reference/esp32-gpio.md) |

## Mechanical source ordering

| Field | Strongest ordinary source | Stronger if available | Warning |
|---|---|---|---|
| PCB outline | Manufacturer mechanical drawing. | Caliper measurement on the actual board. | Board revisions may change silently; cite revision. |
| Assembled height | Manufacturer drawing if it includes fitted connectors. | Calipers on the exact assembly. | Header height dominated the E290 stack. (reference project A, docs/e290-hardware-reference.md) |
| Active display area | Panel datasheet. | Visual coupon/measurement that fixes sign and offset. | E290 active area is off-centre along the long axis. (reference project A, docs/bring-up.md) |
| Mounting holes | Mechanical drawing. | Calipers if round; visual if slots. | E290 holes are slots with no size, so locating posts are invalid. (reference project A, docs/e290-hardware-reference.md) |
| Connector protrusion | Measurement. | None. | E290 USB protrusion was not dimensioned. (reference project A, docs/e290-hardware-reference.md) |
| Fit-critical seller dimensions | Caliper measurement plus fit coupon. | None. | Seller-claimed switch height must not drive a print alone. (reference project A, docs/bom.md) |

## Part-profile source ordering

| Field | Preferred evidence | Notes |
|---|---|---|
| Footprint W/L/H | Manufacturer datasheet or measured sample. | If seller-only, tag `seller_claimed` and require fit coupon before CAD. (electronics-design, parts/_schema.json) |
| `height_includes` | Datasheet drawing or measured reference plane. | Tactile switch W x L x H often means to plunger top. (reference project A, docs/bom.md) |
| I2C address | IC datasheet and module schematic. | DRV2605L is fixed at 0x5A; MCP23017 spans 0x20-0x27 by straps. (electronics-design, parts/drv2605l-adafruit2305.json); (electronics-design, parts/mcp23017-waveshare.json) |
| On-module pull-ups | Module schematic or resistor measurement. | MCP23017 module records 10 kOhm so bus stacking can be counted. (electronics-design, parts/mcp23017-waveshare.json) |
| 5 V tolerance | IC/module datasheet. | SPH0645LM4H is not 5 V tolerant; MAX98357A profile says true. (electronics-design, parts/sph0645lm4h-adafruit3421.json); (electronics-design, parts/max98357a-adafruit3006.json) |
| Failure mode | System behaviour analysis plus source example. | Silent parts require a liveness check. (electronics-design, SKILL.md); (reference project B, README.md) |

## Citation patterns

| Evidence | Good citation | Bad citation |
|---|---|---|
| Source document | `Heltec HT-VME290 schematic rev V0.3.1, U6/R18/PROG` | `Heltec docs` |
| Firmware file | `espressif/arduino-esp32 3.3.11, variants/heltec_vision_master_e290/pins_arduino.h, EINK_SDI` | `Arduino says` |
| Board definition | `esp32:esp32 core 3.3.11, boards.txt, heltec_vision_master_e290.flash_size=8MB` | `board menu` |
| Community variant | `meshtastic/firmware, variants/esp32s3/heltec_vision_master_e290/variant.h, LORA_DIO1` | `Meshtastic` |
| Measurement | `esp_flash_get_size(), COM7, 2026-09-17, stock esp32:esp32 3.3.11` | `runtime says` |
| Photo/teardown | `photo filename, side, visible marking U6=LGS4056H` | `looked at board` |

## Source red flags

| Red flag | Treat as | Example |
|---|---|---|
| One vendor page covers an entire product range. | Boilerplate, not board-specific. | Heltec FAQ charge-IC claim conflicts with E290 schematic. (reference project A, docs/e290-hardware-reference.md) |
| Link contains a space or rewritten filename. | Fetch may fail; preserve working path if known. | Heltec docs page links a datasheet filename with a space that 404s. (reference project A, docs/e290-hardware-reference.md) |
| Pinout PNG disagrees with schematic/header files. | Weak visual aid. | E290 PNG swapped GPIO1/GPIO3 e-ink roles. (reference project A, docs/e290-hardware-reference.md) |
| Product listing invents memory capacity. | `vendor_claim` or `seller_claimed` until measured. | E290 16 MB flash claim lost to 8 MB runtime. (reference project A, docs/bring-up.md) |
| Header label exists. | Broken out, not free. | E290 header exposes LoRa and panel nets that are consumed. (electronics-design, boards/heltec_vision_master_e290.json) |
| Multiple docs use identical wording. | Candidate circular copy. | Count source families, not pages. (board-profiles task brief) |

## What not to cite as load-bearing evidence

| Item | Why |
|---|---|
| A prose `notes` string in the same profile. | It is not machine-readable corroboration and cannot be counted by a linter. |
| A product hero image. | It can be stale, stylised, or for another revision. |
| A seller's package title. | It often mixes search terms with facts. |
| A single grep hit for `GPIO7`. | Same number, different board meanings. (electronics-design, reference/esp32-gpio.md) |
| A static e-ink image. | E-ink persists with no power; require a watched transition. (reference project A, docs/bring-up.md) |
| Runtime PSRAM `0` without enabling PSRAM. | It may mean the core never initialised it, not that no PSRAM exists. (reference project A, docs/e290-hardware-reference.md) |

## Source-list checklist

| Check | Pass condition |
|---|---|
| Exact board identity | Vendor name, model, revision if known, and profile id. |
| Source identity | Every source has path/section/revision/commit/package version where available. |
| Provenance tag | Every field group carries the parent vocabulary tag. |
| Independence note | Corroboration record says which sources are independent and which copy each other. |
| Contradictions retained | Disagreements stay visible; do not erase losing claims without a supersession note. |
| Measurement conditions | Hardware observations include instrument/API, date, firmware, and setup. |
| Product page downgraded | Vendor pages and marketplace listings never outrank schematic, board definition, or silicon. |
| Re-check possible | Another agent can locate the same source without relying on this author's memory. |

## Board-definition details to capture

| Field | Why it matters | Citation target |
|---|---|---|
| FQBN / board id | Selects the variant header and build defaults. | Board stanza name and package version. |
| Flash size option | May contradict product prose. | `boards.txt` key and runtime reading if measured. |
| Partition scheme | Storage plan follows the actual flash ceiling. | Board definition value; do not infer extra space. |
| PSRAM type | QSPI/OPI choice consumes different assumptions. | Board definition key plus PSRAM enable flag. |
| `BOARD_HAS_PSRAM` or equivalent | A zero runtime reading may mean no init, not no chip. | Build flags and runtime method. |
| USB CDC/JTAG flags | Determine whether UART0 pins are conditional spares. | Build flags and profile `conditional_free`. |
| Variant path | Ties board id to pin aliases. | `variants/<board>/pins_arduino.h` path. |
| Core version | Board definitions change over time. | Package name and release number. |

## Schematic details to capture

| Field | Cite | Why |
|---|---|---|
| Refdes | `U6`, `R18`, `JP1`, etc. | Prevents nearby-part mixups such as LED resistor vs PROG resistor. |
| Net name | `ADC_CTRL`, `VBAT_READ`, `QL_SDA`. | Carries meaning across pages. |
| Revision | `V0.3.1` or exact title block. | E290 charge-current evidence depended on schematic revision. |
| Page/sheet | Sheet number or PDF page. | Lets another agent find the net. |
| Population caveat | DNP/alternate values if present. | Schematic is not always shipped BOM. |
| Connector symbol pin order | Pin order is still a claim until metered for power. | Avoids crimping from an unqualified drawing. |

## Community-firmware caveats

| Caveat | Action |
|---|---|
| Board file may support multiple revisions. | Record the target board/revision if named. |
| Constants may be copied from Arduino core. | Check comments/history before counting as independent. |
| Firmware may omit unused peripherals. | Absence does not free a pin. |
| Firmware may carry stretch-goal hardware. | Keep radio/display pins reserved if hardware exists. |
| Path names may lag product names. | Cite path and display name. |
| A compile-time alias is not a measurement. | Use it as corroboration, not as `measured`. |

## Measurement-source caveats

| Measurement | Scope limit |
|---|---|
| Flash runtime size | Applies to that board/chip and firmware method. |
| Free-pin GPIO probe | Applies to observed idle state; still cite schematic for net identity. |
| Caliper dimension | Applies to that sample/revision and measurement conditions. |
| Current draw | Applies to rail, mode, battery/USB state, firmware, and peripherals. |
| Connector polarity | Applies to that board/cable; do not assume another harness. |
| Fit coupon | Applies to printer, material, orientation, and slicer settings. |
