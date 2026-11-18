# 3. Frame and Motion

!!! warning "Ongoing"
    Step-by-step photos and hardware counts for this page are being written. The order and the
    checks below are what we used on the prototype.

## Frame
Assemble the four legs from the bottom, middle and spacer pieces (mirror pairs A and B) and join
them with the 4040 extrusion and 4040 spacers.

!!! tip "Square it now"
    Measure both diagonals of the top frame: they must match within about 1 mm. An out-of-square
    frame shows up later as position errors that calibration can only partly hide.

## CoreXY motion
1. Mount the two motors in the motor corners and the idlers in the idler corners.
2. Fit the X carriage (upper and lower parts) and the rail spacer.
3. Run the two belts in the CoreXY pattern (each belt goes motor -> idlers -> carriage, crossing
   at the back) and tension them with the printed tensioners. Both belts should be equally tight:
   firm, not over-tight.
4. Move the carriage by hand (motors unplugged) over the whole area: it must glide without tight
   spots.

## Toolhead
The V3 toolhead is based on the LumenPnP design: a holder for Samsung CP40 nozzle tips, turned by
a NEMA 11 stepper through a rotary pneumatic fitting, plus the down camera and three LEDs.

1. Assemble the nozzle holder and rotation motor.
2. Mount the down camera (Arducam 12MP USB, M12 lens) so it looks straight down, about 11.5 mm
   above a PCB.
3. Attach the toolhead to the X carriage and the Z stage. Start with the **N08** tip.

## Staging plate
1. Assemble the plate (four quarters or two halves) on the plate brackets, with the up-camera
   opening over the up camera.
2. Mount the up camera (InnoMaker 720P) in its camera mount, with the LED ring on the light plate
   and the diffuser, under the opening, looking up.
3. Fix the **camera datum**, the **PCB mounts** (one fixed, one adjustable) and the **reject bin**
   into their inserts. Positions are set by the plate's insert grid (30 mm pitch); see
   `config.toml [layout]`.

!!! danger "The datum must never move after calibration"
    Visual homing and every camera calibration use datum dot 0 as the origin. If the datum moves,
    redo [Calibration](../calibration/index.md) from step 2.

## Holding the board
Put the board against the fixed PCB mount, slide the adjustable mount up to it and tighten. The
board must not rock: press each corner. The machine finds the board's exact position itself, so
it doesn't have to be placed precisely - just firmly.
