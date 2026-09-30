# Power and battery bench reference

Load this when choosing a cell, charger, rail topology, load switch, bulk capacitor, runtime estimate, or sleep-current measurement. Use it before connecting a battery and whenever a power number would drive a purchase, print, or safety decision.

## Provenance gates for power numbers

| Number | Minimum provenance before acting | Why |
|---|---|---|
| Battery connector polarity | measured | Polarity is not standardised. Meter it before the first connection. (reference project A, docs/bom.md; docs/bring-up.md) |
| Charge current | schematic at design time; measured resistor before charging if possible | It is a battery safety constraint and may be fixed in hardware. (reference project A, docs/e290-hardware-reference.md; docs/bring-up.md) |
| Deep-sleep current | measured | It dominates runtime estimates. (reference project A, docs/bring-up.md) |
| Battery voltage calibration | measured on battery power | USB holds BAT near charger float and invalidates state-of-charge readings. (reference project A, docs/bring-up.md) |
| Rail voltage under load | measured | Brownout often appears only during transients. general engineering rule |
| Runtime | simulated until current measurements exist | Calculations are estimates, not verified hardware behavior. skill plan §8.3 |

## LiPo C-rate rules

| Term | Calculation | Bench use | Source |
|---|---|---|---|
| Charge C-rate | `charge_current_mA / capacity_mAh` | A 600 mA charger charges a 1000 mAh cell at 0.6C. | general battery arithmetic; reference project A, docs/bom.md |
| 1C | Current equal to nominal capacity per hour. | A 600 mAh cell at 600 mA is 1.0C. | general battery arithmetic |
| Conservative warning | Above about 0.7C, check the cell datasheet and heat. | Many pouch cells tolerate less than aggressive charger defaults. | general battery practice |
| Hard error for the skill | Above 1.0C unless the exact protected cell datasheet allows it. | The skill should not design around unsafe or unknown charge rates. | skill plan §4.2, §8.1 |
| Discharge C-rate | `peak_load_mA / capacity_mAh`. | A motor, radio TX, or class-D amp can brown out a small cell even if average runtime looks good. | general battery arithmetic |

## PROG resistor and fixed charge current

| Board / charger fact | Value | Provenance | Consequence |
|---|---|---|---|
| E290 charge IC | LGS4056H, TP4056-class. | schematic, reference project A docs/e290-hardware-reference.md | Treat as a linear single-cell Li-ion charger, not a firmware-controlled charger. |
| E290 `R_PROG` | R18 = 2 kΩ / 5% on PROG. | schematic rev V0.3.1, reference project A docs/e290-hardware-reference.md | Charge current is set by hardware. |
| E290 charge current | About 600 mA using `I ~= 1200 / R_PROG`. | schematic-derived; constant still listed for datasheet confirmation in docs/bring-up.md | Do not fit a cell smaller than about 600 mAh unless R18 changes. |
| Open physical check | Verify R18 on the physical board reads 2 kΩ. | open item, reference project A docs/bring-up.md | Schematic is not silicon; do not call the resistor value measured until metered. |
| Firmware control | Not adjustable from firmware. | reference project A, docs/bom.md; docs/e290-hardware-reference.md | A smaller cell is not made safe by code. |

### Minimum-cell arithmetic

| Charge current | Minimum cell by 1C rule | Better target | Notes |
|---:|---:|---:|---|
| 100 mA | 100 mAh | >=150 mAh if pouch datasheet is unknown | general arithmetic |
| 250 mA | 250 mAh | >=360 mAh if possible | general arithmetic |
| 500 mA | 500 mAh | >=700 mAh if possible | general arithmetic |
| 600 mA | 600 mAh | 1000-1100 mAh gives 0.55-0.6C | E290 R18 case; reference project A, docs/bom.md |
| 1000 mA | 1000 mAh | use a cell with a datasheet and protection | general arithmetic |

## E290 battery and charger facts

Board-specific facts below apply only to the Heltec Vision Master E290.

| Item | Value | Source | Design consequence |
|---|---|---|---|
| Battery connector | JP1, 2-pin 1.25 mm pitch, labelled `1.25X2P-LiPo`. | reference project A, docs/e290-hardware-reference.md | A JST-PH 2.0 cell lead will not mate. |
| Battery sense pin | GPIO7, ADC1_CH6. | reference project A, docs/e290-hardware-reference.md | Do not add a MAX17048 unless the onboard sense path is inadequate. |
| Divider | R13 390 kΩ high, R15 100 kΩ low, ratio 4.9. | reference project A, docs/e290-hardware-reference.md | High impedance; calibrate against a meter. |
| Divider enable | GPIO46, active high through Q3/Q2. | reference project A, docs/e290-hardware-reference.md | Keep low at boot; GPIO46 is a strapping pin. |
| Firmware multiplier | 4.9 x 1.03 = 5.047, attenuation `ADC_ATTEN_DB_2_5`. | reference project A, docs/e290-hardware-reference.md | Project-specific calibration constant; not verified until compared to a meter. |
| E-ink power gate | GPIO18 Vext, active high. | reference project A, docs/e290-hardware-reference.md | Panel rail can be shut off for sleep. |
| Input protection | Schottky, TVS, fuse on USB input. | reference project A, docs/e290-hardware-reference.md | Helpful board feature; still does not replace battery polarity check. |

