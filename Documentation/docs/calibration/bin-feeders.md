# 4. Reject Bin and Feeders

## Reject bin

The bin's default position comes from where it is bolted on the plate (`config.toml [layout]`).
Check it once:

```bash
python -m pnpvision teach-bin --goto       # nozzle goes over the bin at safe Z
```

If the opening is elsewhere, jog the nozzle over it and run `teach-bin` (or tap **Reject bin ->
Teach** on the touchscreen). `teach-bin --default` forgets a taught position.

## Feeders

Each feeder needs its pick spot taught once: see [Teaching a Feeder](../feeders/teaching.md).
After that the pick position refines itself from the up camera as parts are picked.
