# 🗄️ Archive: USB Camera Calibration Utility

## Overview
This directory contains the tools used to calibrate the PnP's USB cameras and remove their lens (barrel / fisheye) distortion. Every camera module is slightly different, so each one is calibrated separately. Generated with Claude AI.

* **Function:** Capture ChArUco board images from a camera on the Raspberry Pi, compute an OpenCV calibration (`.npz`), and optionally serve an undistorted live view to the Mainsail dashboard.
* **Cameras:**
    * **Down camera:** Arducam 12MP USB (M12 manual-focus lens), mounted on the toolhead gantry. **Calibrated.**
    * **Up camera:** InnoMaker 720P USB, 120° DFOV, mounted on the staging plate. **Calibrated.**
* **Status:** **Still used by V3.** pnpvision needs each camera's lens calibration (`.npz`), and the
  `undistort-down` / `undistort-up` services on the Pi run `undistort_stream.py` from this folder.

## ⚠️ Why is it in Archive?
It started as a side project ("vibecode") before pnpvision existed, so it lives here, but the
machine still depends on it: **don't move or rename this folder** without updating the two
undistort services on the Pi (their paths point here). A new machine needs it once per camera
(see [Calibration](../../Documentation/docs/calibration/cameras.md)).

## 📂 Contents
* `calib_capture.py`: Capture and calibration program. Runs headless on the Pi.
* `undistort_stream.py`: Optional service that re-serves a camera stream undistorted, for viewing in Mainsail.
* **/captures**: Each camera keeps its calibration `.npz` plus a few sample shots. The full capture sets stay on the Pi (`~/calib/captures/`).
    * **/cam_down**: Down camera. `calibration_cam_down.npz` and samples 001 (flat), 015 (flat), 030 (tilted)
        * **/annotated**: The samples with the detected markers and ChArUco corners drawn on them
    * **/cam_up**: Up camera. `calibration_cam_up.npz` and samples 001, 012, 025
        * **/annotated**: The samples with detections drawn on them
* The active copies of both `.npz` files live in `Software/pnpvision/calibration/`. After recalibrating, copy the new file there too.

## 🔁 Pipeline
```
USB camera ─► crowsnest (ustreamer) ─► /webcam/?action=snapshot ─► calib_capture.py ─► captures/<name>/calibration_<name>.npz
                    │                                                                                 │
                    └──────────► /webcam/?action=stream ─► undistort_stream.py (port 8090) ◄─────────┘
                                                                     │
                                                         Mainsail webcam (undistorted view)
```
* `calib_capture.py` doesn't open the camera directly. It grabs stills from crowsnest's snapshot URL, so the live stream keeps running and you can aim using the Mainsail webcam view.
* Captures, annotated images and the `.npz` are written on the Pi under `~/calib/captures/<name>/`. Copy them back into this folder with `scp`.

## 🧩 Requirements
* Raspberry Pi running MainsailOS with **crowsnest** streaming the camera. Use MJPEG mode at the resolution you will run the PnP at; the calibration is only valid at that resolution.
* Python venv with OpenCV **4.7+ or 5.x** (both are supported):
  ```bash
  mkdir -p ~/calib && cd ~/calib && python3 -m venv venv
  ./venv/bin/pip install --only-binary=:all: opencv-python-headless numpy
  ```
  Always use `--only-binary=:all:`. Without it, pip may try to build OpenCV from source, which runs a 1 GB Pi out of memory.
* For long installs, use plain SSH inside `tmux` rather than VS Code Remote-SSH, and stop KlipperScreen temporarily. The VS Code server uses enough RAM to freeze a 1 GB Pi during compiles.

## 🏁 Calibration Board
**ChArUco board: 7 x 5 squares, 8 mm squares, 6 mm markers, `DICT_4X4_50`, start id 0.**

These values are set at the top of `calib_capture.py` (`SQUARES_X`, `SQUARES_Y`, `SQUARE_SIZE_MM`, `MARKER_SIZE_MM`, `ARUCO_DICT`). Measure the printed square and marker with calipers and enter the measured sizes.

* **Mount the board flat and rigid.** Tape the sheet's edges taut onto glass, acrylic, aluminum or a flat bare PCB. Loose paper sags and ripples, which was the main error source in the first down camera run. Avoid glue stick on cardboard: the wet glue makes the paper ripple.
* Matte paper reduces glare on the black squares.
* The board doesn't need to fit fully in view. ChArUco works from partial views; the down camera only sees about 5 x 3.5 squares.

