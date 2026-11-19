# Design Rationale

Why V3 looks the way it does.

| Decision | Why |
|---|---|
| **Start from an Ender 3** | cheap or free donor machines: extrusion, motors, belts and hardware for one build |
| **CoreXY instead of roller X/Y** | both motors stay on the frame, so the moving head is light: higher speed and less wobble than V2's rollers |
| **LumenPnP-style toolhead, CP40 tips** | a proven open design; standard, cheap, interchangeable tips |
| **Compressor + venturi instead of a diaphragm pump** | stronger, steadier vacuum; the valve switches it in milliseconds |
| **Cameras instead of precise mechanics** | a printed machine can't be built to 0.05 mm; cameras measure where things really are and the software corrects for it |
| **Visual homing on a printed datum** | sensorless homing alone lands 0.1 - 2 mm off; one camera look fixes it to ~0.01 mm without endstops |
| **Board found from its own pads** | no fiducials needed on student boards; any distinct pads work |
| **Our own software, not OpenPnP** | runs headless on a 1 GB Pi next to Klipper, and the touchscreen can drive it; OpenPnP needs a desktop computer |
| **Job file, not G-code** | placing needs cameras, feeders and retries; the job file stays independent of where the board lands |
| **Klipper with a second MCU (Uno)** | servos and LEDs on a cheap board; the Octopus endstop ports would not pass LED data |
| **Servo feeders (0816)** | simple and cheap; one servo per feeder |
| **Raspberry Pi 4 instead of 5** | touchscreen compatibility |
| **Software emergency stop for now** | the touchscreen e-stop stops every motor and output at once; a hardware switch in the 24 V line is planned |
