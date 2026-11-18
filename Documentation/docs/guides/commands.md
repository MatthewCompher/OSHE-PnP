# pnpvision Commands

Run on the Pi from `~/OSHE-PnP/Software/pnpvision`:

```bash
~/venv-pnp/bin/python -m pnpvision <command> [options]
```

Add `--help` after any command for all its options. Every command that moves lifts the nozzle to
the safe height before any X/Y move and refuses moves outside the limits in `config.toml`.

| Command | Purpose | Moves? |
|---|---|---|
| **Everyday** | | |
| `home` | visual homing (used by `VISION_HOME`) | yes |
| `align-board JOB --rot 90` | find the board from its alignment pads | yes |
| `run-job JOB [--dry-run] [--only R1 R2] [--no-feeders]` | place a job | yes |
| `check-board JOB [--only ...]` | down camera over each footprint: PLACED / MISSING + mm error | yes |
| `report [--out DIR] [--since DATE]` | export the event log (CSV + contact sheets) | no |
| `import-jobs [--device DEV] [--from DIR]` | load job files from SD card / USB stick | no |
| `make-launchers` | `PNP_<job>.gcode` launcher files for the print list | no |
| **Feeders and bin** | | |
| `feed SLOT [--times n]` | feed a servo feeder | no |
| `teach-feeder ID --servo n --package PKG` | save a feeder's pick spot | no |
| `feeder-cycle ID --n 20` | pick and drop in the bin, N times, no vision | yes |
| `teach-bin [--goto] [--default]` | reject bin position | yes |
| **Calibration** | | |
| `check-lens` | check the lens calibration files | no |
| `snapshot --cam up/down [--lit]` | save a camera image | no |
| `find-dot --cam ...` | show which round blobs the detector finds | no |
| `focus-sweep` | step Z over the up camera, score sharpness | yes |
| `calibrate-motion --cam up/down ...` | camera pixels -> mm map | yes |
| `calibrate-offset` / `set-offset X Y` | down camera -> nozzle offset | yes / no |
| `repeatability --n 20` | go away and back, measure scatter | yes |
| `datum [--teach] [--reference]` | datum grid | yes |
| `tip NAME [--board-touch-z Z] [--inspect-z Z] [--current]` | nozzle tip heights | no |
| `inspect-up`, `light-test` | inspect a part on the nozzle; test lights | yes |
| `place-test` | pick and place spare parts, measure where they land | yes |
| `check-machine [--apply]` | recovery check after a disturbance | yes |
| `hmi-test` | test dialog on the touchscreen | no |

Tests that need no hardware: `pytest` in `Software/pnpvision` (92 tests).
