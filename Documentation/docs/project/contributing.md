# Contributing and License

## Contributing

Everything is on GitHub: [OSHE-Github/OSHE-PnP](https://github.com/OSHE-Github/OSHE-PnP). Other OSHE
projects and how to get involved: [oshe.io](https://oshe.io).

- **Report a problem or suggest a change**: open an issue.
- **Change something**: fork, change, and open a pull request.
- Run the tests first: `pytest` in `Software/pnpvision` and `Software/Slicer`.
- **Edit these docs**: the pencil icon on every page opens the Markdown file on GitHub. To preview
  locally:
  ```bash
  pip install -r Documentation/requirements-docs.txt
  mkdocs serve -f Documentation/mkdocs.yml
  ```

### Repository layout

| Folder | Contents |
|---|---|
| `CAD/` | `V3-Active`, `V2-Legacy`, `V1-Legacy` (STEP, STL, 3MF) |
| `BOMs/` | bills of materials |
| `Software/pnpvision/` | machine software (Python) |
| `Software/Slicer/` | pnpslice (Python, Qt) |
| `Software/Klipper/` | Klipper and touchscreen configuration |
| `Documentation/` | these docs (`docs/`), sample images and data (`samples/`) |
| `Media/` | photos |
| `Archive/` | experiments and tools from earlier versions |

## License

| What | License |
|---|---|
| Hardware (CAD, BOM) | **CERN-OHL-S v2** (`LICENSE-HARDWARE`) |
| Software | **GPL-3.0** (`LICENSE-SOFTWARE`) |
| Documentation and media | **CC BY-SA 4.0** |

You may use, study, change and share the design. If you share a modified version, it must stay
under the same licenses.

### Third-party work

| Used | From | License |
|---|---|---|
| Toolhead design basis | LumenPnP by Opulo | see Opulo's LumenPnP repository (compatibility with CERN-OHL-S being checked) |
| Feeder | 0816 low-profile feeder, Mark Maker's version | see the original project |
| CoreXY layout | inspired by Voron 2.3 (no parts copied) | GPL-3.0 |
| Firmware and host | Klipper, Moonraker, Mainsail, KlipperScreen, crowsnest | GPL-3.0 |
| Light effects | klipper-led_effect | GPL-3.0 |
| Legacy firmware | Marlin | GPL-3.0 |
