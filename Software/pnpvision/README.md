# pnpvision

The machine software of the OSHE Pick and Place. It runs on the Raspberry Pi next to Klipper,
moves the machine through Moonraker, reads both cameras from crowsnest, and does everything that
needs vision: visual homing, camera calibration, finding the board, checking every part on the
nozzle, running jobs, checking finished boards and writing reports.

Full documentation: [Calibration](../../Documentation/docs/calibration/index.md),
[Running Jobs](../../Documentation/docs/operate/index.md),
[pnpvision Commands](../../Documentation/docs/guides/commands.md).

## Install (on the Pi, Python 3.11+)

```bash
python3 -m venv ~/venv-pnp
cd ~/OSHE-PnP/Software/pnpvision
~/venv-pnp/bin/pip install --only-binary=:all: -r requirements.txt
```

Always use `--only-binary=:all:`: building OpenCV from source runs a 1 GB Pi out of memory. Do
long installs in `tmux`. Commands then run from this folder as
`~/venv-pnp/bin/python -m pnpvision <command>`.

## Everyday commands

| Command | What it does |
|---|---|
| `home` | visual homing (`VISION_HOME` runs this) |
| `run-job JOB [--dry-run] [--only R1 R2] [--no-feeders]` | place a job (aligns the board first: `[run] align_each_job`) |
| `align-board JOB --rot 90` | find the board from its alignment pads (camera roughly on pad A) |
| `check-board JOB [--only ...]` | down camera over each footprint: PLACED / MISSING + mm error |
| `report --out report_latest` | export the event log: `summary.txt`, `cycles.csv`, `vision_review.csv`, `placement_review.csv`, contact sheets |
| `import-jobs` | load `*.job.json` from an SD card / USB stick (the touchscreen button runs this) |
| `feeder-cycle F1 --n 20` | pick and drop in the reject bin N times (feeder test) |
| `check-machine` | recovery check after the head or gantry was disturbed |

Calibration commands (`calibrate-motion`, `calibrate-offset`, `datum`, `tip`, `teach-feeder`,
`teach-bin`, `focus-sweep`, ...) and the order to run them in: [SETUP_CHECKLIST.md](SETUP_CHECKLIST.md)
and the [Calibration docs](../../Documentation/docs/calibration/index.md). `--help` after any
command lists its options.

## Files

| Path | What |
|---|---|
| `config.toml` | machine settings, commented line by line: limits, safe heights, cameras, lights, speeds, feeders, plate layout |
| `calibration/` | measured values (`machine.json`, motion maps, lens `.npz`); written by the calibration commands, saved atomically |
| `jobs/` | job files (`*.job.json`), shown on the touchscreen Job page |
| `JOB_FORMAT.md` | the `oshe-pnp-job/1` format (the contract with the slicer) |
| `SETUP_CHECKLIST.md` | every per-machine setup step, with its command and when to redo it |
| `scripts/` | small shell scripts the Klipper macros start in the background |
| `pnpvision/` | the code: `runner.py` jobs, `upcam.py` / `detect.py` part detection, `board.py` alignment, `boardcheck.py`, `hmi.py` touchscreen, `feeders.py`, `usbjobs.py` SD/USB, `report.py`, `cli.py` commands |
| `tests/` | `pytest`, no hardware needed (92 tests, many on saved real photos) |
| `results/`, `job_*/`, `board_check_*/`, `pnp_events.sqlite` | outputs on the Pi, **not in git** (photos grow ~1 GB/day of runs) |

Z on this machine: **0 = top, larger Z = nozzle lower** (plate at about Z 50, PCB top Z 39.5 with
the N08 tip). Every command lifts to a safe height before any X/Y move and refuses moves outside
the limits in `config.toml`.

## Tests

```bash
cd Software/pnpvision
pytest
```
