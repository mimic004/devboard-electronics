# Common profile traps

Load this when auditing a plausible board or part profile for mistakes that survive ordinary review. Each row gives the symptom, why it passes a quick read, and the check that catches it.

## Board-profile traps

| Trap | Symptom in profile | Why it survives review | Check that catches it |
|---|---|---|---|
| Copying classic ESP32 rules into ESP32-S3. | S3 profile lists GPIO34-39 as input-only. | Classic ESP32 really has input-only 34-39, so the row looks familiar. | Compare family profile: ESP32-S3 `input_only` is empty. (hardware-electronics, boards/esp32s3-generic.json); (hardware-electronics, boards/esp32-classic.json) |
| Assuming absence means free. | Pin absent from datasheet table becomes `free`. | Documents often omit flash, PSRAM, USB, crystals, buttons, and board nets. | Require schematic/variant/header corroboration before `free`. (hardware-profiles task brief) |
| Trusting pinout PNG over variant header. | GPIO1/GPIO3 e-ink roles swapped. | PNG is visual and official-looking. | Cross-check schematic, datasheet table, Arduino variant, community variant. (reference project A, docs/e290-hardware-reference.md) |
| Forgetting flash pins. | SPI flash pins exposed as normal GPIO. | Header diagrams may not draw internal memory bus. | Family profile reserves flash bus; identify silicon for capacity. (hardware-electronics, boards/esp32s3-generic.json) |
| Forgetting PSRAM pins. | GPIO33-37 shown as free on S3 module. | Runtime PSRAM may read 0 if not enabled, tempting authors to ignore it. | Board definition says QSPI/PSRAM pins; 0 without `BOARD_HAS_PSRAM` is not a measured size. (reference project A, docs/e290-hardware-reference.md) |
| Broken out equals free. | Header pin with LoRa/e-ink/USB net marked usable. | Users can physically solder there. | `consumed` must include onboard functions even if a header carries them. (hardware-electronics, boards/heltec_vision_master_e290.json) |
| ADC2 without Wi-Fi caveat. | ADC2 pin listed as analog input for Wi-Fi design. | Pin has an ADC channel on paper. | ESP32-family rule: ADC2 unusable while Wi-Fi driver is active. (hardware-electronics, reference/esp32-gpio.md) |
| Strapping pins omitted. | GPIO0/3/45/46 treated as ordinary pins on S3. | They behave as GPIO after boot. | Profile must carry `strapping`; GPIO45 pull-up can break boot. (hardware-electronics, boards/esp32s3-generic.json) |
| RTC-capable range copied across families. | Wake source on GPIO44 for S3. | GPIO44 is a valid digital pin. | S3 deep-sleep wake pins are GPIO0-21 only. (hardware-electronics, reference/esp32-gpio.md) |
| Board revision drift. | Old board map remains after hardware changes. | Repo keeps old docs and examples. | Record board revision/source revision; supersede stale profiles rather than delete. (hardware-electronics, boards/crowpanel_213_v1.json) |
| Marketplace capacity invented. | Flash or PSRAM size follows listing. | Listing is easy to find and specific-looking. | Board definition and runtime silicon override; E290 flash is 8 MB measured. (reference project A, docs/bring-up.md) |
| Boilerplate FAQ treated as board-specific. | Charge IC set to MCP73831/TP4054 for E290. | Vendor FAQ has the vendor logo. | Schematic refdes U6 shows LGS4056H; mark FAQ boilerplate. (reference project A, docs/e290-hardware-reference.md) |

## GPIO-number traps

| Trap | Symptom | Why it survives review | Check |
|---|---|---|---|
| Board ID missing. | Answer says `GPIO7 is ...` without model. | GPIO numbers feel universal inside a chip family. | Require `board` before pin answer. (hardware-electronics, reference/esp32-gpio.md) |
| Cross-board pin reuse. | CrowPanel GPIO7 meaning copied to E290 or reverse. | Both are ESP32-S3 e-paper boards. | Compare exact profiles: CrowPanel GPIO7 panel power, E290 GPIO7 VBAT_READ. (hardware-electronics, boards/crowpanel_213_v1.json); (hardware-electronics, boards/heltec_vision_master_e290.json) |
| Conditional pins treated as free. | UART0 pins allocated while serial console still required. | They are not in `consumed`. | Respect `conditional_free` notes. (hardware-electronics, boards/heltec_vision_master_e290.json) |
| JTAG cost omitted. | GPIO40/41/42 allocated silently. | Device still flashes over USB. | Record accepted JTAG cost if using those pins. (hardware-electronics, reference/esp32-gpio.md) |
| Header contradiction ignored. | E290 header pin 11 used. | One table lists it. | Profile `contradicted_header_pins` says do not use it. (hardware-electronics, boards/heltec_vision_master_e290.json) |
| LoRa stretch goal forgotten. | GPIO8-14 reused for buttons. | Current build may not use LoRa. | Keep LoRa pins reserved if stretch goal matters. (reference project A, docs/e290-hardware-reference.md) |
| USB pins spent casually. | GPIO19/20 used as GPIO on USB board. | GPIO matrix makes routing look flexible. | Native USB consumes 19/20 on E290 and generic S3 USB profiles. (hardware-electronics, boards/heltec_vision_master_e290.json) |
| Battery divider enable as spare. | GPIO46 used as output for unrelated load. | It is just another GPIO after boot. | E290 uses GPIO46 as ADC_CTRL and strap; never pull up externally. (hardware-electronics, boards/heltec_vision_master_e290.json) |

