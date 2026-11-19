# Job File Format

Job files follow **`oshe-pnp-job/1`**, defined in `Software/pnpvision/JOB_FORMAT.md`. It is the
contract between the slicer and the machine: any program that writes this format can feed the
machine.

## The board frame
- Seen from above the side being placed.
- Origin at the lower-left corner of the outline's bounding box; +X right, +Y up; millimetres.
- Bottom-side jobs are mirrored so they read as if the bottom were the top.
- Angles in degrees, counter-clockwise positive, from the footprint's library orientation.

## Fields

| Field | Contents |
|---|---|
| `format` | always `"oshe-pnp-job/1"` |
| `source` | optional: generator, input files, date |
| `board` | `name`, `side`, `outline_mm`, `thickness_mm` |
| `alignment` | 2 - 4 pads: `name`, `x`, `y`, `shape`, size, optional `ref` / `pad` |
| `placements` | in order: `ref`, `value`, `package`, `x`, `y`, `rot`, `height_mm`, optional `skip`, `feeder`, `nozzle` |

No machine coordinates, Z heights, feeder positions or G-code: those depend on where the board
lands and on the machine's calibration.

## Example

```json
{
  "format": "oshe-pnp-job/1",
  "source": {"generator": "pnpslice 0.1.0", "inputs": ["Test PCB.kicad_pcb"], "date": "2026-11-11T23:14:46+00:00"},
  "board": {"name": "Test PCB", "side": "top",
            "outline_mm": [[0.0, 0.0], [0.0, 54.0], [46.51, 54.0], [46.51, 0.0]], "thickness_mm": 1.6},
  "alignment": [
    {"name": "A", "x": 25.9662, "y": 24.7098, "shape": "roundrect", "w": 1.025, "h": 1.4, "rot": 120.0, "ref": "R0805_21", "pad": "1"}
  ],
  "placements": [
    {"ref": "R0603_1", "value": "R_0603_1608Metric", "package": "R_0603_1608Metric", "x": 2.01, "y": 15.0, "rot": 0.0, "height_mm": 0.45}
  ]
}
```

## Results files

Each run writes `results/job_<time>.json`: the job path, the board pose used, timing (placed,
attempted, seconds per part, parts per hour) and one result per placement. All events also go into
the SQLite log `pnp_events.sqlite`, which `report` exports as CSV.
