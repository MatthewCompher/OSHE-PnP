# 1. Daily Startup

1. **Check the work area**: nothing on the plate except the board mounts, datum and reject bin;
   reject bin emptied; tape loaded in F1 ([Loading Tape](../feeders/loading-tape.md)).
2. **Power on** the 24 V supply and the servo 5 V supply. The Pi boots in about a minute; the
   touchscreen shows KlipperScreen.
3. **Compressor on.** Let it reach pressure (it cycles by itself).
4. Touchscreen -> **Pick & Place -> Vision home.** The machine homes Z, Y and X, then the down
   camera centres on datum dot 0. Wait for its result message (about 20 s).
5. Lights: the down light is on from boot. Turn the **up light** on (Pick & Place -> Lights) if it
   isn't.

!!! note "What happens at power-up"
    Nothing moves by itself. Klipper starts un-homed, the valve is closed, the servos stay limp until
    the first feed, and no job resumes. The motors switch off after 10 minutes idle (not during a
    job); after that, Vision home again.

If anything was bumped or changed since last time, run the [Recovery Check](../calibration/recovery.md)
before the first job.

Next: [Make a job](make-a-job.md), or go straight to [Run a job](run-a-job.md) if the job is
already on the machine.
