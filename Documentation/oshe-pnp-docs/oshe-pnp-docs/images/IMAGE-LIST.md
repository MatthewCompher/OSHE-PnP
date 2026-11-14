# Image list

Every image slot on the site. Save an image into this `images/` folder with the
exact file name below and it appears on the page automatically (site.js swaps the
gray placeholder for the picture). No HTML editing needed.

Prefer to hard-code it? Replace the whole `<figure class="img-slot" ...>` block with
`<figure><img src="images/NAME" alt="..."><figcaption>...</figcaption></figure>`.

"Repo source" points at an existing file in the GitHub repo that could fill the slot.


## index.html

| File | What it should show | Repo source |
|---|---|---|
| `home-hero.jpg` | Photo of the complete V3 pick-and-place machine | - |
| `home-pipeline.png` | Diagram: KiCad → pnpslice → job file → pnpvision → Moonraker → Klipper → machine | - |

## hardware.html

| File | What it should show | Repo source |
|---|---|---|
| `hw-v3-render.png` | Full CAD render of the V3 machine | - |
| `hw-frame.jpg` | V3 frame: printed legs and 4040 extrusion | - |
| `hw-corexy.jpg` | CoreXY belt path with motor and idler corners | - |
| `hw-toolhead.jpg` | V3 toolhead: CP40 nozzle holder, NEMA 11 rotation motor and down camera | - |
| `hw-staging-plate.jpg` | Staging plate with PCB mounts, camera datum and reject bin | - |
| `hw-cameras.jpg` | Down camera on the toolhead and up camera with its ring light | - |
| `hw-feeder.jpg` | Modified 0816 low-profile tape feeder with servo | - |
| `hw-pneumatics.jpg` | Air compressor, valve and tubing | - |
| `hw-hmi.jpg` | Touchscreen on its printed arm mount | - |

## build.html

| File | What it should show | Repo source |
|---|---|---|
| `build-printed-parts.jpg` | All V3 printed parts laid out | - |
| `build-ender3-teardown.jpg` | Ender 3 partly disassembled, showing which extrusions are reused | - |
| `build-frame.jpg` | Assembled V3 frame without motion parts | - |
| `build-corexy-belts.jpg` | Belt routing diagram for the CoreXY system | - |
| `build-toolhead.jpg` | Toolhead assembled, before mounting | - |
| `build-staging-plate.jpg` | Staging plate with datum, PCB mounts and up camera opening | - |
| `build-feeder.jpg` | Feeder assembled with servo and tape loaded | - |
| `build-wiring.jpg` | Wired electronics bay | - |
| `build-first-board.jpg` | A test PCB with parts placed by the machine | - |

## electronics.html

| File | What it should show | Repo source |
|---|---|---|
| `elec-overview.jpg` | Electronics: Octopus Pro, Raspberry Pi 4, power supply and wiring | - |
| `elec-wiring-diagram.png` | V3 wiring diagram: power, e-stop, Octopus Pro, Pi, Uno, Nano, motors, LEDs, valve | - |

## software.html

| File | What it should show | Repo source |
|---|---|---|
| `sw-stack-diagram.png` | Diagram of the software stack: laptop (KiCad, pnpslice) → Pi (pnpvision, Moonraker, Klipper host, crowsnest, Mainsail, KlipperScreen) → Octopus Pro / Uno / Nano | - |
| `sw-mainsail.png` | Screenshot of the Mainsail dashboard with both camera views | - |

## macros.html

| File | What it should show | Repo source |
|---|---|---|
| `macros-mainsail-panel.png` | Screenshot of the Mainsail macro buttons | - |
| `macros-klipperscreen-dialog.jpg` | KlipperScreen showing a pnpvision job dialog with Continue and Stop buttons | - |

## moonraker.html

| File | What it should show | Repo source |
|---|---|---|
| `moonraker-diagram.png` | Diagram: Mainsail, KlipperScreen and pnpvision talking to Moonraker, which talks to Klipper; crowsnest serving camera streams | - |
| `moonraker-undistorted-view.png` | Mainsail showing the undistorted down-camera view with crosshair and mm ticks | - |

## slicer.html

| File | What it should show | Repo source |
|---|---|---|
| `slicer-window.png` | Screenshot of the pnpslice window with a board loaded in Prepare mode | - |
| `slicer-alignment-pick.png` | Pick-by-hand mode with green and red candidate pads | - |
| `slicer-preview.png` | Preview mode showing placement order and nozzle path | - |

## vision.html

| File | What it should show | Repo source |
|---|---|---|
| `vision-down-cam-crosshair.png` | Down-camera view centered on a datum dot with the crosshair | - |
| `vision-datum.jpg` | The printed camera datum: 4 mm grid with white dots, seen from the down camera | - |
| `vision-charuco.jpg` | ChArUco calibration board used for lens calibration | - |
| `vision-up-cam-inspect.png` | Up-camera view of an 0805 part on the nozzle with its detected outline and angle | - |

## history.html

| File | What it should show | Repo source |
|---|---|---|
| `history-v1.png` | Render of the complete V1 assembly | - |
| `history-v2.png` | Render of the complete V2 assembly | Media/V2/setup.jpg (photo) or Media/V2/MasterRender.PNG (render) |

## about.html

| File | What it should show | Repo source |
|---|---|---|
| `about-team.jpg` | Photo of the OSHE Pick and Place team with the machine | - |