## Memory and build-setting traps

| Trap | Symptom | Why it survives review | Check |
|---|---|---|---|
| Generic board menu hand-tuned. | Profile says generic S3 dev module, 16 MB flash, OPI PSRAM. | Arduino IDE menus invite guesses. | Use vendor FQBN `esp32:esp32:heltec_vision_master_e290` unchanged. (reference project A, docs/bring-up.md) |
| Runtime PSRAM 0 misread. | Profile says no PSRAM exists. | API returns zero. | If board definition omits `BOARD_HAS_PSRAM`, zero means not initialised. (reference project A, docs/e290-hardware-reference.md) |
| PSRAM size inferred from chip suffix. | Profile writes PSRAM size as measured. | ESP32-S3R8 suffix suggests capacity. | Only a build that enables PSRAM can measure it. (reference project A, docs/e290-hardware-reference.md) |
| Flash upper half assumed. | Storage plan expects 16 MB. | Datasheet/teardown claim existed. | `esp_flash_get_size()` measured 8 MB; plan against 8 MB. (reference project A, docs/bring-up.md) |
| Partition CSV used to fix hardware. | Profile suggests custom partition unlocks space. | Partitioning feels like a software issue. | Silicon size is the ceiling. (reference project A, docs/e290-hardware-reference.md) |
| Build flags omitted from source record. | Flash/USB values cited as prose only. | Board definition is not copied into profile. | Cite `boards.txt`, FQBN, and core version. (reference project A, docs/bring-up.md) |

## Power and connector traps

| Trap | Symptom | Why it survives review | Check |
|---|---|---|---|
| Product page connector pitch trusted. | Sensor connector listed as SH2.0-4P. | Page looks official. | Datasheet and Meshtastic say SH1.0-4P; inspect/meter before crimping. (reference project A, docs/e290-hardware-reference.md) |
| JST family name trusted over pitch. | PH lead expected to fit 1.25 mm socket. | Sellers misuse names. | Pitch and pin count decide mating; E290 battery is 1.25 mm. (hardware-electronics, parts/connectors.json) |
| Polarity assumed by connector housing. | Battery plugged without meter. | Same shell often appears in examples. | Polarity is not standardised; meter before connection. (hardware-electronics, SKILL.md) |
| Charge current from wrong resistor. | LED resistor treated as `R_PROG`. | Same page contains several nearby resistors. | Exact schematic rev V0.3.1: R18=2 kOhm on PROG, R17 LED resistor. (reference project A, docs/e290-hardware-reference.md) |
| Firmware expected to change charger current. | Profile marks charge adjustable. | Many chargers are configurable elsewhere. | E290 current fixed in hardware by R18. (reference project A, docs/e290-hardware-reference.md) |
| Battery sense on USB treated as SOC. | No-cell reading ~4.2 V means full battery. | Value is plausible. | Charger holds BAT near float on USB; calibrate on battery with meter. (reference project A, docs/bring-up.md) |
| Sleep current copied from one vendor line. | Runtime budget uses 18 uA unqualified. | Number is attractive and specific. | E290 docs disagree 18 vs 20 uA; require measurement for estimate. (reference project A, docs/e290-hardware-reference.md) |
| Amp powered from small 3V3 LDO. | MAX98357A rail set to board 3V3. | Average current looks small. | Peak can be ~1 A; E290 3V3 LDO is 600 mA. Use VBAT/bulk. (hardware-electronics, parts/max98357a-adafruit3006.json) |

## Mechanical traps

