# Measurement discipline and provenance

Load this whenever a number, success claim, smoke test, fit coupon, or hardware observation may affect a purchase, soldering step, print, or safety decision. Only `measured` may be called verified.

## Provenance ladder

| Provenance | Meaning | May be called verified? | Example |
|---|---|---:|---|
| `assumed` | A guess or placeholder. | No | Assumed USB receptacle height before calipers. (reference project A, docs/bring-up.md) |
| `inferred` | Derived from other values, not directly observed. | No | E290 PCB thickness inferred from stack height. (reference project A, docs/e290-hardware-reference.md) |
| `datasheet` | Manufacturer document. | No | E-ink module outline and active area from panel datasheet. (reference project A, docs/e290-hardware-reference.md) |
| `schematic` | Read from schematic revision. | No | R18 = 2 kΩ on LGS4056H PROG. (reference project A, docs/e290-hardware-reference.md) |
| `vendor_claim` | Product page or marketing/document table. | No | E290 sleep current 18 uA / 20 uA conflict. (reference project A, docs/e290-hardware-reference.md) |
| `seller_claimed` | Marketplace listing with no manufacturer evidence. | No | Generic tactile switch height/force. (reference project A, docs/bom.md) |
| `simulated` | Computed by a tool/model. | No | Runtime estimate or CAD clearance. skill plan §4.8 |
| `measured` | Instrument/firmware observation on actual hardware, with date/context. | Yes | E290 flash size measured 8 MB at runtime. (reference project A, docs/bring-up.md) |

### Vocabulary rules

| Forbidden without `measured` | Use instead |
|---|---|
| verified | expected, specified, claimed, calculated, or measured only if it is measured |
| tested | designed, not yet run, simulated, or measured |
| confirmed | cross-checked, documented, inferred, or measured |
| working | compiled, enumerated, returned without error, or observed transition |
| proven | supported by, consistent with, or measured |

## Measurement record minimum fields

| Field | Why |
|---|---|
| Key | The exact number being promoted. |
| Value and unit | Avoids unit drift. |
| Provenance | Must become `measured` only through a record. |
| Instrument/method | Meter, firmware API, calipers, logic analyzer, serial transcript. |
| Hardware identity | Board, revision, module, serial/MAC if relevant. |
| Date | Measurements supersede old claims. |
| Operator/source | Who or what recorded it. |
| Supersedes | Previous value/provenance if resolving a conflict. |
| Conditions | USB connected/disconnected, battery voltage, firmware build, enclosure state. |

## Implausible success is failure

| Pattern | reference project A case | Rule |
|---|---|---|
| Operation returns success too fast. | CrowPanel e-paper refresh appeared to succeed in about 29 ms with panel power-enable GPIO7 low. | Treat as a fault, not a pass. (reference project A, docs/hardware-findings.md) |
| Hardware line floats into a plausible state. | BUSY floated when the display controller was unpowered. | Wait for BUSY to assert before waiting for release. (reference project A, docs/hardware-findings.md) |
| API reports no error. | Every refresh appeared to succeed; no error was reported. | A validator that only checks "did it return without error" manufactures false confidence. skill plan §0 |
| Timing contradicts physics. | Real CrowPanel display refresh measured 614 ms; 29 ms was implausible. | Put plausibility bounds on smoke tests. (reference project A, docs/hardware-findings.md) |

### Plausibility-band rules

| Rule | Why |
|---|---|
| Every smoke test with timing/current/voltage has a plausible range. | Hardware can fail silently or too quickly. |
| Too good is as suspicious as too bad. | A 29 ms e-paper refresh was not excellent performance; it meant nothing started. |
| Record the reason for each band. | Future agents must not widen it casually. |
| Never widen a plausibility band to make a test pass. | The band is evidence discipline, not a target to game. |
| If a result is outside band, fix the cause. | Do not re-run until it randomly lands inside. |

## Demand a transition

> E-ink retains its last image with no power. A static demo image proves nothing — the factory picture survives a dead driver, a wiped flash, and an unpowered board. Only a change you watch happen counts as evidence.

| Subsystem | Steady-state non-evidence | Transition evidence |
|---|---|---|
| E-paper | A picture is visible. | A counter increments or a newly commanded image appears. (reference project A, docs/bring-up.md) |
| Button | The line reads high now. | Press and release produce debounced level changes. |
| I2C device | Address ACKs once. | Known register changes or device performs an action. |
| Battery monitor | ADC reads 4.2 V on USB. | Reading changes against a metered battery on battery power. (reference project A, docs/bring-up.md) |
| Zigbee sensor | Entity exists in Home Assistant. | Open/close events arrive in the installed location. (reference project B, README.md) |
| Motor | Driver command returns. | Motor physically spins or current changes. |
| Speaker | I2S writes return. | Sound/current transition is observed. |

## Back up factory flash before first write

| Rule | Source |
|---|---|
| If the shipped firmware matters, read flash before the first upload. | reference project A, docs/bring-up.md |
| The CrowPanel factory image was backed up before flashing identify firmware. | reference project A, docs/hardware-findings.md |
| The E290 factory demo was overwritten by the bring-up sketch and was not dumped first. | reference project A, docs/bring-up.md |
| A board that has never been powered on should not be modified. | reference project A, docs/bring-up.md |
| Backup is not a substitute for a liveness transition. | general evidence rule |

## Bound a sweep from both ends

