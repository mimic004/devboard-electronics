# Buses and logic levels

Load this when wiring I2C, SPI, UART, I2S, open-drain signals, or mixed-voltage modules. It is a bench reference for pull-ups, address collisions, chip-select discipline, and level shifting.

## Bus review order

| Step | Question | Failure prevented |
|---|---|---|
| 1 | What voltage are both ends powered from? | 5 V logic on a 3.3 V MCU. |
| 2 | Is the signal open-drain or push-pull? | Missing pull-ups or two outputs fighting. |
| 3 | What devices already have onboard pull-ups? | A bus made too stiff by stacked modules. |
| 4 | What address or chip select identifies each device? | Two parts responding at once. |
| 5 | What is the wire length and bundle routing? | Slow edges, crosstalk, or EMI pickup. |
| 6 | What is the liveness check? | Silent failure that looks like no data rather than a fault. |

## I2C basics

| Item | Rule | Source |
|---|---|---|
| Signalling | I2C SDA/SCL are open-drain; devices pull low and resistors pull high. | general I2C electrical rule |
| Common logic rail | Use the same pull-up voltage as every device can tolerate. | general I2C electrical rule |
| Common ground | Every I2C device needs a shared ground reference. | general wiring rule |
| Pull-ups at 100 kHz | Start around 4.7 kΩ when no module pull-ups are already present. | skill plan §7; general hobby practice |
| Pull-ups at 400 kHz | Start around 2.2 kΩ when bus capacitance and device sink limits allow it. | skill plan §7; general hobby practice |
| Module pull-ups count | Count resistors already fitted on breakouts; do not add blindly. | skill plan §7 |
| Three 10 kΩ modules | Three parallel 10 kΩ pull-ups are about 3.3 kΩ. | resistor arithmetic; skill plan §4.1 |
| Too stiff | Low equivalent resistance increases sink current and can violate device low-level specs. | general I2C electrical rule |
| Too weak | High equivalent resistance plus bus capacitance makes slow rising edges. | general I2C electrical rule |

### Parallel pull-up arithmetic

| Pull-ups present | Equivalent | Bench interpretation |
|---|---:|---|
| One 10 kΩ module | 10.0 kΩ | Often acceptable at 100 kHz on short wires. |
| Two 10 kΩ modules | 5.0 kΩ | Similar to a single 4.7 kΩ pull-up. |
| Three 10 kΩ modules | 3.3 kΩ | The skill treats >=3 stacked 10 kΩ modules as too stiff to ignore. |
| Four 10 kΩ modules | 2.5 kΩ | Approaches 400 kHz starting value before any external pull-up. |
| One 4.7 kΩ plus two 10 kΩ | 2.6 kΩ | Often too strong for a casual 100 kHz module stack; verify sink current. |
| One 2.2 kΩ plus modules | below 2.2 kΩ | Do not add fast-mode pull-ups without calculating the parallel value. |

## I2C address collision table

Addresses are only useful when tied to exact modules or datasheets. reference project A project-specific rows cite project documents; other rows are common part defaults from manufacturer/module documentation and must be checked against the exact breakout.

| 7-bit address | Common part | Notes | Source / attribution |
|---|---|---|---|
| 0x20 | MCP23017 | Default address with A0/A1/A2 low; reference project A chose a Waveshare MCP23017 board here for keypad input. | reference project A, docs/bom.md; docs/pager-hardware-plan.md |
| 0x36 | MAX17048 | Common fuel-gauge default; reference project A did not need one because E290 has onboard battery sense. | general MAX17048 module documentation; reference project A, docs/bom.md |
| 0x3C | SSD1306 OLED | Very common 128x64 OLED default; many modules also offer 0x3D. | general SSD1306 module documentation |
| 0x48 | ADS1115 | Default with ADDR tied to GND; alternatives exist via ADDR pin. | general ADS1115 datasheet/module documentation |
| 0x57 | MAX30102 | Common pulse-oximeter breakout address. | general MAX30102 datasheet/module documentation |
| 0x5A | DRV2605L | Haptic driver default; reference project A includes an Adafruit DRV2605L board. | reference project A, docs/bom.md; general DRV2605L documentation |
| 0x68 | MPU6050 | Common IMU default when AD0 low. | general MPU6050 module documentation |
| 0x68 | DS3231 | Common RTC address; collides with MPU6050 if both are fixed at 0x68. | general DS3231 module documentation |
| 0x76 | BME280 | One common BME280 address. | general BME280 module documentation |
| 0x77 | BME280 | Alternate BME280 address. | general BME280 module documentation |

