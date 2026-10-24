# pnpvision - vision foundation for Klipper/Moonraker pick & place

## Pi setup (Raspberry Pi OS / MainsailOS, run on the Pi)
    sudo apt install python3-venv v4l-utils
    python3 -m venv ~/venv-pnp && source ~/venv-pnp/bin/activate
    pip install -r requirements.txt
    v4l2-ctl --list-devices          # find the two cameras
    ls -l /dev/v4l/by-path/          # use these in config.toml (stable across reboots)
Only ONE program can open a camera at a time. MainsailOS's crowsnest will grab
/dev/video* for webcam streams: disable those camera entries in crowsnest.conf
(or stop crowsnest) while this runs.

## Order of operations
1. `python -m pnpvision check-lens`            (no hardware needed)
2. `python -m pnpvision snapshot --cam up`     (look at the images; tune exposure/lighting)
3. `python -m pnpvision calibrate-motion --cam down --step 1.0`   (px<->mm, axis directions)
4. `python -m pnpvision calibrate-motion --cam up --find-center`
5. `python -m pnpvision calibrate-offset`      (camera-to-nozzle offset; repeat 3-5x)
6. `python -m pnpvision datum --teach`       (jog down cam so the whole grid is centred and sharp)
7. `python -m pnpvision datum --reference`    (records the up camera's position in the datum frame)
8. `python -m pnpvision datum`                (any time later: re-measures, prints drift)
Tests (no hardware): `python tests/test_offline.py && python tests/test_datum.py`
