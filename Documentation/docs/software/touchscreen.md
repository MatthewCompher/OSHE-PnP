# 3. Touchscreen

The 7" touchscreen runs **KlipperScreen**. Everything needed to run the machine is under the
**Pick & Place** menu - no laptop needed.

## Pick & Place menu

| Button | What it does |
|---|---|
| **Job** | the PnP Job page (below) |
| **EMERGENCY STOP** | stops everything at once (see [Safety](../overview/safety.md)) |
| **Vision home** | homes X/Y, then re-zeros on datum dot 0 with the down camera |
| **Calibration check** | `check-machine` (nozzle empty) |
| **Lights >** | up light, down light on/off |
| **Reject bin >** | go to the bin, teach it, back to default |

## The Job page

**Job list.** One row per job file. At the top: a one-line machine status (homed? last result?)
and **Load jobs from SD card / USB stick** ([how](../operate/load-jobs.md)). While a job runs, a
**Running: ...** button takes you back to its status.

**Job details.** Tap a job: board and side, parts to place, packages, which feeder holds each
package, the last run's result and parts per hour, and an estimate. Three options:

| Option | Default | Meaning |
|---|---|---|
| No feeders | off | you put each part in the pocket by hand when asked |
| Align first | on | the camera finds the board again before placing |
| Dry run | off | no parts: the down camera visits every placement and saves a photo |

**Start** asks for confirmation, then switches to the status view.

**Status (while a job runs).** A red **JOB RUNNING: the machine moves on its own. Hands clear.**
line, then: homing state, job, part n / total and reference, placed / failed, elapsed time, the
latest status line. Buttons:

- **Continue**: answers the open question (same as the dialog's button).
- **Stop job**: tap twice; the job ends after the current part.
- **EMERGENCY STOP**: one tap, stops everything now.

Questions from the job (for example "load a part in the pocket") open as dialogs over any page.
