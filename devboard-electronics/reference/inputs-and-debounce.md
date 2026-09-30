# Inputs and debounce

Load this when designing buttons, keypads, tactile switches, rotary-looking controls, GPIO expanders, or TPU membranes. Use it to distinguish electrical evidence from guesses about a physical input.

## Input provenance rules

| Claim | Minimum evidence | Source |
|---|---|---|
| A button is active-low | Observe idle high and pressed low, or cite schematic. | reference project A, docs/hardware-findings.md |
| Internal pull-ups are sufficient | Measure stable idle and clean transitions with internal pull-up enabled. | reference project A, docs/hardware-findings.md |
| A wheel is an encoder | Observe interleaved two-phase quadrature transitions. | general encoder rule; reference project A counterexample in docs/hardware-findings.md |
| Debounce interval is sufficient | Capture transitions and show no spurious edges at that interval. | reference project A, docs/hardware-findings.md |
| Switch height will fit | Datasheet or measured height; seller claim is not enough before print. | reference project A, docs/bom.md |
| A membrane will not preload switches | Arithmetic over switch height, web thickness, and worst-case pretravel. | reference project A, docs/bom.md |

## Active-low buttons with internal pull-ups

| Item | Rule | Source |
|---|---|---|
| Wiring | One side to GPIO, other side to ground. Enable internal pull-up. | general MCU input practice |
| Idle state | Reads high. | reference project A CrowPanel inputs, docs/hardware-findings.md |
| Pressed state | Reads low. | reference project A CrowPanel inputs, docs/hardware-findings.md |
| External parts | No external pull-up is needed when the internal pull-up gives stable idle and the environment is benign. | reference project A, docs/hardware-findings.md |
| Long/noisy harness | Re-evaluate; internal pull-ups are weak and long wires may need external treatment. | general wiring practice |
| Floating input | Never leave a CMOS input floating. | skill plan §7; general digital rule |

### CrowPanel measured inputs

| Function | GPIO | Electrical behavior | Source |
|---|---:|---|---|
| Back / Exit | 1 | Active low, internal pull-up worked. | reference project A, docs/hardware-findings.md |
| Menu / Home | 2 | Active low, internal pull-up worked. | reference project A, docs/hardware-findings.md |
| Wheel down | 4 | Active low, internal pull-up worked. | reference project A, docs/hardware-findings.md |
| Wheel confirm | 5 | Active low, internal pull-up worked. | reference project A, docs/hardware-findings.md |
| Wheel up | 6 | Active low, internal pull-up worked. | reference project A, docs/hardware-findings.md |

## Debounce windows

| Window | Use | Attribution |
|---:|---|---|
| <10 ms | Only after a capture proves the switch and wiring are clean enough. | general debounce practice |
| 10-50 ms | Normal tactile-switch debounce range for human inputs. | skill plan §7; general debounce practice |
| 15 ms | Measured sufficient during CrowPanel input capture; no spurious transitions logged. | reference project A, docs/hardware-findings.md |
| >50 ms | May feel sluggish unless used for very noisy or slow mechanical inputs. | general debounce practice |

### Debounce implementation checks

| Check | Pass condition |
|---|---|
| Edge capture | Firmware records press and release transitions, not just level. |
| Stable interval | State changes only after the input remains changed for debounce interval. |
| Repeat separate from debounce | Held-repeat timer starts after debounced press; it is not bounce filtering. |
| Per-key state | Each key has its own debouncer. |
| Timestamp source | Uses monotonic time, not blocking delays that hide other inputs. |

## The wheel was three switches, not an encoder

This is the model for proving a hardware claim: observe the transitions a real mechanism produces, then match or reject the expected pattern.

| Evidence observed | Meaning | Source |
|---|---|---|
| Turning and pressing produced clean independent press/release pairs on GPIO6, GPIO4, and GPIO5. | Each function behaved like a separate switch closure. | reference project A, docs/hardware-findings.md |
| Press durations were roughly 100-500 ms. | Human switch action, not rapid encoder pulse trains. | reference project A, docs/hardware-findings.md |
| No interleaved two-phase pattern between any pair of pins. | Not quadrature. | reference project A, docs/hardware-findings.md |
| No bursts of rapid transitions per detent. | Not a mechanical encoder presenting multiple pulses per click. | reference project A, docs/hardware-findings.md |
| 15 ms debounce was sufficient. | No spurious transitions in that capture. | reference project A, docs/hardware-findings.md |

