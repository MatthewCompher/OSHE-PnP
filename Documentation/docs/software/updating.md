# Updating

## pnpvision and the Job page

On the Pi:

```bash
cd ~/OSHE-PnP && git pull
```

pnpvision and the Job page (a link into the repository) update right away. Restart the
touchscreen to load a new Job page: `sudo systemctl restart KlipperScreen`.

## Klipper configuration

The `.cfg` files on the Pi are **copies**. After a pull that changed one of them, copy it over and
restart Klipper:

```bash
cp ~/OSHE-PnP/Software/Klipper/pnp_hmi.cfg ~/printer_data/config/pnp_hmi.cfg
```

then `FIRMWARE_RESTART` in the Mainsail console. Check first that the live file has no changes
you made only on the Pi:

```bash
diff ~/printer_data/config/pnp_hmi.cfg ~/OSHE-PnP/Software/Klipper/pnp_hmi.cfg
```

!!! tip "Saving a change made on the Pi back to the repository"
    From your computer: `scp pnp@PnP.local:~/printer_data/config/printer.cfg Software/Klipper/printer.cfg`,
    then commit it.

## Klipper, Moonraker, Mainsail, KlipperScreen, crowsnest

Mainsail -> Machine -> **Update Manager**. Update one at a time and check the machine still homes
afterwards. If Klipper itself updates, the Octopus and Uno firmware may need re-flashing
([Install](install.md) steps 3 - 4): Mainsail tells you when the MCU version doesn't match.

## Recovery

| Problem | Fix |
|---|---|
| Klipper shows an error after a config change | fix the line it names, or copy the repository version back, `FIRMWARE_RESTART` |
| After an emergency stop | `FIRMWARE_RESTART`, then Vision home |
| pnpvision broken after a pull | `git log` to find the last good commit, `git checkout <commit> -- Software/pnpvision` |
| SD card corrupted / new Pi | follow [Install from Scratch](install.md); the calibration files are in the repository |
