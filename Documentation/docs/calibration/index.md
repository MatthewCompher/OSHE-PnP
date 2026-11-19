# Calibration

Calibration ties the two cameras to the machine's coordinates, so that what a camera sees can be
reached by the nozzle to a few hundredths of a millimetre. Do it **once per machine, in this order**.
Each step says when it has to be redone.

All commands run on the Pi from `~/OSHE-PnP/Software/pnpvision` as
`~/venv-pnp/bin/python -m pnpvision <command>`. Results are saved in `calibration/machine.json`.

| # | Step | Command | Redo when |
|---|---|---|---|
| 1 | [Lens calibration](cameras.md#1-lens-calibration) (both cameras) | `calib_capture.py`, then `check-lens` | lens refocused or swapped |
| 2 | [Exposure and lighting](cameras.md#2-exposure-and-lighting) | `snapshot`, `focus-sweep` | camera, light or lens changed |
| 3 | [Down-camera motion map](motion-homing.md#3-down-camera-motion-map) | `calibrate-motion --cam down --step 3` | camera moved or refocused |
| 4 | [Visual homing](motion-homing.md#4-visual-homing) | `home --teach` | datum or down camera moved (then redo all below) |
| 5 | [Datum reference](motion-homing.md#5-datum-reference) | `datum --teach`, `datum --reference` | datum moved |
| 6 | [Up-camera map and centre](nozzle.md#6-up-camera-map-and-centre) | `calibrate-motion --cam up --find-center` | up camera moved or refocused |
| 7 | [Down camera to nozzle offset](nozzle.md#7-down-camera-to-nozzle-offset) | `calibrate-offset` | camera or nozzle holder moved |
| 8 | [Tip heights](nozzle.md#8-tip-heights) | `tip N08 --board-touch-z ... --inspect-z ...` | tip changed |
| 9 | [Rotation direction](nozzle.md#9-rotation-direction) | `inspect-up` | rotation motor or tip changed |
| 10 | [Placement check](nozzle.md#10-placement-check) | `place-test` | nozzle, head or a camera moved |
| 11 | [Reject bin](bin-feeders.md#reject-bin) | `teach-bin --goto` | bin moved |
| 12 | [Feeders](bin-feeders.md#feeders) | `teach-feeder F1 ...` | feeder moved |

After that, the board is found automatically before every job ([Run a Job](../operate/run-a-job.md)).
If anything gets bumped later, use the [Recovery Check](recovery.md).

## Measured on the prototype (2026-11-17)

| Value | Result |
|---|---|
| Repeatability (down camera, go away and back) | about 0.01 mm |
| Datum fit | rms 0.039 mm |
| Down camera to nozzle offset | (9.183, 52.927) mm |
| N08 tip: board touch Z / inspect Z | 39.5 / 34.6 |
| Down camera scale | about 59 px/mm at PCB height |

!!! tip "Lessons that cost us hours"
    - **Calibration targets must not move.** A loose paper dot slid 0.05 mm during fast moves and
      looked like a machine error. Tape or glue it.
    - **Centre a feature before measuring it.** The down camera is only 11.5 mm from the board;
      its scale changes about 9 % per mm of height.
    - **The up camera is tilted ~5°.** Calibrate and inspect at one fixed height (the part-bottom
      plane, Z 34.6 for the N08 tip). Inspecting at the holder face read a fake 0.4 mm offset.
    - **Use square pixels when undistorting.** OpenCV's default made round dots 24 % oval.
    - **Use `calibrate-offset`, not `check-machine --apply`,** to fix the camera offset (see
      [Recovery Check](recovery.md)).
    - **If placements are all shifted the same way, re-align the board** before touching any
      calibration: a stale board position gave a +0.43 mm Y error once.
