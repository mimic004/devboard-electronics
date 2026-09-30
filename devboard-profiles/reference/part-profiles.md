# Authoring part profiles

Load this when deciding whether a reusable component belongs in `parts/*.json` and when writing its geometry, electrical, orientation, keep-out, and liveness fields. A part profile captures stable facts, not shopping data.

## What a part profile is for

| Belongs in `parts/*.json` | Does not belong |
|---|---|
| Geometry that drives CAD. | Price, stock, shipping, coupons. |
| Electrical limits and bus facts. | Vendor recommendation prose not tied to a field. |
| I2C address range and pull-ups. | One project's chosen pin assignment. |
| Orientation constraints. | Placement coordinates in a specific enclosure. |
| Keep-out volumes. | Live sourcing alternatives. |
| Failure mode and liveness check. | Project acceptance criteria not intrinsic to the part. |
| Connector pitch/mating facts. | Cable length chosen by one build unless intrinsic. |

Source: (devboard-electronics, parts/_schema.json)

## When a BOM row is enough

| Use only a BOM row when... | Write a part profile when... |
|---|---|
| The part is a commodity resistor/capacitor with no CAD footprint in the model. | The part has geometry, orientation, or keep-outs a CAD bridge consumes. |
| The only changing facts are price and supplier. | The facts are stable across projects. |
| The item is a consumable or tool. | The item constrains pins, buses, power, fit, service, or safety. |
| The exact model is not selected yet. | The exact module/MPN/SKU is selected. |
| A project-specific length or colour is the only detail. | Wrong substitution would break validation. |

## Required identity fields

