# 💻 Software & Firmware Configuration

## Overview
The OSHE Pick-and-Place runs a 3D-printer software stack adapted for SMT assembly: **Klipper** for motion control, **Moonraker** as its API, **Mainsail** as the web dashboard, and **crowsnest** for the two cameras. A Python vision package, **pnpvision**, drives the machine through Moonraker.

> [!NOTE]
> **Work in progress (Fall 2026, V3.0).** Motion, homing, lighting and the cameras work. The vacuum/valve, feeder and pick-and-place macros are **unfinished**, and the vision pipeline is partway through calibration. See [Status](#-status).

---

## 🧱 The Stack
| Layer | What it is | Where |
|---|---|---|
| **Klipper** | Firmware: motion, steppers, pins, macros. Runs on the Pi (host) and the controller board (MCU). | [`Klipper/printer.cfg`](Klipper/printer.cfg) |
| **Moonraker** | API between Klipper and everything else (web UI, vision code). Also keeps the webcam list and runs the update manager. | `moonraker.conf` on the Pi |
| **Mainsail** | Web dashboard, opened in a browser at the Pi's address | MainsailOS |
| **crowsnest** | Streams both USB cameras (`/webcam/` and `/webcam2/`) | `crowsnest.conf` on the Pi |
| **KlipperScreen** | Touchscreen interface on the Pi's display | MainsailOS |
| **pnpvision** | Vision: camera-to-machine calibration, datum, part inspection | [`pnpvision/`](pnpvision) |

**Hardware:** BTT Octopus Pro (STM32H723) with TMC5160 drivers, Raspberry Pi 4 (1 GB) running MainsailOS.

---

## ⚙️ Machine Configuration (`Klipper/printer.cfg`)
This file is a copy of the live config on the Pi. On the Pi it lives at `~/printer_data/config/printer.cfg` and is edited in Mainsail (**Machine** tab → `printer.cfg` → **Save & Restart**). After changing it on the Pi, copy it back into the repo (run on the PC, not over SSH):
```bash
scp pnp@PnP.local:~/printer_data/config/printer.cfg "C:\Users\<you>\Documents\GitHub\OSHE-PnP\Software\Klipper\printer.cfg"
```

| Item | Value |
|---|---|
| Kinematics | CoreXY |
| Travel | X 0–235, Y 0–343, Z 0–60 mm (sensorless homing on X/Y/Z) |
| **Z direction** | **0 = homed at the top, larger Z = nozzle lower.** The nozzle touches the staging plate at about Z 50 and the PCB top at about Z 38. |
| Nozzle rotation | `[manual_stepper stepper_r]`, 1 unit = 1° (LumenPnP NEMA 11). No endstop: `G28` / `G28 R` sets the current angle as 0. |
| Homing | `[homing_override]`: Z first, then Y, then X, then zeroes R |
| Lights | 3-LED neopixel chain: LED 1 = status, LEDs 2–3 = down-camera light |

`printer.cfg` includes `mainsail.cfg` (supplied by MainsailOS) and `moonraker_obico_macros.cfg` (from the Obico plugin). On a machine without Obico, remove that `[include]` line.

### Macros
| Macro | Purpose | Status |
|---|---|---|
| `VISION_LIGHT_ON` / `_OFF` / `_TOGGLE` | Down-camera light (LEDs 2–3). It turns on at boot. | ✅ Working |
| `LEDS_IDLE` / `LEDS_BUSY` / `LEDS_ERROR` / `LEDS_RAINBOW` / `LEDS_OFF` | Status LED (LED 1) effects | ✅ Working |
| `TEST_BED_MOVEMENT [LOOPS=n]` | Corner, diagonal and Z exercise | ✅ Working |
| `PNP_DEMO [LOOPS=n]` | Simulated pick/place motion only (no vacuum) | ✅ Working |
| `VALVE_ON` / `VALVE_OFF` / `TOGGLE_VALVE` | Solenoid valve (FAN1 header, `PD12`) | 🚧 Pin control works; pneumatics not finished |
| `FEEDER_TOGGLE SLOT=n [COUNT=k]` / `FEEDER_SET SLOT=n ANGLE=` (`OFF=1`) | Tape feeder servos on the Uno (`Klipper/pnp_feeders.cfg`): slot 1 D5, 2 D6, 3 D3 | 🚧 Slot 1 works; slot 2 servo to replace; slot 3 untested |
| `PICK SPOOL=n` | Move to a spool, lower, open the valve, lift | ⚠️ **Unfinished, don't run.** `z_safe = 80` is outside Z 0–60, and the safe heights assume the old Z direction. |
| `PLACE X= Y=` | Move, lower, release, lift | ⚠️ **Unfinished, don't run.** It references an undefined `default_z_place`. |

**Clearance:** the tallest fixtures on the staging plate are the reject bin (15 mm), the datum (11 mm) and the PCB clamps (8–10 mm). When jogging X/Y by hand, keep the nozzle at **Z 30 or higher (smaller number)**.

---

## 📷 Cameras & Vision
| Camera | Hardware | crowsnest | Calibration |
|---|---|---|---|
| Down (on the toolhead gantry) | Arducam 12MP USB, M12 lens | `[cam 1]`, 1920x1080, `/webcam/` | `calibration_cam_down.npz` |
| Up (staging plate) | InnoMaker 720P, 120° | `[cam 2]`, 1280x720, `/webcam2/` | `calibration_cam_up.npz` |

* **Lens calibration** and the **undistorted Mainsail views** (`undistort-down` / `undistort-up` services on ports 8090 / 8091) are documented in [`Archive/USB Camera Calibration Vibecode Project`](../Archive/USB%20Camera%20Calibration%20Vibecode%20Project).
* **pnpvision** ([README](pnpvision/README.md)) reads both cameras from crowsnest's snapshot URLs, so the dashboard views keep working while it runs. It moves the machine through Moonraker and always lifts the nozzle to a safe travel height (Z 30) before any X/Y move.

---

## 📋 Status
| Subsystem | State |
|---|---|
| Motion, homing, nozzle rotation stepper | ✅ Working |
| Status and down-camera lighting | ✅ Working |
| Cameras: streaming, lens calibration, undistorted views | ✅ Done |
| Vision: camera ↔ machine calibration, nozzle offset, datum | 🚧 In progress (pnpvision steps 1–4) |
| Board alignment from pads (no fiducials) | 📅 Planned |
| Bottom vision (part offset/rotation on the nozzle) | 📅 Planned (code exists; needs a part on the nozzle) |
| Vacuum / valve pneumatics | 🚧 Unfinished |
| Feeders | 🚧 Unfinished (one servo, uncalibrated) |
| Pick / place macros and job runner (reject bin, missed-pick retry) | 📅 Planned |
| Up-camera light | 📅 Not wired yet |

---

## ⚠️ Legacy: Marlin Firmware (Deprecated)
*Version 1.0 (Fall 2025) used Marlin; the source is in [`Legacy-Marlin`](Legacy-Marlin). It isn't used on the current machine.*

## 🔍 Troubleshooting
* **TMC driver communication:** if all registers read zero, check the 24 V supply to the board. Klipper reports a communication failure when the drivers are unpowered.
* **Moonraker warning about crowsnest `install_script`:** in `moonraker.conf`, set `install_script: tools/install.sh`.
* **Camera shows "NO SIGNAL" or crowsnest won't start:** check `~/printer_data/logs/crowsnest.log`. "`ustreamer` not found" means crowsnest must be reinstalled (`cd ~/crowsnest && sudo make install`, inside `tmux`).
* **Pi freezes during installs:** a 1 GB Pi runs out of memory. Use plain SSH plus `tmux`, stop KlipperScreen temporarily, and always install OpenCV with `pip install --only-binary=:all:`.

---
*See the [Master Documentation](https://docs.google.com/document/d/1zdPMhOE8R7Szz68Ky9EoDyxVyp7iftD7q8Uco1WKPY8/edit?usp=sharing) for assembly and electrical details.*
