# Macro Reference

Macros are commands defined in the Klipper configuration. Type them in the Mainsail console,
click them in Mainsail's macro panel, or tap them on the touchscreen.

!!! warning "Before jogging: Z = 0 is the top, a larger Z is lower"
    Keep the nozzle at Z 30 or higher (a smaller number) when moving X/Y by hand.

| Macro | What it does | File |
|---|---|---|
| **Homing** | | |
| `G28 [X] [Y] [Z] [R]` | home all or some axes (homing override: Z, then Y, then X; R set to 0) | printer.cfg |
| `VISION_HOME [NO_G28=1]` | home X/Y, then re-zero on datum dot 0 with the down camera | printer.cfg |
| **Jobs** | | |
| `RUN_JOB JOB=<name> [ALIGN=1/0] [NO_FEEDERS=1] [DRY_RUN=1] [ONLY=R1,R2]` | start a job (job name with spaces as `_`) | pnp_hmi.cfg |
| `PNP_CONTINUE` / `PNP_ANSWER VALUE=1/0` | answer the open job question | pnp_hmi.cfg |
| `PNP_STOP` | stop the job after the current part | pnp_hmi.cfg |
| `PNP_IMPORT_JOBS` | load job files from an SD card / USB stick | pnp_hmi.cfg |
| `_PNP_STATE` | print the machine/job state | pnp_hmi.cfg |
| **Machine buttons** | | |
| `PNP_CHECK_MACHINE [APPLY=1]` | calibration check (nozzle empty) | pnp_hmi.cfg |
| `PNP_BIN_GOTO` / `PNP_BIN_TEACH` / `PNP_BIN_DEFAULT` | reject bin | pnp_hmi.cfg |
| `PNP_SCREEN_TEST` | show a test dialog (nothing moves) | pnp_hmi.cfg |
| `PNP_LAUNCHERS` | write `PNP_<job>.gcode` launchers into the print list | pnp_hmi.cfg |
| **Feeders** | | |
| `FEEDER_TOGGLE SLOT=n [COUNT=k]` | feed k parts on slot n | pnp_feeders.cfg |
| `FEEDER_SET SLOT=n ANGLE=a` / `OFF=1` | move a servo / let it go limp | pnp_feeders.cfg |
| **Vacuum** | | |
| `VALVE_ON` / `VALVE_OFF` / `TOGGLE_VALVE` | solenoid valve | printer.cfg |
| **Lights** | see [Lighting](lighting.md) | LEDS.cfg |
| **Testing** | | |
| `TEST_BED_MOVEMENT`, `PNP_DEMO` | old motion demos | printer.cfg |

!!! danger "`TEST_BED_MOVEMENT` and `PNP_DEMO` are from V2"
    They move to Z 60, beyond V3's Z limit of 51, and will error. They are kept only as examples.

## Writing your own

Add a `[gcode_macro NAME]` section with a `description:` and a `gcode:` block, then
`FIRMWARE_RESTART`. Always use absolute moves (`G90`) and lift to a safe Z before any X/Y move.
