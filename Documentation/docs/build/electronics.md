# 4. Electronics and Wiring

!!! warning "Ongoing"
    The V3 wiring diagram, power supply rating, wire gauges and port labels are being added.
    This page lists every connection the configuration expects.

## Components

| Part | Role | Connects to |
|---|---|---|
| BTT Octopus Pro (STM32H723) | Klipper main MCU: steppers, valve, toolhead LEDs, fan | Pi (USB) |
| 4 x TMC5160 drivers | Stepper drivers (SPI), sensorless homing, current limits | Octopus driver slots |
| Arduino Uno R3 | Second Klipper MCU: **feeder servos**, up-camera ring, frame lights | Pi (USB) |
| Raspberry Pi 4 (1 GB) | Host: MainsailOS, Klipper, Moonraker, cameras, pnpvision, touchscreen | USB to Octopus, Uno, both cameras, card reader hub |
| 7" touchscreen | KlipperScreen | Pi (display + touch) |
| Steppers | 2 x NEMA 17 (CoreXY), 1 x NEMA 17 (Z), 1 x NEMA 11 (rotation) | Octopus |
| Down / up camera | Arducam 12MP USB / InnoMaker 720P USB | Pi |
| Servos | one hobby servo per feeder | Uno signal pins, **separate 5 V supply** |
| Solenoid valve | vacuum on/off | Octopus FAN1 |
| 24 V supply, fuse | power for the Octopus | Octopus power input |

## Pin map

From `Software/Klipper/printer.cfg`, `pnp_feeders.cfg` and `LEDS.cfg`.

| Klipper name | Device | Pin | Notes |
|---|---|---|---|
| `stepper_x` | CoreXY motor, **rear left** (seen from the front) | step PF13, dir PF12, en PF14, CS PC4 (MOTOR0) | 1.0 A, diag PG6 |
| `stepper_y` | CoreXY motor, **rear right** | step PG0, dir PG1, en PF15, CS PD11 (MOTOR1) | 1.0 A, diag PG9 |
| `stepper_z` | Z | step PF11, dir PG3, en PG5, CS PC6 | 0.5 A (homes at 0.8), diag PG10 |
| `manual_stepper stepper_r` | nozzle rotation | step PG4, dir PC1, en PA2, CS PC7 | 0.5 A |
| `output_pin valve` | solenoid valve | PD12 (FAN1) | off at power loss |
| `fan` | electronics fan | PA8 (FAN0) | |
| `neopixel leds` | toolhead: LED 1 status, LEDs 2-3 down light | PB10 | |
| `neopixel up_light` | up-camera ring (6 LEDs) | `uno:PB3` (Uno D11) | |
| `neopixel frame` | frame strip (44 LEDs) | `uno:PB2` (Uno D10) | |
| `servo feeder_1` | feeder slot 1 | `uno:PD5` (Uno D5) | the working feeder |
| `servo feeder_2`, `_3` | feeder slots 2, 3 | `uno:PD6`, `uno:PD3` | not in use |

All TMC5160s share software SPI: SCLK PA5, MOSI PA7, MISO PA6.

!!! tip "Which CoreXY motor is which"
    In Klipper's CoreXY, `stepper_x` drives the X+Y belt and `stepper_y` the X-Y belt. With the
    Voron-style belt path and both motors at the back, that puts `stepper_x` (Octopus **MOTOR0**) on
    the **rear left** and `stepper_y` (**MOTOR1**) on the **rear right**, which matches this machine
    homing to the front left with neither direction inverted. If the two plugs are swapped, X still
    moves correctly but Y runs backwards and homing ends at the back left: swap MOTOR0 and MOTOR1
    back. To check a motor directly (machine homed, nozzle up): `FORCE_MOVE STEPPER=stepper_x
    DISTANCE=5 VELOCITY=10` turns only that motor (the head moves diagonally).

## Wiring rules we learned

!!! danger "Servos need their own 5 V supply"
    Power the servos from a separate 5 V supply and join its ground to an Uno GND pin. Never power
    servos from the Uno's 5 V pin. Never use Uno D0/D1 (the USB link to the Pi).

!!! warning "No LED data on the Octopus endstop (STOP) ports"
    They are filtered inputs and did not pass the LED signal. That is why the lights run from the
    Uno.

- **Stepper cables:** many NEMA 17s have a 6-pin connector (2.00 mm) while the board is 4-pin
  (2.54 mm). Wire board -> motor as 1->1, 2->4, 3->3, 4->6. If a motor buzzes and doesn't turn,
  check this first. Label each cable with its axis: they are identical and easy to swap.
- **LED noise:** an LED data line next to stepper wires picked up noise and made the down light
  flicker purple, which darkens white features for the camera. Twist a ground wire with the data
  wire, add a 220 - 470 Ω series resistor and a 100 - 1000 µF capacitor across the LED supply.
- **USB:** the Pi's four ports carry both cameras, the Uno and the Octopus. The SD card reader goes
  on a USB 3.0 hub on a blue port, together with the up camera - never the Octopus or the Uno, so a
  hub problem can't drop the Klipper link. Cameras are found by ID, so they can move ports.
- **Power:** the 24 V line is fused. Don't split leads with tape: use a lever connector, ferrules or
  a proper splice.
