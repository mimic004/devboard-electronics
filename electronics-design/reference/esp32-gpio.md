# ESP32 GPIO restrictions and board profiles

Load this when allocating ESP32-family pins, answering a pin-availability question, or reviewing a board bring-up plan. A pin question can never be answered without a board ID: the same GPIO number may mean opposite things on two ESP32-S3 boards.

## First rule: name the board before naming a pin

| Rule | Why | Source |
|---|---|---|
| Require a board ID before answering any pin question. | Generic ESP32-S3 facts are not enough; board wiring consumes pins before the user touches them. | general engineering rule; reference project A, docs/e290-hardware-reference.md |
| Treat the board definition and measured silicon as higher priority than a datasheet table. | Heltec's E290 flash claim conflicted with the board definition; the chip reported 8 MB at runtime. | reference project A, docs/e290-hardware-reference.md; docs/bring-up.md |
| Namespaced board profiles prevent false grep answers. | `GPIO7` is panel power-enable on the CrowPanel 2.13 v1 but VBAT_READ on the Heltec E290. | reference project A, docs/hardware-findings.md; docs/e290-hardware-reference.md |
| Never infer a free pin from a single `grep GPIO n` hit. | Old board documents can remain in a repo after the hardware choice changes. | skill plan §12.2 |
| If silicon disagrees with prose, record a measured supersession. | The E290 16 MB flash claim became 8 MB only after a runtime read. | reference project A, docs/bring-up.md |

### Board-ID example: GPIO7

| Board | GPIO7 role | Consequence |
|---|---|---|
| CrowPanel 2.13 v1 | Panel power-enable; must be high before refresh. | With it low, every e-paper refresh appeared to succeed in about 29 ms. Treat implausibly fast success as a fault. (reference project A, docs/hardware-findings.md) |
| Heltec Vision Master E290 | VBAT_READ, ADC1_CH6, battery divider sense path. | A battery reading on USB reports the charger BAT float voltage, not state of charge. (reference project A, docs/e290-hardware-reference.md; docs/bring-up.md) |

## ESP32-S3 family restrictions

| Item | ESP32-S3 rule | Design consequence | Source |
|---|---|---|---|
| Input-only pins | None in the classic ESP32 sense. | Do not reject GPIO34-39 as input-only on S3; that rule belongs to classic ESP32. | reference project A, docs/e290-hardware-reference.md |
| Strapping pins | GPIO0, GPIO3, GPIO45, GPIO46. | Avoid external pulls and loads that change boot state. | reference project A, docs/e290-hardware-reference.md |
| GPIO45 strap | Selects VDD_SPI voltage at boot. | An external pull-up can switch flash to 1.8 V and brick boot. | reference project A, docs/e290-hardware-reference.md |
| GPIO46 strap | Strapping pin; on E290 also battery-divider enable. | On E290 it must be low at boot; firmware drives it high after boot only. Never add an external pull-up. | reference project A, docs/e290-hardware-reference.md |
| RTC-capable pins | GPIO0-GPIO21 only. | A deep-sleep wake source cannot live on GPIO44 or other 38-48 header pins. | reference project A, docs/e290-hardware-reference.md; docs/pager-hardware-plan.md |
| ADC1 | GPIO1-GPIO10. | ADC1 may already be entirely consumed by board functions. | reference project A, docs/e290-hardware-reference.md |
| ADC2 | Exists, but is unusable while Wi-Fi driver is active. | `adc2_get_raw()` returns `ESP_ERR_TIMEOUT` with Wi-Fi active; do not use ADC2 for UI controls on a Wi-Fi product. | reference project A, docs/pager-hardware-plan.md |
| Flash bus | GPIO26-GPIO32. | Treat as reserved unless a board profile explicitly exposes otherwise. | reference project A, docs/e290-hardware-reference.md |
| PSRAM bus | GPIO33-GPIO37. | Treat as reserved; on E290 size/init is unmeasured even though pins are consumed. | reference project A, docs/e290-hardware-reference.md |
| Native USB | GPIO19/GPIO20. | Preserve if USB CDC/JTAG is needed; they are not general spare pins on USB boards. | reference project A, docs/e290-hardware-reference.md |
| Hardware JTAG | GPIO40/GPIO41/GPIO42 carry MTDO/MTDI/MTMS. | Using them as normal GPIO costs hardware JTAG; USB-Serial-JTAG can still work on GPIO19/20. | reference project A, docs/e290-hardware-reference.md |
| GPIO matrix | Many digital peripherals can route to many pins. | Routing freedom does not override straps, RTC wake, ADC, flash, PSRAM, USB, or board-reserved nets. | general ESP32-S3 architecture |

