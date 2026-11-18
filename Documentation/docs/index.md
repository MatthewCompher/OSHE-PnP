# OSHE Pick and Place

The OSHE Pick and Place is a low-cost, open-source machine that places surface-mount parts onto
printed circuit boards. It starts from the parts of a Creality Ender 3 3D printer and adds a
3D-printed CoreXY frame, a vacuum toolhead, two cameras, tape feeders and its own software.

It is built by students in the **Open Source Hardware Enterprise** at Michigan Technological
University. Learn more about OSHE at **[oshe.io](https://oshe.io)**. Every design file, config file
and line of code is in the repository:
**[github.com/OSHE-Github/OSHE-PnP](https://github.com/OSHE-Github/OSHE-PnP)**.

!!! info "Project state: functional prototype (V3, Fall 2026)"
    The machine runs complete jobs from the touchscreen: feeder, pick, camera check, place.
    The build guide, bill of materials and wiring diagram for V3 are still being written
    (marked **Ongoing** on those pages).

## At a glance

| | V3 result (2026-11-18) |
|---|---|
| Speed | **~511 parts per hour** on average over four 23-part runs (best 527) |
| Pick success | **97.9 %** (92 of 94 picks, 0603 resistors) |
| Placement accuracy | mean error **0.075 - 0.094 mm**, worst 0.229 mm |
| Vision decisions | all 193 up-camera and 138 board-check decisions judged correct by hand |
| Operation | touchscreen only: no laptop or network needed to load and run a job |

See [Testing & Results](testing/index.md) for how these were measured.

## How a board gets made

1. **Design** the board in KiCad.
2. **Slice** it with the pnpslice app on your computer: it writes a job file per board side.
3. **Load** the job onto the machine from an SD card or USB stick (or over the network).
4. **Run** it from the touchscreen: the machine finds the board with its down camera, then for each
   part it feeds the tape, picks the part, checks it over the up camera, corrects offset and angle,
   and places it.

## Begin here

- **New to the machine?** Read [How It Works](overview/index.md) and [Safety](overview/safety.md).
- **Building one?** Start at [Build](build/index.md), then [Software Setup](software/index.md)
  and [Calibration](calibration/index.md).
- **Running a board?** Go to [Running Jobs](operate/index.md).

## Table of contents

| Section | Pages |
|---|---|
| **Get to Know It** | [How It Works](overview/index.md) · [Specifications](overview/specs.md) · [Safety](overview/safety.md) · [Known Limitations](overview/limitations.md) |
| **Build** | [Overview](build/index.md) · [1. Print the Parts](build/printing.md) · [2. Take Apart the Ender 3](build/teardown.md) · [3. Frame and Motion](build/mechanical.md) · [4. Electronics and Wiring](build/electronics.md) · [5. Pneumatics](build/pneumatics.md) · [6. Feeder Hardware](build/feeders.md) |
| **Software Setup** | [Overview](software/index.md) · [1. Install from Scratch](software/install.md) · [2. Configuration Files](software/config-files.md) · [3. Touchscreen](software/touchscreen.md) · [Updating](software/updating.md) |
| **Calibration** | [Overview and order](calibration/index.md) · [1. Cameras](calibration/cameras.md) · [2. Motion and Homing](calibration/motion-homing.md) · [3. Nozzle and Up Camera](calibration/nozzle.md) · [4. Reject Bin and Feeders](calibration/bin-feeders.md) · [Recovery Check](calibration/recovery.md) |
| **Running Jobs** | [Overview](operate/index.md) · [1. Daily Startup](operate/startup.md) · [2. Make a Job](operate/make-a-job.md) · [3. Load Jobs from SD / USB](operate/load-jobs.md) · [4. Run a Job](operate/run-a-job.md) · [5. After the Job](operate/after-the-job.md) · [6. Shutdown](operate/shutdown.md) |
| **Feeders** | [How They Work](feeders/index.md) · [Loading Tape](feeders/loading-tape.md) · [Teaching a Feeder](feeders/teaching.md) · [Testing and Troubleshooting](feeders/troubleshooting.md) |
| **Guides** | [Speed Settings](guides/speed.md) · [Nozzle Tips](guides/nozzle-tips.md) · [Lighting](guides/lighting.md) · [Macro Reference](guides/macros.md) · [pnpvision Commands](guides/commands.md) · [Moonraker and Cameras](guides/moonraker.md) · [Job File Format](guides/job-format.md) |
| **Testing & Results** | [Overview](testing/index.md) · [Acceptance Tests](testing/acceptance.md) · [Results](testing/results.md) · [Sample Images and Data](testing/samples.md) |
| **Help** | [Troubleshooting](help/troubleshooting.md) · [FAQ](help/faq.md) |
| **Project** | [Overview and Team](project/index.md) · [History (V1, V2)](project/history.md) · [Design Rationale](project/rationale.md) · [Roadmap](project/roadmap.md) · [Contributing and License](project/contributing.md) · [Revision History](project/revisions.md) |

Use the search box at the top to find anything else.
