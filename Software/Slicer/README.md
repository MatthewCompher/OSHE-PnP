# pnpslice

A "slicer" for the pick-and-place machine. You give it a KiCad board (`.kicad_pcb`)
and it makes `oshe-pnp-job/1` job files, one per board side ("plate"). The job runner
does everything machine-side.

**Status: milestone 5.** It reads the board, converts each side into job coordinates
(a "plate"), checks it, works out the placement order, chooses the alignment pads, and
writes job files that follow `JOB_FORMAT.md` (`oshe-pnp-job/1`, v1 draft 2026-11-09).
`tests/test_slicer.py::test_spec_example_validates` checks the spec's own example against
our validator. Next is the optional preview G-code.

**Quick start:** open `run.py` in VS Code and click Run. The first time, it offers to
install PySide6 (Qt) for the window.

In the window:
- Plate 1 / Plate 2 switch between the top and bottom sides.
- Mouse wheel zooms. Drag empty space (or use the middle or right mouse button) to pan.
- Press `F`, or double-click empty space, to fit the board.
- Click a part, or a row in the parts table, to select it.
- `Ctrl+O` opens a board. You can also drop a `.kicad_pcb` file onto the window.
- `F5` reloads the board after you save it in KiCad.
- **Slice plate** (`Ctrl+R`) checks the plate and works out the order. If anything blocks
  it, the Problems list says what and how to fix it. Then **Preview** shows the order:
  drag the slider on the right, or use the ↑ ↓ keys. **Export job…** (`Ctrl+E`) saves
  `<board>-top.job.json` or `<board>-bottom.job.json`.
- **Slice settings:** "Auto-number duplicate references" and **Edit heights…** are saved
  per board in `<board>.pnpslice.json`, next to the `.kicad_pcb` file.
- **Excluding parts:** untick a part in the Parts table, or right-click it (or a whole
  package) on the board. Excluded parts stay in the job with `"skip": true`, as the spec
  describes, and are saved per board. See `USER_GUIDE.md`, section 10.
- **Alignment pads** are chosen automatically (magenta rings, A/B/C). To choose your own,
  click **Pick by hand**: distinct pads turn green and look-alikes red. Click pads to add
  or remove them; **Auto** goes back to the automatic choice. **Look-alike clearance**
  (default 3 mm, as the spec asks): a pad only counts as distinct if no pad of similar
  shape and size is closer than this. If no pad on a side qualifies, the most distinct
  ones are used and a warning says so.

## Set up on your laptop

You need Python 3.10 or newer (3.12 or 3.13 recommended) and, optionally, Git.

1. **Install Python** from <https://www.python.org/downloads/>.
   - Windows: in the installer, tick **"Add python.exe to PATH"**.
   - macOS: the python.org installer is fine, or use `brew install python@3.13`.
2. **Put this folder somewhere sensible**, for example `Software/pnpslice` next to
   `Software/pnpvision` in your repo.
3. **Create a virtual environment** in this folder, so the project's packages stay
   separate from the rest of your system:

   Windows (PowerShell):
   ```powershell
   cd path\to\pnpslice
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   If PowerShell refuses to run the activate script, run this once, then try again:
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

   macOS / Linux:
   ```bash
   cd path/to/pnpslice
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   Your prompt now starts with `(.venv)`. Activate it again each time you open a new
   terminal.
4. **Install pnpslice in editable mode**, with the test tools:
   ```bash
   python -m pip install --upgrade pip
   pip install -e ".[dev]"
   ```
   "Editable" means changes to files in `src/` take effect immediately, with no reinstall.