## ▶️ Usage: `calib_capture.py`
On the Pi, inside `tmux`:
```bash
cd ~/calib && ./venv/bin/python calib_capture.py --name cam_down
```
Up camera (crowsnest camera 2):
```bash
cd ~/calib && ./venv/bin/python calib_capture.py --name cam_up --url "http://localhost/webcam2/?action=snapshot"
```

| Option | Default | Meaning |
|---|---|---|
| `--name` | timestamp | Run folder `captures/<name>/`. Re-running with the same name resumes it. |
| `--url` | `http://localhost/webcam/?action=snapshot` | Snapshot URL. Use `/webcam2/` for the second crowsnest camera. |

**Keys** (type in the terminal, then press Enter):
* `Enter` : capture a still. It's saved only if at least 8 ChArUco corners are found, and an annotated copy goes to `annotated/`.
* `k` : calibrate from every capture in the run folder
* `q` : quit

**Shot advice:**
* Focus the lens at working height first, then don't touch it again.
* Take about 25–30 shots. Move the board (or jog the toolhead) so the board covers the center, edges and corners of the frame, and rotate it (0° / 45° / 90°).
* Tilting helps only if the camera's depth of field allows it. On the down camera (no Z control, very shallow focus), keep tilts small and the board fully supported.

## 📐 Calibration Method (`k`)
* **Detection:** tuned for close-up, partial-board views. A corner can be used with only one neighboring marker visible (`minMarkers = 1`), and the polygon fit is looser to tolerate marker edges bent by the lens.
* **Solver:** seeded with a sensible initial guess, so OpenCV 4.x doesn't converge to a nonsense camera. **k3 is fixed at 0**, because near-flat views don't constrain it. Leaving it free made the down camera result about 3x less repeatable without lowering the error.
* **Outlier rejection:** images with their own RMS above `max(1.0 px, 3 x median)` are dropped and the solve is repeated (up to 3 passes). The files are left in place, and the dropped images are listed.
* **Output:** RMS error, median per-image RMS, the 5 worst images, the camera matrix and the distortion coefficients, saved to `captures/<name>/calibration_<name>.npz` (`camera_matrix`, `dist_coeffs`, `image_size`, `rms`, `used_images`).

Tunable constants at the top of the script: `MIN_CORNERS` (8), `OUTLIER_FACTOR` (3.0), `OUTLIER_FLOOR_PX` (1.0), `MAX_REJECT_PASSES` (3), `LEGACY_BOARD`.

### Down camera result (`cam_down`, 1920x1080)
| Value | Result |
|---|---|
| Images used | 58 of 60 (2 blurry shots auto-dropped) |
| RMS | 1.46 px, about 0.034 mm (about 0.023 mm per pixel at the board) |
| Field of view | about 105°, which sees about 44 mm across |
| Principal point | (902, 626) |

The **focal length (~732 px) is not reliable.** It can't be determined from near-straight-down views when the camera has no Z travel. For a camera that always looks at one fixed plane, only the distortion and principal point matter, so the pixel correction is unaffected. Recapturing with a rigidly mounted board should roughly halve the RMS.

### Up camera result (`cam_up`, 1280x720)
| Value | Result |
|---|---|
| Images used | 24 of 25 (1 blurry shot auto-dropped) |
| RMS | 1.64 px, about 0.044 mm (about 0.027 mm per pixel at the board) |
| Repeatability (inner half / full frame) | 0.84 px / 1.88 px |
| Principal point | (687, 391) |

The standard model with k3 fixed was compared against k3 free, the rational model and the fisheye model on these captures. It was the most repeatable. The others fit slightly tighter but were less stable, and the fisheye model was unusable. The board was held by hand at 2–11° of tilt and only about 10 corners were visible per shot. A smaller board, steadier shots and larger tilts would improve the result.

## 📺 Undistorted View in Mainsail: `undistort_stream.py`
This reads the crowsnest MJPEG stream, undistorts each frame with a `.npz`, and serves:
* `http://<pi>:8090/stream` : live view (Mainsail **Stream URL**)
* `http://<pi>:8090/snapshot` : single JPEG (Mainsail **Snapshot URL**)

The image has **square pixels** (round things look round) and the same geometry pnpvision measures in (`square_new_K`, kept identical in `Software/pnpvision/pnpvision/lens.py`).

