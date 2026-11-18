# Specifications

## Machine

| | V3 |
|---|---|
| Motion | CoreXY (Voron-inspired), sensorless homing, refined by visual homing on a datum dot |
| Travel | X 0 - 235 mm, Y 0 - 343 mm, Z 0 - 51 mm |
| Limits | Klipper max 600 mm/s and 7500 mm/s²; jobs run at 400 mm/s and 5000 mm/s²; Z capped at 50 mm/s |
| Repeatability | about 0.01 mm measured with the down camera |
| Nozzle | one nozzle, Samsung CP40 tips (N08 for 0603/0805) |
| Rotation | NEMA 11, 360 °/s, 3000 °/s² |
| Parts tested | 0603 resistors (acceptance), 0805 resistors (place tests) |
| Feeders | 8 mm paper tape, servo-driven; 1 working (F1) |
| Host | Raspberry Pi 4, 1 GB, MainsailOS |
| Controller | BTT Octopus Pro (STM32H723), TMC5160 drivers; Arduino Uno as second Klipper MCU |
| Interface | 7" touchscreen (KlipperScreen), Mainsail in a browser |
| Job input | KiCad `.kicad_pcb` -> pnpslice -> `.job.json`, loaded over the network or from SD card / USB stick |

!!! warning "Ongoing"
    Machine footprint, maximum PCB size and power supply rating are still to be measured and added.

## Performance (acceptance runs, 2026-11-18)

| Requirement | Target | Result |
|---|---|---|
| Throughput | 500 parts/hour | 491 / 519 / 499 / 527 CPH (average ~511) |
| Picks from tape | 95 % | 97.9 % (92/94) |
| Vision pass/fail correct | 95 % | 100 % of 193 up-camera and 138 board-check decisions |
| Placement error | - | mean 0.075 - 0.094 mm, worst 0.229 mm |
| Operation without a laptop | yes | job loaded from SD/USB and run from the touchscreen |

Details: [Results](../testing/results.md).
