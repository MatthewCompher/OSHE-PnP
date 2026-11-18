# How It Works

The machine moves a single vacuum nozzle over a fixed plate. The board sits on the plate, the tape
feeders sit at the front, and two cameras tell the software exactly where everything is.

## The parts of the machine

| Subsystem | What it is |
|---|---|
| **Frame** | Ender 3 aluminum extrusion with 3D-printed legs and corners |
| **Motion** | CoreXY (two motors share X and Y through crossed belts), Z for nozzle height, a small stepper to turn the nozzle |
| **Toolhead** | LumenPnP-style holder for Samsung CP40 nozzle tips, NEMA 11 rotation motor, down camera, LEDs |
| **Staging plate** | Printed tiles holding the PCB mounts, the camera datum (reference grid), the reject bin and the up camera |
| **Cameras** | Down camera on the toolhead (finds the board, checks placed parts), up camera under the plate (checks the part on the nozzle) |
| **Feeders** | 0816-style tape feeders, each advanced by a hobby servo driven by an Arduino Uno |
| **Pneumatics** | Compressor and solenoid valve for the nozzle vacuum |
| **Electronics** | BTT Octopus Pro (motion), Arduino Uno (servos, lights), Raspberry Pi 4 (host), 7" touchscreen |

## The software

| Program | Runs on | Job |
|---|---|---|
| **pnpslice** | your computer (Windows app or Python) | Reads a KiCad board, checks it, orders the parts, writes the job file |
| **Klipper** | Pi + Octopus Pro + Uno | Motion, steppers, servos, lights, G-code macros |
| **Moonraker / Mainsail** | Pi | Web API and web dashboard |
| **KlipperScreen** | Pi (touchscreen) | The machine's own screen, including the PnP Job page |
| **crowsnest** | Pi | Streams both cameras |
| **pnpvision** | Pi | Calibration, visual homing, board alignment, the job runner, logging and reports |

## One part, step by step

1. **Feed**: the servo advances the tape by one pocket.
2. **Pick**: the nozzle drops onto the part and the vacuum switches on.
3. **Inspect**: the nozzle stops over the up camera. pnpvision measures the part's size, offset
   and angle. A wrong part, an empty nozzle, a part on its side or upside down is rejected.
4. **Correct and place**: the nozzle turns to the right angle, moves to the board position plus
   the measured offset, lowers, releases the vacuum and lifts.
5. Rejected parts go to the **reject bin** and the machine tries again (up to 3 picks).

Before the first part, the machine **finds the board**: the down camera visits the alignment pads
chosen by pnpslice and fits the board's exact position and rotation.

!!! note "Z runs upside down"
    Z = 0 is the top. A **larger Z moves the nozzle lower**. The nozzle touches the plate at about
    Z 50 and the top of a PCB at about Z 39.5.