**Reticle:** both URLs draw a yellow crosshair on the **optical axis**, the point pnpvision centres features on. It is not the middle of the frame, so turn off Mainsail's own crosshair. With `--motion`, it also draws 1 mm ticks (labelled every 5 mm) along the machine's +X and +Y axes, read from pnpvision's motion map. The ticks are only true at the height the motion map was calibrated at (the PCB top for the down camera). Add `?reticle=0` for a clean view, e.g. `http://<pi>:8090/stream?reticle=0`; a second Mainsail webcam entry with that URL gives a with/without pair.

It only processes frames **while someone is watching**. With nobody watching it disconnects from the stream and uses 0% CPU, so it can stay running permanently as a debug view.

| Option | Default | Meaning |
|---|---|---|
| `--calib` | required | Calibration `.npz` to apply |
| `--source` | `http://localhost/webcam/?action=stream` | crowsnest stream. Use `/webcam2/` for the second camera. |
| `--port` | `8090` | HTTP port to serve on |
| `--fps` | `10` | Maximum frames processed per second. Extra frames are skipped before decoding. This is the main CPU lever. |
| `--scale` | `0.5` | Output size relative to the camera frame (0.5 of 1920x1080 is 960x540) |
| `--quality` | `80` | Output JPEG quality |
| `--motion` | none | pnpvision motion map (`calibration/motion_down.json`) for the reticle's mm ticks. Re-read automatically when `calibrate-motion` rewrites it. Without it: crosshair only. |

**Run at boot** (systemd service `undistort-down`):
```bash
sudo tee /etc/systemd/system/undistort-down.service > /dev/null << 'EOF'
[Unit]
Description=Undistorted down camera stream
After=network-online.target crowsnest.service
Wants=crowsnest.service

[Service]
User=pnp
WorkingDirectory=/home/pnp/OSHE-PnP/Software/pnpvision
ExecStart=/home/pnp/venv-pnp/bin/python "/home/pnp/OSHE-PnP/Archive/USB Camera Calibration Vibecode Project/undistort_stream.py" --calib /home/pnp/OSHE-PnP/Software/pnpvision/calibration/calibration_cam_down.npz --motion /home/pnp/OSHE-PnP/Software/pnpvision/calibration/motion_down.json --fps 10 --scale 0.5
Restart=always
RestartSec=5
Nice=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now undistort-down
```
* To change options, add them to the end of the `ExecStart=` line (for example `--fps 5`), then run `sudo systemctl daemon-reload && sudo systemctl restart undistort-down`.
* After recalibrating, run `sudo systemctl restart undistort-down` so it loads the new `.npz`.
* For the up camera, run a second service with `--source http://localhost/webcam2/?action=stream`, its own `.npz`, `--port 8091` and `--scale 1` (add `--motion .../motion_up.json` once the up camera has one).
* **This view is for people.** Vision code should read the **raw** `/webcam/` stream and apply the `.npz` itself. Undistorting the undistorted stream again would distort it a second time.
* In Mainsail you can hide the raw webcam entry, but keep the crowsnest `[cam 1]` section. The undistorted view is built from it.

## 🔧 Troubleshooting
| Symptom | Cause / fix |
|---|---|
| `only 0 corners` every time | Wrong `ARUCO_DICT`. It must match the printed board (this board is 4x4). |
| Markers found but few corners | Board size (`SQUARES_X`/`SQUARES_Y`) or `LEGACY_BOARD` doesn't match the print |
| `drawDetectedCornersCharuco` assertion error | Old copy of the script on OpenCV 5. The current script handles 5.x. |
| Snapshot fetch fails, `502` | crowsnest isn't running. Check `systemctl status crowsnest`. "`ustreamer` not found" means reinstall with `cd ~/crowsnest && sudo make install` inside tmux. |
| Moonraker warning about crowsnest `install_script` | In `moonraker.conf`, set `install_script: tools/install.sh` |
| High RMS, but even across all images | The board isn't flat. Mount it rigidly. |
| A few images with very high RMS | Blurry shots. They're dropped automatically. |

## 🖥️ Copying Files (run on the PC, not over SSH)
```bash
scp "C:\Users\<you>\Documents\GitHub\OSHE-PnP\Archive\USB Camera Calibration Vibecode Project\calib_capture.py" pnp@PnP.local:~/calib/
scp -r pnp@PnP.local:~/calib/captures/cam_down "C:\Users\<you>\Documents\GitHub\OSHE-PnP\Archive\USB Camera Calibration Vibecode Project\captures"
```
Don't end a quoted Windows path with `\"`. Windows reads the backslash as escaping the quote.
