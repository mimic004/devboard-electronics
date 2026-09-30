# Bench review checklist

Load this before first power, first battery connection, first firmware upload, or first peripheral bring-up. It is the electronics analogue of a CAD design review: stop and check the bench sequence before irreversible work.

## Stage 0 — scope and safety

- [ ] The project is below the skill safety limit: no mains/line voltage and no system above 50 V AC / 120 V DC.
- [ ] The project is not a primary life-safety, medical, automotive, aviation, lifting, or safety-critical device.
- [ ] Battery chemistry is known and the charger is for that chemistry.
- [ ] The cell has protection, or an external protection circuit is explicitly present.
- [ ] No pouch cell will be punctured, crushed, soldered directly, or pressed against sharp metal.
- [ ] A multimeter is available for polarity, continuity, rail, and current checks.
- [ ] Any number that will be called verified has a `measured` record; otherwise use claim/calculation wording.

## Stage 1 — documents and board identity

- [ ] Exact board ID and revision are named.
- [ ] Board-specific profile is selected before answering pin questions.
- [ ] Old/superseded board notes in the repo are not mixed with the active board.
- [ ] Any pin answer cites the active board profile, not a grep hit.
- [ ] For E290: `GPIO7` is VBAT_READ, not panel power-enable. (reference project A, docs/e290-hardware-reference.md)
- [ ] For CrowPanel 2.13 v1: `GPIO7` is panel power-enable, not VBAT_READ. (reference project A, docs/hardware-findings.md)
- [ ] Datasheet contradictions are recorded rather than smoothed over.
- [ ] Board definition is treated as authoritative until silicon measurement supersedes it.

## Stage 2 — before modifying hardware

- [ ] The board has powered on at least once before irreversible modification.
- [ ] The board enumerates over USB or the intended debug path.
- [ ] A basic firmware or factory demo transition has been observed.
- [ ] If the shipped firmware matters, factory flash is backed up before the first upload.
- [ ] Header removal, cutting, soldering, or rework is postponed until the board is known alive.
- [ ] For reference-project-A-style E290 header removal: do not bulk-desolder 40 pins; cut body, snip stubs, optionally desolder one at a time, then cover sharp areas with Kapton. (reference project A, docs/bring-up.md)
- [ ] A board that has never been powered on is not modified. (reference project A, docs/bring-up.md)

## Stage 3 — pre-power visual inspection

- [ ] Board orientation is known and marked.
- [ ] All connectors are identified by series and pitch, not just "JST".
- [ ] Battery connector series/pitch is known.
- [ ] Battery connector polarity is not assumed from wire color.
- [ ] No loose strands, solder balls, clipped leads, or metal swarf are present.
- [ ] Pouch cells are clear of sharp pin stubs, screws, and uninsulated solder joints.
- [ ] Heat-set inserts, screws, magnets, and motor cans are outside antenna keep-outs.
- [ ] Cable paths do not pinch at the shell split or hinge.
- [ ] USB plug path reaches the real receptacle with the actual cable boot.
- [ ] U.FL/coax cables have strain relief and no sharp bend.

## Stage 4 — continuity and shorts before power

- [ ] Meter continuity from battery positive to board BAT/VBAT positive where intended.
- [ ] Meter continuity from battery negative to board ground where intended.
- [ ] Meter for a short between battery positive and ground.
- [ ] Meter for a short between USB 5 V/VBUS and ground.
- [ ] Meter for a short between 3V3 and ground.
- [ ] Meter for a short between 5 V and 3V3 if both rails exist.
- [ ] Meter connector pinout at the exact mating connector, not just the PCB silkscreen.
- [ ] Confirm power switch/load switch default state if present.
- [ ] Confirm no signal line is shorted to an adjacent high-current line.
- [ ] Confirm no strapping pin has an unintended external pull.

## Stage 5 — polarity and charger review

- [ ] Battery connector polarity is metered before the first battery connection.
- [ ] Adapter leads are metered; do not trust that they preserve polarity.
- [ ] Cell capacity is compared to charger current.
- [ ] For E290: R18 = 2 kΩ on LGS4056H PROG is schematic-derived; verify physically if possible before charging. (reference project A, docs/e290-hardware-reference.md; docs/bring-up.md)
- [ ] For E290: about 600 mA charge current means no cell smaller than about 600 mAh unless R18 changes. (reference project A, docs/bom.md)
- [ ] USB-attached battery voltage is not treated as state of charge.
- [ ] Battery UI suppresses/flags readings while USB holds BAT near charger float voltage.

## Stage 6 — first power-on

- [ ] First power is current-limited.
- [ ] Start with no battery if USB/bench supply can safely power the board for identity checks.
- [ ] Set current limit low enough to catch shorts but high enough for boot inrush.
- [ ] Watch supply current during connection.
- [ ] Stop immediately on unexpected current, heat, smell, or voltage collapse.
- [ ] Measure 3V3 before plugging external modules into it.
- [ ] Measure 5 V/VBUS if exposed to modules.
- [ ] Measure VBAT/BAT node only with the correct interpretation for USB vs battery.
- [ ] Record rail voltages with provenance; idle readings are not load tests.

