# Moonraker and Cameras

**Moonraker** is the web API between Klipper and everything else: Mainsail, KlipperScreen and
pnpvision all talk to Klipper through it.

| From | To | How |
|---|---|---|
| Mainsail (browser) | Moonraker | HTTP / WebSocket, port 7125 |
| KlipperScreen | Moonraker | same API, on the Pi |
| pnpvision | Moonraker | `http://localhost:7125`: sends G-code (`/printer/gcode/script`), reads state (`/printer/objects/query`) |
| pnpvision | cameras | snapshots from crowsnest, so the Mainsail views keep working |
| Klipper macros | pnpvision | `gcode_shell_command` starts pnpvision in the background |

!!! note "Why pnpvision starts in the background"
    pnpvision sends its moves back through Klipper. If a macro waited for it, Klipper would wait for
    pnpvision while pnpvision waits for Klipper. So the scripts in `Software/pnpvision/scripts/`
    start it with `setsid nohup ... &` and return at once. Output goes to the console and to
    `results/*_macro.log`.

## Network and security

- Moonraker trusts the local network ranges (10.x, 172.16-31.x, 192.168.x): anyone on the same
  network can control the machine without a login. Connect it only to a network you trust, or to a
  laptop directly (our setup: Pi at `192.168.137.50`).
- No internet service is needed to run a job. Obico (remote monitoring) is optional; it sends
  camera images to its server when enabled.
- Jobs can be loaded with no network at all ([SD / USB](../operate/load-jobs.md)).

## Cameras (crowsnest)

| | `[cam 1]` down | `[cam 2]` up |
|---|---|---|
| Device | Arducam 12MP USB | InnoMaker U20CAM 720P |
| Resolution | 1920 x 1080 | 1280 x 720 |
| Port / URL | 8080, `/webcam/` | 8081, `/webcam2/` |
| Snapshot (pnpvision) | `http://localhost/webcam/?action=snapshot` | `http://localhost/webcam2/?action=snapshot` |
| Exposure | automatic | fixed (`exposure_time_absolute=80`) |

Devices are set **by ID** (`/dev/v4l/by-id/...`), so a camera keeps its role on any USB port or hub.

| Problem | Fix |
|---|---|
| "NO SIGNAL" / crowsnest won't start | `~/printer_data/logs/crowsnest.log`; "ustreamer not found" -> `cd ~/crowsnest && sudo make install` (in tmux) |
| Moonraker warns about crowsnest `install_script` | set `install_script: tools/install.sh` under `[update_manager crowsnest]` |
| pnpvision can't reach the machine | Moonraker running? `config.toml [moonraker] url` = `http://localhost:7125` |
