# feeder_nano (obsolete)

> [!WARNING]
> **Not used by V3. Don't flash this for the current machine.** Since 2026-11-16 the feeder servos
> are Klipper `[servo]` objects on the Arduino Uno (`Software/Klipper/pnp_feeders.cfg`,
> `FEEDER_TOGGLE SLOT=n`), and pnpvision drives them through Klipper (`config.toml [feeders] bus =
> "klipper"`).

This sketch ran the tape-feeder servos from a separate **Arduino Nano** over USB serial (115200
baud): `F<n>` queued one stroke on feeder n, `A<n>,<deg>` moved a servo to an angle, `?` reported
the state. It ran strokes one at a time so the servos never drew current together. pnpvision can
still talk to it (`config.toml [feeders] bus = "serial"`), which is why it is kept: it is a working
fallback if a machine has no spare Klipper MCU.

Why it was replaced: one less board and serial port, the servos are controlled by the same
firmware as the motion, and the feeder pins live in the Klipper config with everything else.
