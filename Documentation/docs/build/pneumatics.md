# 5. Pneumatics

The nozzle vacuum comes from compressed air: a small compressor feeds a solenoid valve, and the
valve drives a venturi vacuum generator connected to the toolhead's rotary fitting.

```
compressor (auto-cycling, ~60 psi) -> solenoid valve (Octopus FAN1, PD12)
    -> venturi vacuum generator -> tubing -> rotary fitting -> CP40 nozzle tip
```

| Step | Check |
|---|---|
| Mount the compressor away from the work area | it vibrates; the machine must not move with it |
| Run tubing to the toolhead with a service loop | the toolhead travels the whole plate: no pulling at any corner |
| Wire the valve to FAN1 | `VALVE_ON` / `VALVE_OFF` in the Mainsail console click the valve |
| Test the vacuum | `VALVE_ON`, cover the tip with a finger: you should feel suction; a 0603 should jump to the tip |

pnpvision switches the valve itself: vacuum on 150 ms before lifting at the pick, off 200 ms
before lifting at the place (`config.toml [run] vac_ms / release_ms`).

!!! warning "Ongoing"
    Compressor, valve and venturi part numbers and the regulator setting are being added to the
    V3 BOM.

!!! tip "Before disconnecting any tubing"
    Switch the compressor off and open the valve (`VALVE_ON`) to bleed the pressure.