| Trap | Symptom | Why it survives review | Check |
|---|---|---|---|
| Marketplace dimensions drive CAD. | Shell printed around seller-only dimensions. | Listings are precise-looking. | Fit-critical `seller_claimed` or `assumed` dimensions require fit coupon or calipers. (hardware-electronics, reference/measurement-discipline.md) |
| Mounting slots treated as holes. | Locating posts placed in E290 slots. | CAD likes centres. | Slot lacks long-axis constraint; use rib frame or slotted bosses. (reference project A, docs/e290-hardware-reference.md) |
| Header height forgotten. | Enclosure too shallow. | Header is on underside/out of sight. | E290 header adds 9.00 mm below PCB. (reference project A, docs/e290-hardware-reference.md) |
| Active display area assumed centred. | Window clips one side. | Symmetric margins are natural. | E290 active area has 3.05 mm long-axis offset. (reference project A, docs/e290-hardware-reference.md) |
| Board/panel orientation sign wrong. | Offset doubled instead of cancelled. | Magnitude is right, sign is not. | Coupon/visual measurement settled `win_offset_x=-3.05`. (reference project A, docs/bring-up.md) |
| USB connector protrusion invented. | Cable channel misses receptacle. | Common USB-C dimensions are available. | Measure connector body/protrusion; E290 docs omit it. (reference project A, docs/e290-hardware-reference.md) |
| Fit sweep endpoint accepted. | Best insert pilot is edge of sampled range. | It passes once. | Sweep farther; endpoint winner is not bounded. (hardware-electronics, reference/measurement-discipline.md) |
| 3D model assumed available. | Profile cites STEP/DXF that does not exist. | Vendors often provide models. | E290 resource set has PDFs and PNG only. (reference project A, docs/e290-hardware-reference.md) |

## Part-profile traps

| Trap | Symptom | Why it survives review | Check |
|---|---|---|---|
| Tactile switch third number misread. | 4.5 x 4.5 x 3.8 mm switch treated as 3.8 mm body height. | W x L x H looks like package body. | For this class, H is to plunger top; record `height_includes`. (reference project A, docs/bom.md) |
| Fixed I2C address treated as strappable. | Two DRV2605L modules on same bus. | Many I2C breakouts have jumpers. | DRV2605L profile has only 0x5A; use mux or one device. (hardware-electronics, parts/drv2605l-adafruit2305.json) |
| Strappable address treated as fixed. | MCP23017 collision declared unavoidable. | Default 0x20 is common. | MCP23017 A0/A1/A2 select 0x20-0x27. (hardware-electronics, parts/mcp23017-waveshare.json) |
| Pull-ups not counted. | Three I2C modules plus extra pull-ups. | Each module works alone. | Record `onboard_pullup_ohm`; MCP23017 module carries 10 kOhm. (hardware-electronics, parts/mcp23017-waveshare.json) |
| 5 V tolerance assumed from breakout. | 5 V bus connected to 3.3 V-only mic. | Breakout boards often include regulators. | SPH0645LM4H profile says `level_tolerant_5v=false`. (hardware-electronics, parts/sph0645lm4h-adafruit3421.json) |
| Silent failure not declared. | Sensor/driver has no liveness check. | No immediate error path exists. | `failure_mode: silent` forces liveness check. (hardware-electronics, parts/_schema.json) |
| Functional axis ignored. | Bottom-port mic points inside enclosure. | Electrical connections still work. | Orientation constraint locks acoustic port to outside path. (hardware-electronics, parts/sph0645lm4h-adafruit3421.json) |
| RF keep-out ignored. | Metal/carbon-filled filament around antenna. | Case still prints. | reference project B warns against lossy filled filament near Zigbee. (reference project B, README.md) |

## Evidence wording traps

| Trap | Symptom | Why it survives review | Check |
|---|---|---|---|
| Non-measured value called verified. | Datasheet row says verified. | Human prose wants confidence words. | Only `measured` may be called verified. (hardware-electronics, SKILL.md) |
| Static e-ink image counted as liveness. | Display marked alive from visible picture. | E-ink retains images without power. | Demand a watched transition. (reference project A, docs/bring-up.md) |
| Fast success accepted. | E-paper refresh in 29 ms treated as excellent. | Command returned with no error. | Plausibility bound catches implausibly fast success. (hardware-electronics, reference/measurement-discipline.md) |
| Blind retry hides fault. | Failure disappears after retries. | Intermittent success feels like flake. | Hardware retry that sometimes works is a wiring/power/timing fault. (hardware-electronics, reference/measurement-discipline.md) |
| Losing claims deleted. | Profile shows only final value. | Clean data feels easier to maintain. | Keep conflicts and supersession reason in corroboration record. (hardware-profiles task brief) |
| Source count equals URL count. | Three URLs from same vendor page lineage. | Spreadsheet has three rows. | Collapse circular sources. (hardware-profiles task brief) |

