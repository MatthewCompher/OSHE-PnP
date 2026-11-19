# Acceptance Tests

## Conditions (all tests)

| | |
|---|---|
| Machine | V3 prototype, calibration of 2026-11-17, settings as committed on 2026-11-18 (`config.toml`, `printer.cfg`) |
| Board | Test PCB (`Software/Slicer/tests/fixtures/Test PCB/`), top side, held in the PCB mounts |
| Job | `jobs/Test PCB-top-0603.job.json`: 23 x 0603 resistors |
| Parts | 0603 resistors on 8 mm paper tape in feeder F1 |
| Tip | N08 (board touch Z 39.5, inspect Z 34.6) |
| Air | compressor ~60 psi |
| Room | indoor lab, normal ceiling light; machine lights as configured (frame strip 15 %) |
| Operator steps allowed | load the board, load tape, Vision home, Start; answer dialogs |

## Requirements and tests

| # | Requirement | Test | Pass criterion |
|---|---|---|---|
| 1 | Operate without a laptop or network: start, stop, jog, home, choose a program on an HMI | load a job from an SD card / USB stick and run it using only the touchscreen | job loaded, started, watched, stopped from the screen |
| 2 | Vision identifies passes and fails correctly | every up-camera decision (PASS / REJECT / EMPTY) and every board-check decision (PLACED / MISSING) over the runs, judged by a person from the saved photo (`human_agrees` column) | ≥ 95 % correct out of ≥ 100 |
| 3 | Pick 0603/0805 parts from tape | picks that came up with a good part / all picks, from the event log (`report`) | ≥ 95 % |
| 4 | Feeder runs without failures | consecutive 23-part runs from F1 | runs complete; each miss logged and retried |
| 5 | 500 components per hour | seconds per part over a full job, timed by `run-job` (alignment excluded) | ≥ 500 CPH (≤ 7.2 s/part) |
| 6 | Placement accuracy (characterised) | `check-board` after each run: offset of each part from its pads | reported (mean, worst) |
| 7 | Continuous operation | four 23-part runs back to back without repair, re-calibration or reboot | all complete |

## Procedure

1. [Daily startup](../operate/startup.md). Load tape in F1. Empty the reject bin.
2. Put a bare Test PCB on the plate.
3. Touchscreen -> Job -> **Test PCB-top-0603**, Align first on -> **Start**.
4. When done, run `python -m pnpvision check-board "jobs/Test PCB-top-0603.job.json"`.
5. Replace the board, repeat for the next run.
6. After the last run: `python -m pnpvision report --out report_latest`.
7. Fill in `human_agrees` in `vision_review.csv` and `placement_review.csv` by looking at each
   photo; count the agreements.
8. Back up `pnp_events.sqlite`, `report_latest/` and `results/`.

Results: [Results](results.md).
