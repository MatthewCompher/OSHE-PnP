# Sample machine outputs (for the documentation)

A small, curated set of real outputs from the acceptance runs on 2026-11-17/18 (Test PCB, top
side, 0603 resistors from feeder F1). Everything the machine writes stays on the Pi or in
`Software/pnpvision/captures/` (both ignored by git); these copies are kept on purpose.

## up_camera/ — part on the nozzle, seen from below (`run-job`)
| File | Decision | Why |
|---|---|---|
| `pass_0603_on_nozzle.jpg` | PASS | 0603 flat, white ceramic underside, right size |
| `reject_0603_on_its_side.jpg` | REJECT | 0.55 mm wide instead of ~0.9: standing on its side (min_width_frac check) |
| `empty_nozzle_bare_tip.jpg` | EMPTY | only the N08 tip end (~0.85 x 0.8 mm blob): no part picked |
| `upside_down_0603.jpg` *(if present)* | REJECT (since 2026-11-18) | black top facing the camera inside a white outline (flip_check) |

## down_camera/ — the board, seen from above
| File | What |
|---|---|
| `board_check_placed_0603.jpg` | `check-board`: PLACED. Green square = window checked for solder-mask green, yellow cross = target, pink x = measured part centre, label = offset in mm and angle |
| `board_check_empty_footprint.jpg` | `check-board`: MISSING (bare green mask between the pads) |
| `dry_run_crosshair_stale_alignment.jpg` | `run-job --dry-run`: crosshair = where the part centre will go. Here the part sat on the crosshair but ~0.43 mm off its pads: the board alignment was stale (fixed by re-running align-board) |

## report/ — `pnpvision report` output (trimmed to the acceptance runs)
| File | What |
|---|---|
| `summary.txt` | every run: picks good/tried per package, s/part and CPH, vision decisions, placement error |
| `cycles.csv` | per part: phase times (pick, inspect, turn, place) and cycle time, runs fa036095, b76c1d40, 6f30de08, f0c9f5f1 |
| `placement_review.csv` | board checks 677e8924, 707db587, 0c4df0d2: PLACED/MISSING, green share, dx/dy/err mm, angle error |
| `sheet_up_camera_b76c1d40.jpg` | contact sheet: every up-camera photo of a 23-part run, numbered and labelled |
| `sheet_up_camera_6f30de08_flipped_part.jpg` | the run with an upside-down part: tiles 9-11 (dark centre in a white outline) |
| `sheet_board_check_677e8924.jpg` | contact sheet of a board check: 23 placed 0603, 23 empty 0805 footprints |

Acceptance results: picks 92/94 (97.9 %); 491 / 519 / 499 / 527 CPH (clean runs 517-527);
placement error mean 0.075-0.094 mm, worst 0.229 mm over 68 parts; all 138 board-check and
193 up-camera decisions judged correct by hand.