### ESP32-S3 quick screen

| Question | Safe answer pattern |
|---|---|
| Can I use GPIO34-39 as outputs on S3? | Family-wise, yes; S3 has no classic input-only GPIOs. Still check the board profile. |
| Can a wake interrupt use GPIO44? | No for ESP32-S3 EXT0/EXT1 deep-sleep wake; RTC pins are GPIO0-GPIO21 only. |
| Can a resistor ladder use a free ADC2 pin while Wi-Fi runs? | No. Treat ADC2-with-Wi-Fi as a design error. |
| Can GPIO45 have a pull-up? | No. It is a VDD_SPI strap and a pull-up can break boot. |
| Can I spend GPIO40/41/42? | Yes only if losing hardware JTAG is acceptable and the board profile marks them free. |

## Classic ESP32 restrictions

| Item | Classic ESP32 rule | Design consequence | Source |
|---|---|---|---|
| Input-only pins | GPIO34-GPIO39 are input-only. | They cannot drive LEDs, chip selects, power enables, buzzers, or outputs. | general ESP32 documentation |
| ADC2 with Wi-Fi | ADC2 is unavailable while Wi-Fi is active. | Same trap as S3: avoid ADC2 for controls on Wi-Fi devices. | general ESP32 documentation; mirrored by reference project A ADC2 finding |
| Strapping pins | Board-specific set includes common boot straps such as GPIO0, GPIO2, GPIO4, GPIO5, GPIO12, GPIO15. | Check the exact module and dev board; external pulls can change boot mode or flash voltage. | general ESP32 documentation |
| Flash pins | Module-dependent; many boards consume GPIO6-GPIO11 for flash. | Do not use unless the board vendor explicitly exposes and documents them. | general ESP32 documentation |
| RTC wake | Subset of RTC GPIOs only. | Board profile must list wake-capable pins rather than relying on a generic header diagram. | general ESP32 documentation |

### Classic ESP32 quick screen

| Question | Safe answer pattern |
|---|---|
| Can GPIO34 drive a relay input? | No. GPIO34-GPIO39 are input-only on classic ESP32. |
| Can I put an analog keypad on ADC2? | Not if Wi-Fi will ever be active during reads. |
| Are pins with silkscreen labels automatically usable? | No. Check flash, straps, onboard peripherals, and module variant. |

## Heltec Vision Master E290 board-specific map

Board-specific facts in this section apply only to the Heltec Vision Master E290, not to other ESP32-S3 boards. Source rows are document/schematic/firmware cross-checks unless a measurement is explicitly named.

