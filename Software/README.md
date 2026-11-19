# 💻 Software

Everything that runs the OSHE Pick and Place (V3). Full setup and usage are in the
documentation: [Software Setup](../Documentation/docs/software/index.md),
[Calibration](../Documentation/docs/calibration/index.md),
[Running Jobs](../Documentation/docs/operate/index.md).

## 🧱 What runs where

```
Your computer                        Raspberry Pi 4 (MainsailOS)                Controllers
-------------                        ---------------------------                -----------
KiCad -> pnpslice -> job file  ----> pnpvision (calibration, jobs, reports)
         (SD/USB or network)          |  Moonraker API (port 7125)
                                      |    -> Klipper host -------------------> Octopus Pro: steppers, valve, toolhead LEDs
                                      |  KlipperScreen (touchscreen Job page)  \-> Arduino Uno: feeder servos, camera + frame lights
                                      |  Mainsail (browser)
                                      \- crowsnest (down + up camera)
```

| Folder | What | README |
|---|---|---|
| [`Klipper/`](Klipper) | Klipper configuration, touchscreen menu and Job page, SD/USB mount rule | [Klipper/README.md](Klipper/README.md) |
| [`pnpvision/`](pnpvision) | Python on the Pi: visual homing, camera calibration, board alignment, the job runner, board check, reports, SD/USB import | [pnpvision/README.md](pnpvision/README.md) |
| [`Slicer/`](Slicer) | **pnpslice**: KiCad board -> `oshe-pnp-job/1` job file; Windows app or Python | [Slicer/README.md](Slicer/README.md) |
| [`feeder_nano/`](feeder_nano) | **obsolete** Arduino Nano feeder firmware (replaced by Klipper servos on the Uno) | [feeder_nano/README.md](feeder_nano/README.md) |
| [`Legacy-Marlin/`](Legacy-Marlin) | **obsolete** V1 Marlin firmware | - |

Lens calibration and the undistorted camera views come from
[`Archive/USB Camera Calibration Vibecode Project`](../Archive/USB%20Camera%20Calibration%20Vibecode%20Project)
(still used by V3).

## ⚙️ Hardware and key facts

| | |
|---|---|
| Controller | BTT Octopus Pro (STM32H723), TMC5160 drivers; Arduino Uno R3 as second Klipper MCU |
| Host | Raspberry Pi 4 (1 GB), MainsailOS, user `pnp`, repository at `~/OSHE-PnP` |
| Kinematics | CoreXY; travel X 0 - 235, Y 0 - 343, Z 0 - 51 mm |
| **Z direction** | **0 = top, larger Z = nozzle lower.** Plate at about Z 50, PCB top at Z 39.5 (N08 tip), travel at Z 26, Z 22 in front of Y 30 (feeders) |
| Rotation | `[manual_stepper stepper_r]`, 1 unit = 1°, no endstop (`G28` sets 0) |
| Homing | sensorless, then **Vision home** re-zeros X/Y on datum dot 0 with the down camera |
| Cameras | down: Arducam 12MP (1920 x 1080, `/webcam/`); up: InnoMaker 720P (1280 x 720, `/webcam2/`, fixed exposure) |

## 📋 Status (2026-11-18)

| Subsystem | State |
|---|---|
| Motion, homing, visual homing, nozzle rotation | ✅ working |
| Lights (toolhead, up-camera ring, frame) | ✅ working |
| Cameras, lens calibration, motion maps, nozzle offset | ✅ calibrated |
| Board alignment from copper pads | ✅ working (before every job) |
| Up-camera inspection: size, angle, on its side, upside down, empty | ✅ working, rejects go to the bin |
| Vacuum (compressor, valve, venturi) | ✅ working |
| Feeders | ✅ F1 working; F2 / F3 abandoned (hardware) |
| Job runner, retries, reject bin, event log, reports | ✅ working: 97.9 % picks, ~511 parts/hour |
| Touchscreen Job page, SD/USB job loading, emergency stop | ✅ working |
| Slicer (KiCad -> job), Windows app, dry-run G-code | ✅ working |

## 🔍 Troubleshooting

See [Troubleshooting](../Documentation/docs/help/troubleshooting.md). The ones that come up most:

* **"Unknown command PNP_..."**: the `.cfg` files on the Pi are copies; after `git pull`, copy the
  changed ones into `~/printer_data/config/` and `FIRMWARE_RESTART` ([Klipper/README.md](Klipper/README.md)).
* **TMC registers read zero**: the board has no 24 V (USB power alone isn't enough).
* **Pi freezes during installs**: 1 GB of RAM. Use SSH + `tmux`, stop KlipperScreen, install with
  `pip install --only-binary=:all:`.
* **Camera "NO SIGNAL"**: `~/printer_data/logs/crowsnest.log`; "ustreamer not found" -> reinstall
  crowsnest (`cd ~/crowsnest && sudo make install`, in `tmux`).
