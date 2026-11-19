# Software Setup

The machine runs a 3D-printer software stack (Klipper, Moonraker, Mainsail, KlipperScreen,
crowsnest) plus two programs written for this project: **pnpslice** (on your computer) and
**pnpvision** (on the Pi).

```
Your computer                        Raspberry Pi 4                         Controllers
-------------                        --------------                         -----------
KiCad -> pnpslice.exe -> job file -> pnpvision (calibration, jobs)
                         (SD/USB      |  Moonraker API (port 7125)
                          or network) |    -> Klipper host -------------->  Octopus Pro (motion, valve)
                                      |  KlipperScreen (touchscreen)  \-->  Arduino Uno (servos, lights)
                                      |  Mainsail (browser)
                                      \- crowsnest (both cameras)
```

## Pages
1. [Install from scratch](install.md): a blank SD card to a working machine, every package and file.
2. [Configuration files](config-files.md): which files are live and where they go.
3. [Touchscreen](touchscreen.md): the Pick & Place menu and the Job page.
4. [Updating](updating.md): getting new versions from the repository.

## Platform requirements

| Component | Version used (Nov 2026) |
|---|---|
| Raspberry Pi | Pi 4 Model B, 1 GB RAM, 32 GB microSD |
| OS | MainsailOS (Raspberry Pi OS Bookworm based, 64-bit, kernel 6.12) |
| Klipper, Moonraker, Mainsail, KlipperScreen, crowsnest | as installed by MainsailOS, updated through Mainsail's Update Manager |
| Klipper extensions | `gcode_shell_command` (KIAUH), `klipper-led_effect` |
| Python on the Pi | 3.11 (system) in a venv `~/venv-pnp`; packages pinned in `Software/pnpvision/requirements-lock.txt` |
| Your computer | Windows 10/11 for `pnpslice.exe`; or any OS with Python 3.10 - 3.13 to run pnpslice from source |
| KiCad | 6 or newer |

!!! tip "Record your versions"
    Mainsail -> Machine -> Update Manager lists the exact Klipper, Moonraker and extension
    versions. Note them when you set up a new machine.