## State of charge is unreadable while on USB

| Observation | Meaning | Source |
|---|---|---|
| reference project A divider read 4.201 V with no cell fitted. | With USB attached, the LGS4056H holds BAT at about its 4.2 V float voltage whether a cell is present or not. | reference project A, docs/bring-up.md |
| The reading proves the divider, GPIO46 enable, and ADC path respond. | It does not calibrate the battery multiplier and does not prove a cell is present. | reference project A, docs/bring-up.md |
| Any battery UI on USB must suppress or flag state of charge. | A USB-powered board can look permanently full. | reference project A, docs/bring-up.md |
| Calibration must happen on battery power. | Compare the ADC-derived voltage to a meter at the cell terminals. | reference project A, docs/bring-up.md |

## Deep-sleep current measurement procedure

| Step | Action | Why | Source |
|---|---|---|---|
| 1 | Load firmware that can enter the intended sleep state. | Measure the real firmware state, not an idle prompt. | general engineering rule; reference project A, docs/bring-up.md |
| 2 | Power from battery only. | USB charger current and BAT float voltage invalidate the reading. | reference project A, docs/bring-up.md |
| 3 | Disconnect USB completely. | USB connected means the charger and USB rail participate. | reference project A, docs/bring-up.md |
| 4 | Put the meter in series with the battery positive lead. | Current must flow through the meter. | reference project A, docs/bring-up.md |
| 5 | Start on a safe current range, then switch to uA range after sleep is established. | Avoid blowing a meter fuse during wake/transmit. | general meter practice |
| 6 | Record Vext/load-switch states. | A gated rail accidentally left on changes the result. | reference project A, docs/bring-up.md |
| 7 | Record instrument, date, firmware build, and board state. | Only this can promote the value to `measured`. | skill plan §4.8 |

### 18 uA vs 20 uA conflict

| Claim | Provenance | Use in estimate |
|---|---|---|
| E290 sleep current 18 uA | vendor datasheet table/product page; unmeasured in reference project A | Lower bound for a runtime range. (reference project A, docs/e290-hardware-reference.md; docs/bring-up.md) |
| E290 sleep current 20 uA | vendor datasheet text; unmeasured in reference project A | Upper vendor-claim bound for a runtime range. (reference project A, docs/e290-hardware-reference.md) |
| No anomalous community reports in 34 Meshtastic issues | weak negative evidence, not a measurement | Do not promote provenance. (reference project A, docs/e290-hardware-reference.md) |
| Correct report form | runtime range, not a point estimate | The dominant term is unmeasured. skill plan §12.5 |

## Runtime estimation pattern

| Field | Formula / rule | Notes |
|---|---|---|
| Average current | Sum of `state_current * duty_fraction` over all states. | Tool output should show each contribution. |
| Usable capacity | `capacity_mAh * usable_fraction`. | Use a derate; reference project A examples used about 850 mAh effective from 1000 mAh. (reference project A, docs/pager-hardware-plan.md) |
| Runtime | `usable_mAh / average_mA`. | Report margin against target, not just days. |
| Dominant unmeasured term | Warn when most average current comes from vendor claims. | reference project A sleep current dominates long sleep estimates. |
| Point estimates | Avoid when key terms conflict. | Use 18-20 uA sleep range until measured. |

## Load switches and gated rails

| Load | Why gate it | Source |
|---|---|---|
| Class-D amplifier | Idle current can be milliamps; MAX98357A `SD_MODE` is an analog mode selector, not a plain shutdown. | reference project A, docs/e290-hardware-reference.md; docs/pager-hardware-plan.md |
| MEMS microphone breakout | Audio is push-to-talk; no need to power while asleep. | reference project A, docs/pager-hardware-plan.md |
| Haptic driver / motor rail | Avoid standby current and accidental inrush during sleep. | reference project A, docs/pager-hardware-plan.md |
| E-paper panel rail | E-ink retains the image; panel electronics need not stay powered. | general e-paper behavior; reference project A, docs/bring-up.md |
| External sensors with silent failure | Gate only if wake/liveness behavior is declared. | reference project B, README.md |

### Load-switch checklist

| Check | Pass condition |
|---|---|
| Default state at reset | Load is off or benign while boot straps settle. |
| Gate pin legality | Gate control is not a dangerous strapping pin with an external pull. |
| Inrush path | Bulk capacitance and source impedance prevent brownout. |
| Backfeed path | Data pins cannot power an unpowered module through ESD diodes. |
| Liveness | A silently failed sensor has a liveness check before relying on it. |

