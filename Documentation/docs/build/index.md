# Build

This section takes you from a donor Ender 3 to a machine ready for [Software Setup](../software/index.md).

!!! warning "Ongoing: V3 build guide"
    The V3 step-by-step assembly (with hardware counts and photos), the **V3 bill of materials**
    and the **V3 wiring diagram** are being written. Until then, these pages give the build order,
    the files to use and everything we learned the hard way. The V2 guide (in the
    [History](../project/history.md)) shows the level of detail that is coming.

## Order

1. [Print the parts](printing.md)
2. [Take apart the Ender 3](teardown.md)
3. [Frame and motion](mechanical.md): frame, CoreXY, toolhead, staging plate
4. [Electronics and wiring](electronics.md)
5. [Pneumatics](pneumatics.md)
6. [Feeder hardware](feeders.md)
7. Then: [Software Setup](../software/index.md) and [Calibration](../calibration/index.md)

## Before you start

### Tools
- Metric hex keys (M3, M5 hardware; 1.5 mm for set screws) and a metric wrench set
- Needle-nose pliers, wire strippers, crimpers (JST and ferrules)
- Soldering iron (heat-set inserts, LED wiring)
- A 3D printer for large parts (tested: Bambu Lab A1, Prusa CORE One, Voron 2.4)
- A computer to flash the SD card and run the slicer

### Skills
- Basic 3D printing and heat-set inserts
- Crimping connectors
- Using a terminal over SSH (the setup commands are all written out)

### Materials
- A Creality Ender 3 (a broken one is fine): extrusion, motors, belts, pulleys, hardware
- PETG for structural parts and motor mounts, PLA for the rest
- M3/M4/M5 T-nuts and screws, heat-set inserts
- Electronics, cameras, servos and pneumatics: see the [BOM](https://github.com/OSHE-Github/OSHE-PnP/tree/main/BOMs) (**Ongoing** for V3)

## Where the files are

| What | Repository folder |
|---|---|
| CAD (STEP, STL, 3MF) | `CAD/V3-Active/` (Framing, X-Axis, Staging, Feeder, Electrical) |
| Bill of materials | `BOMs/` |
| Klipper configuration | `Software/Klipper/` |
| Machine software | `Software/pnpvision/` |
| Slicer | `Software/Slicer/` |
| Photos | `Media/` |
