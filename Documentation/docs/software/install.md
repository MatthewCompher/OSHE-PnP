# 1. Install from Scratch

From a blank microSD card to a machine ready for [Calibration](../calibration/index.md). Every
command is run on the Pi over SSH unless it says otherwise.

!!! tip "The Pi has only 1 GB of memory"
    Do long installs over plain SSH inside `tmux` (so a dropped connection doesn't kill them), stop
    KlipperScreen while installing (`sudo systemctl stop KlipperScreen`), and always install Python
    packages with `--only-binary=:all:` - building OpenCV from source runs the Pi out of memory.

## 1. Flash MainsailOS

1. On your computer, open **Raspberry Pi Imager**.
2. Device: **Raspberry Pi 4**. OS: **Other specific-purpose OS -> 3D printing -> MainsailOS**.
3. Edit settings: hostname **`PnP`**, username **`pnp`**, a password, Wi-Fi if you need it, SSH on.
4. Write the card, put it in the Pi, power on, wait two minutes.
5. Open `http://PnP.local` (or the Pi's IP) in a browser: Mainsail appears.

!!! note "Keep these names"
    Scripts and macros use `/home/pnp/OSHE-PnP`. With other names, change the paths in
    `pnp_hmi.cfg`, `printer.cfg` and `Software/pnpvision/scripts/`.

On our machine the Pi is wired straight to a laptop: static address `192.168.137.50`, laptop
Internet Connection Sharing on for updates. Connect with `ssh pnp@192.168.137.50` (or
`ssh pnp@PnP.local` on a normal network).

## 2. Get the repository

```bash
cd ~
git clone https://github.com/OSHE-Github/OSHE-PnP.git
sudo apt install -y tmux
```

## 3. Flash Klipper onto the Octopus Pro

!!! warning
    Disconnect anything on the heater outputs (HE0/HE1) before the first flash.

```bash
cd ~/klipper
make clean
make menuconfig
```

| Setting | Octopus Pro H723 (this machine) |
|---|---|
| Enable extra low-level options | yes |
| Architecture | STMicroelectronics STM32 |
| Processor | STM32H723 |
| Bootloader offset | 128KiB |
| Clock reference | 25 MHz crystal |
| Communication | USB (PA11/PA12) |

Then `make`, copy `out/klipper.bin` to a FAT32 microSD card as **`firmware.bin`**, put the card in
the Octopus and power it on. `ls /dev/serial/by-id/` should now list `usb-Klipper_stm32h723...`.

## 4. Flash Klipper onto the Arduino Uno

```bash
cd ~/klipper
make menuconfig KCONFIG_CONFIG=config.uno     # Atmega AVR, atmega328p
make KCONFIG_CONFIG=config.uno
ls /dev/serial/by-id/                         # find usb-Arduino...
make flash KCONFIG_CONFIG=config.uno FLASH_DEVICE=/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_...-if00
```

## 5. Klipper extensions

- **G-Code Shell Command** (runs pnpvision from macros): `~/kiauh/kiauh.sh` -> Extensions ->
  G-Code Shell Command. Decline the example config.
- **klipper-led_effect** (all the light effects):
  ```bash
  cd ~ && git clone https://github.com/julianschill/klipper-led_effect.git
  cd klipper-led_effect && ./install-led_effect.sh
  ```

## 6. Klipper configuration

```bash
cd ~/OSHE-PnP/Software/Klipper
cp printer.cfg pnp_hmi.cfg pnp_feeders.cfg LEDS.cfg ~/printer_data/config/
```

Then in `~/printer_data/config/printer.cfg` set the two serial lines to your boards'
`/dev/serial/by-id/...` paths (`[mcu]` = Octopus, `[mcu uno]` = Uno). If you don't use Obico, delete
`[include moonraker_obico_macros.cfg]`. Restart Klipper (`FIRMWARE_RESTART`). Details of every file:
[Configuration Files](config-files.md).

!!! danger "Before the first move"
    Check each motor sits in the slot the config expects. Jog each axis a few mm at low speed and
    check the direction. Home one axis at a time: `G28 Z`, `G28 Y`, `G28 X`.

## 7. Cameras (crowsnest)

In Mainsail -> Machine -> `crowsnest.conf`, set up two cameras **by ID** (so they keep their
roles on any USB port):

```ini
[cam 1]
mode: ustreamer
device: /dev/v4l/by-id/usb-Arducam_Technology_Co.__Ltd._Arducam_12MP_USB_Camera_...-video-index0
resolution: 1920x1080
max_fps: 15
port: 8080

[cam 2]
mode: ustreamer
device: /dev/v4l/by-id/usb-Innomaker_Innomaker-U20CAM-720P_SN0001-video-index0
resolution: 1280x720
max_fps: 15
port: 8081
v4l2ctl: auto_exposure=1,exposure_dynamic_framerate=0,white_balance_automatic=0,power_line_frequency=2,exposure_time_absolute=80
```

`ls /dev/v4l/by-id/` shows your camera names. The up camera's exposure is fixed so it doesn't
change every time the ring light switches.

## 8. pnpvision

```bash
python3 -m venv ~/venv-pnp
cd ~/OSHE-PnP/Software/pnpvision
~/venv-pnp/bin/pip install --only-binary=:all: -r requirements-lock.txt
~/venv-pnp/bin/python -m pnpvision check-lens     # no moves: checks the lens calibration files
```

(`requirements-lock.txt` has the exact versions the machine runs; `requirements.txt` lists the
packages without versions.)

### Allow SD/USB job loading

The **Load jobs from SD card / USB stick** button mounts the stick read-only, which needs root.
This rule allows exactly that mount and unmount without a password, nothing else:

```bash
cp ~/OSHE-PnP/Software/Klipper/sudoers-pnp-usb-import /tmp/pnp-usb-import
sudo visudo -cf /tmp/pnp-usb-import && sudo install -m 440 -o root -g root /tmp/pnp-usb-import /etc/sudoers.d/pnp-usb-import
```

`visudo -cf` checks the file first, so a typo can't break `sudo`.

## 9. Touchscreen

```bash
ln -sf ~/OSHE-PnP/Software/Klipper/klipperscreen/pnp_job.py ~/KlipperScreen/panels/pnp_job.py
```

Paste the contents of `Software/Klipper/KlipperScreen_pnp.conf` into
`~/printer_data/config/KlipperScreen.conf`, **above** the line
`#~# --- Do not edit below this line`, then `sudo systemctl restart KlipperScreen`. See
[Touchscreen](touchscreen.md).

## 10. Check it all works

| Check | Expected |
|---|---|
| Mainsail dashboard | Klipper ready, both MCUs connected, both camera views |
| `VISION_HOME` (console) | a result line after about 20 s, no error (after calibration) |
| Touchscreen -> Pick & Place -> Job | the job list with `Test PCB-top-0603` |
| `FEEDER_TOGGLE SLOT=1` | the feeder clicks once |
| `VALVE_ON` / `VALVE_OFF` | the valve clicks |

Next: [Calibration](../calibration/index.md).