## Stage 7 — USB and enumeration

- [ ] Use a known data-capable USB cable first.
- [ ] If nothing enumerates, try another known data-capable cable before changing firmware assumptions.
- [ ] If still absent on ESP32 boards, hold BOOT while tapping RESET or plugging in.
- [ ] For E290, note that the button dance was not needed in the source bring-up; it flashed over a plain USB-C cable. (reference project A, docs/bring-up.md)
- [ ] Filter Bluetooth COM ports out of auto-detect.
- [ ] If more than one serial candidate exists, pass the port explicitly; do not guess.
- [ ] Opening a serial monitor does not assert DTR/RTS unless reset is intended.
- [ ] Reset is opt-in because it can interrupt a device mid-configuration. (reference project A, scripts/board.ps1)

## Stage 8 — toolchain and board definition

- [ ] Prefer the stock `esp32:esp32` core when the vendor fork emits its own warnings.
- [ ] Select the vendor board definition and change nothing unless a measured mismatch requires it.
- [ ] For E290, use `esp32:esp32:heltec_vision_master_e290` for bring-up. (reference project A, docs/bring-up.md)
- [ ] Do not substitute generic `ESP32S3 Dev Module` and guess options by hand.
- [ ] Do not guess OPI PSRAM or 16 MB flash for E290; both contradict the board definition, and 16 MB flash is measured wrong. (reference project A, docs/bring-up.md)
- [ ] Expect E290 PSRAM to report unavailable unless `BOARD_HAS_PSRAM` is defined; that is not by itself a fault. (reference project A, docs/e290-hardware-reference.md)
- [ ] Runtime chip/flash identity is compared against the board profile.
- [ ] Any silicon/profile mismatch is a hard finding, not a note.

## Stage 9 — factory flash backup

- [ ] Decide whether the shipped firmware matters.
- [ ] If yes, run a read-flash backup before first upload.
- [ ] Store backup artifact outside committed source if it is large or proprietary.
- [ ] Record size, hash, board identity, and date.
- [ ] CrowPanel source backed up factory flash before writing identify firmware. (reference project A, docs/hardware-findings.md)
- [ ] E290 source did not dump the factory demo before overwriting it; treat that as the cautionary example. (reference project A, docs/bring-up.md)

## Stage 10 — initial identity firmware

- [ ] Build the smallest identity/bring-up sketch, not full application firmware.
- [ ] It prints chip family, revision, flash size, PSRAM status, MAC/ID if relevant.
- [ ] It uses core APIs only where possible.
- [ ] It does not require untested peripherals.
- [ ] It compiles with warnings visible.
- [ ] Upload hash/check passes in the tool.
- [ ] Serial monitor shows a prompt or report.
- [ ] The report is saved or copied into a measurement record.

## Stage 11 — smoke-test ordering

- [ ] Identify board/chip/flash first.
- [ ] Confirm rails before external modules.
- [ ] Confirm GPIO free/held sweep before allocating pins.
- [ ] Confirm I2C bus scan with no devices or one known device.
- [ ] Confirm each button/input as a transition.
- [ ] Confirm each gated rail toggles and changes current/voltage.
- [ ] Confirm battery divider on battery power before using it for SOC.
- [ ] Measure sleep current only after firmware can enter intended sleep state.
- [ ] Test RF only with antenna/dummy load connected for transmit.
- [ ] Save logs/transcripts with date and board identity.

## Stage 12 — one peripheral at a time

- [ ] Add exactly one new peripheral for first bring-up.
- [ ] Power the peripheral from the intended rail.
- [ ] Confirm rail voltage at the peripheral, not just at the source.
- [ ] Confirm bus idle levels before running firmware.
- [ ] Run the smallest possible probe for that peripheral.
- [ ] Demand a transition or known-register read, not just no error.
- [ ] Remove/disable the peripheral if the next test needs isolation.
- [ ] Do not bring up an I2S microphone and I2S amplifier together and interpret silence; that tells you nothing. (skill plan §2.1)

## Stage 13 — display/e-paper checks

- [ ] Power-enable/precondition line is asserted before panel commands.
- [ ] BUSY wait has a timeout.
- [ ] Driver waits for BUSY to assert before waiting for release.
- [ ] Refresh duration is checked against a plausible band.
- [ ] Implausibly fast success is a fault.
- [ ] A static image is not accepted as evidence.
- [ ] Evidence is a change watched happen, such as a counter increment.
- [ ] E-ink retains its last image with no power; factory picture can survive dead driver, wiped flash, and unpowered board. (reference project A, docs/bring-up.md)
- [ ] For CrowPanel v1, GPIO7 must be high for panel power. (reference project A, docs/hardware-findings.md)