| GPIO | E290 role | Use in a new design? | Source |
|---|---|---|---|
| 0 | BOOT button plus strapping. | Avoid except as existing button/wake input. | reference project A, docs/e290-hardware-reference.md |
| 1 | E-ink SDI / MOSI. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 2 | E-ink CLK. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 3 | E-ink CS plus strapping. | Reserved; do not add pull changes. | reference project A, docs/e290-hardware-reference.md |
| 4 | E-ink D/C. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 5 | E-ink RST. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 6 | E-ink BUSY. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 7 | VBAT_READ, ADC1_CH6. | Use board battery-sense path, not general GPIO. | reference project A, docs/e290-hardware-reference.md |
| 8 | LoRa NSS. | Reserved if LoRa may ever be used. | reference project A, docs/e290-hardware-reference.md |
| 9 | LoRa SCK. | Reserved if LoRa may ever be used. | reference project A, docs/e290-hardware-reference.md |
| 10 | LoRa MOSI. | Reserved if LoRa may ever be used. | reference project A, docs/e290-hardware-reference.md |
| 11 | LoRa MISO. | Reserved if LoRa may ever be used. | reference project A, docs/e290-hardware-reference.md |
| 12 | LoRa RESET. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 13 | LoRa BUSY. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 14 | LoRa DIO1 / IRQ; header pin documentation contradictory. | Do not use header pin 11. | reference project A, docs/e290-hardware-reference.md |
| 15/16 | 32.768 kHz crystal. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 17 | Free, ADC2_CH6. | Digital/I2S possible; not a Wi-Fi-time analog input. | reference project A, docs/e290-hardware-reference.md; docs/pager-hardware-plan.md |
| 18 | Vext, gates e-ink 3V3, active high. | Reserved for panel power. | reference project A, docs/e290-hardware-reference.md |
| 19/20 | USB D- / D+. | Reserved for native USB. | reference project A, docs/e290-hardware-reference.md |
| 21 | USER button. | Candidate RTC wake input; proposed expander INT diode-OR with USER. | reference project A, docs/e290-hardware-reference.md; docs/pager-hardware-plan.md |
| 26-32 | SPI flash; flash measured 8 MB. | Reserved. | reference project A, docs/e290-hardware-reference.md; docs/bring-up.md |
| 33-37 | PSRAM bus; size/init unmeasured. | Reserved. | reference project A, docs/e290-hardware-reference.md |
| 38 | QuickLink I2C SCL. | Use as I2C bus, not spare GPIO. | reference project A, docs/e290-hardware-reference.md |
| 39 | QuickLink I2C SDA. | Use as I2C bus, not spare GPIO. | reference project A, docs/e290-hardware-reference.md |
| 40 | Free, JTAG MTDO. | Usable if JTAG cost accepted. | reference project A, docs/e290-hardware-reference.md; docs/bring-up.md |
| 41 | Free, JTAG MTDI. | Usable if JTAG cost accepted. | reference project A, docs/e290-hardware-reference.md; docs/bring-up.md |
| 42 | Free, JTAG MTMS. | Usable if JTAG cost accepted. | reference project A, docs/e290-hardware-reference.md; docs/bring-up.md |
| 43/44 | UART0 TX/RX; free if console uses USB CDC. | Conditional spares; not RTC wake capable. | reference project A, docs/e290-hardware-reference.md |
| 45 | LED_POWER plus VDD_SPI strapping. | Do not use or pull. | reference project A, docs/e290-hardware-reference.md |
| 46 | ADC_CTRL plus strapping. | Reserved for battery divider enable; never pull up externally. | reference project A, docs/e290-hardware-reference.md |
| 47/48 | Free SPICLK_P/N. | Usable as digital pins if board profile allows. | reference project A, docs/e290-hardware-reference.md; docs/bring-up.md |

### E290 free-pin budget

| Category | Pins | Notes |
|---|---|---|
| Free pins measured by reference project A bring-up | 17, 40, 41, 42, 47, 48 | The `g` command reported all six free on hardware. (reference project A, docs/bring-up.md) |
| Conditional spares | 43, 44 | Only if serial console runs over USB CDC; cannot wake from deep sleep. |
| I2C already assigned | 39 SDA, 38 SCL | QuickLink connector; a good place for MCP23017/DRV2605L. |
| Proposed wake interrupt | 21 | RTC capable and already a USER button; diode-OR proposal for MCP23017 INT. |
| Audio allocation in reference project A | 41/42/40 to I2S mic, 47/48/17 to I2S amp | Consumes all six measured-free pins. (reference project A, docs/pager-hardware-plan.md) |

## CrowPanel 2.13 v1 board-specific map

This is a different board from the E290 and must not be mixed with it.

| GPIO | CrowPanel v1 measured role | Source |
|---|---|---|
| 1 | Back / Exit button, active low with internal pull-up. | reference project A, docs/hardware-findings.md |
| 2 | Menu / Home button, active low with internal pull-up. | reference project A, docs/hardware-findings.md |
| 4 | Wheel down switch, active low. | reference project A, docs/hardware-findings.md |
| 5 | Wheel confirm switch, active low. | reference project A, docs/hardware-findings.md |
| 6 | Wheel up switch, active low. | reference project A, docs/hardware-findings.md |
| 7 | Panel power-enable; must be high. | reference project A, docs/hardware-findings.md |
| 19 | Power LED. | reference project A, docs/hardware-findings.md |
| 40/41 | I2C header used in `Wire.begin(40, 41, 100000)`. | reference project A, docs/hardware-findings.md |

