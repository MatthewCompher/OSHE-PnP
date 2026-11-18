# Known Limitations

What V3 can't do yet, or does with a caveat. Each item is also on the [Roadmap](../project/roadmap.md).

## Feeders
- **One working feeder (F1).** Feeders 2 and 3 were built but abandoned for this release: one
  servo stripped its gears, and the other feeder's lever did not reliably catch and release the
  tape holes. Jobs place one package type (0603 resistors on F1); other packages can be loaded by
  hand with the job's **No feeders** option.
- The feeder stroke is a plain 400 ms out / 400 ms back. Faster or ramped strokes bounced parts
  out of the pocket.
- Each feed waits for the servo (it does not overlap with motion yet).

## Parts and accuracy
- Tested on **0603 and 0805 resistors** with the N08 tip. Other packages are in the tables but
  not proven.
- Rotations at 45° landed about 4 - 5° short in early tests (0°/90° are within ±1°). Chip parts
  self-align in reflow; a correction can be added.
- The upside-down check works for resistors only (dark top vs white body).
- One nozzle: no tip changer. A job that needs two tips asks you to swap them.

## Vision and setup
- Alignment starts from the last known board position: if the board is put down far from where
  it was, center the down camera on pad A by eye first (`align-board`).
- Bright frame lights wash out the up camera's view of the nozzle bore: keep them at about 15 %.
- `check-machine --apply` assumes the nozzle moved. If the up camera moved instead it gives a wrong
  offset: use `calibrate-offset` ([Recovery Check](../calibration/recovery.md)).
- Sensorless homing alone lands 0.1 - 2 mm off; always use **Vision home** before work.

## Machine
- **Software emergency stop only** (see [Safety](safety.md)).
- The Pi 4 has 1 GB of memory: large installs must be done over SSH with the touchscreen stopped.
- Moonraker accepts commands from the whole local network without a login.
- No measured long-term (multi-hour) run yet; the longest recorded run is four 23-part jobs back to
  back.
