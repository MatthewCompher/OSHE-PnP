# 1. Print the Parts

Print everything in `CAD/V3-Active/`. Start with the frame and motion parts: they take longest.
All files are STEP; open them in your slicer (or any CAD program) and export what it needs.

## Print settings

| Setting | Value |
|---|---|
| Material | PETG for structural parts and motor/idler mounts; PLA is fine for enclosures and light parts |
| Layer height | 0.2 mm |
| Walls | 2 or more |
| Infill | 12 % gyroid |
| Supports | tree supports, only where the part needs them |
| Nozzle | 0.4 mm |

## Parts by folder

Parts named **A** and **B** are mirror images: print one of each (for example one motor corner
for each back corner).

### Framing
| Folder / file | Qty | Notes |
|---|---|---|
| `Framing/Frame Leg Bottom A`, `Bottom B` | per leg | legs, mirror pair |
| `Framing/Frame Leg Middle`, `Frame Leg Spacer` | per leg | |
| `Framing/Framing 4040 Spacer`, `... Spacer Logo` | | one with the OSHE logo for the front |
| `Framing/TOP motor A` and `B` | 1 set each | `Top Motor Frame`, `Upper Motor mount`, `Lower Motor mount`: the two back corners with the motors |
| `Framing/TOP idler A` and `B` | 1 set each | `Upper Idler`, `Lower Idler`, `Top Tensioner Mount`, `Tensioner`: the two front corners |

### X axis
| File | Notes |
|---|---|
| `X-Axis/UpperA`, `UpperB`, `LowerA`, `LowerB` | X carriage parts, mirror pairs |
| `X-Axis/RailSpacer` | |

### Staging plate
| Folder / file | Notes |
|---|---|
| `Staging/Plate/Four Quarters/Tile LL, LR, UL, UR` | the plate in four printable quarters, **or** |
| `Staging/Plate/Two Halves/Tiling Staging Plate Model` + `... Model Camera` | the plate in two halves (for a large printer); the "Camera" half has the up-camera opening |
| `Staging/Plate/Acrylic/Acrylic Panel` (+ `Acrylic 2D.dxf` for laser cutting) | acrylic panel, cut instead of printed |
| `Staging/Plate/OPTIONAL Spacers` | only if your plate needs raising |
| `Staging/Brackets/PlateBracket`, `Double M3 Bracket 20mm` | hold the plate on the frame |
| `Staging/Mounts/PCB Mount Static`, `PCB Mount Dynamic` | one each: fixed and adjustable board mounts |
| `Staging/Mounts/CameraDatum.3mf` | multi-color datum, **or** the `CameraDatum NO AMS` parts (`MainBody`, `4mmGrid`, `Dot`) printed separately |
| `Staging/Mounts/Up Camera Mount/CameraMount`, `LightPlate`, `LightDiffuser` | up camera and its LED ring under the plate |

### Feeders
| Folder | Notes |
|---|---|
| `Feeder/Tape Alignment/LeftEndV2`, `RightEndV2`, `RibV4` | tape guide parts, one set per feeder |
| `Feeder/Manual Feeder/ManualFeederLeftV2`, `RightV2` | a hand-loaded track (no servo) |

### Electrical
| Folder | Notes |
|---|---|
| `Electrical/HMI/Frame`, `Arm`, `FrameEnd` | touchscreen mount |

!!! warning "Ongoing: still being added"
    - **Toolhead** (`CAD/V3-Active/Toolhead/`): the LumenPnP-based head as built
    - **Modified 0816 feeder** (`CAD/V3-Active/Feeder/0816 Feeder/`): the servo feeder body
    - **Electrical mounting brackets** (`CAD/V3-Active/Electrical/Electrical Mounts/`)
    - **Complete assembly** (`PnP_Full_Assembly_V3.step`)
    - Per-part quantities, and native CAD files (Fusion 360 / SolidWorks / Onshape)

!!! tip "The camera datum must be flat and crisp"
    The cameras use the datum's white dots as their reference. Print it slowly with a fresh, flat
    first layer, and don't sand the dots.
