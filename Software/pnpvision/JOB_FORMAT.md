# OSHE-PnP job file format — `oshe-pnp-job/1`

The contract between a **job generator** (a "slicer" that reads KiCad output) and the
**pnpvision job runner** on the machine. A generator that writes files exactly as described
here will work with the runner. Status: **v1, in use** (written 2026-11-09; the pnpvision runner and the
pnpslice slicer both implement it, and ran the V3 acceptance tests on 2026-11-18). Any
incompatible change bumps the version.

## The split of responsibilities

```
KiCad (Gerbers, pos file, BOM, .kicad_pcb) ──► generator ──► job file (.json) ──► pnpvision runner ──► live G-code via Moonraker/Klipper
```

| The generator (board side) does | The runner (machine side) does |
|---|---|
| Converts KiCad coordinates to the **board frame** below | Homes with vision (`VISION_HOME`) |
| Writes **one file per board side**, already mirrored for bottom-side jobs | Finds the board on the plate by centring the camera on the alignment pads |
| Picks 2–4 **alignment pads** vision can find | Converts board coordinates to machine coordinates |
| Gives every part a unique `ref`, its centre, angle and height | Feeder positions, pick/place Z heights, nozzle offsets, tape orientation |
| Orders the placements | Checks each part on the nozzle (bottom vision), corrects offset and angle |
| | Retries missed picks, uses the reject bin, logs everything |

**The job file never contains machine coordinates, Z heights, feeder positions or G-code.**
Those depend on where the board lands on the plate, how each part sits on the nozzle, and
the machine's calibration, all of which are only known while the job runs.

## File

- UTF-8 JSON, extension `.json`. One board side per file (a double-sided board = two files).
- All lengths in **millimetres**, all angles in **degrees**, plain JSON numbers.
- Unknown extra fields are allowed and ignored by the runner (use them for notes or debugging).

### Top level

| Field | Type | Required | Meaning |
|---|---|---|---|
| `format` | string | yes | Exactly `"oshe-pnp-job/1"` |
| `board` | object | yes | See below |
| `alignment` | array | yes | 2–4 alignment pads, see below |
| `placements` | array | yes | Parts to place, in placement order |
| `source` | object | no | Free-form provenance: generator name and version, input file names, date |

### `board`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | Human-readable board name |
| `side` | `"top"` or `"bottom"` | yes | Which side this job places |
| `outline_mm` | array of `[x, y]` | yes | Board outline polygon in the board frame (at least 3 points, no repeated closing point) |
| `thickness_mm` | number | yes | PCB thickness |

### The board frame (the most important rule)

- Viewed from **above the side being placed**, as the board will lie on the machine with that side up.
- **Origin = lower-left corner of the outline's bounding box** in that view; **+X right, +Y up** (away from the viewer's bottom edge). So all coordinates are ≥ 0.
- **Bottom-side jobs:** the board is turned over left-to-right, like turning a page about its
  vertical edge. The generator must mirror X (and the angles, see below) so the file reads as
  if the bottom were the top. KiCad's own bottom-side conventions (mirrored X in the pos file
  or not, angle sign) depend on export options: verify with a test footprint.
- KiCad's page origin (which made our pos file's Y values negative) must not leak through.

### Angles

- `rot`: the footprint's rotation **as seen from the side being placed**, counter-clockwise
  positive, normalised to the range (-180, 180]. 0 = the footprint at its library orientation.
- Do **not** add tape/feeder orientation or motor direction: the runner applies those from
  its own per-package and per-feeder tables, so the job file stays valid when feeders change.

### `alignment` (2–4 entries)

Exposed copper pads on the placed side that the down camera will centre on to find the
board's position and rotation. Choose them well; this is where Gerber/PCB parsing pays off:

- As **far apart** as possible (ideally near opposite corners), at least 2, preferably 3, not all in a line.
- **Distinct**: no pad of similar shape and size within 3 mm, so vision can't confuse them.
- Not hidden by anything before placement (true for bare pads); not under a stencil-only area.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | Label used in logs |
| `x`, `y` | number | yes | Pad centre, board frame |
| `shape` | `"rect"`, `"roundrect"`, `"oval"`, `"circle"` | yes | Pad shape |
| `w`, `h` | number | for rect/roundrect/oval | Pad size before rotation |
| `d` | number | for circle | Diameter |
| `rot` | number | no (default 0) | Pad rotation, same convention as parts |
| `ref` | string | no | Footprint the pad belongs to, e.g. `"U1"`, with `pad` e.g. `"1"` |

