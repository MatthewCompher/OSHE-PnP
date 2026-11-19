# 5. After the Job

## Check the board

The down camera can check every footprint: is a part there, and how far off is it?

```bash
python -m pnpvision check-board "jobs/Test PCB-top-0603.job.json"
```

For each footprint it prints **PLACED** or **MISSING** with the offset in mm and degrees, and saves
a photo in `board_check_<time>/`. `--only R1 R5` checks a few parts.

## The report

```bash
python -m pnpvision report --out report_latest
```

writes, from the event log (`pnp_events.sqlite`):

| File | Contents |
|---|---|
| `summary.txt` | per run: picks good/tried, placed, parts per hour, rejects, vision verdicts |
| `cycles.csv` | per part: cycle time and its phases (pick, inspect, turn, place, feeder wait) |
| `vision_review.csv` | every up-camera decision (PASS / REJECT / EMPTY) with photo, size, angle and a `human_agrees` column to fill in |
| `placement_review.csv` | every board-check decision with green share, dx/dy/error and angle |
| `sheet_*.jpg` | contact sheets of the photos, one per run |

Examples: [Sample Images and Data](../testing/samples.md).

## Keep the evidence

Photo folders grow by about 1 GB per day of runs. Back up `pnp_events.sqlite`, `report_latest/`
and `results/`; delete old `job_*/` photo folders when you no longer need them.

## Remove the board

Loosen the adjustable mount and lift the board straight up. Empty the reject bin.

Next: [Shutdown](shutdown.md).
