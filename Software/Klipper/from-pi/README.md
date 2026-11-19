# from-pi: old snapshot, NOT the live configuration

These files were copied off the Pi on 2026-11-08 for reference while the machine was being brought
up (they still mention a Pi 5 and older Z speeds). Klipper does not read anything in this folder.

**The live configuration is one level up, in `Software/Klipper/`:**

| File | What it holds |
|---|---|
| `printer.cfg` | Octopus Pro + Uno MCUs, CoreXY kinematics, steppers, homing, limits |
| `pnp_hmi.cfg` | touchscreen / Mainsail macros: RUN_JOB, PNP_*, job state, SD/USB import |
| `pnp_feeders.cfg` | feeder servos on the Uno (FEEDER_TOGGLE) |
| `LEDS.cfg` | toolhead, up-camera and frame lights |
| `KlipperScreen_pnp.conf` | the touchscreen "Pick & Place" menu |
| `klipperscreen/pnp_job.py` | the touchscreen Job page |

On the Pi these live in `~/printer_data/config/` (copies or links of the repo files). After a
`git pull`, copy the changed `.cfg` files there and run `FIRMWARE_RESTART`.