### Consequences of the wheel finding

| Design choice | Correct response |
|---|---|
| Decoder | Do not implement quadrature decoding. |
| Input model | Treat up, down, and confirm as three debounced buttons. |
| Velocity | There is no rotational velocity to read. |
| Acceleration | Use held-repeat for long lists, not turn speed. |
| UI wording | "Wheel up/down/press" can map to Up/Down/Select buttons. |

## How to prove a claim about an input

| Claim | Expected evidence | Reject if |
|---|---|---|
| "This is a button" | One GPIO changes level on press and returns on release. | Multiple phase-shifted signals appear. |
| "This is a quadrature encoder" | Two channels transition in an ordered Gray-code sequence as it turns. | You only see independent human-length closures. |
| "This button is active-low" | Idle high, pressed low. | Idle is low or floating. |
| "Internal pull-up is enough" | Stable idle across time and enclosure/harness states. | Idle flickers or changes when touched. |
| "Debounce is 15 ms" | Logged transitions show no false edges at 15 ms. | Bounce persists or mechanism varies across samples. |
| "This input can wake from sleep" | Pin is RTC/wake-capable and wired to the event. | It is only a normal GPIO or expander line without legal interrupt. |

## Held-repeat instead of turn velocity

| Parameter | Starting rule | Attribution |
|---|---|---|
| Initial repeat delay | Choose a human-feeling delay after a debounced press; tune in UI tests. | general UI practice |
| Repeat interval | Fixed or accelerated over hold duration. | general UI practice |
| Release | Stop repeat immediately on debounced release. | general UI practice |
| Multiple keys | Define priority if Up and Down are held together. | general input design |
| Encoder-like UI | Emulate with held-repeat because no velocity signal exists on a three-switch wheel. | reference project A, docs/hardware-findings.md |

## Tactile-switch dimension trap: `W x L x H`

| Trap | Correct interpretation | Source |
|---|---|---|
| `4.5 x 4.5 x 3.8 mm` looks like body footprint plus actuator travel. | For the cited tactile-switch class, the third figure is total height from PCB seating plane to the top of the plunger. | reference project A, docs/bom.md |
| A 3.8 mm switch seemed like it might fit. | It was about 1.9 mm too tall for reference project A's keypad stack. | reference project A, docs/bom.md |
| Seller photos can hide plunger height convention. | Use datasheets or calipers, not listing shorthand. | reference project A, docs/bom.md |
| The finding was cross-checked. | The `H` interpretation was confirmed against three separate datasheets in the source project. | reference project A, docs/bom.md |
| Through-hole parts may have lead/body assumptions. | If PCB footprint already exists, SMD vs through-hole can make the chosen part unusable. | reference project A, docs/bom.md |

### Switch height options from reference project A

| Part / option | Height | Provenance in source | Notes |
|---|---:|---|---|
| TS011-TBW1EH1.9 | 1.9 mm | seller-claimed; no manufacturer datasheet | Chosen because it matches the model if it measures as advertised. (reference project A, docs/bom.md) |
| SH-TS-1187-20-160gf | 2.0 mm | seller-claimed; no manufacturer datasheet | Backup point in legal range. (reference project A, docs/bom.md) |
| Würth 435451019820 | 1.90 mm | datasheet-backed | Alternative with manufacturer datasheet. (reference project A, docs/bom.md) |
| 4.5 x 4.5 x 3.8 mm tactile | 3.8 mm overall height | listing shorthand; incompatible with keypad stack | About 1.9 mm too tall. (reference project A, docs/bom.md) |

## Switch-preload arithmetic

| Quantity | Value / rule | Source |
|---|---|---|
| Required stack band | `switch_h + web_t` must land between 2.30 and 2.40 mm. | reference project A, docs/bom.md |
| Chosen switch example | 1.90 mm switch requires 0.40 mm web. | reference project A, docs/bom.md |
| Bad web example | 0.60 mm web with 1.90 mm switch gives +0.20 mm preload. | reference project A, docs/bom.md |
| Typical stroke spec | 0.25 mm +0.10 / -0.15. | reference project A, docs/bom.md |
| Worst-case pretravel | 0.10 mm, not 0.20 mm. | reference project A, docs/bom.md |
| Consequence | +0.20 mm preload exceeds worst-case pretravel and keys read permanently held. | reference project A, docs/bom.md |
| Legal switch-height range | 1.70-2.10 mm before the frame floor must move. | reference project A, docs/bom.md |