### Address-table cautions

| Caution | Rule |
|---|---|
| Do not invent an entry for a number just because a scan saw it. | Identify the exact part that ACKs. |
| Do not reserve 0x62 as a generic unknown. | Use a real part and cite its datasheet or module documentation. |
| A scan with no devices only proves the bus did not hang and no connected device ACKed. | CrowPanel I2C on GPIO40/41 found 0 devices because no fuel gauge or haptic driver was attached. (reference project A, docs/hardware-findings.md) |
| A scan that finds a device is not a functional test. | Read a known register or make the device perform a transition. |
| Address straps must be captured in the BOM. | A0/A1/A2 jumpers, solder bridges, and module defaults affect collisions. |

## I2C wire length and capacitance

| Situation | Practical rule | Attribution |
|---|---|---|
| Same PCB or short internal harness | 100 kHz with counted pull-ups is usually robust. | general bench practice |
| Long internal enclosure run | Prefer slower clock, twisted SDA/GND and SCL/GND pairs, and a liveness check. | general signal-integrity practice |
| Cable leaving enclosure | Treat as a connector/cable design problem, not casual I2C. | general signal-integrity practice |
| Unknown capacitance | Lower speed before lowering pull-up resistance blindly. | general I2C electrical rule |
| Noisy loads nearby | Route away from motors, speakers, class-D outputs, and RF feed lines. | general layout rule; reference project A motor/audio layout concerns in docs/pager-hardware-plan.md |

## Open-drain vs push-pull

| Signal type | Electrical behavior | Bench checks |
|---|---|---|
| Open-drain / open-collector | Devices only pull low; resistor pulls high. | Pull-up exists, voltage safe, total resistance calculated. |
| Push-pull output | Device actively drives high and low. | No two outputs tied together; voltage compatible. |
| Interrupt line, open-drain | Multiple devices may share if wired-OR and pulled up safely. | Firmware distinguishes sources; wake pin is legal. |
| Interrupt line, push-pull | Do not tie outputs together. | Use separate pins or diode/logic isolation. |
| ESP32 strapping pin | May be sampled at boot with internal/external pulls. | Do not attach external circuits that change boot levels. |

## Bidirectional level shifters

| Case | Recommended treatment | Source |
|---|---|---|
| 3.3 V MCU to 5 V I2C module | Use an I2C-capable bidirectional level shifter or power the module at 3.3 V if allowed. | general level-shifting rule |
| 3.3 V MCU input from 5 V push-pull output | Use divider, buffer, or level shifter; do not rely on clamping diodes. | general level-shifting rule |
| 3.3 V push-pull output to 5 V TTL-like input | May work electrically only if VIH threshold is low enough; check datasheet. | general level-shifting rule |
| Open-drain bus with mixed pull-ups | Pull-ups must go to a voltage every device tolerates, or use a shifter. | general I2C rule |
| Unpowered module on live bus | Prevent back-power through signal pins. | general mixed-power rule |
| Auto-direction MOSFET shifters | Good for I2C, often poor for high-speed push-pull SPI. | general module practice |

## SPI discipline

| Item | Rule | Source |
|---|---|---|
| Mode | Record CPOL/CPHA mode per device. | general SPI rule |
| Chip select | Each SPI device needs its own CS unless the board explicitly multiplexes it. | general SPI rule |
| CS idle state | Keep every nonselected CS inactive during boot and transfers. | general SPI rule |
| MISO sharing | Devices must release MISO when not selected. | general SPI rule; reference project A microSD caution in docs/bom.md |
| No MISO panel | Some displays are write-only; they cannot identify themselves over SPI. | reference project A, docs/hardware-findings.md |
| Existing board buses | Do not share a board-reserved SPI bus unless the board profile says it is allowed. | reference project A, docs/e290-hardware-reference.md |
| E290 LoRa bus | GPIO8-14 are LoRa SPI/control lines; keep them unused if LoRa is a stretch goal. | reference project A, docs/pager-hardware-plan.md |
| E290 e-ink bus | GPIO1-6 are panel SPI/control; reserved. | reference project A, docs/e290-hardware-reference.md |

