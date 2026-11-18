# 4. Run a Job

## Put the board on the plate

1. Put the board against the fixed PCB mount, slide the adjustable mount up and tighten.
2. Put it in roughly the same place and orientation as last time: the machine looks for alignment
   pad A where it last found it and searches a few mm around.

!!! tip "Board in a new place?"
    Centre the down camera on pad A by eye (Mainsail jog, Z 30 or higher), then run
    `python -m pnpvision align-board "jobs/<job>.job.json" --rot 90` once. Every job after that
    finds the board by itself.

## Start

1. Touchscreen -> **Pick & Place -> Job**, tap the job.
2. Check the details: parts to place, which feeder holds each package (a package with **NO
   FEEDER** is skipped unless **No feeders** is on), the estimate.
3. Options: **Align first** on (recommended), **No feeders** off, **Dry run** off.
4. **Start** -> confirm. The nozzle must be empty and the up light on.

## What the machine does

1. **Vision home** if needed.
2. **Align**: the down camera visits pads A, B, C, fits the board's position and rotation, and
   reports the worst pad error. (Not counted in parts-per-hour.)
3. For each part: feed, pick, check over the up camera, turn, place.
4. Rejects (wrong size, empty nozzle, on its side, upside down) go to the reject bin, and the part
   is picked again - up to 3 tries, then the job stops and asks you.
5. At the end: placed / failed and parts per hour, on the screen and in `results/job_<time>.json`.

## During the job

- The red **JOB RUNNING** line means: hands out of the work area.
- **Questions** (load a part, swap a tip, retry?) open as dialogs: answer on the screen.
- **Stop job** (two taps): ends cleanly after the current part.
- **EMERGENCY STOP**: stops everything now ([Safety](../overview/safety.md)).
- Don't jog or run other macros: other PnP buttons refuse while a job runs.

## Dry run

With **Dry run** on, no parts are picked: the down camera visits every placement and saves a photo
with a crosshair on the target, in `job_<time>/`. Use it for a new board or after re-calibrating.

## From Mainsail or SSH

```
RUN_JOB JOB=Test_PCB-top-0603 ALIGN=1          (Mainsail console; spaces as _)
```
```bash
python -m pnpvision run-job "jobs/Test PCB-top-0603.job.json" [--dry-run] [--only R1 R2] [--no-feeders]
```

Next: [After the job](after-the-job.md).
