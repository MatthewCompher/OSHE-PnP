# FAQ

**Who makes it?**
Students of the Open Source Hardware Enterprise at Michigan Technological University:
[oshe.io](https://oshe.io).

**Do I need a laptop to run it?**
No. Load jobs from an SD card or USB stick and run them from the touchscreen. A laptop (or any
browser on the same network) is handy for Mainsail and for calibration over SSH.

**Does it use OpenPnP?**
No. The machine runs its own software (pnpvision) on the Pi, driving Klipper. OpenPnP support is
an idea on the [Roadmap](../project/roadmap.md).

**Why a job file and not G-code?**
Placing needs the cameras, the feeders and retries, which plain G-code can't express. The slicer
can also write a [dry-run G-code](../operate/make-a-job.md#dry-run-g-code) of the placements.

**Does the board have to be placed exactly?**
No. Put it firmly in the mounts in roughly the usual place: the down camera finds its exact position
and rotation from the alignment pads before every job.

**Which parts can it place?**
Proven: 0603 and 0805 chip resistors with the N08 tip. The tip table covers 0201 - SOIC-8, but those
are untested.

**How fast is it?**
About 511 parts per hour on average (7 s per part) with one feeder.

**Why is Z "upside down"?**
Z homes at the top, so Z = 0 is the top and a larger Z is lower. Everything in the docs uses
that convention.

**What does it cost?**
Much less than a commercial machine, especially with a donor Ender 3. The V3 BOM with prices is
being written.

**Can I change it?**
Yes, please: see [Contributing and License](../project/contributing.md).