## Trap triage table

| If you see... | First suspicion | First check |
|---|---|---|
| S3 GPIO34-39 input-only | Classic ESP32 copy-paste | Compare `esp32s3-generic.json` input list. |
| `free` pins with one source | Absence-of-evidence | Demand GPIO corroboration record. |
| Flash capacity from listing | Seller invention | Read `boards.txt` and silicon. |
| Connector name without pitch | JST-family ambiguity | Require pitch, pin count, gender, polarity status. |
| `verified` without measurement record | Vocabulary breach | Downgrade wording/provenance. |
| No `conflicts[]` despite known disagreement | Evidence laundering | Restore all claims and resolution. |
| Generic FAQ citation | Boilerplate | Prefer schematic/refdes or mark unusable. |
| Part profile with price/stock | Wrong artefact | Move to BOM row; profiles hold stable facts only. |

## Review checklist

| Check | Pass condition |
|---|---|
| Board family exact | Family-specific GPIO, RTC, ADC, strap rules match MCU. |
| Board ID exact | No generic pin answer where board-specific profile exists. |
| Free list hard | Every free pin has corroboration or measured support. |
| Reservations hard | Flash, PSRAM, USB, straps, crystals, radio, panel, buttons consumed. |
| Conditional pins explicit | Console/JTAG/wake tradeoffs not hidden. |
| Mechanical provenance visible | CAD-driving dimensions are measured/datasheet/seller_claimed as appropriate. |
| Connector pitch/polarity present | No connector row relies on name alone. |
| Silent failures declared | Liveness checks exist for silent components. |
| Source lineage collapsed | Duplicate/circular sources count once. |
| Unresolved fields block blessings | Conservative escape only over-reserves. |

## Quick micro-checks by profile field

| Field | Plausible wrong value | Catch |
|---|---|---|
| `family` | `ESP32-S3` profile uses classic ESP32 constraints. | Compare family-specific `input_only`, `rtc_capable`, and straps. |
| `gpio_valid` | Includes pins hidden by memory bus. | Cross-check consumed flash/PSRAM pins. |
| `free` | Derived by subtracting only named peripherals. | Require positive evidence for each free pin. |
| `conditional_free` | Empty despite UART/USB/JTAG tradeoffs. | Look for console, native USB, and debug pins. |
| `contradicted_header_pins` | Empty despite vendor disagreement. | Search source notes for NC/alternate labels. |
| `onboard_i2c.pullup_ohm` | Omitted or assumed. | Read module schematic or measure resistance unpowered. |
| `power.charge.ic` | Generic charger copied from FAQ. | Require schematic refdes. |
| `battery_connector.pitch_mm` | Family name only. | Record numeric pitch and pin count. |
| `radio.antenna` | Product-page connector assumed. | Inspect board or cite teardown/photo. |
| `mechanical.pcb_mm` | Seller outline copied. | Prefer datasheet drawing or calipers. |

## Review questions that expose copy-paste

| Question | Bad smell |
|---|---|
| Does this profile have the same notes as another family? | Family rules may have been pasted. |
| Are all pins in numeric order but board functions missing? | Generic MCU table, not board profile. |
| Are straps listed but not consumed where onboard nets use them? | Family data not reconciled with board. |
| Does every source come from the same vendor page tree? | Weak independence. |
| Does a community source cite the same vendor header? | Circular source risk. |
| Are conflicts absent for a known messy board? | Author may have flattened evidence. |
| Are seller dimensions rounded to neat values? | CAD may rest on marketplace copy. |
| Does a note say "probably" but JSON says active/free? | Prose uncertainty leaked into data. |

## Minimum repair actions

| Finding | Repair |
|---|---|
| Wrong family rule | Correct family facts and re-evaluate every derived field. |
| Absence-of-evidence free pin | Move to consumed/unknown or collect corroboration. |
| Circular source count | Collapse lineage and lower corroboration level. |
| Unresolved positive blessing | Return profile or field group to `draft`. |
| Unsafe connector assumption | Add pitch/polarity gate and source. |
| Seller CAD dimension | Tag `seller_claimed` and require measurement/fit coupon. |
| Boilerplate FAQ | Remove from board-specific source count. |
| Missing liveness | Set `failure_mode` honestly and add check or block profile. |
