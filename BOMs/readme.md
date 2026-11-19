# BOMs

## BOMs Directory

* **/V3-Active**: bills of materials for the current V3 machine. **Ongoing: being written** (the
  folder is empty until the first V3 BOM is committed). Until then, the parts are described in the
  documentation: [Build](../Documentation/docs/build/index.md),
  [Electronics](../Documentation/docs/build/electronics.md),
  [Pneumatics](../Documentation/docs/build/pneumatics.md).
* **/Legacy**: the BOMs for V1 and V2 (Master BOM, Hardware List, and one per subsystem).

## How to Navigate (Legacy BOMs; V3 will follow the same layout)

* The Master BOM contains an extensive list of every fastener and item needed to construct the OSHE-PnP, and their use within their respective subsystem.
* The Hardware List is a subset of the Master BOM that lists specifically all required fasteners.
* Each subsystem has its own BOM. It includes hardware from the Master BOM/Hardware List, so **do not double count** the fasteners needed.

## V3 BOM: what it needs to cover

So the V3 BOM is complete when it's written: frame and CoreXY (extrusion, belts, idlers, motors),
X carriage and rails, toolhead (CP40 holder, NEMA 11, rotary fitting, CP40 tips), staging plate
(prints, acrylic, inserts, PCB mounts, datum), cameras (Arducam 12MP USB, InnoMaker 720P) and LEDs
(WS2812 ring and strips), electronics (BTT Octopus Pro, 4 x TMC5160, Raspberry Pi 4 1 GB + SD
card, Arduino Uno R3, 7" touchscreen, 24 V supply + fuse, 5 V servo supply, USB 3.0 hub + SD
reader), pneumatics (compressor, solenoid valve, venturi + silencer, tubing, fittings), feeders
(printed parts, servos), and fasteners. Include sources and prices (MFG-09).

## Hardware Preparation (V2)

*This table is from V2 (roller axes). V3 reuses the Ender 3 extrusion differently; see
[Frame and Motion](../Documentation/docs/build/mechanical.md).*

| # | Part Name | Qty. | Description |
|---|-----------|:----:|-------------|
| 1 | 290mm 40x40mm Aluminum Extrusion | 2 | Double-slotted on all sides, these extrusion pieces are used to contain tape feeders and provide the front and back support of our machine. Could be increased up to 80mm in length foregoing spacers. |
| 2 | 400mm 20x40mm Aluminum Extrusion | 2 | Longer, two by one slotted extrusion are used in building the x-axes of the machine and interface with the structured mounting pieces as well as y-axis support rollers |
| 3 | 345mm 20x20mm Aluminum Extrusion | 1 | Single-slotted extrusion pulled directly off the x-axis of the Ender 3 builds our y-axis for the toolhead. Interfaces with the roller support pieces |