## Stage 14 — I2C checks

- [ ] SDA/SCL pins match the board profile.
- [ ] Pull-ups are present and their parallel value is calculated.
- [ ] On-module pull-ups are counted.
- [ ] Address list contains exact expected addresses, not a broad "any device" pass.
- [ ] Address collisions are resolved before wiring both devices.
- [ ] Scan finding zero devices is interpreted correctly when no devices are attached.
- [ ] Known register/liveness read follows address ACK.
- [ ] For E290 QuickLink, SDA is GPIO39 and SCL is GPIO38. (reference project A, docs/e290-hardware-reference.md)

## Stage 15 — SPI / I2S / audio checks

- [ ] SPI mode is recorded per device.
- [ ] Each SPI device has a unique CS.
- [ ] MISO sharing/release behavior is known before sharing a bus.
- [ ] Write-only SPI displays are not expected to identify themselves.
- [ ] I2S mic is brought up independently from amp.
- [ ] I2S amp is brought up with a known tone independently from mic.
- [ ] Amp supply rail is appropriate for peak current.
- [ ] MAX98357A is not powered from E290 3V3 LDO in reference-project-A-style design. (reference project A, docs/e290-hardware-reference.md)
- [ ] Amp, mic, and haptic rails are gated if sleep current matters. (reference project A, docs/pager-hardware-plan.md)

## Stage 16 — input checks

- [ ] Idle and pressed levels are captured for every input.
- [ ] Internal pull-up use is validated by stable idle.
- [ ] Debounce starts at 10-50 ms unless a capture justifies another value.
- [ ] 15 ms is acceptable only when measured sufficient on that input path; it was sufficient on CrowPanel. (reference project A, docs/hardware-findings.md)
- [ ] Rotary-looking mechanisms are classified by transition pattern, not appearance.
- [ ] The CrowPanel wheel was three discrete switches, not an encoder. (reference project A, docs/hardware-findings.md)
- [ ] Held-repeat implements acceleration when there is no turn velocity.
- [ ] Wake inputs are on wake-capable pins.

## Stage 17 — power and sleep checks

- [ ] All loads with >100 mA transient have local bulk capacitance declared.
- [ ] Motor start current is measured without causing reset.
- [ ] Radio TX current is measured with antenna connected.
- [ ] Deep-sleep current is measured in series with battery positive lead.
- [ ] USB is disconnected for sleep-current measurement.
- [ ] Meter starts on safe current range before switching to uA.
- [ ] Vext/load-switch state is recorded during sleep measurement.
- [ ] 18 uA vs 20 uA E290 vendor conflict is reported as a range until measured. (reference project A, docs/e290-hardware-reference.md)

## Stage 18 — RF checks

- [ ] Regional LoRa band was chosen at order time.
- [ ] Antenna is connected before transmit.
- [ ] U.FL connector existence/location is physically inspected when docs conflict.
- [ ] Antenna keep-out excludes battery, speaker magnet, motor, metal, and filled filament.
- [ ] Range trial is completed in the installed location and orientation.
- [ ] reference project B range test is done in place, not on a desk next to the coordinator. (reference project B, README.md)
- [ ] Silent radio sensors have offline and battery alerts.

## Stage 19 — enclosure-before-final-print checks

- [ ] Parts that drive CAD dimensions are measured or explicitly accepted risks.
- [ ] Seller-claimed dimensions are not treated as measured.
- [ ] Fit coupon is printed before a full shell when clearances are critical.
- [ ] Coupon sweep is bounded from both ends; endpoint winners require another sweep.
- [ ] Cable channels fit actual connector boots and bend radii.
- [ ] Battery bay does not intrude into USB/channel path.
- [ ] Antenna keep-outs are preserved in final geometry.
- [ ] Board has completed bring-up before irreversible enclosure-driven rework.

## Stage 20 — if nothing works

- [ ] Stop and preserve the current state; do not randomly retry.
- [ ] Re-check current limit and rails.
- [ ] Re-check data-capable USB cable first.
- [ ] Re-check port selection and Bluetooth filtering.
- [ ] Try BOOT/RESET only after cable/port checks.
- [ ] Re-check board definition/FQBN.
- [ ] Re-check connector polarity and shorts.
- [ ] Remove all peripherals and return to identity firmware.
- [ ] Add peripherals back one at a time.
- [ ] Treat intermittent success as wiring/power/timing fault until diagnosed otherwise.

## Stage 21 — review sign-off

- [ ] Every passed item has evidence: measurement, transcript, photo, or cited document.
- [ ] Every skipped item has a reason.
- [ ] Every open risk is named near the result, not buried.
- [ ] No summary says verified/tested/confirmed unless the item is measured.
- [ ] The next irreversible action is explicitly identified.
- [ ] The user-facing report distinguishes measured hardware from calculations and claims.

