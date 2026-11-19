# 3. Load Jobs from SD / USB

No Wi-Fi or laptop needed: carry the job on an SD card or USB stick.

1. On your computer, **Export job...** from pnpslice straight onto the SD card or stick. Any
   folder works: the machine looks in the card's top folder and one folder down.
2. Put the card in the **USB card reader** on the machine (or plug in the stick).
3. Touchscreen -> **Pick & Place -> Job -> Load jobs from SD card / USB stick**.
4. The status line says **"USB: loaded 1 job (...). You can remove the card."** and the job appears
   in the list within a second.
5. Pull the card out any time - it was only read, never written.

## What it does

- Looks only at USB storage (never the Pi's own boot card), **mounts it read-only**, copies every
  `*.job.json`, and **unmounts** it again.
- Checks each file: valid JSON with a placement list, under 5 MB, a plain file name (letters,
  digits, space, `_ . -`). Anything else is skipped and the console says why.
- **Never replaces a job already on the machine.** A file with the same name but different content
  is saved as `<name>-usb.job.json`; loading a newer export again replaces that `-usb` copy.

## Messages

| Message | Meaning |
|---|---|
| `USB: loaded 2 jobs (A, B). You can remove the card.` | done |
| `USB: loaded 0 jobs, 1 already there` | the same file is already on the machine |
| `USB: no SD card / USB stick found` | plug in the reader with the card in it |
| `USB: card reader found, but no card in it` | insert the card |
| `USB: could not read the card: ... sudo: a password is required` | the mount rule isn't installed: [Install, "Allow SD/USB job loading"](../software/install.md#allow-sdusb-job-loading) |
| `USB: could not read the card: ...` | unusual format: use FAT32 or exFAT |
| `... a job is running; PNP_STOP it first` | loading waits until the job ends |

The same import runs from the Mainsail console (`PNP_IMPORT_JOBS`) or over SSH
(`python -m pnpvision import-jobs`, with `--device /dev/sda1` or `--from <folder>`).

## Over the network instead

Copy the job into `~/OSHE-PnP/Software/pnpvision/jobs/` on the Pi (for example with `scp`, or
Mainsail's file manager). It shows up in the Job list at once.

Next: [Run the job](run-a-job.md).
