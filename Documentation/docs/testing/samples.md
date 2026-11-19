# Sample Images and Data

Real photos and report files from the acceptance runs. The originals are in
`Documentation/samples/` in the repository (see its README).

## Up camera (part on the nozzle)

| | |
|---|---|
| ![Good 0603 on the nozzle](../assets/samples/pass_0603_on_nozzle.jpg) | **PASS**: 0603 seen from below, size and angle measured |
| ![0603 on its side](../assets/samples/reject_0603_on_its_side.jpg) | **REJECT**: picked on its side (wrong size) -> reject bin |
| ![Upside-down 0603](../assets/samples/upside_down_0603.png) | **REJECT**: resistor upside down (dark top facing the camera) |
| ![Empty nozzle](../assets/samples/empty_nozzle_bare_tip.jpg) | **EMPTY**: bare tip, nothing picked -> feed and try again |

## Down camera (board)

| | |
|---|---|
| ![Placed 0603](../assets/samples/board_check_placed_0603.jpg) | `check-board`: **PLACED**, offset measured |
| ![Empty footprint](../assets/samples/board_check_empty_footprint.jpg) | `check-board`: **MISSING** (bare green pads) |
| ![Dry run with stale alignment](../assets/samples/dry_run_crosshair_stale_alignment.jpg) | dry run: crosshair = target. Here the board had moved since alignment - re-align |

## Contact sheets

![Up-camera sheet, run b76c1d40](../assets/samples/sheet_up_camera_b76c1d40.jpg)

![Board check sheet 677e8924](../assets/samples/sheet_board_check_677e8924.jpg)

## Report files

`Documentation/samples/report/` holds `summary.txt`, `cycles.csv` and `placement_review.csv` from
these runs. What each column means: [After the Job](../operate/after-the-job.md#the-report).
