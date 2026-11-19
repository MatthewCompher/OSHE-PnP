# 2. Configuration Files

## Klipper (live files)

Everything Klipper reads lives in `~/printer_data/config/` on the Pi. The repository keeps the
master copies in `Software/Klipper/`.

| Repository file | On the Pi | What it holds |
|---|---|---|
| `printer.cfg` | `~/printer_data/config/printer.cfg` | MCUs, CoreXY kinematics, steppers, homing override, limits, valve |
| `pnp_hmi.cfg` | same folder | touchscreen/Mainsail macros: `RUN_JOB`, `PNP_*`, job state, SD/USB import |
| `pnp_feeders.cfg` | same folder | feeder servos on the Uno, `FEEDER_TOGGLE` |
| `LEDS.cfg` | same folder | toolhead, up-camera and frame lights and their effects |
| `KlipperScreen_pnp.conf` | pasted into `KlipperScreen.conf` | the touchscreen "Pick & Place" menu |
| `klipperscreen/pnp_job.py` | linked into `~/KlipperScreen/panels/` | the touchscreen Job page |

`Software/Klipper/from-pi/` is an **old snapshot** (2026-11-08) kept for reference only. Klipper
never reads it.

!!! note "`[force_move]` is on, on purpose"
    Visual homing re-zeros X/Y with `SET_KINEMATIC_POSITION`, which Klipper only allows with
    `enable_force_move: True`. Nothing else uses it.

## pnpvision

| File | What it holds | Edited by |
|---|---|---|
| `Software/pnpvision/config.toml` | travel limits, safe heights, camera URLs, lights, speeds, feeder bus, plate layout | you (commented line by line) |
| `calibration/machine.json` | measured values: camera offset, up-camera centre, tips, board pose, visual home | calibration commands |
| `calibration/motion_down.json`, `motion_up.json` | camera pixel -> mm maps | `calibrate-motion` |
| `calibration/calibration_cam_*.npz` | lens calibrations | the ChArUco capture script |
| `calibration/feeders.json` | each feeder's pick spot and package | `teach-feeder` |
| `jobs/*.job.json` | jobs | pnpslice / SD-USB import |
| `results/`, `job_*/`, `pnp_events.sqlite` | logs, photos, event database | pnpvision (not in git) |

Calibration files are written safely (temp file, then rename), so a power cut can't leave a
half-written file.

## Important settings in `config.toml`

| Setting | Value | Meaning |
|---|---|---|
| `[machine] safe_travel_z` | 26 | nozzle height for X/Y travel (smaller = higher) |
| `[machine] front_zone_y / front_zone_z` | 30 / 22 | in front of Y 30 (feeders) travel at Z 22 or higher |
| `[run] xy_feedrate` | 24000 mm/min | job travel speed (400 mm/s) |
| `[run] accel` | 5000 mm/s² | job acceleration |
| `[run] align_each_job` | true | find the board again before every job |
| `[run] flip_check` | true | reject resistors picked upside down |
| `[lighting.up] settle_s` | 0.10 | wait after the ring light before the photo |

More in [Speed Settings](../guides/speed.md).
