# Example: ESP32-S3 LiPo sensor

A battery-powered greenhouse sensor. Wakes every fifteen minutes, reads a
BME280 over I2C, publishes over Wi-Fi, sleeps again. It lives in a bought box,
so there is no enclosure design and no CAD handoff.

**This example passes every implemented gate in strict mode.** Read it first.

## Run it

```powershell
$py = "..\..\.venv\Scripts\python.exe"
foreach ($p in 0,1,2,3,4,9) { & $py ..\..\hw.py check --phase $p --dir . }
```

All six exit 0. Phases 5 and 8 are explicitly skipped with recorded reasons.
Phases 6 and 7 happened against the board itself — the flash size in
`measurements.jsonl` came from `esp_flash_get_size()` on silicon — and are run
directly rather than gated from a project directory:

```powershell
& $py ..\..\board_cli.py identify --board esp32s3-generic --strict
```

## What it demonstrates

**Phases can be skipped, but not silently.** `project.json` records two skips
with reasons: no wiring artefact (four wires between two boards), and no CAD
handoff (no enclosure is being designed). An absent artefact and a deliberate
skip look identical from the outside, and only one of them is safe.

**A power budget where nothing is a guess.** Both duty-cycle states carry
`"provenance": "measured"` and both are backed by ledger entries naming the
instrument. `power_budget.py` reports `unmeasured_share: 0.0` and does not raise
`SLEEP_UNMEASURED`. Compare with the pager example, where it does.

**The charge current is a BOM constraint, not a preference.** `R_PROG` was
metered at 1.19 kΩ, giving roughly 1 A. That sets a 1000 mAh floor on the cell,
which `bom_lint.py --power` checks automatically. Firmware cannot change a
resistor.

**Silicon beats the listing.** The board was sold as 16 MB of flash. Reading
`esp_flash_get_size()` said 8 MB, and the ledger records the supersession with
both values. The guess was wrong in the direction that would have silently
truncated an OTA partition.

**Seller-claimed dimensions get measured before they matter.** The cell was
listed at 7.0 mm and measures 7.4 mm at its thickest. It still clears the 22 mm
interior, so nothing changed — which is the usual outcome, and still worth the
ten seconds. `measure_log.py audit --bom bom.json` is what forced the check.

**The range test happened in place.** 46 m against a 40 m target, box closed, in
the greenhouse — not on the desk next to the access point.

## Files

| File | Phase |
|---|---|
| `project.json` | 0 — intake, voltage class, tool inventory, recorded skips |
| `requirements.json` | 1 — every value provenance-tagged |
| `bom.json` | 2 |
| `power.json` | 3 |
| `pinmap.json` | 4 |
| `measurements.jsonl` | the ledger that closes phase 9 |

## Try breaking it

```powershell
# Move the analog input to an ADC2 pin with Wi-Fi on, and watch phase 4 fail.
# Change the cell to 500 mAh, and watch phase 2 reject it against the charger.
# Change a state's provenance to "vendor_claim", and watch phase 3 stop passing.
```