| Sweep | Result | Lesson | Source |
|---|---|---|---|
| reference project A insert pilot coupons | Tested 3.0 / 3.2 / 3.4 / 3.6 mm. Only 3.0 gripped. | The winner was the smallest value tested, so the range was bounded from the wrong end; optimum may be below 3.0. | reference project A, docs/bom.md |
| Correct follow-up | Test smaller values such as a round-2 set below 3.0. | A successful endpoint is not a bounded optimum. | reference project A, docs/bom.md |
| General rule | If best result is at either end of sweep, sweep farther in that direction. | Avoid false optimum. | general experimental design |

### Fit-coupon rules

| Rule | Source |
|---|---|
| Print the fit test first when dimensions are seller-claimed or assumed. | reference project B, README.md; reference project A, docs/bom.md |
| A small coupon can save a long full-body print. | reference project B: 94 x 16 x 12 mm coupon, about 15 minutes; "Ten minutes here saves a ten-hour mistake." (reference project B, README.md) |
| Promote dimensions only after measurement, not after a model exports. | skill plan §5.6 |
| Record both pass and fail sizes. | Needed to bound the sweep. |
| If endpoint wins, run another sweep. | reference project A insert pilot lesson. |

## Silent-failure parts need liveness checks

| Part / subsystem | Silent failure | Required liveness check | Source |
|---|---|---|---|
| Aqara Zigbee door sensor | Stops reporting; user simply stops getting reminders. | Sensor-offline automation plus battery warning. | reference project B, README.md |
| Battery monitor | Reads charger float on USB, looks full with no cell. | Battery-power calibration against meter; suppress USB SOC. | reference project A, docs/bring-up.md |
| E-paper | Retains old image with no power. | Watched display transition. | reference project A, docs/bring-up.md |
| I2C sensor | Last value remains in software. | Fresh read, timestamp, and stimulus if possible. | general sensor rule |
| LoRa/Wi-Fi link | No message arrives. | Heartbeat or stale-data alert. | general network rule; reference project B pattern |

## Never retry failed hardware steps blindly

| Anti-pattern | Why it is wrong | Replacement |
|---|---|---|
| Retry refresh until it works. | Intermittent success can be wiring, power, or timing fault. | Report failure with transcript and preconditions. |
| Retry upload without checking cable/BOOT. | May hide charge-only cable or wrong port. | Try data-capable cable first, then BOOT/RESET procedure. (reference project A, docs/bring-up.md) |
| Retry I2C scan after no devices. | Missing pull-ups, wrong pins, or unpowered module will not be fixed by hope. | Measure idle levels and power. |
| Retry motor command after reset. | Brownout is a power design issue. | Measure rail during inrush. |
| Retry flaky sensor reads. | A retry that sometimes works is a wiring fault, not a flake. | Fix connection, pull-up, level, or timing. |

## Board definition and silicon measurement

| Case | Evidence | Rule |
|---|---|---|
| E290 flash | Runtime firmware measured 8 MB. | Measured silicon supersedes datasheet/teardown claim. (reference project A, docs/bring-up.md) |
| E290 PSRAM | Board definition does not enable SPIRAM; runtime reports not enabled. | Do not call actual PSRAM size measured until a build that enables it measures it. (reference project A, docs/e290-hardware-reference.md) |
| E290 board selection | Vendor board definition encodes 8 MB flash and QSPI PSRAM defaults. | Select vendor board definition and change nothing unless measurement says otherwise. (reference project A, docs/bring-up.md) |
| CrowPanel flash backup | Factory flash backed up before writing. | Backup first if factory image matters. (reference project A, docs/hardware-findings.md) |

## USB and battery measurement caveats

| Observation | Correct interpretation | Source |
|---|---|---|
| 4.201 V battery reading with no cell on USB. | Charger holds BAT at float; not state of charge. | reference project A, docs/bring-up.md |
| Divider path responded. | ADC path exists but calibration is not done. | reference project A, docs/bring-up.md |
| State of charge while USB attached. | Unreadable; UI should suppress or flag. | reference project A, docs/bring-up.md |
| Deep-sleep current with USB connected. | Meaningless for battery runtime. | reference project A, docs/bring-up.md |
| Meter in series with battery positive lead. | Required method for sleep current. | reference project A, docs/bring-up.md |

## Evidence hierarchy for documents

| Higher | Lower | Example |
|---|---|---|
| Measured hardware | Datasheet claim | E290 flash size 8 MB measured vs 16 MB claim. |
| Schematic revision | Generic FAQ boilerplate | E290 LGS4056H vs Heltec FAQ naming MCP73831/TP4054. (reference project A, docs/e290-hardware-reference.md) |
| Datasheet text/schematic/firmware agreement | Pin map PNG | E290 GPIO1/GPIO3 e-ink signal correction. (reference project A, docs/e290-hardware-reference.md) |
| Exact board profile | Generic dev-board guess | E290 board definition over generic ESP32S3 module settings. |
| Exact module docs | Seller listing | Tactile switch height/force seller claims require measurement. |

## Measurement checklist

| Check | Pass condition |
|---|---|
| Transition observed | Evidence is a change watched happen, not a static state. |
| Plausibility bounded | Result is inside a justified range; too-fast success fails. |
| Provenance tagged | Every number records assumed/inferred/datasheet/schematic/vendor_claim/seller_claimed/simulated/measured. |
| Measurement recorded | Instrument, date, conditions, and superseded value are captured. |
| Factory backup considered | Flash read happens before first upload when original image matters. |
| Sweep bounded | Winning coupon is not at an untested edge, or a follow-up sweep is planned. |
| Silent failure covered | Liveness check exists for sensors/links that can fail quietly. |
| No blind retries | Failure leads to diagnosis, not repeated command execution. |
