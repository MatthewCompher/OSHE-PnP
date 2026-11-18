# History (V1, V2)

One version per semester. Files for older versions are in `CAD/V1-Legacy`, `CAD/V2-Legacy` and
`BOMs/`. The full V2 build guide, wiring and BOM are in the V2 documentation (Google Doc / PDF,
linked from the repository README).

## V1: proof of concept (Fall 2025)

An Ender 3 frame converted into a basic XYZ machine, running modified **Marlin** firmware on the
Ender 3's own board (V4.2.2). The firmware is kept in `Software/Legacy-Marlin` but no longer used.

| | V1 |
|---|---|
| Machine size | 486 x 365 x 320 mm |
| Max PCB area | 125 x 125 mm |
| X-Y travel | 237 x 287 mm |
| Reel space | 200 mm |

## V2: Klipper and a rotating toolhead (Spring 2026)

- A nearly fully printed toolhead with nozzle rotation (bevel gears, thrust bearings,
  spring-loaded nozzle).
- Vacuum from a 12 V diaphragm pump and a normally-closed solenoid, in their own enclosure.
- A modular printed frame with roller-based X and Y axes; a spring-loaded PCB clamp on rods.
- BTT Octopus Pro with TMC5160 drivers and a Raspberry Pi 5; firmware moved to **Klipper** and
  Mainsail with sensorless homing.

| | V2 |
|---|---|
| Machine size | 370 x 480 x 352.5 mm |
| Max PCB area | 250 x 250 mm |
| X-Y travel | 305 x 289 mm |
| Reel space | 280 mm |

**V2 results:** about 88 of 100 picks and 18 of 25 placements succeeded. Most placement failures
came from one batch with an operator error, and one error tended to cause the next. The modified
PushPull feeder was unreliable on 40 mm extrusion.

## V3: CoreXY and vision (Fall 2026)

| | V2 | V3 |
|---|---|---|
| Motion | roller X/Y | CoreXY |
| Toolhead | printed, bevel-gear rotation | LumenPnP-style, CP40 tips, NEMA 11 |
| Air | diaphragm vacuum pump | compressor + venturi |
| Feeders | PushPull | 0816 low-profile with servos on an Uno |
| Board holding | rod clamp | staging plate, PCB mounts, datum |
| Vision | none | up and down cameras, pnpvision |
| Jobs | hand-written macros | pnpslice from KiCad |
| Interface | Mainsail | touchscreen Job page, SD/USB jobs |
| Host | Raspberry Pi 5 | Raspberry Pi 4 (touchscreen compatibility) |
| Result | 88 % picks | 97.9 % picks, ~511 CPH, ~0.08 mm |

## Archived experiments

- **Gerber to G-code** (`Archive/Gerber to PCB Vibecode Mini Project`): a V1 browser tool. Replaced
  by pnpslice.
- **USB camera calibration** (`Archive/USB Camera Calibration Vibecode Project`): lens calibration
  capture and the undistorted stream service. Still used by V3.