## ADC allocation rules

| Rule | Detail | Source |
|---|---|---|
| Prefer ADC1 for user analog measurements. | ADC1 remains usable when Wi-Fi is active; board functions may consume it. | general ESP32 rule |
| Reject ADC2-with-Wi-Fi designs. | On the E290, GPIO17 was the only free analog pin and it was ADC2_CH6; the keypad ladder idea died because Wi-Fi is required. | reference project A, docs/pager-hardware-plan.md |
| Do not present resistor ladders as pin-saving unless analog constraints are checked. | A ladder saves GPIO only if a legal ADC channel is available in the operating mode. | reference project A, docs/pager-hardware-plan.md |
| On E290, no free ADC1 channel exists. | GPIO1-GPIO10 are consumed by e-ink, VBAT sense, and LoRa lines. | reference project A, docs/e290-hardware-reference.md |
| Use a digital expander when the ADC gate fails. | reference project A moved keypad input to an MCP23017 at I2C address 0x20. | reference project A, docs/pager-hardware-plan.md; docs/bom.md |

## Deep-sleep wake rules

| Rule | Detail | Source |
|---|---|---|
| Wake source must be RTC-capable. | On ESP32-S3, that means GPIO0-GPIO21 only. | reference project A, docs/e290-hardware-reference.md |
| I2C expander interrupt must land on an RTC pin if it wakes the chip. | GPIO44 cannot be used for E290 expander INT wake. | reference project A, docs/pager-hardware-plan.md |
| Wake design may need diode-OR or other isolation. | reference project A proposed diode-OR to share GPIO21 with the USER button. | reference project A, docs/pager-hardware-plan.md |
| A digital input can be electrically valid but sleep-invalid. | GPIO40/41/42/47/48 were measured free but cannot provide S3 deep-sleep wake. | reference project A, docs/bring-up.md; docs/e290-hardware-reference.md |

## Board definition beats the datasheet

| Case | What happened | Lesson |
|---|---|---|
| E290 flash size | Datasheet/teardown claim conflicted with board definition; runtime read measured 8 MB. | Do not hand-select generic flash settings from intuition. Use the vendor board definition and identify silicon. (reference project A, docs/bring-up.md) |
| E290 PSRAM | Datasheet and chip suffix imply PSRAM, but Arduino board definition does not define `BOARD_HAS_PSRAM`; the core reports unavailable. | A 0 PSRAM report can be expected, not a board fault, until measured with a build that enables it. (reference project A, docs/e290-hardware-reference.md) |
| E290 GPIO1/GPIO3 | Heltec pin map PNG swaps e-ink signals; datasheet/schematic/firmware variants agree otherwise. | A vendor image is lower provenance than multiple source documents and firmware definitions. (reference project A, docs/e290-hardware-reference.md) |
| Board selection | Generic ESP32S3 Dev Module plus guessed options gave OPI PSRAM and 16 MB flash; both contradict the E290 profile. | Select `esp32:esp32:heltec_vision_master_e290` and change nothing. (reference project A, docs/bring-up.md) |

## Pin-allocation checklist

| Check | Pass condition |
|---|---|
| Board ID named | Exact board, revision, and profile file are known. |
| Reserved nets removed | Flash, PSRAM, USB, LoRa, panel, crystal, and onboard buttons are marked consumed. |
| Straps reviewed | No external pulls or loads alter GPIO0/3/45/46 on S3, especially GPIO45. |
| ADC reviewed | Analog nets use ADC1 when Wi-Fi is active, or the design changes architecture. |
| Wake reviewed | Sleep-wake nets are on RTC-capable pins. |
| JTAG cost accepted | Use of GPIO40/41/42 records loss of hardware JTAG. |
| Board contradictions recorded | Any discrepancy is tagged with provenance; only hardware measurements may be called measured. |
| Output/input family rules applied | Classic ESP32 GPIO34-39 input-only; ESP32-S3 has no such input-only group. |
