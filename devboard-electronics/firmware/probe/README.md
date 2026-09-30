# `probe.ino` - the vendored diagnostic sketch

A menu-driven peripheral probe that speaks a line protocol, so a host program
can parse it deterministically instead of scraping English out of a serial
monitor.

This file is **vendored data**, not something to re-derive per project. Copy it
into your project directory alongside your board and part profiles so the
project stays runnable standalone.

## Build and flash

```powershell
$cli = "$env:LOCALAPPDATA\arduino-cli\arduino-cli.exe"
& $cli compile --fqbn <your-board-fqbn> --warnings all firmware\probe
& $cli upload  --fqbn <your-board-fqbn> --port COM7      firmware\probe
```

Or through the wrapper, which parses the result into JSON and warns about
generic FQBNs:

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py board_cli.py backup --out factory.bin --port COM7   # FIRST, on an unseen board
& $py board_cli.py build --sketch firmware\probe --fqbn <fqbn>
& $py board_cli.py flash --sketch firmware\probe --fqbn <fqbn> --port COM7
```

**Back up the factory flash before the first upload.** Factory demo firmware
cannot be recovered once it is overwritten, and nothing warns you at the time.

## The protocol

Requests are single lines. Responses are always `probe.<something>`, one fact
per line, terminated by exactly one `probe.done <name> ok|fail`.

```
> PROBE i2c 39 38 100000
< probe.i2c.begin ok
< probe.i2c.sda 39
< probe.i2c.scl 38
< probe.i2c.found 0x20
< probe.i2c.found 0x5a
< probe.i2c.count 2
< probe.i2c.elapsed_ms 41
< probe.done i2c ok
```

| Command | What it does |
|---|---|
| `ID` | Chip model, revision, cores, flash, PSRAM, SDK |
| `HELP` | Command list |
| `PROBE i2c <sda> <scl> [hz]` | Scans 0x08–0x77 and reports every address that answers |
| `PROBE gpio sweep` | Reports which pins are free and which are already driven on-board |
| `PROBE adc <pin>` | Raw and millivolt reading, averaged, with the USB caveat |
| `PROBE buttons <pin> <ms>` | Captures debounced edges over a window |
| `PROBE rail <pin> <high\|low>` | Toggles a gated rail and reports the state change |
| `PROBE busy <busy> <trig> <sense> [timeout]` | Asserts a trigger and times a busy line — **read the note below** |
| `PROBE spi <sck> <mosi> <miso> <cs>` | Loopback byte test (tie MOSI to MISO) |
| `PROBE sleep <seconds>` | Prints the metering procedure, then deep-sleeps |

## Why `PROBE busy` is the important one

It waits for the busy line to **assert** before waiting for it to **release**.

A peripheral whose controller is unpowered leaves its BUSY line floating. The
naive sequence — "kick it off, then wait until not busy" — completes
immediately and reports success. On one real board, with the panel
power-enable line low, *every e-paper refresh appeared to succeed in about
29 ms*. Nothing errored. The fault was only found by comparing the duration
against a plausible refresh time.

So this probe reports three separate facts:

- `probe.busy.asserted yes|no` — did it ever start?
- `probe.busy.assert_ms` — how long until it did
- `probe.busy.busy_ms` — how long it stayed busy

and the host applies a **plausibility band** to `busy_ms`. A success that is far
too fast is a `IMPLAUSIBLE_SUCCESS` failure, not a pass. Never widen the band to
make it go green.

## Three rules the sketch does not break

1. **Every busy-wait has a timeout**, including the `while (!Serial)` in
   `setup()`. Vendor drivers routinely spin forever, and a peripheral that never
   releases BUSY otherwise hangs the device with the rail up.
2. **Assert before release.** See above.
3. **Elapsed time is always reported.** The sketch does not decide what is
   plausible; it makes the timing visible so the host can.

## One peripheral at a time

Bring up an I2S microphone and an I2S amplifier together, get silence, and you
have learned nothing about which one is wrong. The probe spec format is
deliberately one file per peripheral for this reason.

## The escape hatch

A generic sketch cannot cover every peripheral. When yours needs something this
does not have, write a project-specific probe **using the same line protocol**:
`probe.<name>.<key> <value>` lines terminated by `probe.done <name> ok|fail`,
with a timeout on every wait and elapsed time on every operation.
`probe_client.py` will drive it without modification, and its plausibility
checking will apply to your measurements exactly as it does to these.

## Testing without hardware

Record a session once, replay it forever:

```powershell
& $py board_cli.py record --out transcript.json --port COM7 --send "PROBE i2c 39 38 100000"
& $py probe_client.py spec.json --transcript transcript.json
```

A replayed run reports `"source": "recorded"` and can never be mistaken for a
measurement. There is no flag that changes that.