5. **Run the tests.** You should see about 110 passed (UI tests are skipped if PySide6 isn't installed):
   ```bash
   pytest
   ```
6. **Try it on the test board:**
   ```bash
   pnpslice info "tests/fixtures/test_pcb/Test PCB.kicad_pcb"
   pnpslice check-gerbers "tests/fixtures/test_pcb/Test PCB.kicad_pcb" tests/fixtures/test_pcb
   ```
7. *(Optional)* In VS Code, use **File > Open Folder** to open this folder, then
   **Python: Select Interpreter** and pick `.venv`.

When the UI arrives you'll run `pip install -e ".[gui,dev]"`, which adds PySide6 (Qt).

## Commands

| Command | What it does |
|---|---|
| `pnpslice info BOARD [--json]` | Outline size and origin, the parts on each plate (side), and problems such as duplicate references. Exits 1 if the board can't be sliced yet. |
| `pnpslice slice BOARD [--side top\|bottom\|both] [-o DIR] [--auto-number]` | Writes the job file(s). Exits 1 if a side has errors. |
| `pnpslice check-gerbers BOARD GERBER_DIR` | Checks that every SMD pad centre pnpslice computes lands on a pad in KiCad's copper Gerbers, for both sides. |

## How it's organised

```
src/pnpslice/
  sexpr.py       S-expression reader for KiCad files
  board.py       Board / Footprint / Pad model (KiCad coordinates)
  outline.py     Edge.Cuts -> closed outline (lines, arcs, circles, rects, polys, curves)
  geometry.py    rotation (KiCad's convention), arcs, point-in-polygon
  gerber.py      minimal Gerber flash reader (used only for checking)
  crosscheck.py  board pads vs copper Gerbers
  frame.py       KiCad coordinates -> job frame (origin lower-left, +Y up, bottom mirrored)
  plate.py       one side of the board in job coordinates: parts, pads, outline
  heights.py     part heights: your setting > KiCad Height field > typical-by-package table
  project.py     per-board settings file (<board>.pnpslice.json)
  slicer.py      checks (errors / warnings), auto-numbering, placement order
  alignment.py   alignment pad candidates, distinctness, automatic choice
  job.py         oshe-pnp-job/1 writer and validator
  cli.py         command line
  ui/            Qt window (PySide6): app.py, main_window.py, board_view.py, theme.py
tests/           pytest; fixtures/test_pcb holds the test board and its copper and outline Gerbers
```

The board model deliberately stays in KiCad's coordinates: millimetres, +Y down, page
origin. That way it can be checked directly against KiCad's own output. `frame.py`
converts to the job frame:

| | x | y | angle |
|---|---|---|---|
| Top | x − min_x | max_y − y | angle |
| Bottom (seen from below) | max_x − x | max_y − y | 180 − angle |

`tests/test_frame.py` checks every pad on the test board against this.

## Rules so far

- Placement order: lowest parts first, then smaller packages, one package at a time,
  with the shortest path inside each package group.
- Errors (no job file): duplicate or unnumbered references (unless auto-numbered),
  a pick point outside the outline, a package with no height, or no parts on the side.
- Feeder and nozzle are left out of the job; they're set at the machine.
- Pick point (`x`, `y`) = the centre of the footprint's pads, as the spec asks. A warning
  lists parts whose footprint origin is somewhere else.
- Do-not-populate SMD parts stay in the job with `"skip": true`. Their pads are never
  covered, so they make good alignment pads.
- `source` records the generator, the input file and the date.
- Alignment: copper pads with a solder-mask opening on the placed side. Preference order:
  distinct, spread out and not in a line, then fiducials, then pads that stay visible,
  then pads of parts placed late. Each entry has `name`, `x`, `y`, `shape` (`rect`,
  `roundrect`, `oval` or `circle`), size (`w`/`h`/`rot`, or `d`), `ref` and `pad`, plus
  the extra field `corner_r` for `roundrect` pads.

- Only SMD parts are placed. Through-hole parts, do-not-populate parts, parts excluded
  from position files, and board-only items are skipped.
- One side per job. Each side is a separate "plate".
- Supports KiCad 6 files and newer (tested with KiCad 10.0).