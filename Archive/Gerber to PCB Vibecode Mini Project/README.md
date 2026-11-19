# 🗄️ Archive: Gerber-to-GCode Utility

## Overview
This directory contains legacy software tools utilized during the early development phases (V1.0) of the OSHE Pick-and-Place project. 

### 🛠️ Gerber-to-GCode (HTML/JS)
This is a lightweight, browser-based utility designed to convert PCB Gerber files into machine-readable G-Code. 

* **Function:** It parses the aperture and coordinate data from Gerber files to generate toolpaths for component placement or basic PCB isolation milling.
* **Usage:** Open the `index.html` file in any modern web browser to access the interface.
* **Status:** **Legacy / Unmaintained.** Replaced by **pnpslice** (`Software/Slicer`), which reads the KiCad board directly.
## ⚠️ Why is this archived?
As the project transitioned to **Version 2.0 (Spring 2026)**, the workflow shifted toward integrated coordinate exports from EDA software (like KiCad) and sophisticated Klipper macros. While this tool remains functional for basic conversions, it does not support the advanced safety checks, variable spool offsets, or vacuum logic found in the current V2.0 software stack.

## 📂 Contents
* `index.html`: The main user interface and logic engine.

---
*Note: This code is provided as-is for historical reference and is released under the same GNU GPL license as the main project.*
