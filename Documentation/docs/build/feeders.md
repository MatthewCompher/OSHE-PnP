# 6. Feeder Hardware

V3 uses a modified version of Mark Maker's **0816 low-profile tape feeder**, adapted to standard
fasteners. A hobby servo pushes a lever that advances the tape by one pocket (4 mm for 0603/0805
paper tape). Files: `CAD/V3-Active/Feeder` (left end, right end, rib).

1. Print one set of feeder parts per feeder.
2. Assemble the mechanism following the original 0816 feeder documentation.
3. Fit the servo and connect its signal to the Uno: slot 1 = D5, slot 2 = D6, slot 3 = D3
   (counted left to right from the front; slot 1 is the feeder against the datum).
4. Power all servos from the **separate 5 V supply** and join its ground to the Uno.
5. Mount the feeder on the front rail, against the datum side.

!!! warning "Current state"
    Only **slot 1 (F1)** is in use. F2 and F3 were abandoned for this release (stripped servo gears;
    a lever that didn't reliably catch and release the tape). See
    [Known Limitations](../overview/limitations.md).

Next: how the software drives the feeders, loading tape and teaching the pick position are in
[Feeders](../feeders/index.md).
