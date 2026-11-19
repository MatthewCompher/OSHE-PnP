# Testing & Results

How we showed the machine meets its specification, and how you can repeat it.

- [Acceptance Tests](acceptance.md): each requirement, the test, the conditions and the pass
  criterion.
- [Results](results.md): the numbers and plots from the final runs (2026-11-18).
- [Sample Images and Data](samples.md): real photos and report files from those runs.

## Software tests

Both programs have automated tests that need no hardware:

| Program | Command | Result (2026-11-18) |
|---|---|---|
| pnpvision | `cd Software/pnpvision && pytest` | 92 passed |
| pnpslice | `cd Software/Slicer && pytest` | 99 passed, 1 skipped (window test needs PySide6) |

They cover the vision detectors (on saved real photos), the job planner, the touchscreen Job page,
SD/USB import, the job file validator, and the slicer's geometry and ordering.
