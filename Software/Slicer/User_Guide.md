# pnpslice user guide

pnpslice turns a KiCad board into **job files** for the OSHE-PnP pick-and-place machine.
It works like a 3D-printer slicer: open a board, check it, **slice** each side, step
through the result in **Preview**, then **export** the job file the machine's runner reads.

This guide covers everything the program does. For the file format itself, see
`JOB_FORMAT.md`, the contract with the runner.

---

## Contents

1. [What pnpslice does (and doesn't do)](#1-what-pnpslice-does-and-doesnt-do)
2. [Starting the program](#2-starting-the-program)
3. [Getting your KiCad board ready](#3-getting-your-kicad-board-ready)
4. [The window at a glance](#4-the-window-at-a-glance)
5. [Opening a board](#5-opening-a-board)
6. [Plates and the board frame](#6-plates-and-the-board-frame)
7. [Moving around the board view](#7-moving-around-the-board-view)
8. [What the colours and marks mean](#8-what-the-colours-and-marks-mean)
9. [The Prepare sidebar, section by section](#9-the-prepare-sidebar-section-by-section)
10. [Excluding parts](#10-excluding-parts)
11. [Part heights](#11-part-heights)
12. [Alignment pads](#12-alignment-pads)
13. [Slicing](#13-slicing)
14. [Preview](#14-preview)
15. [Exporting the job file](#15-exporting-the-job-file)
16. [What's in a job file](#16-whats-in-a-job-file)
17. [The settings file next to your board](#17-the-settings-file-next-to-your-board)
18. [Problems: every message and how to fix it](#18-problems-every-message-and-how-to-fix-it)
19. [Command line](#19-command-line)
20. [A complete job, start to finish](#20-a-complete-job-start-to-finish)
21. [Troubleshooting](#21-troubleshooting)
22. [Keyboard and mouse reference](#22-keyboard-and-mouse-reference)

---

## 1. What pnpslice does (and doesn't do)

**It does the board side of the work:**

- reads your `.kicad_pcb` file (KiCad 6 or newer) directly: parts, pads and outline;
- converts KiCad's coordinates into the **board frame** the runner expects (origin at the
  board's lower-left corner, +Y up, bottom side mirrored);
- works out each part's pick point, rotation and height;
- checks for problems (duplicate references, missing heights, parts off the board…);
- puts the placements in a sensible order;
- chooses 2–4 **alignment pads** the machine's camera can find;
- writes one job file per board side.

**It deliberately does not** put machine coordinates, Z heights, feeder positions or
nozzle choices in the job file. The runner works all of that out on the machine, because it
depends on where the board lands, how each part sits on the nozzle, and the machine's
calibration. (Optionally it also writes a **dry-run G-code** of the placements in board
coordinates: see [section 15](#15-exporting-the-job-file).)

**Only SMD parts are placed.** Through-hole parts are skipped, and so are parts marked
*Exclude from position files* or *Not in schematic / board only*. Parts marked
*Do not populate* in KiCad, and parts you **exclude** in pnpslice, stay in the job file
flagged to be skipped (see [section 10](#10-excluding-parts) and
[section 16](#16-whats-in-a-job-file)).

---

## 2. Starting the program

### The Windows app (easiest)

Double-click **`pnpslice.exe`** (from the repository's Releases, or built with
`build_exe.ps1` into `Slicer\dist\`). Nothing to install. It opens the board you used last;
dropping a `.kicad_pcb` file onto `pnpslice.exe` opens that board instead. The first start takes
a few seconds while it unpacks.

### From VS Code (from source)

1. Open the `Slicer` folder in VS Code.
2. Open `run.py`.
3. Click the **▶ Run** button in the top-right corner.

**The first time,** the terminal asks:

```
The slicer window needs PySide6 (the Qt toolkit, about 100 MB download).
Install it now? [Y/n]
```

Press **Enter**. It installs once, and then the window opens.

### Which board opens

When you click Run, `run.py` decides what to open:

1. If `BOARD` at the top of `run.py` is set to a path, it opens that board.
2. Otherwise, it opens the first `Test PCB.kicad_pcb` it finds anywhere under
   `tests\fixtures`.
3. Otherwise, it reopens the last board you used, or shows an empty window.

To always open one of your own boards, edit the line near the top of `run.py`:

```python
BOARD = r"C:\Users\you\Projects\My Board\My Board.kicad_pcb"
```

Keep the `r` before the quotes; it stops Windows backslashes being misread.

### Text-only mode

Set `MODE = "text"` in `run.py` to get a printed summary and the Gerber pad check in the
terminal instead of the window. This is useful for a quick check, or if Qt won't install.

---

## 3. Getting your KiCad board ready

pnpslice reads exactly what's in the `.kicad_pcb` file, so most problems are fixed in
KiCad. Before slicing a real board, check the following.

| Check | Why | Where in KiCad |
|---|---|---|
| **Every part has its own reference** (`R1`, `R2`, … not `R?` or `R0805` ×30) | The runner logs, retries and resumes by reference | Schematic: *Tools › Annotate Schematic*, then *Update PCB*. PCB only: *Tools › Geographical Reannotate* |
| **SMD parts have the SMD attribute** | Only SMD parts are placed | Footprint properties › *Fabrication attributes* › Component type = SMD |
| **Parts you won't fit are marked Do not populate** | They're kept in the job with `skip` | Footprint or symbol properties › *Do not populate* |
| **The board outline is closed**, on **Edge.Cuts** | The outline sets the origin and checks parts are on the board | Run DRC; it reports gaps in the outline |
| **2–3 fiducials**, if you can | The best alignment targets: round, distinct, never covered by parts | Library `Fiducial`, e.g. `Fiducial_1mm_Mask2mm`, near opposite corners |
| *(Optional)* **a `Height` field** on footprints whose height you know | Overrides the typical height for that package | Footprint properties › add field `Height`, value like `1.75` or `1.75 mm` |

Save the board in KiCad before opening it in pnpslice. If you change it later, press
**F5** in pnpslice to reload.

---

## 4. The window at a glance

```
┌────────────────────────────────────────────────────────────────────────────┐
│ pnpslice   Prepare  Preview          Open board…  Reload  [Slice plate] [Export job…] │  ← top bar
├──────────────────────┬─────────────────────────────────────────────────────┤
│ Board                │ [Plate 1 · Top (92)] [Plate 2 · Bottom (64)]  Labels Grid Fit │ ← plate bar
│ Plate                │                                                     │
│ Slice settings       │                                                     │
│ Alignment pads       │          board view                                 │ slider
│ Problems             │          (zoom, pan, click parts)                    │ (Preview
│ Parts                │                                                     │  only)
│                      │                                                     │
├──────────────────────┴─────────────────────────────────────────────────────┤
│ X  12.345  Y  6.789 mm │ hovered or current part …               12.5 px/mm │ ← status bar
└────────────────────────────────────────────────────────────────────────────┘
```

- **Top bar:**
  - **Prepare** and **Preview** switch between setting up a plate and checking the sliced result.
  - **Open board…** and **Reload** load or re-read a board.
  - **Slice plate** works out the job.
  - **Export job…** saves it.
- **Plate bar:** choose the side, and switch **Labels**, **Grid** and **Fit**. For the
  bottom plate it also reminds you the view is mirrored.
- **Sidebar:** everything about the current board and plate. It scrolls if the window is short.
- **Board view:** the board as the machine will see it.
- **Status bar:** the cursor position in board millimetres, details of the part under the
  mouse, and the zoom level.

---

## 5. Opening a board

There are three ways to open a board:

- **Open board…** (or `Ctrl+O`): choose a `.kicad_pcb` file.
- **Drag** a `.kicad_pcb` file from File Explorer onto the window.
- **Run `run.py`** (see [section 2](#which-board-opens)).

**Reload** (or `F5`) re-reads the same file. Use it after saving changes in KiCad: the
view, plate and settings stay as they were. Reloading also clears any sliced results,
since they may be out of date.

If a board can't be opened, a message says why. Common causes are a KiCad 5 file (open
and save it in KiCad 6 or newer) or an outline with a gap. See
[section 18](#18-problems-every-message-and-how-to-fix-it).

---

## 6. Plates and the board frame

A **plate** is one side of the board, the same idea as a plate in OrcaSlicer:

| Plate | Side | How it's drawn |
|---|---|---|
| **Plate 1 · Top** | The top (F.Cu) | Looking down at the top, the same as KiCad |
| **Plate 2 · Bottom** | The bottom (B.Cu) | The board **turned over left-to-right**, looking at the underside, **mirrored** compared with KiCad |

Each plate becomes its own job file. A double-sided board needs two jobs: you place one
side, turn the board over, and place the other.

The number in brackets on each button is how many parts that side will place. A **✓**
appears after a plate has been sliced.

### The board frame

All coordinates shown in pnpslice, and written to job files, are in the **board frame**:

- **Origin (0, 0)** is the **lower-left corner** of the board outline's bounding box,
  *as seen from the side being placed*. It's marked in the view with a red **X** arrow
  and a green **Y** arrow.
- **+X is right, +Y is up.** Everything on the board has coordinates ≥ 0.
- **Angles** are degrees, **counter-clockwise positive**, as seen from the side being
  placed, in the range −180 to 180. 0 means the part sits as drawn in its KiCad library footprint.

For the **bottom** plate, pnpslice mirrors left-to-right for you:
`x = board width − KiCad x` and `angle = 180 − KiCad angle`. What you see on Plate 2 is
exactly what you see with the real board turned over. Comparing the two is the best
check that everything is right.

KiCad's own page origin and its downward Y axis never appear in pnpslice.

---

## 7. Moving around the board view

| Action | How |
|---|---|
| Zoom | **Mouse wheel**, centred on the cursor. Or `+` / `−` with the view focused |
| Pan | **Drag empty board space** with the left button, or drag **anywhere** with the middle or right button |
| Part menu | **Right-click** a part (without dragging): exclude or include it, or its whole package ([section 10](#10-excluding-parts)) |
| Fit the board | **Fit** button, the `F` key, or **double-click** empty space |
| Part details | **Hover** a part: a tooltip shows reference, value, package, X/Y and rotation, and the status bar repeats it |
| Select a part | **Click** it. Its row in the Parts table is highlighted |
| Find a part | Click its row in the **Parts** table: the view centres on it |
| Deselect | Click empty space |
| Labels | **Labels** button. Part references appear once you're zoomed in far enough (about 14 pixels per mm) |
| Grid | **Grid** button. 5 mm grid, plus 1 mm lines when zoomed in |

The **status bar** shows the cursor position in board millimetres, useful for checking
against calipers on the real board.

---

## 8. What the colours and marks mean

### Prepare

| Mark | Meaning |
|---|---|
| Green board, yellow edge | The board outline (Edge.Cuts) |
| Gold shapes | Copper pads |
| **Orange** pad | **Pin 1**, shown on parts with more than two pads |
| Small white **+** | The **pick point**: the centre of the part's pads, where the nozzle picks |
| **Faded** part | Excluded by you, or do-not-populate in KiCad: in the job with `skip`, never placed |
| Thin line from the + | The part's **rotation**: its library +X direction. Shown when selected or zoomed in |
| Teal box | The selected part |
| **Magenta ring** with A, B, C… | An **alignment pad** |
| Red / green arrows at (0, 0) | The board-frame origin and axes |

### Pick by hand (alignment)

| Mark | Meaning |
|---|---|
| **Green** pad | Distinct: no look-alike pad within the clearance |
| **Red** pad | Has a look-alike pad too close |
| White outline | The pad under the mouse |

### Preview

| Mark | Meaning |
|---|---|
| Dark grey part | Already placed at this step |
| **Teal** part with `#n REF` | The part placed **at this step** |
| Faded pads | Not placed yet |
| `(skip)` | Excluded or do-not-populate: in the job, never placed |
| Thin teal line | The path the nozzle takes between placements |
| Grey alignment ring | That alignment pad's part has been placed, so the pad is now covered |

---

## 9. The Prepare sidebar, section by section

### Board

Name, size, thickness, the KiCad version that saved the file, and the file name. Hover
the file name to see its full path.

### Plate

The side, how many parts it will place, a count per package, and anything **skipped**
with the reason (through-hole, board-only, excluded from position files). Parts you
excluded and do-not-populate parts are counted separately, because they stay in the job.
When any are excluded, an **Include all** button appears here.

### Slice settings

- **Auto-number duplicate references.** For testing only. Parts that share a reference
  (or have none, like `R?`) get numbered names in the job file: `R0805_1`, `R0805_2`, …
  - Numbering follows reading order on that plate: rows from top to bottom, then left to right.
  - References that are already unique are left alone. Names that already exist are skipped.
  - Your KiCad file is **not** changed. For real jobs, annotate in KiCad instead.
- **Edit heights…** opens the heights table (see [section 11](#11-part-heights)). The note
  next to it says where the current heights come from.
- **Order:** lowest parts first, one package at a time, shortest path (see
  [section 13](#placement-order)).

### Alignment pads

The pads the camera will use to find the board, with the controls to change them. See
[section 12](#12-alignment-pads).

### Problems

A live check of the plate, updated whenever anything changes:

- **✖ red** = **error**: blocks slicing until fixed.
- **⚠ amber** = **warning**: slicing still works, but read it.
- **✔ Ready to slice** = no errors.

**Click a problem** to jump to the first part it's about. Every message is explained in
[section 18](#18-problems-every-message-and-how-to-fix-it).

### Parts

Every part on this plate: **Ref, Package, X, Y, Rot, H** (height).

- Click a column header to **sort**.
- Type in the filter box to show only matching references, values or packages.
- Click a row to select the part and centre the view on it.
- Hover **H** to see where that height came from.
- **Untick** a part's box to exclude it, or right-click a row for the part menu
  ([section 10](#10-excluding-parts)).
- Do-not-populate parts are shown as `R5 (DNP)`, greyed, with no box.

---

## 10. Excluding parts

You can leave parts out of a job without touching KiCad: for example a feeder that isn't
loaded yet, a part you'll fit by hand, or one you want to test on its own.

**Excluded parts stay in the job file with `"skip": true`.** `JOB_FORMAT.md` describes
this as "kept for completeness, not placed", so the runner knows about the part and can
log it, but never picks it. Do-not-populate parts from KiCad are handled exactly the same way.

### How to exclude parts

| Where | How |
|---|---|
| **Parts table** | **Untick** the box next to the reference. Tick it again to include the part |
| **Board view** | **Right-click** a part › **Exclude R12** (or **Include R12**) |
| **A whole package** | Right-click any part of that package (on the board or in the table) › **Exclude all 23 × R_0805_2012Metric on this plate**. Useful when a whole feeder isn't loaded |
| **Undo everything on a plate** | Click **Include all (N excluded)** under the Plate section, or right-click › **Include everything on this plate** |

Right-click without moving the mouse to open the menu. Right-click and drag still pans.

### What changes

- Excluded parts are **faded** on the board and labelled `(excluded)` when labels are
  showing. In the Parts table their box is unticked and the reference is greyed.
- The **Plate** section and the plate button count only parts that will be placed, for
  example *56 parts to place (+8 excluded: kept with skip)*.
- In **Preview** they keep their place in the order, labelled `(skip)`, and the nozzle
  path goes past them.
- Their pads are **never covered**, so they become good **alignment pad** candidates.
- Exclusions are **saved with the board** ([section 17](#17-the-settings-file-next-to-your-board)).
  They're tied to KiCad's internal ID for each footprint, so they survive reannotating
  and moving parts. Like any setting, changing them clears the current slice; slice again.

### Rules

- An excluded part still needs a **unique reference**, because every entry in the job
  file must have one.
- An excluded part that is **off the board**, or whose package has **no known height**,
  is simply left out of the file (with a warning) instead of blocking the slice. Every
  entry in the file must be on the board and have a height.
- If **every** part on a plate is excluded or do-not-populate, there's nothing to place
  and slicing is blocked.
- Do-not-populate parts can't be included from pnpslice; change that in KiCad. Their
  box is greyed out.

---

## 11. Part heights

The runner needs each part's **height** to work out how far down to place it. pnpslice
takes each package's height from the first of these that has one:

1. **Your setting**: a height you entered in **Edit heights…**, saved for this board.
2. **The KiCad footprint field**: a field named `Height` (also `Height_mm`,
   `Component Height` or `Max Height`), with a value like `1.75` or `1.75 mm`.
3. **The typical height for the package**: a built-in table for common KiCad
   footprints (chip resistors, capacitors and LEDs, SOD, SMA/SMB, SOT-23/89/223, SOIC,
   SSOP, TSSOP, MSOP, QFP, QFN, DFN).

If none of these has a height, slicing is blocked until you set one.

**Typical heights are a starting point.** A warning lists packages using them, because
real parts vary. Capacitors in particular get taller with higher values. Check them
against your parts' datasheets.

### The heights dialog

**Edit heights…** lists every package on the board (both sides), how many parts use it,
the current height, and where that height comes from.

- To set a height, double-click the **Height (mm)** cell, type the value, and press Enter.
  **From** changes to *your setting*.
- To go back to the default, clear the cell.
- Click **OK** to save. Values must be between 0 and 50 mm.

Heights you set are saved in the board's settings file
([section 17](#17-the-settings-file-next-to-your-board)), so you only enter them once.

---

## 12. Alignment pads

Before placing, the machine centres its down-looking camera on each **alignment pad** to
find exactly where the board is and how it's rotated. pnpslice chooses them automatically,
and you can override its choice.

### What makes a good alignment pad

- **Visible:** copper with a solder-mask opening on the side being placed.
- **Distinct:** no pad of **similar shape and size** within the **look-alike
  clearance** (3 mm by default, as `JOB_FORMAT.md` asks).
  - "Similar" means the same kind of shape (rectangle, oval or circle) and both sides
    within 25% of each other.
  - Twin pads of the same resistor count as look-alikes.
- **Spread out**, ideally near opposite corners, and **not in a line**. With 3 or more
  pads, the runner can measure rotation as well as position.
- **Stays visible**, ideally. In order of preference:
  1. fiducials;
  2. pads of parts that aren't placed in this job (through-hole, do-not-populate);
  3. pads of parts placed late in the order.

  A part covers its own pads once it's placed, which matters if the job is stopped and
  needs re-aligning.

### The Alignment pads section

| Control | What it does |
|---|---|
| **Pads** (2–4) | How many pads to choose automatically. 3 is recommended |
| **Look-alike clearance ≥** | The distinct rule. Default 3 mm. Lower it only if the board sits accurately on the machine: a look-alike must be more than twice the board's possible position error away |
| The list | Each chosen pad, for example `A  R12 pad 1 · 1.025×1.4 · look-alike 3.40 mm · covered at #57` |
| **Pick by hand** | Choose pads yourself by clicking them on the board |
| **Auto** | Forget your picks and go back to the automatic choice |
| *chosen automatically* / *picked by hand* | Which of the two is in use |

**Reading a list entry:**
- **look-alike 3.40 mm**: the distance to the nearest similar pad.
- **covered at #57**: placement step 57 places that pad's part.
- **stays visible** or **fiducial**: the pad is never covered.
- **⚠ too close**: the pad doesn't meet the clearance.

Pads are named A, B, C, D: **A** is nearest the origin, and the rest follow
counter-clockwise around the board.

### Picking by hand

1. Click **Pick by hand**. The button turns purple, and every candidate pad turns
   **green** (distinct) or **red** (has a look-alike too close).
2. Hover a pad: the status bar shows its details.
3. **Click a pad** to add it, or click a chosen pad to remove it. You can pick 2 to 4 pads.
4. Click **Pick by hand** again when you're done.

When you start, your list begins with the automatic choice, so you can adjust it rather
than start from scratch. With fewer than 2 picked, the automatic choice is used and a
warning says so.

Your picks are **saved per side**. They're tied to each footprint's internal ID and pad
number, so they still work after you reannotate or move parts in KiCad. If a picked
footprint is deleted, a warning tells you and the remaining picks (or the automatic
choice) are used.

### If no pad is distinct

Some boards have no pad that meets the clearance. On dense boards every pad often has a
twin close by. pnpslice then uses the **most distinct pads available** and shows a
warning. The proper fix is to add **fiducials** in KiCad.

---

## 13. Slicing

Click **Slice plate** (or press `Ctrl+R`) to slice the **current** plate.

- **If there are errors,** a message lists them and you stay in Prepare. Fix them (the
  Problems list says how) and slice again.
- **Otherwise,** pnpslice switches to **Preview**, the plate button gets a ✓, and
  **Export job…** becomes available.

Slicing is quick; slice again whenever you like. **Changing any setting** (heights,
auto-numbering, alignment, excluded parts) or **reloading** the board throws away existing slices, so
you never export something out of date. The status bar reminds you to slice again.

### Placement order

The runner places parts in file order. pnpslice orders them like this:

1. **By height, lowest first.** The nozzle never has to reach past a taller part that's
   already placed.
2. **Parts of the same height and package together**, smaller packages first, so each
   feeder is used in one run.
3. **Within a package, the shortest path.** Each next part is the nearest one not yet
   placed, starting from where the previous group ended.

On the test board's bottom side, that means all the 0201s first, then 0402, 0603, 0805,
1206, and the SOIC-8s last.

---

## 14. Preview

Preview shows the sliced job step by step, like the layer slider in OrcaSlicer.

**Moving through the steps:**
- **Slider** on the right: drag it, or click above or below the handle. The number at the
  top is the current step out of the total.
- **Keys** (click on the board first): `↑` / `→` next step, `↓` / `←` previous step,
  `Page Up` / `Page Down` ±10 steps, `Home` first step, `End` last step.
- **Placement order table** in the sidebar: click a row to jump to that step.
- **Click a part** on the board to jump to its step.

**What you see:** placed parts turn dark grey, the current part is teal and labelled
`#n REF`, and parts still to come are faded. A thin line traces the nozzle's path.
Alignment rings turn grey once their pad is covered.

**The Preview sidebar:**
- **Job:** how many placements (and skips), packages, the height range, the alignment
  pads, and the file name the export will use.
- **Warnings:** anything to know before exporting.
- **Placement order:** `#`, **Ref** (as written to the job, auto-numbered if that's on),
  **Package**, **H**.

Click **Prepare** to go back and change things.

---

## 15. Exporting the job file

In Preview, click **Export job…** (or press `Ctrl+E`). The save dialog suggests:

```
<board name>-top.job.json
<board name>-bottom.job.json
```

It opens in the folder you last exported to, or next to the board the first time. Export
each plate you need; each is a separate file.

**To the machine without a network:** export straight onto an SD card or USB stick (top folder,
or one folder down), then on the machine's touchscreen tap **Pick & Place -> Job -> Load jobs from
SD card / USB stick**. Keep the name ending in `.job.json` and use only letters, digits, spaces,
`_`, `.` and `-`.

### Dry-run G-code (optional)

Tick **+ dry-run G-code** (next to **Export job…**) and the export also writes
`<board>-top_dryrun.gcode` next to the job file: for every part to place, in order, a
`PNP_BOARD_MOVE X= Y=` line in **board coordinates** and a short pause. The setting is
remembered. The command line does the same with `pnpslice slice BOARD --gcode`.

It is a preview and record of the placements as G-code. The machine runs jobs from the
`.job.json` (placing needs the cameras, feeders and retries). The `PNP_*` macros it calls are not
on the machine yet, so if the file is printed, Klipper stops at its first command and nothing
moves.

Before giving a file to the runner, it's worth a quick look in VS Code (it's plain
JSON, one placement per line) to see the order and values are what you expect.

---

## 16. What's in a job file

Here's a shortened example from the test board's bottom side:

```json
{
  "format": "oshe-pnp-job/1",
  "source": {
    "generator": "pnpslice 0.1.0",
    "inputs": ["Test PCB.kicad_pcb"],
    "date": "2026-11-10T03:23:42+00:00"
  },
  "board": {
    "name": "Test PCB",
    "side": "bottom",
    "outline_mm": [[0.0, 0.0], [46.51, 0.0], [46.51, 54.0], [0.0, 54.0]],
    "thickness_mm": 1.6
  },
  "alignment": [
    {"name": "A", "x": 2.0375, "y": 33.5, "shape": "roundrect", "w": 1.125, "h": 1.75, "rot": 0.0, "corner_r": 0.25, "ref": "R1206_15", "pad": "1"},
    ...
  ],
  "placements": [
    {"ref": "R0201_1", "value": "R_0201_0603Metric", "package": "R_0201_0603Metric", "x": 8.0, "y": 22.5, "rot": 0.0, "height_mm": 0.23, "kicad_ref": "R0201"},
    ...
    {"ref": "SOIC8_1", "value": "SOIC-8_3.9x4.9mm_P1.27mm", "package": "SOIC-8_3.9x4.9mm_P1.27mm", "x": 8.5, "y": 5.5, "rot": -90.0, "height_mm": 1.75, "kicad_ref": "SOIC8"}
  ]
}
```

| Field | Meaning |
|---|---|
| `format` | Always `oshe-pnp-job/1` |
| `source` | Where the file came from: pnpslice version, input file, date |
| `board.side` | `top` or `bottom`. Everything else in the file is as seen from this side |
| `board.outline_mm` | The board outline in the board frame, starting at the (0, 0) corner |
| `alignment[]` | 2–4 pads: `name`, centre `x`/`y`, `shape` (`rect`, `roundrect`, `oval`, `circle`), size `w`/`h` and `rot` (or `d` for circles), and the `ref`/`pad` they belong to. `corner_r` is an extra field giving the corner radius of `roundrect` pads |
| `placements[]` | In placement order: `ref`, `value`, `package`, `x`/`y` (the pads' centre = pick point), `rot`, `height_mm` |
| `skip: true` | Excluded by you, or do-not-populate in KiCad: listed but not placed |
| `kicad_ref` | Only on auto-numbered parts: the reference in KiCad |

**Not in the file, on purpose:** `feeder` and `nozzle`. The spec says missing means
"assigned at the machine". There are also no machine coordinates, Z values or G-code
(the optional dry-run G-code is a separate file).

---

## 17. The settings file next to your board

Your choices for a board are saved next to it, as `<board name>.pnpslice.json`, for example:

```json
{
  "pnpslice_settings": 1,
  "heights": {"R_0603_1608Metric": 0.5},
  "auto_number": false,
  "align_count": 3,
  "align_clearance_mm": 3.0,
  "alignment": {"bottom": ["2f577eea-…/1", "…"]},
  "excluded": ["8c1d0e4a-…", "…"]
}
```

- It's written whenever you change a setting, and read when the board opens.
- **To start over**, delete it.
- It's small and safe to commit to Git with the board, so everyone gets the same heights
  and alignment picks.
- If the file is damaged, pnpslice ignores it and uses defaults rather than refusing to
  open the board.

Window size and the last board and folders are remembered separately, by Windows.

---

## 18. Problems: every message and how to fix it

### Errors (block slicing)

| Message | Cause | Fix |
|---|---|---|
| *N parts share N reference(s)…* | Parts with the same reference | Annotate in KiCad (*Tools › Geographical Reannotate* in the PCB editor), or tick **Auto-number** for testing |
| *Unnumbered reference(s): R?…* | Parts never annotated | As above |
| *Part centre outside the board outline* | A part's pad centre is off the board or in a cut-out | Move the part, or fix the outline in KiCad, or exclude the part |
| *No height for package(s)…* | No setting, footprint field or typical height | **Edit heights…**, or add a `Height` field in KiCad |
| *There are no SMD parts to place on the … side* | Nothing to place on this side | Nothing to do if that's expected; otherwise check the parts have the SMD attribute |
| *Nothing to place on the … side: every part is excluded or do-not-populate* | You excluded everything | Include some parts (right-click › Include, or **Include all**) |
| *Fewer than 2 visible copper pads…* | Can't align the board | Pads need a solder-mask opening on this side; add fiducials |

### Warnings (slicing still works)

| Message | Meaning |
|---|---|
| *N part(s) were numbered automatically…* | Auto-number is on; the names exist only in the job file |
| *N package height(s) are typical values…* | Check them in **Edit heights…** |
| *Within 0.5 mm of the board edge* | A part's centre is very near the edge (rectangular boards only) |
| *Footprint origin isn't the pad centre for…* | The part is picked at its pad centre, as the spec asks. Check this is the part's middle; it matters for parts with lopsided pads |
| *Not placed, but kept in the job with "skip": true (… do-not-populate, … excluded by you)* | Information: they're listed but not placed |
| *Part(s) you won't place have no known height, so they were left out of the job file* | The spec needs a height for every entry; set one if you want them listed |
| *Part(s) you won't place are off the board, so they were left out of the job file* | Every entry must be on the board, so these aren't listed at all |
| *Alignment pad(s) … have a look-alike pad closer than 3 mm* | Vision could confuse them: pick other pads, add fiducials, or lower the clearance if the board sits accurately |
| *The alignment pads are close together or nearly in a line* | Rotation will be less accurate: pick pads further apart |
| *All alignment pads belong to parts in this job and get covered…* | Fine for a normal run; re-aligning after a stop would need other pads. Fiducials fix this |
| *You've picked 1 alignment pad; pick at least 2* | You're picking by hand; add another |
| *The alignment pads you picked aren't on the board any more* | The footprints were deleted; the automatic choice is used |
| *Edge.Cuts shape(s) lie outside the main board edge* | Extra outlines (a panel?); only the largest is used |
| *Board file format … is newer than tested* | Saved by a newer KiCad; check the preview carefully |

### When a board won't open

| Message | Fix |
|---|---|
| *…is from KiCad 5 or older* | Open and save it in KiCad 6 or newer |
| *…is not a KiCad board* | You opened a schematic or another file; choose the `.kicad_pcb` |
| *board outline (Edge.Cuts) is not closed: there is a gap near (x, y)* | Close the gap in KiCad (DRC finds it). The coordinates are KiCad's |
| *the board has no outline* | Draw the outline on the Edge.Cuts layer |

---

## 19. Command line

Everything except Preview also works from a terminal. That's useful for scripts, or for
checking a board quickly.

From the `Slicer` folder in VS Code's terminal (PowerShell):

```powershell
$env:PYTHONPATH = "src"
python -m pnpslice.cli info  "tests\fixtures\Test PCB\Test PCB.kicad_pcb"
python -m pnpslice.cli slice "tests\fixtures\Test PCB\Test PCB.kicad_pcb" --auto-number
```

If you install the project with `pip install -e .`, you can type `pnpslice` instead of
`python -m pnpslice.cli`.

| Command | What it does |
|---|---|
| `info BOARD [--json]` | Outline, parts per plate, skipped parts, problems. Exit code 1 if references need fixing |
| `slice BOARD [--side top\|bottom\|both] [-o FOLDER] [--auto-number]` | Writes the job file(s), next to the board unless `-o` is given. Uses the board's saved settings. Lists any problems; a side with errors isn't written, and the exit code is 1 |
| `check-gerbers BOARD GERBER_FOLDER [--tol MM]` | Checks every SMD pad centre pnpslice computes against KiCad's copper Gerbers. A good check of a new board or a new KiCad version |

---

## 20. A complete job, start to finish

1. **In KiCad:** annotate, check the SMD and Do-not-populate attributes, run DRC, and
   ideally add fiducials. Save.
2. **Open** the board in pnpslice. Look at **Problems** and fix any ✖ errors.
3. **Plate 1 · Top:**
   1. Check the parts table and the drawing look right.
   2. Exclude anything you won't place this time (untick it, or right-click a package).
   3. **Edit heights…**: confirm or correct the heights.
   4. Check the **alignment pads**. Prefer green, distinct pads near the corners.
   5. **Slice plate**. Step through **Preview**, watching the order and the path.
   6. **Export job…** → `<board>-top.job.json`.
4. **Plate 2 · Bottom:** the same steps → `<board>-bottom.job.json`. Compare the
   picture with the real board turned over, especially pin 1 positions.
5. Give the job files to the runner on the machine.
6. If you change the board in KiCad later: save, press **F5**, slice and export again.
   Your heights and alignment picks are kept.

---

## 21. Troubleshooting

**The window doesn't open, or an error appears in the terminal**
- `No module named 'pnpslice.src'`, or an import line containing `src.pnpslice`: VS Code
  rewrote imports when files were moved. Correct imports start with `from .` (or
  `from ..` in the `ui` folder) and never contain `src`. When VS Code offers to "update
  imports" after you move a file, click **No**.
- `No module named 'pnpslice.ui.app'` (or another file): that file is missing or in the
  wrong folder. The layout must be `Slicer\src\pnpslice\` for the main files and
  `Slicer\src\pnpslice\ui\` for `app.py`, `main_window.py`, `board_view.py`, `theme.py`
  and `__init__.py`.
- `run.py` must be in `Slicer\`, next to `pyproject.toml`, not inside `src`.
- PySide6 failed to install: paste the error into the chat. Meanwhile, `MODE = "text"`
  in `run.py` still works.

**The board looks wrong**
- Mirrored or upside down on Plate 2: that's expected. It's the board turned over. Compare
  it with the real board flipped left-to-right.
- Parts in the wrong place: run `check-gerbers` (or `MODE = "text"` in `run.py`, which runs
  it) against freshly plotted Gerbers. `[OK]` on both sides means pnpslice reads the pads
  exactly where KiCad puts them.
- A part's pick point isn't its middle: check the *Footprint origin isn't the pad centre*
  warning, and the footprint in KiCad.

**Changes in KiCad don't show:** save in KiCad, then press **F5**.

**Slice plate does nothing:** there are errors. A message lists them, and so does Problems.

**Export job… is greyed out:** slice the current plate first. Changing a setting also
clears the slice.

**Pick by hand doesn't respond:** it only works in Prepare, and only on candidate pads
(green or red). Hover until a pad gets a white outline, then click.

**Running the tests:** VS Code's **Testing** panel (flask icon) › **Run All Tests**. They
all pass on a correct setup. The window tests are skipped if PySide6 isn't installed.

---

## 22. Keyboard and mouse reference

### Anywhere in the window

| Key | Action |
|---|---|
| `Ctrl+O` | Open board |
| `F5` | Reload the board |
| `Ctrl+R` | Slice the current plate |
| `Ctrl+E` | Export the job (after slicing) |

### Board view (click on the board first)

| Key / mouse | Action |
|---|---|
| Mouse wheel | Zoom at the cursor |
| Drag empty space (left), or drag anywhere (middle or right) | Pan |
| `F`, or double-click empty space | Fit the board |
| `+` / `−` | Zoom in / out |
| Click a part | Select it (Prepare) or jump to its step (Preview) |
| Click a pad (in Pick by hand) | Add or remove it as an alignment pad |
| Right-click a part (no drag) | Part menu: exclude or include it, or its whole package |

### Preview

| Key | Action |
|---|---|
| `↑` / `→` | Next placement |
| `↓` / `←` | Previous placement |
| `Page Up` / `Page Down` | 10 placements forward / back |
| `Home` / `End` | First / last placement |