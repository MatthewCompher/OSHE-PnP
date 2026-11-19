# 1. Cameras

## 1. Lens calibration

Each camera's lens bends straight lines. A one-time calibration with a printed **ChArUco board**
(7 x 5 squares, 8 mm squares, 6 mm markers, dictionary **DICT_4X4**) measures that distortion.

1. Print the board and glue it to something rigid and flat (loose paper gave 1.5 px errors).
2. On the Pi, run `Archive/USB Camera Calibration Vibecode Project/calib_capture.py` (it has its
   own venv in `~/calib`) and take 20 - 30 views at different positions and small tilts.
3. Copy the result into `Software/pnpvision/calibration/calibration_cam_down.npz` (and `_up`).
4. Check: `python -m pnpvision check-lens` (no moves).

Our results: down camera ~105° field of view, ~0.023 mm/px; up camera rms 1.66 px. The camera
resolution in `crowsnest.conf`, `config.toml` and the calibration must all match (1920 x 1080 down,
1280 x 720 up).

## 2. Exposure and lighting

| Camera | Light | Exposure |
|---|---|---|
| Down | 2 white LEDs on the toolhead (`VISION_LIGHT_ON`, on at boot) | automatic; pnpvision handles the colour shift |
| Up | 6-LED ring (`UP_LIGHT_ON`) | **fixed** in `crowsnest.conf` `[cam 2]` (`exposure_time_absolute=80`) |

1. `python -m pnpvision snapshot --cam up --lit` and `--cam down`: look at the images.
2. With a part on the nozzle over the up camera, `focus-sweep` reports sharpness and the share of
   saturated pixels. Aim for 0 - 0.3 % saturated.
3. To try exposure values live: `v4l2-ctl -d /dev/v4l/by-id/<up camera> -c exposure_time_absolute=80`.

!!! warning "Frame lights"
    The 44-LED frame strip at 50 % washed out the up camera's view of the nozzle bore. Keep it at
    about 15 % (`LEDS.cfg [led_effect frame_on]`).

## Undistorted views in Mainsail (optional)

The services `undistort-down` (port 8090) and `undistort-up` (8091) show lens-corrected views with
a crosshair, handy for centring things by eye. They come from
`Archive/USB Camera Calibration Vibecode Project/undistort_stream.py`; restart them after a new lens
calibration. They use no CPU while nobody watches.
