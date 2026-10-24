# Pick and Place CAD Documentation

<div align="center">

![Complete Assembly V2](https://github.com/josephp-eng/OSHE-PnP/blob/main/Media/CompleteAssembly.PNG?raw=true)

</div>

This directory contains all mechanical design files for the OSHE Pick and Place project.

Each subsystem is organized in the preceding folders. Various STL and STEP files are available here for the current version of the pick-and-place machine.

Our system currently includes a CoreXY based motion structure, 3D printed base structures, PCB staging plate support, pneumatic and electrical separation, and the modified 0816-feeder and reel holder we used in the making of our project.

Each iteration of the Pick and Place is technically buildable and usable for your needs. It is highly recommended to stick to V3 as it is the most complete state of the project.

The major differences between V3 and previous iterations are in the motion system overhaul as well as the utilization of a custom LumenPnP based toolhead.

With every version of the project, it is highly recommended to start with an Ender 3. A scrap, nonfunctioning Ender 3 today can save potentially $100 in parts, although it is not required for the build of the project.

With every version of the machine, certain hardware features are not required for a minimum setup, and exact extrusion lengths are not specifically mandated. Belt lengths, extrusion lengths, motion system hardware, are all proportionally relative. HMI display is not necessary for function.

## Folder Structure
* **/V1-Legacy**: Baseline Ender 3 conversion (Fall 2025).
* **/V2-Legacy**: Current Klipper-integrated development (Spring 2026).
* **/V3-Active**: The most up to date, Klipper based PnP, now with a CoreXY system and improved toolhead with vision validation system . The final iteration of the Michigan Tech student led project (Fall 2026). Note that V3 also features an air compressor compared to V2's diaphragm pump.
* `Ender-3-Full-Assembly.step`: Included as a reference model for Ender 3 3D printer, which we used to design around for aluminum extrusion and electrical hardware.

## Design Environment
* Autodesk Fusion 360, Solidworks, and OnShape were used for modeling and integration of our Pick and Place.
* All components exported to `.step` and/or `.stl` and are viewable in any CAD software.

## V3 Directory
* **/Electrical**: Staging plate mounting for electrical hardware, HMI enclosure, up facing camera mount
    * Utilizes acrylic and PLA support to attach to the underside of the staging plate
* **/Feeder**: Tape and reel feeding system, including our tape holder solution as well as modified 0816 low-profile feeder
* **/Framing**: The PnP structure and CoreXY motion system support
* **/Staging**: Structure for 3D printed staging plate and brackets
* **/Toolhead**: LumenPnP inspired CP40 toolhead with vision support
* `PnP_Full_Assembly_V3.step`: **Master File** 

### V2 Directory (outdated)
* **/AxisSupport**: Supporting pieces for rolling the Y-axis along the X-axis
    * `YAxisSupportA.step`: Mounts the Y-axis with rollers, featuring an end stop for alignment, for the side of the Y-motor (print one)
    * `YAxisSupportB.step`: Mounts the Y-axis with rollers openly (print one)
* **/Clamping**: PCB Clamping mechanism
    * `ClampingAssembly.step`: Reference assembly of the clamp
    * `clampMount.step`, `clamp.step`, and `clampMountMirror.step`: Extrusion attachments for mount and clamping piece (print one of each)
    * `THandle.step`, `TSlotShaftCollar.step`, and `TSlotSpacer.step`: Printable clamping components to tension PCB. Print two of each, acquiring two compression springs.
* **/ElectricalEnclosure**: Housing for control board, Raspberry Pi, etc
    * `EncAssembly.step`: Reference assembly of constructed enclosure
    * Print one of each component in this folder. We utilized an Ender 3 fan and installed it on the back piece
* **/Framing**: The PnP structure and axis mounts
    * `BOT_leg.step` and `BOT_leg_MIRROR.step`: Print two of each to build idler, motor, mirrored idler, and mirrored motor structures, standard length
    * `MID_leg.step`: Print four of these for each of the four structure assemblies
    * `TOP_idler.step` and `TOP_idler_MIRROR.step`: Print one of each for the regular idler mount and mirrored idler structure
    * `TOP_motor.step` and `TOP_motor_MIRROR.step`: Print one of each for the regular motor mount and mirrored motor structure
    * *OPTIONALLY* `BOT_leg_LP.step` and `BOT_leg_LP_MIRROR.step`:  Alternative leg models for a lower profile, shorter machine
* **/PneumaticEnclosure**: Housing for vacuum pump and solenoid
    * `BackFrontPanel.step`: Print two of these for the front and back sides
    * `Baseplate.step`: Print one to build the base of the enclosure
    * `Sidepanel.step`: Print two of these for the smallest sides of the enclosure
    * `Top.step`: Print one of these for the top of the enclosure
* **/PushPullFeeder**: The Mark Maker, fully 3D printed tape and reel feeder (PETG)
    * `PushPullFeeder1.stl` and `PushPullFeeder2.stl`: Phase 1 and phase 2 of printing the feeder
    * `PushPullFeeder.scad`: The base code for the OpenSCAD model, venture if you dare
* **/Toolhead**: Nearly fully 3D printable toolhead with Z rotation
    * Print one of everything here
    * Supports are absolutely necessary for many components
    * `Prongs.step`: Print four of each of these for the 3D printed nozzle support, recommended in PETG for flexure
    * `Tool_Head_Assembly.step`: Reference assembly of constructed toolhead
* `PnP_Full_Assembly_V2.step`: **Master File** 

## Hardware Attribution
We utilize and build upon the work of the open-source community:
* **Push-Pull Feeder:** Designed by **Mark Maker**.
    * [Push-Pull Feeder Repository](https://github.com/markmaker/PushPullFeeder)
    * Our implementation includes optimization for use with 4040 v-slotted aluminum extrusion (commonly found on Ender 3), found in `/V2-Legacy/PushPullFeeder`.
    * We found our modified feeder is pretty unreliable, and in our testing, we struggled to have it operate consistently with our current modifications to work with 40-wide extrusion.
* **0816 SMT Automatic Feeder Design:** Designed by **Mark Maker**.
    * [Original 0816 Website](https://docs.mgrl.de/maschine:pickandplace:feeder:0816feeder)
    * [0816 Low-Profile Worm Gear Feeder (pick and place)](https://makerworld.com/en/models/778189-0816-low-profile-worm-gear-feeder-pick-and-place#profileId-714997)
    * Our implementation references the original 0816 feeder with the low profile enhancements, modified to fit standard fastener hardware we had on hand `/V3-Active/Feeder`. Please follow their guides and documentation for additional information.

## Fabrication Guide **(WIP)**
* **Material:** PETG (Motor mounts, Push Pull Feeder, Structural), PLA (Toolhead, PCB Clamping, Enclosures)
*Our Pick and Place structures can be printed in either PETG or PLA, but PETG is preferred*
* **Minimal Settings:** 0.2mm layer height, 2+ perimeters, 12% Gyroid infill, tree supports recommended
*The Push Pull Feeder is recommended by Mark Maker to be printed with more specific settings. See the attributed repository for more information.*
* **Hardware:** Our compoennts were printed and verified across the **Bambu Lab A1**, **Prusa Core 1**, and **Voron 2.4** platforms with their respective slicers.
    * Standard 0.4mm nozzle recommended
