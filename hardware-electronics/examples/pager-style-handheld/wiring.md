# Wiring - pager-style-handheld

One row per wire. Tick them off as you make them; the point of the column is that a half-built harness is indistinguishable from a finished one without it.

| Done | Net | Kind | From | To | Colour | AWG | Peak mA |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [ ] | `gnd` | ground | battery.- | mainboard.GND | black | 26 | - |
| [ ] | `gnd` | ground | mainboard.GND | amp.GND | black | 26 | - |
| [ ] | `gnd` | ground | amp.GND | mic.GND | black | 26 | - |
| [ ] | `gnd` | ground | mic.GND | haptic.GND | black | 26 | - |
| [ ] | `gnd` | ground | haptic.GND | expander.GND | black | 26 | - |
| [ ] | `gnd` | ground | expander.GND | piezo.2 | black | 26 | - |
| [ ] | `vbat` | power | battery.+ | mainboard.VBAT | red | 26 | 1220 |
| [ ] | `vbat` | power | mainboard.VBAT | amp.VIN | red | 26 | 1220 |
| [ ] | `v3v3` | power | mainboard.3V3 | mic.3V3 | orange | 28 | 165 |
| [ ] | `v3v3` | power | mic.3V3 | haptic.VIN | orange | 28 | 165 |
| [ ] | `v3v3` | power | haptic.VIN | expander.VCC | orange | 28 | 165 |
| [ ] | `i2c_sda` | signal | mainboard.39 | expander.SDA | blue | 30 | - |
| [ ] | `i2c_sda` | signal | expander.SDA | haptic.SDA | blue | 30 | - |
| [ ] | `i2c_scl` | signal | mainboard.38 | expander.SCL | white | 30 | - |
| [ ] | `i2c_scl` | signal | expander.SCL | haptic.SCL | white | 30 | - |
| [ ] | `exp_int` | signal | mainboard.21 | expander.INTA | green | 30 | - |
| [ ] | `mic_bclk` | signal | mainboard.41 | mic.BCLK | grey | 30 | - |
| [ ] | `mic_ws` | signal | mainboard.42 | mic.WS | violet | 30 | - |
| [ ] | `mic_sd` | signal | mainboard.40 | mic.SD | brown | 30 | - |
| [ ] | `amp_bclk` | signal | mainboard.47 | amp.BCLK | grey | 30 | - |
| [ ] | `amp_lrc` | signal | mainboard.48 | amp.LRC | violet | 30 | - |
| [ ] | `amp_din` | signal | mainboard.17 | amp.DIN | brown | 30 | - |
| [ ] | `spk_p` | signal | amp.OUT+ | speaker.1 | red | 30 | 700 |
| [ ] | `spk_n` | signal | amp.OUT- | speaker.2 | black | 30 | 700 |
| [ ] | `motor_p` | signal | haptic.OUT+ | motor.1 | red | 28 | 156 |
| [ ] | `motor_n` | signal | haptic.OUT- | motor.2 | black | 28 | 156 |
| [ ] | `piezo_drive` | signal | expander.GPB0 | piezo.1 | yellow | 30 | 12 |

## Before power-on

- [ ] Continuity and short check across every power rail, board unpowered.
- [ ] Battery connector polarity metered. Polarity is not standardised.
- [ ] First power-on current-limited if a bench supply is available.
- [ ] One peripheral at a time. Silence from two at once tells you nothing.

See `reference/bench-review.md` for the full checklist.
