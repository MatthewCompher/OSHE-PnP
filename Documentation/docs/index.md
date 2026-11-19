---
hide:
  - navigation
---

<div class="oshe-hero" markdown>

![OSHE logo](assets/oshe-logo.png){ .oshe-hero-logo }

# OSHE Pick and Place

An open-source pick-and-place machine for surface-mount parts, built from a Creality Ender 3,
a 3D-printed CoreXY frame, a vacuum toolhead, two cameras and its own software.

Made by students of the **Open Source Hardware Enterprise** at Michigan Technological University:
[oshe.io](https://oshe.io) · every file is on
[GitHub](https://github.com/OSHE-Github/OSHE-PnP).

[Begin here](overview/index.md){ .md-button .md-button--primary }
[Run a job](operate/index.md){ .md-button }
[See the results](testing/results.md){ .md-button }

</div>

<div class="oshe-stats" markdown>
<div><strong>~511</strong><span>parts per hour (best 527)</span></div>
<div><strong>97.9 %</strong><span>picks from tape (92 / 94)</span></div>
<div><strong>0.08 mm</strong><span>mean placement error</span></div>
<div><strong>331 / 331</strong><span>vision decisions correct</span></div>
</div>

<figure class="oshe-video" markdown>
<video src="assets/media/job-realtime.mp4" autoplay loop muted playsinline></video>
<figcaption>Three 0603 resistors placed at real speed (about 7 s each), then the finished board.</figcaption>
</figure>

!!! info "Project state: functional prototype (V3, Fall 2026)"
    The machine runs complete jobs from the touchscreen: feeder, pick, camera check, place.
    The build guide, bill of materials and wiring diagram for V3 are still being written
    (marked **Ongoing** on those pages).

## How a board gets made

<div class="grid cards" markdown>

-   :material-pencil-ruler: **1. Design**

    ---
    Lay out the board in KiCad as usual.

-   :material-layers-triple: **2. Slice**

    ---
    [pnpslice](operate/make-a-job.md) checks the board, orders the parts and writes a job file.

-   :material-sd: **3. Load**

    ---
    Carry the job on an [SD card or USB stick](operate/load-jobs.md) - no network needed.

-   :material-robot-industrial: **4. Run**

    ---
    [Start it on the touchscreen](operate/run-a-job.md): the cameras find the board, check every
    part and correct it before placing.

</div>

## Where do you want to go?

<div class="grid cards" markdown>

-   :material-book-open-variant: **New to the machine**

    ---
    [How It Works](overview/index.md) · [Specifications](overview/specs.md) ·
    [Safety](overview/safety.md)

-   :material-hammer-wrench: **Building one**

    ---
    [Build](build/index.md) -> [Software Setup](software/index.md) ->
    [Calibration](calibration/index.md)

-   :material-play-circle: **Running boards**

    ---
    [Daily startup](operate/startup.md) · [Run a job](operate/run-a-job.md) ·
    [Troubleshooting](help/troubleshooting.md)

</div>

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
