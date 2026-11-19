# Lighting

| Light | LEDs | Pin | Macros | Used for |
|---|---|---|---|---|
| Toolhead status | LED 1 of `neopixel leds` | Octopus PB10 | `LEDS_IDLE`, `LEDS_BUSY`, `LEDS_ERROR`, `LEDS_RAINBOW`, `LEDS_OFF` | status |
| Down light | LEDs 2 - 3 of `neopixel leds` | Octopus PB10 | `VISION_LIGHT_ON` / `_OFF` / `_TOGGLE` | down camera (on at boot) |
| Up-camera ring | 6 x WS2812 `up_light` | Uno D11 | `UP_LIGHT_ON`, `UP_LIGHT_OFF`, `UP_LIGHT_RAINBOW` | up camera |
| Frame strip | 44 x WS2812 `frame` | Uno D10 | `FRAME_ON`, `FRAME_OFF`, `FRAME_RAINBOW` | room light, kept dim |

Effects come from the `klipper-led_effect` extension (`LEDS.cfg`).

!!! warning "Lights change what the cameras see"
    - The frame strip at 50 % washed out the up camera's view of the nozzle bore; it runs at 15 %.
    - pnpvision sets the up ring with `SET_LED`. An active `led_effect` on the same LEDs overrides
      it: if up-camera images look odd, check no effect is running on `up_light`.
    - Keep the up ring on during jobs (`keep_on = true`): switching it makes the camera re-adjust.
    - A flickering (purple) down light means noise on the LED data line: see the wiring tips in
      [Electronics](../build/electronics.md#wiring-rules-we-learned).