### Preload worked examples

| Switch height | Web thickness | Sum | Verdict |
|---:|---:|---:|---|
| 1.90 mm | 0.40 mm | 2.30 mm | Lower edge of target band. |
| 1.90 mm | 0.50 mm | 2.40 mm | Upper edge of target band. |
| 1.90 mm | 0.60 mm | 2.50 mm | +0.20 mm over band; permanent-hold risk. |
| 2.00 mm | 0.40 mm | 2.40 mm | Upper edge; measure the real part. |
| 3.80 mm | any normal web | far above band | Incompatible with this stack. |

## TPU keypad rules from reference project A

| Parameter | Source value / rule | Source |
|---|---|---|
| TPU hardness | 85A preferred; 95A acceptable if thin. | reference project A, docs/pager-hardware-plan.md |
| Web thickness | 0.4-0.6 mm design range, but switch preload narrowed this to exact stack arithmetic. | reference project A, docs/pager-hardware-plan.md; docs/bom.md |
| Key cap thickness | 1.5-2.5 mm. | reference project A, docs/pager-hardware-plan.md |
| Total travel | 0.6-1.0 mm. | reference project A, docs/pager-hardware-plan.md |
| Cap-to-switch gap | 0.0-0.2 mm preload target. | reference project A, docs/pager-hardware-plan.md |
| Plunger stub | 2.0-2.5 mm diameter by 0.8-1.2 mm. | reference project A, docs/pager-hardware-plan.md |
| Key pitch | 8 mm minimum; 10-12 mm for a pager row. | reference project A, docs/pager-hardware-plan.md |
| Coupon expectation | Expect 2-4 small test iterations before full keypad. | reference project A, docs/pager-hardware-plan.md |

## GPIO expander input rules

| Rule | Why | Source |
|---|---|---|
| Use expander when ADC ladder is illegal. | E290 had no free ADC1 and ADC2 fails with Wi-Fi. | reference project A, docs/pager-hardware-plan.md |
| MCP23017 default address is 0x20 in reference project A BOM. | Needed for I2C collision review. | reference project A, docs/bom.md |
| INT line needs wake-capable MCU pin if it wakes from sleep. | On E290, GPIO38-48 cannot wake; proposed INT is GPIO21. | reference project A, docs/pager-hardware-plan.md |
| Internal/external pulls on expander inputs must be known. | Floating expander inputs are still floating CMOS inputs. | general digital rule |
| Multi-key rollover | Expander gives real per-key state instead of analog ladder ambiguity. | reference project A, docs/pager-hardware-plan.md |

## Side-button mechanical cautions

| Caution | Source |
|---|---|
| A top-actuated switch cannot be levered sideways unless the PCB is perpendicular to the wall. | reference project A, docs/bom.md |
| A side-button cap needs a close-fitting guide boss to avoid off-axis plunger loading. | reference project A, docs/bom.md |
| Cap-to-plunger gap still needs about +/-0.15 mm control. | reference project A, docs/bom.md |
| Through-hole leads need clipping flush if clearance is tight. | reference project A, docs/bom.md |
| Side-actuated alternatives such as Omron B3U-3000P may be appropriate when the PCB is parallel to the wall. | reference project A, docs/bom.md |

## Input bring-up checklist

| Check | Pass condition |
|---|---|
| Idle state recorded | Each input has idle high/low measured or cited. |
| Press state recorded | Each input has observed press/release transitions. |
| Pull strategy recorded | Internal pull-up, external pull-up/down, or expander pull is known. |
| Debounce chosen | 10-50 ms default or measured project-specific value. |
| Mechanism identified | Button, three-switch wheel, quadrature encoder, reed switch, or other type proven by transition pattern. |
| Sleep wake legal | Wake input is on a wake-capable pin or has a declared always-on monitor path. |
| Mechanical stack checked | Switch height plus membrane/web arithmetic stays in band. |
| Seller claims gated | Seller-claimed switch dimensions are measured before printing around them. |