### SPI mode table

| Mode | CPOL | CPHA | Use |
|---|---:|---:|---|
| 0 | 0 | 0 | Common default; do not assume. |
| 1 | 0 | 1 | Device-specific. |
| 2 | 1 | 0 | Device-specific. |
| 3 | 1 | 1 | Device-specific. |

## UART discipline

| Item | Rule |
|---|---|
| Cross TX/RX | MCU TX goes to module RX; MCU RX goes to module TX. |
| Voltage | TTL UART voltage must match or be shifted. |
| Boot console | Do not steal UART0 pins unless console plan is known. |
| USB CDC | On E290, USB CDC frees GPIO43/44 as conditional spares, but they are not RTC wake pins. (reference project A, docs/e290-hardware-reference.md) |
| Flow control | RTS/CTS lines are not optional if the module needs them at target baud. |

## I2S discipline

| Item | Rule | Source |
|---|---|---|
| Signals | Typical digital audio uses BCLK, word select/LRCLK, and data. | general I2S rule |
| Direction matters | MEMS mic data is output from mic to MCU; amp DIN is input to amp. | general I2S rule |
| Independent controllers | ESP32-S3 has two I2S controllers routable via GPIO matrix; routing still obeys pin restrictions. | general ESP32-S3 architecture; reference project A docs/pager-hardware-plan.md |
| Bring-up order | Do not bring up mic and amp together and interpret silence. | reference project A, docs/bring-up.md; skill plan §2.1 |
| E290 example | reference project A mapped mic to 41/42/40 and amp to 47/48/17. | reference project A, docs/pager-hardware-plan.md |

## Decoupling and power at bus modules

| Module type | Minimum bench rule | Source |
|---|---|---|
| Any IC/breakout | 100 nF near each power pin or module input. | skill plan §7; general practice |
| Motor / haptic load | Local bulk capacitance for inrush. | reference project A, docs/pager-hardware-plan.md |
| Class-D amplifier | Local bulk on its supply; do not hang peak load on weak MCU LDO. | reference project A, docs/e290-hardware-reference.md |
| Long harness | Consider bulk at the far end plus ground return planning. | general wiring practice |
| Shared bus with transients | Scope or meter rail under load, not just idle. | general bench practice |

## Bench symptoms and bus causes

| Symptom | Likely cause | First check |
|---|---|---|
| I2C scan hangs | SDA/SCL stuck low, wrong pins, short, unpowered device backfeeding. | Measure idle levels; disconnect modules one at a time. |
| I2C finds nothing | Wrong pins, missing pull-ups, no common ground, module unpowered, address assumption wrong. | Check idle high and module VCC. |
| I2C finds too many/odd addresses | Level issue, noise, or marginal pull-ups. | Slow to 100 kHz and inspect wiring. |
| SPI reads all 0xFF | MISO floating, CS wrong, device unpowered, wrong mode. | Probe CS and power; read known ID. |
| SPI reads all 0x00 | MISO held low, wrong mode, device in reset, bus contention. | Check reset and MISO release. |
| Works until motor runs | Ground bounce or rail sag. | Add local bulk, route grounds, measure rail. |
| Works on desk, fails in enclosure | Wire length/routing/RF/mechanical strain changed. | Range-test and bus-test in place. |

## Level-and-bus checklist

| Check | Pass condition |
|---|---|
| Voltage domains listed | Every bus endpoint has VCC and logic-high tolerance recorded. |
| Pull-ups counted | On-module and external pull-ups are combined as parallel resistors. |
| Addresses unique | All fixed/default I2C addresses on the bus are known and non-colliding. |
| CS unique | Each SPI device has a unique chip select and documented idle state. |
| Common ground present | Every signal has a return path. |
| Straps protected | Boot strapping pins are not driven into unsafe states. |
| Liveness declared | Each part has a transition or register read that proves it is alive. |
| One peripheral at a time | First bring-up isolates each device before integration. |
