# 6. Shutdown

1. Wait for the job to finish (or **Stop job** and wait for "stopped").
2. Remove the board and empty the reject bin.
3. Raise the nozzle (Z 20) and park the head over an empty spot, so nothing sits on the nozzle.
4. **Shut down the Pi**: touchscreen -> the power icon -> **Shutdown**, or Mainsail -> power menu
   -> **Shutdown**. Wait until the screen goes dark and the Pi's green LED stops blinking.
5. Switch off the **24 V supply** and the **servo 5 V supply**.
6. Switch off the **compressor** and bleed the line (open the valve before power-off, or the
   compressor's own release).

!!! warning "Don't just pull the plug on the Pi"
    Cutting power while the Pi writes can corrupt its SD card. Calibration files are written safely,
    but the operating system is not.

## Maintenance schedule

| Every | Check |
|---|---|
| Each session | reject bin empty; tape loaded; nozzle tip clean and straight |
| Weekly / 20 jobs | belt tension (both equal), loose screws on toolhead and corners, tubing for kinks |
| Monthly | wipe the up-camera window and the datum; run the [Recovery Check](../calibration/recovery.md) |
| When placements drift | re-align the board, dry run, then the Recovery Check |
| Nozzle tip worn or bent | replace the CP40 tip, record its heights ([Nozzle Tips](../guides/nozzle-tips.md)) |
| Feeder skips or double-feeds | check the servo horn screw and the lever ([Feeders](../feeders/troubleshooting.md)) |

## Consumables

| Item | Notes |
|---|---|
| Samsung CP40 nozzle tips (N08 for 0603/0805) | replace when bent or clogged |
| Component tape (8 mm paper) | see [Loading Tape](../feeders/loading-tape.md) |
| Hobby servos | the weak point of the feeders: keep a spare |
| Compressor | drain any water trap as its manual says |
| Venturi silencer | replace if clogged (vacuum gets weaker) or missing (noise) |
| Hearing protection | ear plugs or muffs for operators of long runs |
