# Recovery Check

Use this when the head was removed, the nozzle swapped, the gantry used for something else, or
anything bumped.

1. Nozzle **empty**, **Vision home** done, `UP_LIGHT_ON`.
2. Touchscreen **Pick & Place -> Calibration check**, or:
   ```bash
   python -m pnpvision check-machine
   ```
3. It checks that `printer.cfg` still has the pnpvision sections, that the homing dot sits on the
   crosshair, that both camera maps still predict a small jog, and that the nozzle bore is where the
   up camera expects. Each line says **OK** or **REDO** with the step to repeat.

!!! warning "Don't trust `check-machine --apply` blindly"
    `--apply` assumes the **nozzle** moved and shifts the camera offset to match. If the **up
    camera** moved instead (or a light washed out the bore), it saves a wrong offset: on 11-17 it
    added a bad +0.47 mm in Y. To fix the offset, measure it directly with
    [`calibrate-offset`](nozzle.md#7-down-camera-to-nozzle-offset), then check with a dry run.

## Placements all shifted the same way?

Before changing any calibration:

1. **Re-align the board** (Job page with **Align first** on, or `align-board`). A stale board
   position is the most common cause.
2. Do a **dry run** and look at the photos in `job_<time>/`: the crosshair marks the target, and
   the down camera sees about 59 px per mm.
3. Only then look at the camera offset.
