# 🗄️ Archive: USB Camera-Calibrater Utility

## Overview
This directory contains a software tool used to calibrate ELP-USB camera modules. The goal is to eliminate fisheye and barrel distortion. For advanced users, you apply this software separately to each camera module, due to tiny manufacturing differences from camera to camera. Generated with Claude AI.

* **Function:** Apply OpenCV camera distortion correction features based on calibration procedure.
* **Usage:** Run calib_capture.py and take at least 15 captures at different distances, angles, viewpoints of a uniform checkerboard grid.
* **Status:** **Legacy / Unmaintained.**
## ⚠️ Why is this archived?
This program is only useful to specific advanced users and requires specific setup. While it is recommended for people to understand how the process works and apply it to their system, it is not necessary for PnP functionality.

## 📂 Contents
* **/captures**:
    * **/cam_A**:: Camera specific generated calibration files
        * **/annotated**: Generated calibration files visualizing tracking checkerboard corners
    * `calib_capture.py`: The camera calibration program

**Checker Board Used: 8 x 11 squares, 15 mm each**

**Keys**:
   * SPACE / c : capture a frame (only saved if the checkerboard is detected)
   * k         : run calibration on this run's captures (shows tracked corners)
   * q / ESC   : quit

**Terminal Commands**:
   * python calib_capture.py                 # camera 0, new timestamped run folder
   * python calib_capture.py --name cam_A    # captures/cam_A/ (re-running resumes it)
   * python calib_capture.py --camera 1      # a different camera
   * python calib_capture.py --width 1280 --height 720 --fps 30