### `placements`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `ref` | string | yes | **Unique** reference designator (`R1`, `C3`, `U1`). Annotate in KiCad first. |
| `value` | string | yes | Value (`10k`, `100nF`, `NE555`) |
| `package` | string | yes | KiCad footprint name (`R_0603_1608Metric`) |
| `x`, `y` | number | yes | Part centre in the board frame = the point the nozzle picks at. Should equal the centre of the footprint's pads. |
| `rot` | number | yes | See *Angles* |
| `height_mm` | number | yes | Body height above the board (from the package or BOM), > 0 |
| `feeder` | string | no | Feeder/tray id; empty or missing = assigned at the machine |
| `nozzle` | string | no | Nozzle tip id; empty or missing = runner decides |
| `skip` | boolean | no (default false) | DNP / do-not-place: kept for completeness, not placed |

Rules:
- Every `ref` appears once. Every part centre lies inside `outline_mm`.
- **Order matters**: the runner places in file order. Default ordering: lowest `height_mm`
  first, then smallest package, so the nozzle never meets an already-placed taller part.

## Example

```json
{
  "format": "oshe-pnp-job/1",
  "source": {"generator": "example", "inputs": ["Test PCB-all-pos.csv", "Test PCB.kicad_pcb"]},
  "board": {
    "name": "Test PCB",
    "side": "top",
    "outline_mm": [[0, 0], [45.0, 0], [45.0, 45.0], [0, 45.0]],
    "thickness_mm": 1.6
  },
  "alignment": [
    {"name": "A", "x": 2.50, "y": 3.10, "shape": "rect", "w": 1.0, "h": 1.3, "rot": 0, "ref": "J1", "pad": "1"},
    {"name": "B", "x": 41.80, "y": 40.20, "shape": "circle", "d": 1.2},
    {"name": "C", "x": 40.90, "y": 4.00, "shape": "rect", "w": 0.6, "h": 0.9, "rot": 90}
  ],
  "placements": [
    {"ref": "R1", "value": "10k", "package": "R_0603_1608Metric",
     "x": 12.535, "y": 20.000, "rot": 90.0, "height_mm": 0.45, "feeder": "F3"},
    {"ref": "U1", "value": "NE555", "package": "SOIC-8_3.9x4.9mm_P1.27mm",
     "x": 30.000, "y": 15.500, "rot": -90.0, "height_mm": 1.75}
  ]
}
```
(The numbers are illustrative, not the real test PCB.)

## Optional: preview G-code

A generator may also write a separate **preview** `.gcode` (moves only: no vision, no vacuum).
It is not used by the runner. pnpslice's `--gcode` / **+ dry-run G-code** writes the placements in
**board coordinates** as `PNP_BOARD_MOVE X= Y=` lines (applying the machine's board alignment is
left to a macro, like a CNC work offset; those `PNP_*` macros are not on the machine yet). A tool
that writes **machine** coordinates instead must take the board's position on the plate as an
explicit input and respect: mm, `G90`; X 0–235 left to right, Y 0–343 away from the front;
**Z is inverted (larger Z = nozzle lower)**: travel at Z 26 (Z 22 in front of Y 30, where the
feeders are), PCB top ≈ Z 39.5 with the N08 tip; rotation is
`MANUAL_STEPPER STEPPER=stepper_r MOVE=<deg>`; start with `VISION_HOME`.

## Validation and versioning

- pnpslice validates every file it writes against these rules (`pnpslice.job.validate_job`,
  tested on this document's own example). A standalone `pnpvision check-job` command is still an
  idea; until then, other generators should follow the rules above literally.
- `format` changes to `oshe-pnp-job/2` for any incompatible change, with a changelog here.
- Settled since the draft: the rotation sense is runner-internal (`config.toml [rotation]
  direction`); feeder ids are the machine's own (`F1`, ...), assigned at the machine from
  `calibration/feeders.json` when a placement has no `feeder`.
