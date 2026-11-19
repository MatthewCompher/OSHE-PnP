# Troubleshooting

## Motion and homing

| Problem | What to check |
|---|---|
| TMC driver registers all read zero | the board needs 24 V, not just USB; then SPI pins, CS pins, MISO |
| Motor doesn't move, or buzzes | driver slot vs config; the 6-pin/4-pin cable order ([Electronics](../build/electronics.md#wiring-rules-we-learned)) |
| X and Y moves are swapped or diagonal | the two CoreXY motor cables are swapped (A/B); swap them back |
| Homing stops early in mid-air | stall detection too sensitive: homing 40 mm/s at 1.0 A (20 mm/s or 0.8 A false-triggers) |
| Homing crashes into the frame | motor direction wrong or stall detection not sensitive enough; test slowly |
| Z skips (clicks, nozzle at wrong height) | Z speed above 50 mm/s or current too low; Z runs 0.5 A, homes at 0.8 A |
| Jerky motion, skipped steps | lower speed/acceleration; belt tension; something binding |
| "Motors off after 10 min idle" | normal: Vision home again |

## Vision

| Problem | What to check |
|---|---|
| Vision home fails to find the dot | down light on; datum clean; nothing covering dot 0 |
| Up-camera images washed out or odd colours | frame lights too bright (keep 15 %); an LED effect running on `up_light`; exposure is fixed in crowsnest |
| Calibration check says REDO for the nozzle | see [Recovery Check](../calibration/recovery.md); don't use `--apply` if the up camera moved |
| All placements off by the same amount | re-align the board first; then dry run; then the camera offset |
| Parts rejected as "wrong size" | part on its side or two parts picked; tip clogged; wrong package taught on the feeder |
| Good parts rejected as upside down | dirty up-camera window or very dark parts: `config.toml [run] flip_check` |

## Picking and placing

| Problem | What to check |
|---|---|
| Empty picks | tape not advanced (feeder); pick spot drifted (re-teach); air pressure; tip clogged |
| Part drops before placing | `vac_ms` too short; leak at the rotary fitting or tubing |
| Part sticks to the nozzle after placing | `release_ms` too short; touch height too high for the board |
| Part placed at the wrong height | wrong tip recorded (`tip`), or the board isn't seated flat |

## Touchscreen and jobs

| Problem | What to check |
|---|---|
| "Unknown command PNP_..." | `pnp_hmi.cfg` on the Pi is older than the repository: copy it and `FIRMWARE_RESTART` ([Updating](../software/updating.md)) |
| Job page says "pnp_hmi.cfg is not loaded" | `[include pnp_hmi.cfg]` missing in `printer.cfg` |
| A button says "a job is running" | finish or stop the job first |
| Job questions don't appear | use `PNP_CONTINUE` / `PNP_STOP` in the console; check `PNP_SCREEN_TEST` |
| SD/USB: "no card found" | reader plugged into the hub, card inserted; FAT32 or exFAT |
| Logs | `Software/pnpvision/results/run_job_macro.log`, `pnp_cmd_macro.log`, `vision_home_macro.log` |

## Pi and software

| Problem | What to check |
|---|---|
| Pi freezes during installs | out of memory: SSH + tmux, stop KlipperScreen, `--only-binary=:all:` |
| Camera "NO SIGNAL" | crowsnest log; reinstall crowsnest ([Moonraker and Cameras](../guides/moonraker.md)) |
| MCU "unable to connect" | USB cable; `ls /dev/serial/by-id/`; serial path in `printer.cfg`; Uno must never be on the hub |
| Nothing powers on | supply switch; fuse; crimps |
