# Feeder servos on the Arduino Uno — wiring + Klipper setup (handoff)

For whoever is wiring the tape feeders, and their Claude. Goal: each tape feeder's servo is driven
by Klipper through the Arduino Uno, the same way the up-camera light ring already is. When this
is done, the Pi software (`pnpvision`) will advance a feeder by sending one G-code command. Joey
(and Joey's Claude) will change `pnpvision` to use it — **you don't need to touch any Python.**

Deadline for the whole machine is ~Wed 2026-11-18, so aim for the simplest thing that works
reliably: 3 feeders now, with room for about 10 later.

---

## 1. How the machine is set up today

- **Raspberry Pi 4** runs Klipper + Moonraker + Mainsail (http://192.168.137.50 over direct
  Ethernet from Joey's laptop) and the KlipperScreen touchscreen.
- **Two Klipper MCUs:**
  - `[mcu]` — BTT Octopus Pro (motors, vacuum, etc.). Don't change anything on it.
  - `[mcu uno]` — **Arduino Uno R3 (ATmega328P) already flashed with Klipper**, plugged into
    the Pi by USB:
    ```ini
    [mcu uno]
    serial: /dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_5573032383135130C112-if00
    restart_method: arduino
    ```
- **The pattern to copy** — the up-camera LED ring is on Uno pin D11, which Klipper calls
  `uno:PB3`:
  ```ini
  [neopixel up_light]
  pin: uno:PB3
  chain_count: 6
  ```
  Feeders work the same way: a `[servo ...]` section per feeder, with `pin: uno:<port pin>`.

### Klipper pin names on the Uno
Klipper uses the AVR port names, not the Arduino "D" numbers. Prefix them with `uno:`.

| Arduino pin | Klipper name | Status |
|---|---|---|
| D0, D1 | PD0, PD1 | **DO NOT USE** — this is the USB serial link to the Pi |
| D2 | PD2 | free |
| D3 | PD3 | **feeder slot 3** |
| D4 | PD4 | free |
| D5 | PD5 | **feeder slot 1** |
| D6 | PD6 | **feeder slot 2** |
| D7 | PD7 | free |
| D8 | PB0 | free |
| D9 | PB1 | free |
| D10 | PB2 | **TAKEN** — frame lights (44 x WS2812, LEDS.cfg) |
| D11 | PB3 | **TAKEN** — up-camera LED ring |
| D12 | PB4 | free |
| D13 | PB5 | onboard LED, avoid |
| A0–A5 | PC0–PC5 | free (work as digital pins) |

Slot → pin map (slots 1–3 as wired 2026-11-16; 4–10 suggested). **Pick the final list, write it into the config comments and into the
table at the bottom of this file, and don't change it afterwards** — the software assumes
"slot k = servo k":

| Slot | Arduino | Klipper |
|---|---|---|
| 1 | D5 | uno:PD5 |
| 2 | D6 | uno:PD6 |
| 3 | D3 | uno:PD3 |
| 4 | D9 | uno:PB1 |
| 5 | D2 | uno:PD2 |
| 6 | D4 | uno:PD4 |
| 7 | D7 | uno:PD7 |
| 8 | D8 | uno:PB0 |
| 9 | D12 | uno:PB4 |
| 10 | A0 | uno:PC0 |

(Klipper drives servos with its own timed pulses, so any free GPIO works — not just the
Arduino "PWM ~" pins.)

---

## 2. Wiring

**Slot k = servo k, fixed.** Slots are positions on the feeder bar, counted **left to right**
looking at the machine from the front; the leftmost slot (slot 1) is the feeder butted against
the datum. The harness belongs to the bar: whatever feeder sits in slot 3 plugs into the slot-3
cable. Label both ends of each cable with the slot number.

Each servo has 3 wires:

| Servo wire (usual colours) | Goes to |
|---|---|
| Signal (orange / yellow / white) | Uno pin for that slot (table above) |
| +5 V (red) | **separate 5 V supply** + |
| GND (brown / black) | **separate 5 V supply** − |

And one extra wire: **5 V supply − (GND) to an Uno GND pin.** Without this common ground the
signal has no reference and the servos twitch or ignore commands.

Rules:
- **Do not power the servos from the Uno's 5 V pin.** It comes from the Pi's USB port; a servo
  stalling (~0.5–1 A each for SG90/MG90-class) will brown out the Uno, Klipper loses the MCU and
  the whole machine shuts down mid-job.
- Use a 5 V supply rated about **1 A per servo that can move at once, plus margin** — e.g. a
  5 V / 3 A or better supply for the first 3–4. The software will only stroke one feeder at a time.
- Don't connect the 5 V supply's + to the Uno at all.
- Keep signal leads reasonably short / twisted with GND if you see jitter; a 470–1000 µF
  capacitor across 5 V/GND near the servos helps with supply dips.
- Power off (or at least unplug the servo supply) while changing wiring.

---

## 3. Klipper config

Put the feeder config in its **own file**, `Software/Klipper/pnp_feeders.cfg`, next to
`printer.cfg` and `pnp_hmi.cfg`, and include it from `printer.cfg`:

```ini
[include pnp_hmi.cfg]
[include pnp_feeders.cfg]
```

That keeps your changes out of the big `printer.cfg`, which Joey is also editing.

### The live file
`pnp_feeders.cfg` (in this folder) is the source of truth: per-slot `[servo feeder_N]` sections,
`FEEDER_TOGGLE SLOT=n [COUNT=k]` (one feed: rest -> stroke -> rest, then the servo goes limp;
per-slot angles and shared timings at the top of the macro) and `FEEDER_SET SLOT=n ANGLE=deg`
/ `OFF=1` (hold one servo at an angle, for setup). Pulse widths 650-2350 us, no `initial_angle`.

**Adding a slot:** copy a `[servo feeder_N]` block with the next pin from the table, add its
angles to `rest_angles` / `stroke_angles`, and raise the slot limit check in `FEEDER_TOGGLE`.

The old Octopus `[servo feeder1]` on PG13 and its `FEED` macro were removed 2026-11-17;
`FEEDER_SET` now means the Uno version above.

### Getting the config onto the Pi
The live config is in `~/printer_data/config/` on the Pi. Either:
- upload `pnp_feeders.cfg` through Mainsail (Machine tab → upload) and add the `[include]` line
  to the live `printer.cfg` there, then **FIRMWARE_RESTART**; or
- ask Joey to upload it.

Then make sure the **repo copy matches the live copy** (Joey commits). Before editing the live
`printer.cfg`, compare it with the repo's `Software/Klipper/printer.cfg` so nothing gets lost.

### If Klipper complains after restart
- `mcu 'uno': Unable to connect` → Uno unplugged/brown-out; check it isn't powering servos.
- An error mentioning an unknown command / missing feature on `uno` → the Uno firmware was built
  with optional features trimmed (it's at the 32 KB flash limit). Klipper's servo normally needs
  nothing optional, but if it does, tell Joey before reflashing: the Uno build is
  `cd ~/klipper && make KCONFIG_CONFIG=config.uno` and must still fit.
- `Pin 'PD3' used multiple times` / pin errors → a pin is already used, or a typo in the name.

---

## 4. Bring-up and test (Mainsail console)

Do this with **one servo first**, then 3–4, before trusting all of them.

1. Servo horn off (or feeder lever free), servo supply on, `FIRMWARE_RESTART`.
2. `FEEDER_SET SLOT=1 ANGLE=0`, then `ANGLE=90`, then `ANGLE=180` — check it moves,
   in the expected direction, with no buzzing at the ends. If it buzzes / hits its own stop at
   0 or 180, narrow `minimum_pulse_width` / `maximum_pulse_width` (e.g. 0.0007 / 0.0023).
3. `FEEDER_SET SLOT=1 OFF=1` → servo goes limp.
4. Fit the horn / lever. Find the **rest** and **stroke** angles that advance the tape exactly
   one pocket (4 mm pitch for 0805/0603 paper tape) and come back cleanly. Set them in
   `variable_rest_angles` / `variable_stroke_angles` (one entry per slot).
5. Shorten `out_ms` / `back_ms` as far as it still works reliably — **speed matters**: the
   target is 500 parts/hour (7.2 s per part total), so a feed should take well under 1 s.
6. With tape loaded: `FEEDER_TOGGLE SLOT=1 COUNT=20` and check the tape advances 20 pockets, the part
   ends up in the same spot every time, and the cover tape peels cleanly.
7. Repeat for slots 2, 3. Then run them back-to-back (`FEEDER_TOGGLE SLOT=1`, `FEEDER_TOGGLE SLOT=2`, …)
   to check the 5 V supply holds and the Uno never disconnects.
8. Run the motors at the same time as a feed (jog X/Y in Mainsail) to make sure nothing
   glitches (the Uno also drives the LED ring; that's fine, just confirm).

Write the results into the table below.

---

## 5. What the software side expects (the contract)

`pnpvision` will call, over Moonraker G-code:

| Command | Meaning |
|---|---|
| `FEEDER_TOGGLE SLOT=n` | advance feeder in slot n by one part; returns when finished |
| `FEEDER_TOGGLE SLOT=n COUNT=k` | advance k parts (loading / clearing leader tape) |
| `FEEDER_SET SLOT=n ANGLE=deg` / `OFF=1` | setup only |

Please keep those names and parameters. Everything else (angles, timings, pins) is yours to tune.
Joey's side will add the `pnpvision` "Klipper feeder bus" that replaces the old Nano serial
protocol (`Software/feeder_nano/feeder_nano.ino` is now obsolete for this machine — don't flash
it to the Uno, the Uno must stay on Klipper firmware).

Nice-to-have (only if the basics are solid): make `FEEDER_TOGGLE` non-blocking so the head can keep
moving while the tape advances (e.g. send the stroke, then do the return with a
`[delayed_gcode]` instead of `G4`). Talk to Joey first — the software would then need a way to
know the feed is done before picking.

---

## 6. Results (fill in)

| Slot | Uno pin | Klipper pin | Servo model | Pulse min/max (s) | Rest° | Stroke° | out/back ms | 20-feed test OK? |
|---|---|---|---|---|---|---|---|---|
| 1 | D5 | uno:PD5 | | | | | | |
| 2 | D6 | uno:PD6 | | | | | | |
| 3 | D3 | uno:PD3 | | | | | | |

5 V servo supply used (V / A): ______  Common GND to Uno: yes / no

Problems / notes:
