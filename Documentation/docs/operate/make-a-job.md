# 2. Make a Job

A **job file** (`<board>-top.job.json`) lists every part to place on one side of a board, in
order, in board coordinates. It is made on your computer with **pnpslice**, the project's slicer.
It never contains machine coordinates: the machine finds the board itself.

## Get pnpslice

=== "Windows app (easiest)"

    Download `pnpslice.exe` from the repository's **Releases** page and double-click it. No Python
    needed. To build it yourself: `Software/Slicer/build_exe.ps1` (see `Software/Slicer/README.md`).

=== "From source (any OS)"

    Python 3.10 - 3.13:
    ```bash
    cd Software/Slicer
    python -m venv .venv
    .venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
    pip install -e ".[gui]"
    python run.py
    ```

## Prepare the board in KiCad

| Check | Why |
|---|---|
| Every part has its own reference (R1, R2, not R?) | the machine logs, retries and resumes by reference |
| SMD parts have the SMD attribute | only SMD parts are placed |
| Parts you won't fit are marked Do not populate | they stay in the job, skipped |
| Closed board outline on Edge.Cuts | sets the board origin |
| 2 - 3 fiducials, if you can | the best alignment targets |

## Slice and export

1. **Open board...** (or drop the `.kicad_pcb` onto the window).
2. Untick any part you don't want placed (they stay in the job as skipped).
3. **Slice plate** (Ctrl+R). The Problems list says what blocks it and how to fix it.
4. **Preview**: step through the placement order with the slider.
5. Optionally tick **+ dry-run G-code** to also write `<job>_dryrun.gcode` (below).
6. **Export job...** (Ctrl+E).

pnpslice also chooses 2 - 4 **alignment pads** (A, B, C) the machine uses to find the board.
Good pads are distinct (no look-alike within 3 mm), spread out, and never covered by a placed part.

!!! tip "Placement order"
    Lowest parts first, then smaller packages, one package at a time, shortest path within each
    group - so the nozzle never meets a taller part already placed.

## Dry-run G-code

The **+ dry-run G-code** option writes the job's placements as a G-code file: for each part, a
move in board coordinates and a short pause. The coordinates are board coordinates because only
the machine knows where the board sits; a `PNP_BOARD_MOVE` macro is meant to apply the machine's
board alignment, like a CNC work offset.

!!! note "Production jobs run from the job file"
    The machine runs jobs from the `.job.json` file: placing needs the cameras, feeders and
    retries, which plain G-code can't do. The `PNP_DRYRUN_*` / `PNP_BOARD_MOVE` macros are not on the
    machine yet, so if the G-code file is printed, Klipper stops at its first command and nothing
    moves.

Next: [Load the job onto the machine](load-jobs.md).
