# 1. Print the Parts

Print everything in `CAD/V3-Active/`. Start with the frame and motion parts: they take longest.

## Print settings

| Setting | Value |
|---|---|
| Material | PETG for structural parts and motor/idler mounts; PLA is fine for enclosures and light parts |
| Layer height | 0.2 mm |
| Walls | 2 or more |
| Infill | 12 % gyroid |
| Supports | tree supports, only where the part needs them |
| Nozzle | 0.4 mm |

## Parts list by group

| Group | Folder | Notes |
|---|---|---|
| Frame legs and spacers | `Framing` | A and B versions are mirror images: print one of each |
| Motor and idler corners | `Framing/TOP motor A` and `B`, `TOP idler A` and `B` | include the belt tensioners |
| X carriage | `X-Axis` | upper/lower A and B, rail spacer |
| Staging plate | `Staging/Plate`, `Support`, `Mounts` | one camera tile, the rest regular tiles |
| Camera datum | `Staging/Mounts/CameraDatum...` | multi-color `.3mf`, or the "NO AMS" parts printed separately and glued |
| Feeders | `Feeder` | one set per feeder |
| Touchscreen mount | `Electrical/HMI` | frame, arm, end mount |

!!! warning "Ongoing"
    The V3 toolhead files and `PnP_Full_Assembly_V3.step` are being added to the repository, with
    per-part quantities.

!!! tip "The camera datum must be flat and crisp"
    The cameras use the datum's white dots as their reference. Print it slowly with a fresh, flat
    first layer, and don't sand the dots.
