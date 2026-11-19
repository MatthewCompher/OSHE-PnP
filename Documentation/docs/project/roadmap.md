# Roadmap

## Ongoing (being written or built now)

- **V3 CAD**: native CAD files, the V3 toolhead and `PnP_Full_Assembly_V3.step` in the repository
- **V3 bill of materials** with sources and prices
- **Step-by-step V3 build guide** with photos and hardware counts
- **V3 wiring diagram**, power supply rating and wire gauges
- **Port and cable labels** on the machine
- **Photos** of the V3 machine in these docs
- **Merge** the V3 work into [OSHE-Github/OSHE-PnP](https://github.com/OSHE-Github/OSHE-PnP)

## Next improvements

- **Hardware emergency stop** in the 24 V line
- **More feeders**: fix or redesign F2/F3 (stronger servos, a lever that reliably catches the tape)
- Overlap the feeder stroke with motion; pre-turn the nozzle on the way to the up camera (speed)
- Correct the 45° rotation shortfall
- More packages: 0402, 1206, SOIC-8, with tested tip heights
- Run the dry-run G-code on the machine (`PNP_BOARD_MOVE` with the saved board alignment)
- Package the slicer as a release download for every version

## Ideas for later

- More than one nozzle / a tip changer
- More reel space and larger reels; front and back loading
- A soldering or paste module
- OpenPnP support
