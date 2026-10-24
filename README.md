# (WIP) OSHE Pick and Place (V3.0)

![Project Status](https://img.shields.io/badge/Status-Work_in_Progress-yellow)
![License](https://img.shields.io/badge/License-GNU%20GPL%20v3-blue)
![Platform](https://img.shields.io/badge/Platform-Klipper-orange)

<div align="center">

![Physical Model](https://github.com/josephp-eng/OSHE-PnP/blob/main/Media/setup.jpg?raw=true)

</div>

## 🎯 Summary

The **OSHE Pick-and-Place** is a low-cost, open-source automated PCB assembly system developed at Michigan Technological University. While industrial SMT solutions are often financially out of reach for small labs and hobbyists, this project provides a modular, 3D-printable framework optimized for performance and ease of assembly. 

The system leverages the mechanical foundations of a Creality Ender 3, extending its capabilities into a dedicated manufacturing tool. By utilizing a vacuum-based toolhead and precision motion control, this project bridges the gap between manual prototyping and industrial production.

The modern V3 system draws heavy inspiration in its CoreXY motion system from the Voron 2.3 3D printer.

### 🛠️ Core Technical Achievements

* **Precision Motion Control:** xxxxxxxx
* **Advanced Toolhead Design:** xxxxxxxxxx
* **Expanded Work Envelope:** Features a xxxx mm footprint and support for PCBs up to xxxxxxx mm.
* **Safety-First Integration:** xxxxxxx

### 📈 Current Project Status

The Fall 2026 revision (V3.0) has is the current work in progress iteration. 
This project currently exists separately from the OpenPnP architecture. It was not designed around their software suite but could possibly be adapted.

---

## 📂 Project Documentation

> [!IMPORTANT]
> For the complete technical breakdown, including assembly guides and safety protocols, refer to the full master document below.

* **[📄 Full Technical Manual](https://docs.google.com/document/d/1zdPMhOE8R7Szz68Ky9EoDyxVyp7iftD7q8Uco1WKPY8/edit?usp=sharing)** - Detailed assembly, electrical, and safety documentation.
* **[📦 Bill of Materials (BOM)](https://docs.google.com/spreadsheets/d/12Wk4rjcJYJA1_MIOu3757zk9U3lGuzmtH0hi1Tlr5gI/edit?usp=sharing)** - Comprehensive Google Spreadsheet lists of hardware, electronics, and 3D-printed parts.
* **[⚙️ Configuration Files](Software/Klipper)** - `printer.cfg` and macro definitions for Klipper.
* **[📐 CAD & Model Files](CAD)** - Full assembly models and printable components.

---

## 📋 Repository Structure
* `/CAD`: STEP and STL files for the machine and custom components.
* `/Software`: Klipper configurations and legacy Marlin firmware.
* `/Archive`: Legacy V1 designs and research notes.
* `/Media`: Renders and isometric views of models.
* `/BOMs`: Subsystem bills of materials, including hardware and 3D printed components.

## 💻 Getting Started
1. Review the [Our Documentation](https://docs.google.com/document/d/1zdPMhOE8R7Szz68Ky9EoDyxVyp7iftD7q8Uco1WKPY8/edit?usp=sharing) for the full build guide. Follow along with the 3D printing settings outlined in [CAD]([link](https://github.com/OSHE-Github/OSHE-PnP/tree/main/CAD))
2. Clone this repo to access the latest Klipper `printer.cfg`.
3. Join the conversation on the [OSHE Website]((https://oshe.io/)) and check out other OSHE projects at our [enterprise GitHub](https://github.com/OSHE-Github)

## Project Sponsors

---
*Developed under the Michigan Technological University Open Source Hardware Enterprise (OSHE)*

*ABET Accrediting: [Checklist](https://docs.google.com/document/d/1hHnjDPqjZ3jRmd8Yd_ip3oN7XcyjQFGSi8Tkr0fagdQ/edit?usp=sharing)*
