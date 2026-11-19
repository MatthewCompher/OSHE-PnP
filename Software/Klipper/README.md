# Klipper configuration and touchscreen

The master copies of everything Klipper and KlipperScreen read. Full explanation:
[Configuration Files](../../Documentation/docs/software/config-files.md) and
[Macro Reference](../../Documentation/docs/guides/macros.md).

| File | Goes to (on the Pi) | What it holds |
|---|---|---|
| `printer.cfg` | `~/printer_data/config/` | MCUs (Octopus Pro + Uno), CoreXY, steppers, homing override, limits, valve, `VISION_HOME`; includes the files below |
| `pnp_hmi.cfg` | `~/printer_data/config/` | touchscreen / Mainsail macros: `RUN_JOB`, `PNP_*` buttons, job state (`_PNP_STATE`), `PNP_IMPORT_JOBS`, safe PAUSE/RESUME/CANCEL, idle timeout |
| `pnp_feeders.cfg` | `~/printer_data/config/` | feeder servos on the Uno (slot 1 D5, 2 D6, 3 D3), `FEEDER_TOGGLE`, `FEEDER_SET` |
| `LEDS.cfg` | `~/printer_data/config/` | toolhead LEDs, up-camera ring, frame strip and their effects (needs `klipper-led_effect`) |
| `KlipperScreen_pnp.conf` | paste into `~/printer_data/config/KlipperScreen.conf`, **above** `#~# --- Do not edit below this line` | the **Pick & Place** touchscreen menu (Job, EMERGENCY STOP, Vision home, ...) |
| `klipperscreen/pnp_job.py` | **link** into `~/KlipperScreen/panels/` | the touchscreen **Job page** |
| `sudoers-pnp-usb-import` | install to `/etc/sudoers.d/pnp-usb-import` | lets the SD/USB button mount a stick read-only (and nothing else) |
| `from-pi/` | - | an **old snapshot** of the Pi's files (2026-11-08); not live, see its README |

## After `git pull`: copy the changed `.cfg` files

The `.cfg` files on the Pi are **copies**, so a pull doesn't change them. (The Job page is a link,
so it updates by itself; restart KlipperScreen to load it.) For each `.cfg` that changed, check
for local edits, copy it, then restart Klipper. Pi SSH:

```bash
diff ~/printer_data/config/pnp_hmi.cfg ~/OSHE-PnP/Software/Klipper/pnp_hmi.cfg
cp ~/OSHE-PnP/Software/Klipper/pnp_hmi.cfg ~/printer_data/config/pnp_hmi.cfg
```

then `FIRMWARE_RESTART` in the Mainsail console. "Unknown command PNP_..." on the touchscreen
almost always means this step was missed.

## First-time setup (new Pi)

```bash
cd ~/OSHE-PnP/Software/Klipper
cp printer.cfg pnp_hmi.cfg pnp_feeders.cfg LEDS.cfg ~/printer_data/config/
ln -sf ~/OSHE-PnP/Software/Klipper/klipperscreen/pnp_job.py ~/KlipperScreen/panels/pnp_job.py
cp sudoers-pnp-usb-import /tmp/pnp-usb-import
sudo visudo -cf /tmp/pnp-usb-import && sudo install -m 440 -o root -g root /tmp/pnp-usb-import /etc/sudoers.d/pnp-usb-import
```

Then set the two `serial:` lines in `printer.cfg` to your boards (`ls /dev/serial/by-id/`), paste the
menu into `KlipperScreen.conf`, `FIRMWARE_RESTART` and `sudo systemctl restart KlipperScreen`.
Needs the **G-Code Shell Command** (KIAUH) and **klipper-led_effect** extensions. Full steps:
[Install from Scratch](../../Documentation/docs/software/install.md).

## Saving a change made on the Pi back to the repository

From your computer: `scp pnp@PnP.local:~/printer_data/config/printer.cfg Software/Klipper/printer.cfg`
(adjust the address; ours is `192.168.137.50`), then commit.