## Bulk-capacitance sizing

| Case | Rule | Source |
|---|---|---|
| Any load with `I_peak - I_avg >= 100 mA` | Declare a local bulk capacitor and place it near the load. | skill plan §4.2; general engineering rule |
| Vibration motor | reference project A motor estimate was about 100-156 mA start current; needs local bulk cap. | reference project A, docs/pager-hardware-plan.md |
| Motor example | >=10 uF local bulk was required in the reference project A enclosure plan. | reference project A, docs/pager-hardware-plan.md |
| Class-D amplifier | Do not power MAX98357A from E290 3V3 LDO; it can pull about 1 A peak into 4 Ω. | reference project A, docs/e290-hardware-reference.md |
| Radio TX | Use datasheet peak current, not average current. | general RF power rule; E290 LoRa TX table in docs/e290-hardware-reference.md |
| E-paper refresh | Treat boost rails as transient loads even when logic current is small. | general e-paper power rule |

## Brownout review

| Symptom | Likely power cause | What to measure |
|---|---|---|
| ESP32 resets during Wi-Fi TX | Cell/internal resistance or regulator droop. | 3V3 rail and cell terminal voltage during TX. |
| Reset when motor starts | Motor inrush and no local bulk cap. | Motor rail at start, common ground bounce. |
| Audio clicks or resets | Amp peak current on weak rail. | VBAT and amp supply while playing loud tone. |
| I2C devices disappear during action | Rail dip or ground bounce. | Sensor VCC at the module during load transient. |
| Works on USB, fails on battery | USB source hides weak cell/current path. | Repeat all rail measurements on battery. |

## Protection circuits and cells

| Design item | Required rule | Source |
|---|---|---|
| Single-cell LiPo in hobby enclosure | Use a protected cell or external protection IC. | skill plan §4.2, §8.1 |
| Pouch-cell handling | Do not puncture, crush, solder directly to tabs, or place against sharp pin stubs. | general LiPo safety; reference project A, docs/bring-up.md |
| Header removal near battery | Cover cut/stub area with Kapton if a pouch cell sits over it. | reference project A, docs/bring-up.md |
| Sealed enclosure | Declare venting/safety treatment; unvented LiPo enclosure is a warning/refusal depending on context. | skill plan §8.1 |
| Charger chemistry | Do not charge LiFePO4 on a Li-ion profile. | general battery safety; skill plan §8.1 |
| Protection bypass | Never bypass fuses, thermal cutouts, or protection components. | skill plan §8.1 |

## Coin-cell limits

| Limit | Design consequence | Source |
|---|---|---|
| Coin cells are high-impedance sources. | Avoid Wi-Fi, motors, speakers, relays, and high-current LEDs directly from a coin cell. | general battery engineering |
| Pulse loads cause voltage sag. | A coin-cell sensor may need a reservoir capacitor and very low duty cycle. | general battery engineering |
| Capacity at tiny loads does not predict capacity at pulses. | Do not compute runtime from nominal mAh alone. | general battery engineering |
| Vendor sensors may handle this internally. | reference project B uses an Aqara MCCGQ11LM with its own CR1632; the project does not design that power path. | reference project B, README.md |
| Serviceability matters. | The reference project B never traps the sensor because the CR1632 is replaced by lifting the sensor out. | reference project B, README.md |

## Rail-allocation rules

| Load | Preferred rail decision | Rationale |
|---|---|---|
| ESP32 module logic | Board 3V3 regulator. | Native design point. |
| I2C logic modules | Same logic rail, usually 3.3 V. | Avoid level shifting when possible. |
| MAX98357A amp | VBAT or suitable separate supply, not E290 3V3 LDO. | Peak current can exceed LDO rating. (reference project A, docs/e290-hardware-reference.md) |
| Vibration motor | Switched VBAT or driver-specified rail with local bulk. | Inrush and noise. |
| E-paper panel | Board's intended gated rail. | Avoid permanent panel power draw. |
| 5 V modules on 3.3 V MCU | Use level shifting and check VCC range. | Logic high/absolute maximum issue. |

## Pre-battery checklist

| Check | Pass condition |
|---|---|
| Polarity metered | Connector positive/negative are confirmed at the exact mating connector. |
| Charge current bounded | PROG resistor/charger configuration gives a C-rate the cell can accept. |
| Cell protection known | Cell or circuit provides overcharge/overdischarge/short protection. |
| First power current-limited | Bench supply or USB power path is current-limited for first power-on. |
| No sharp metal near pouch | Cut pins, headers, screw ends, and solder spikes are isolated. |
| Rails checked before modules | Regulator outputs are correct before plugging expensive peripherals. |
| USB caveat understood | Battery state-of-charge is not inferred while USB holds BAT at float. |