| Field | Rule | Example source |
|---|---|---|
| `id` | Stable, lowercase, model-specific when possible. | `drv2605l-adafruit2305`. (devboard-electronics, parts/drv2605l-adafruit2305.json) |
| `description` | Human-readable exact part/module. | `MCP23017 16-channel I2C GPIO expander breakout`. (devboard-electronics, parts/mcp23017-waveshare.json) |
| `vendor` / `sku` / `mpn` | Include what uniquely identifies the module. | Adafruit SKU 3421 for SPH0645LM4H breakout. (devboard-electronics, parts/sph0645lm4h-adafruit3421.json) |
| `class` | Use schema enum; do not invent free text. | `haptic`, `expander`, `microphone`. (devboard-electronics, parts/_schema.json) |
| `sources` | Cite datasheet/module/project facts. | Every existing part profile carries sources. (devboard-electronics, parts/*.json) |

## Footprint fields

| Field | Meaning | Trap |
|---|---|---|
| `shape` | Rect/box/circle/cylinder/polygon approximation validators can consume. | Do not hide irregular features; add keep-outs/access where needed. |
| `l`, `w`, `h`, `d` | Physical envelope dimensions in mm. | Do not round seller values into confidence. |
| `height_includes` | What the height reaches: body only, plunger top, shaft top, connector, unknown. | Tactile switch third figure may be to plunger top. |
| `provenance` | One tag for all footprint fields or per-axis object. | Seller-claimed dimensions must remain tagged. |
| `keepouts` | Volumes not captured by body envelope. | Acoustic/RF/access clearance is not normal fit clearance. |

Source: (devboard-electronics, parts/_schema.json)

## The tactile-switch W x L x H trap

| Issue | Correct handling | Source |
|---|---|---|
| Seller lists `4.5 x 4.5 x 3.8 mm`. | Treat third number as height to top of plunger unless datasheet states otherwise. | (reference project A, docs/bom.md) |
| CAD needs body height or plunger top. | Record `height_includes` explicitly. | (devboard-electronics, parts/_schema.json) |
| Seller-only height drives preload. | Measure part before printing or gate on fit coupon. | (reference project A, docs/bom.md) |
| Switch height tolerance affects keys. | Store measured or datasheet-backed values; do not bury in prose. | (reference project A, docs/bom.md) |
| Wrong switch still useful elsewhere. | Side buttons may use taller parts only if mechanics support them. | (reference project A, docs/bom.md) |

## Provenance for part fields

| Field type | Typical minimum | Stronger evidence |
|---|---|---|
| IC voltage/current/address | Manufacturer datasheet. | Module schematic plus bench current for project. |
| Breakout dimensions | Vendor drawing/product page tagged `vendor_claim`. | Caliper measurement. |
| Seller generic part | `seller_claimed` only. | Replace with datasheet-backed part or measure. |
| Connector pitch | Datasheet/schematic or measurement. | Mating trial plus polarity meter for power. |
| Failure mode | System reasoning with source example. | Observed installed behaviour. |
| Orientation | Datasheet/manual/mechanical analysis. | Fit coupon or functional measurement. |

## I2C address modelling

| Pattern | How to write profile | Example |
|---|---|---|
| Fixed address | One address in `addresses`, same `default`, `address_select: Fixed`. | DRV2605L fixed at `0x5A`. (devboard-electronics, parts/drv2605l-adafruit2305.json) |
| Strap-select address | Full address list, default, and strap explanation. | MCP23017 `0x20`-`0x27` via A0/A1/A2. (devboard-electronics, parts/mcp23017-waveshare.json) |
| Module jumper address | List only addresses exposed by the module, not theoretical IC modes. | General module rule. |
| Software address | Record only if the part truly supports nonvolatile/runtime address change. | Omit if not sourced. |
| Collision | Validator must see conflict from data. | Two DRV2605Ls cannot share one bus without mux. (devboard-electronics, parts/drv2605l-adafruit2305.json) |

## Pull-up resistor recording

| Field | Why | Example |
|---|---|---|
| `i2c.onboard_pullup_ohm` | Lets bus check compute effective pull-up when stacking modules. | MCP23017 module: 10 kOhm. (devboard-electronics, parts/mcp23017-waveshare.json) |
| `null` | Honest when no source or measurement exists. | Board QuickLink pull-up unknown. (devboard-electronics, boards/heltec_vision_master_e290.json) |
| Per-module value | Prevents adding pull-ups blindly. | Three 10 kOhm modules combine near 3.3 kOhm. (devboard-electronics, parts/mcp23017-waveshare.json) |
| Source | Module schematic or resistor measurement. | Use `schematic` or `measured`; do not infer from one I2C ACK. |

## Voltage and 5 V tolerance

| Field | Meaning | Examples |
|---|---|---|
| `logic_v` | Normal logic domain for the module in this use. | Existing profiles use 3.3 V for modules. (devboard-electronics, parts/*.json) |
| `level_tolerant_5v` | Whether logic pins tolerate 5 V signalling. | MAX98357A and DRV2605L profiles say true; SPH0645LM4H says false. (devboard-electronics, parts/max98357a-adafruit3006.json); (devboard-electronics, parts/sph0645lm4h-adafruit3421.json) |
| `electrical.v_min/v_max` | Supply range from datasheet. | MCP23017 1.8-5.5 V in profile. (devboard-electronics, parts/mcp23017-waveshare.json) |
| `rail` | Intended supply rail for the project archetype. | MAX98357A should use VBAT, not E290 3V3 LDO. (devboard-electronics, parts/max98357a-adafruit3006.json) |

## Current and transient facts

| Field | Rule | Source |
|---|---|---|
| `i_avg_ma` | Average current is not enough for rails. | MAX98357A average can mislead. (devboard-electronics, parts/max98357a-adafruit3006.json) |
| `i_peak_ma` | Record peak/transient when it can brown out rail. | MAX98357A profile records 1000 mA peak. |
| `bulk_uf_recommended` | Record when source/profile requires local bulk capacitance. | MAX98357A 100 uF, DRV2605L 10 uF in profiles. (devboard-electronics, parts/max98357a-adafruit3006.json); (devboard-electronics, parts/drv2605l-adafruit2305.json) |
| Inductive load note | Motor/coil requires flyback path or driver handling. | DRV2605L profile warns about motor transient. (devboard-electronics, parts/drv2605l-adafruit2305.json) |
| Rail suitability | Do not let validators assume board 3V3 can feed peaks. | E290 3V3 LDO warning in board and amp profiles. (devboard-electronics, boards/heltec_vision_master_e290.json) |

## Failure mode

| `failure_mode` | Meaning | Required follow-up |
|---|---|---|
| `loud` | Failure is apparent quickly. | Liveness may be optional, but bring-up still needs plausibility. |
| `degraded` | System functions badly rather than completely. | Add functional check if user would not notice. |
| `silent` | No obvious error when it stops. | `liveness_check.required = true`. |
| `unknown` | Honest absence of evidence. | Blocks confidence; add how to close. |

Source: (devboard-electronics, parts/_schema.json)

## When `silent` is the honest answer

| Part/subsystem | Why silent | Liveness check |
|---|---|---|
| Aqara MCCGQ11LM sensor | Dead Zigbee sensor just stops reporting. | Last-seen automation and battery alert. (reference project B, README.md); (devboard-electronics, parts/aqara-mccgq11lm.json) |
| DRV2605L haptic path | A stopped haptic may produce no software error. | Device ID readback and user-observable startup pulse. (devboard-electronics, parts/drv2605l-adafruit2305.json) |
| E-paper display | Old image remains without power. | Watched transition, not static picture. (reference project A, docs/bring-up.md) |
| Battery monitor | USB float can look like full battery. | Metered battery-power calibration. (reference project A, docs/bring-up.md) |
| Wireless link | No packet may mean no sender, no receiver, or no range. | Heartbeat/stale-data alert. (devboard-electronics, reference/measurement-discipline.md) |

## Orientation constraints

| Part type | Constraint | Example/source |
|---|---|---|
| Bottom-port MEMS microphone | Acoustic port must face gasketed external opening. | SPH0645LM4H profile. (devboard-electronics, parts/sph0645lm4h-adafruit3421.json) |
| Reed/contact sensor | Magnet must approach sensing axis/marker face. | Aqara sensor stands on edge; marker lines align. (reference project B, README.md) |
| Speaker cone | Cone/grille axis must face acoustic opening; back volume matters. | General acoustic design; reference project A separates speaker/mic concerns. (reference project A, docs/bom.md) |
| Antenna | RF keep-out and material restrictions around radiating element. | Aqara Zigbee antenna keep-out; no lossy filled filament. (reference project B, README.md) |
| Magnet | Field path and moving gap matter, not just static clearance. | Aqara magnet gap sweeps with lid angle. (reference project B, README.md) |
| Vibration motor | Mechanical coupling and noise path matter. | DRV2605L profile warns mic will hear motor. (devboard-electronics, parts/drv2605l-adafruit2305.json) |

## Orientation field pattern

| Field | What to include |
|---|---|
| `locked` | `true` when CAD may not rotate arbitrarily. |
| `kind` | `port_axis`, `sensing_axis`, `rf_axis`, or similar stable category. |
| `feature` | Physical feature such as acoustic port, marker line, cone, antenna end. |
| `reason` | Why function fails if rotated. |
| `drives` | CAD parameters affected by the orientation. |
| `cost` | Space or serviceability consequence if sourced. |

Source examples: (devboard-electronics, parts/aqara-mccgq11lm.json); (devboard-electronics, parts/sph0645lm4h-adafruit3421.json)

## Keep-out kinds

| Kind | Purpose | Example/source |
|---|---|---|
| `mechanical` | Space for body motion, connectors, wire bend, service removal. | Aqara sensor must lift straight out for battery. (devboard-electronics, parts/aqara-mccgq11lm.json) |
| `acoustic` | Open/gasketed sound path or speaker grille volume. | SPH0645LM4H acoustic path cylinder. (devboard-electronics, parts/sph0645lm4h-adafruit3421.json) |
| `rf` | Antenna clearance and material exclusion. | Aqara Zigbee antenna keep-out. (devboard-electronics, parts/aqara-mccgq11lm.json) |
| `thermal` | Venting, hot parts, regulator dissipation. | Aqara manual ventilation warning captured in profile. (devboard-electronics, parts/aqara-mccgq11lm.json) |
| `magnetic` | Magnet/reed/Hall field space and ferrous avoidance. | Aqara magnet relation. (reference project B, README.md) |
| `access` | Connector screwdriver, reset window, cable entry. | MCP23017 connector edge; Aqara reset window. (devboard-electronics, parts/mcp23017-waveshare.json); (devboard-electronics, parts/aqara-mccgq11lm.json) |

## Connector data inside part profiles

| Field | Rule | Source |
|---|---|---|
| Pitch | Pitch is the fact; family name is marketing. | (devboard-electronics, parts/connectors.json) |
| Pin count | Required for mating. | (devboard-electronics, parts/connectors.json) |
| Gender/orientation | Needed for mechanical fit and cable selection. | general connector practice. |
| Polarity status | Power connectors require meter before first connection. | (devboard-electronics, SKILL.md) |
| Cross-plug risk | Different pitches can be a safety feature. | E290 battery 1.25 mm vs QuickLink 1.0 mm. (devboard-electronics, parts/connectors.json) |

## Serviceability fields

| Part | Service issue | Profile pattern |
|---|---|---|
| Coin-cell sensor | Battery replacement requires removal. | `serviceability.battery`, `removable`, requirement text. (devboard-electronics, parts/aqara-mccgq11lm.json) |
| Reset/pair button | User may need access after assembly. | Access keep-out/window. (reference project B, README.md) |
| Screw terminal | Wire entry and screwdriver clearance. | Access keep-out on connector edge. (devboard-electronics, parts/mcp23017-waveshare.json) |
| USB receptacle | Cable boot clearance may dominate enclosure. | Board profile or project manifest, not generic part unless receptacle module selected. (reference project A, docs/bom.md) |

## Part profile versus board profile

| Board profile | Part profile |
|---|---|
| Names MCU board and consumed/free pins. | Names reusable component/module. |
| Owns `gpio_valid`, straps, RTC, ADC, USB, JTAG. | Owns bus address, module pull-ups, footprint, keep-outs. |
| May include onboard peripherals fixed to board. | Does not allocate host pins. |
| Status depends on GPIO/data corroboration. | Status depends on stable geometry/electrical corroboration. |
| Example: Heltec E290. | Example: DRV2605L breakout. |

## Authoring sequence

| Step | Action |
|---:|---|
| 1 | Decide if stable reusable facts justify a profile. |
| 2 | Identify exact module/MPN/SKU and class. |
| 3 | Record footprint with `height_includes` and per-axis provenance if mixed. |
| 4 | Record electrical rails, voltage limits, logic tolerance, current, and transients. |
| 5 | Record bus facts: I2C addresses, pull-ups, pins consumed by bus type. |
| 6 | Add orientation constraints for functional axes. |
| 7 | Add keep-outs for mechanical/acoustic/RF/thermal/magnetic/access constraints. |
| 8 | Set `failure_mode` and liveness check if silent. |
| 9 | Add traps that validators or reviewers should surface. |
| 10 | Cite sources with enough path/document detail to re-check. |

## Validation questions

| Question | Fail if... |
|---|---|
| Does any field go stale quickly? | It is price, stock, delivery, or seller availability. |
| Would CAD change if this value changes? | It lacks provenance or `height_includes`. |
| Can two modules collide on a bus? | I2C addresses or pull-ups are missing. |
| Can a wrong voltage destroy it? | `level_tolerant_5v` or supply range is missing. |
| Can it fail silently? | `failure_mode` is not `silent` or liveness check is missing. |
| Can CAD rotate it freely? | A functional axis exists but `orientation_constraint.locked` is absent. |
| Can plastic block function? | Keep-out is missing for acoustic/RF/thermal/magnetic/access path. |
| Is evidence re-checkable? | Source lacks document/path/revision or profile just says `datasheet`. |

## Existing profiles as patterns

| Profile | Good pattern to copy | Caution |
|---|---|---|
| `drv2605l-adafruit2305` | Fixed I2C address, silent failure, liveness, motor transient. | Do not generalise address to other haptic drivers. |
| `mcp23017-waveshare` | Strap-select addresses and onboard pull-up recording. | Module size is large and vendor-claimed/assumed; measure for CAD. |
| `sph0645lm4h-adafruit3421` | Bottom-port mic orientation and acoustic keep-out. | Its 40 mm speaker separation note is project-derived, not universal. |
| `max98357a-adafruit3006` | Peak current and rail warning. | Average current alone is misleading. |
| `aqara-mccgq11lm` | Orientation drives geometry, serviceability, RF keep-out, silent liveness. | Sensor dimensions are measured for that sample; scope measurements. |
| `connectors.json` | Pitch-first mating rules and cross-plug guidance. | Connector polarity still needs a meter for power. |

## Checklist before saving

| Check | Pass condition |
|---|---|
| Stable fact only | No price, stock, or supplier availability. |
| Exact identity | Vendor/SKU/MPN sufficient to distinguish variants. |
| Geometry sourced | Footprint fields have provenance and `height_includes`. |
| Electrical sourced | Voltage, tolerance, current, and transient fields cite data. |
| Bus complete | Addresses, address select, and onboard pull-ups recorded or honestly null. |
| Failure mode honest | Silent and unknown cases force liveness or closure path. |
| Orientation locked | Functional axes cannot be rotated away by CAD. |
| Keep-outs explicit | Mechanical/acoustic/RF/thermal/magnetic/access constraints are data. |
| Substitution safe | A BOM substitute that changes profile facts must create or select another profile. |
| Sources re-checkable | Another agent can locate every non-obvious claim. |
